"""Kiro 混合注册 — HTTP 协议 + 最小化 Playwright

Signin 流程全部通过 HTTP 协议完成（快速、稳定）；
Profile 页面因 AWS TES 反作弊需要浏览器指纹，使用 Playwright 自动填表。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import string
import time
import uuid
from typing import Callable, Optional
from urllib.parse import urlencode

import requests
from jwcrypto import jwe, jwk

REGION = "us-east-1"
OIDC_BASE = f"https://oidc.{REGION}.amazonaws.com"
PORTAL_BASE = f"https://portal.sso.{REGION}.amazonaws.com"
SIGNIN_BASE = f"https://{REGION}.signin.aws"
PROFILE_BASE = "https://profile.aws.amazon.com"
DIR_ID = "d-9067642ac7"

_RANDOM_NAMES = [
    "Zhang Wei", "Wang Fang", "Li Na", "Liu Yang", "Chen Jing",
    "Zhang Min", "Wang Lei", "Li Qiang", "Liu Min", "Chen Wei",
    "Maria Silva", "João Santos", "Ana Oliveira",
    "James Smith", "Emily Johnson", "Michael Brown",
]

_CODE_RE = re.compile(r"\b(\d{6})\b")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SENDER_KEYWORDS = (
    "signin.aws", "no-reply", "noreply", "kiro.dev", "kiro", "aws",
)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _gen_password(length: int = 16) -> str:
    upper = random.choices(string.ascii_uppercase, k=2)
    lower = random.choices(string.ascii_lowercase, k=2)
    digits = random.choices(string.digits, k=2)
    special = random.choices("!@#$%^&*", k=2)
    rest = random.choices(
        string.ascii_letters + string.digits + "!@#$%^&*", k=length - 8
    )
    pool = upper + lower + digits + special + rest
    random.shuffle(pool)
    return "".join(pool)


def _extract_verification_code(body: str) -> Optional[str]:
    plain = _HTML_TAG_RE.sub(" ", body)
    m = _CODE_RE.search(plain)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Graph API 验证码收取
# ---------------------------------------------------------------------------

def _graph_get_token(client_id: str, refresh_token: str) -> str:
    resp = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _graph_fetch_emails(access_token: str, user_email: str, top: int = 5):
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "$top": str(top),
            "$select": "id,subject,from,body,receivedDateTime",
            "$orderby": "receivedDateTime desc",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def _graph_wait_for_code(
    client_id: str, refresh_token: str, user_email: str,
    timeout: int = 120, poll_interval: int = 5,
    progress_fn=None,
) -> str:
    _log = progress_fn or (lambda m: None)

    _log("正在连接邮箱服务...")
    try:
        access_token = _graph_get_token(client_id, refresh_token)
    except Exception as e:
        raise RuntimeError(f"邮箱认证失败: {e}")

    seen: set[str] = set()
    _log("正在扫描已有邮件...")
    try:
        for msg in _graph_fetch_emails(access_token, user_email, top=10):
            code = _extract_verification_code(
                msg.get("body", {}).get("content", "")
            )
            if code:
                seen.add(code)
    except Exception as e:
        raise RuntimeError(f"读取邮件失败: {e}")

    _log(f"已标记 {len(seen)} 个旧验证码，开始轮询新邮件...")
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            msgs = _graph_fetch_emails(access_token, user_email)
        except Exception as e:
            _log(f"邮件查询出错: {e}，重试中...")
            time.sleep(poll_interval)
            continue

        for msg in msgs:
            from_addr = (
                msg.get("from", {}).get("emailAddress", {}).get("address", "")
            )
            subject = msg.get("subject", "")
            body_content = msg.get("body", {}).get("content", "")
            code = _extract_verification_code(body_content)

            if attempt <= 2:
                _log(f"  邮件: {from_addr} | {subject[:40]} | code={code}")

            if code and code not in seen:
                _log(f"验证码已获取: {code}（来自 {from_addr}）")
                return code

        remaining = int(deadline - time.time())
        _log(f"第 {attempt} 次查询（{len(msgs)} 封邮件），暂未收到验证码（剩余 {remaining}s）")
        time.sleep(poll_interval)
    raise TimeoutError(f"超时 {timeout}s 未收到验证码")


# ---------------------------------------------------------------------------
# 主注册流程
# ---------------------------------------------------------------------------

class KiroProtocolRegister:
    """HTTP + Playwright 混合完成 Kiro (AWS Builder ID) 注册 + OAuth 授权。"""

    def __init__(
        self,
        api_client,
        progress_fn: Optional[Callable[[str], None]] = None,
    ):
        self.api = api_client
        self._log = progress_fn or (lambda m: None)
        self._cancelled = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def cancel(self):
        self._cancelled = True

    def _emit(self, msg: str):
        self._log(msg)

    def _check_cancel(self):
        if self._cancelled:
            raise RuntimeError("用户取消")

    # ================================================================ 入口
    def run(self) -> dict:
        self._emit("正在初始化注册...")

        # 1) 获取邮箱
        self._emit("正在获取邮箱...")
        email_data = self._fetch_email()
        email = email_data["email"]
        ms_client_id = email_data["ms_client_id"]
        ms_refresh_token = email_data["ms_refresh_token"]
        existing_pw = email_data.get("existing_password")
        self._emit("邮箱已分配")
        self._check_cancel()

        try:
            return self._do_register(
                email, ms_client_id, ms_refresh_token, existing_pw,
            )
        except Exception as e:
            self._report_failure(email, str(e))
            raise

    def _report_failure(self, email: str, reason: str):
        """注册失败时通知后端，标记邮箱为失败状态。"""
        try:
            self.api.push_kiro_register_result({
                "email": email,
                "status": "error",
                "error_reason": reason[:200] if reason else "unknown",
            })
        except Exception:
            pass

    def _do_register(
        self, email: str, ms_client_id: str,
        ms_refresh_token: str, existing_pw: str | None,
    ) -> dict:
        # 2) OIDC 客户端注册
        self._emit("正在连接 Kiro 服务...")
        client_id, client_secret = self._register_oidc_client()

        # 3) 设备授权
        self._emit("正在获取认证会话...")
        device_auth = self._start_device_auth(client_id, client_secret)
        user_code = device_auth["userCode"]
        device_code = device_auth["deviceCode"]
        self._check_cancel()

        # 4) Portal 登录 → 获取 signin redirect
        self._emit("正在创建注册会话...")
        signin_url, _csrf = self._portal_login(user_code)

        # 5) Signin 登录流程 → 导航到注册 → 获取 profile workflowID
        self._emit("正在跳转注册页面...")
        workflow_id, signup_wf, signup_step_id = (
            self._navigate_signin_to_signup(signin_url, email)
        )
        self._check_cancel()

        # 6) Profile 注册（Playwright），同时 API 级保活 signup workflow
        self._emit("正在获取安全令牌...")
        password = existing_pw or _gen_password()
        name = random.choice(_RANDOM_NAMES)

        import threading
        signup_url_ka = f"{SIGNIN_BASE}/platform/{DIR_ID}/signup/api/execute"
        keepalive_stop = threading.Event()
        ka_wf = {"handle": signup_wf}

        def _workflow_keepalive():
            while not keepalive_stop.is_set():
                try:
                    d = self._signin_execute(
                        signup_url_ka,
                        {"workflowStateHandle": ka_wf["handle"]},
                    )
                    new_wf = d.get("workflowStateHandle", "")
                    if new_wf:
                        ka_wf["handle"] = new_wf
                except Exception:
                    pass
                keepalive_stop.wait(8)

        ka_thread = threading.Thread(target=_workflow_keepalive, daemon=True)
        ka_thread.start()

        try:
            registration_code = self._profile_signup_playwright(
                workflow_id, email, name,
                ms_client_id, ms_refresh_token,
            )
        finally:
            keepalive_stop.set()
            ka_thread.join(timeout=5)
            signup_wf = ka_wf["handle"]

        self._check_cancel()

        # 7) 提交 registrationCode + 设置密码
        self._emit("正在设置密码...")
        self._submit_registration_and_password(
            signup_wf, signup_step_id, registration_code, password,
        )
        self._check_cancel()

        # 8) 轮询 Token
        self._emit("正在获取访问令牌...")
        access_token, refresh_token = self._poll_token(
            client_id, client_secret, device_code,
            device_auth.get("interval", 5),
        )

        self._emit("正在生成凭证...")
        cid_hash = hashlib.sha256(client_id.encode()).hexdigest()
        oauth_info = json.dumps({
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "provider": "BuilderId",
            "authMethod": "IdC",
            "expiresAt": "",
            "clientIdHash": cid_hash,
            "region": REGION,
            "clientId": client_id,
            "clientSecret": client_secret,
        })

        # 9) 推送结果
        self._emit("正在同步注册结果...")
        try:
            self.api.push_kiro_register_result({
                "email": email,
                "status": "success",
                "kiro_password": password,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "client_id_hash": cid_hash,
                "region": REGION,
                "oauth_info": oauth_info,
            })
        except Exception:
            pass

        self._emit("注册成功！")
        return {
            "email": email,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_hash": cid_hash,
            "region": REGION,
            "oauth_info": oauth_info,
        }

    # ================================================================ 后端 API
    def _fetch_email(self) -> dict:
        r = self.api.fetch_kiro_register_email()
        if not r.get("success"):
            raise RuntimeError(
                r.get("message") or "获取注册邮箱失败，请检查网络或联系客服"
            )
        data = r.get("data")
        if not data or not isinstance(data, dict):
            raise RuntimeError("服务器返回数据异常")
        if (
            not data.get("email")
            or not data.get("ms_client_id")
            or not data.get("ms_refresh_token")
        ):
            raise RuntimeError("注册邮箱信息不完整")
        return data

    # ================================================================ OIDC
    def _register_oidc_client(self) -> tuple[str, str]:
        resp = self.session.post(
            f"{OIDC_BASE}/client/register",
            json={
                "clientName": "Kiro IDE Auto Registration",
                "clientType": "public",
                "scopes": [
                    "codewhisperer:completions",
                    "codewhisperer:analysis",
                    "codewhisperer:conversations",
                    "codewhisperer:transformations",
                    "codewhisperer:taskassist",
                ],
                "grantTypes": [
                    "urn:ietf:params:oauth:grant-type:device_code",
                    "refresh_token",
                ],
                "issuerUrl": OIDC_BASE,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        d = resp.json()
        return d["clientId"], d["clientSecret"]

    def _start_device_auth(self, client_id: str, client_secret: str) -> dict:
        resp = self.session.post(
            f"{OIDC_BASE}/device_authorization",
            json={
                "clientId": client_id,
                "clientSecret": client_secret,
                "startUrl": "https://view.awsapps.com/start",
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _poll_token(
        self,
        client_id: str,
        client_secret: str,
        device_code: str,
        interval: int = 5,
        max_attempts: int = 60,
    ) -> tuple[str, str]:
        body = {
            "clientId": client_id,
            "clientSecret": client_secret,
            "grantType": "urn:ietf:params:oauth:grant-type:device_code",
            "deviceCode": device_code,
        }
        wait = interval
        for _ in range(max_attempts):
            time.sleep(wait)
            self._check_cancel()
            resp = self.session.post(
                f"{OIDC_BASE}/token",
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 200:
                d = resp.json()
                return d["accessToken"], d["refreshToken"]
            err = ""
            try:
                err = resp.json().get("error", "")
            except Exception:
                pass
            if err == "authorization_pending":
                continue
            elif err == "slow_down":
                wait = interval + 5
            elif err == "expired_token":
                raise RuntimeError("设备码已过期，请重试")
            elif err == "access_denied":
                raise RuntimeError("授权被拒绝")
            elif err:
                raise RuntimeError(f"OAuth 错误: {err}")
        raise TimeoutError("Token 轮询超时")

    # ================================================================ Portal 登录
    def _portal_login(self, user_code: str) -> tuple[str, str]:
        """调用 Portal API 获取 signin redirect URL + CSRF token。"""
        redirect_url = (
            f"https://view.awsapps.com/start/#/device?user_code={user_code}"
        )
        resp = self.session.get(
            f"{PORTAL_BASE}/login",
            params={
                "directory_id": "view",
                "redirect_url": redirect_url,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        signin_url = data["redirectUrl"]
        csrf_token = data.get("csrfToken", "")
        self.session.get(signin_url, timeout=30)
        return signin_url, csrf_token

    # ================================================================ Signin 流程
    def _signin_execute(self, url: str, payload: dict) -> dict:
        resp = self.session.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": SIGNIN_BASE,
                "Referer": f"{SIGNIN_BASE}/platform/{DIR_ID}/signup/",
            },
            timeout=30,
        )
        return resp.json()

    def _navigate_signin_to_signup(
        self, signin_url: str, email: str,
    ) -> tuple[str, str, str]:
        """通过 HTTP 协议操作 signin 流程，获取 profile workflowID。

        Returns (workflowID, signup_workflowStateHandle, signup_stepId)
        """
        login_url = f"{SIGNIN_BASE}/platform/{DIR_ID}/api/execute"
        signup_url = f"{SIGNIN_BASE}/platform/{DIR_ID}/signup/api/execute"

        wf_match = re.search(r"workflowStateHandle=([^&]+)", signin_url)
        wf = wf_match.group(1) if wf_match else ""

        # Step 1: Init
        d = self._signin_execute(login_url, {"workflowStateHandle": wf})
        wf = d["workflowStateHandle"]

        # Step 2: SIGNUP action → get-identity-user
        d = self._signin_execute(login_url, {
            "stepId": "start",
            "workflowStateHandle": wf,
            "actionId": "SIGNUP",
            "inputs": [],
        })
        wf = d["workflowStateHandle"]

        # Step 3: Submit email → ENTITY_DOES_NOT_EXIST
        d = self._signin_execute(login_url, {
            "stepId": "get-identity-user",
            "workflowStateHandle": wf,
            "actionId": "SUBMIT",
            "inputs": [
                {"input_type": "UserRequestInput", "username": email},
            ],
        })

        # Step 4: Retry SIGNUP → user-signup with redirect
        d = self._signin_execute(login_url, {
            "stepId": "get-identity-user",
            "workflowStateHandle": wf,
            "actionId": "SIGNUP",
            "inputs": [],
        })
        redirect = d.get("redirect", {})
        if not redirect.get("url"):
            raise RuntimeError("无法获取注册页面跳转地址")

        signup_redirect = redirect["url"]
        signup_wf_match = re.search(
            r"workflowStateHandle=([^&]+)", signup_redirect
        )
        signup_wf = signup_wf_match.group(1) if signup_wf_match else ""
        self.session.get(signup_redirect, timeout=30)

        # Step 5: Init signup workflow
        d = self._signin_execute(
            signup_url, {"workflowStateHandle": signup_wf}
        )
        signup_wf2 = d["workflowStateHandle"]

        # Step 6: Submit email in signup → redirect to profile
        d = self._signin_execute(signup_url, {
            "stepId": "start",
            "workflowStateHandle": signup_wf2,
            "actionId": "SUBMIT",
            "inputs": [
                {"input_type": "UserRequestInput", "username": email},
            ],
        })
        profile_redirect = d.get("redirect", {}).get("url", "")
        wf_id_match = re.search(r"workflowID=([^&\"]+)", profile_redirect)
        if not wf_id_match:
            raise RuntimeError("无法获取 Profile 注册工作流 ID")

        signup_step_id = d.get("stepId", "")
        signup_wf_out = d.get("workflowStateHandle", signup_wf2)
        return wf_id_match.group(1), signup_wf_out, signup_step_id

    # ================================================================ Profile 注册 (Playwright)
    def _profile_signup_playwright(
        self,
        workflow_id: str,
        email: str,
        name: str,
        ms_client_id: str,
        ms_refresh_token: str,
    ) -> str:
        """Playwright 完成 profile.aws.amazon.com（姓名+验证码）。

        Returns: registrationCode
        """
        from playwright.sync_api import sync_playwright

        profile_url = (
            f"{PROFILE_BASE}/#/signup/start?workflowID={workflow_id}"
        )
        self._emit("正在加载注册页面...")

        pw_instance = sync_playwright().start()
        browser = None
        try:
            browser = pw_instance.chromium.launch(
                headless=True,
                channel="chrome",
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=_UA,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = context.new_page()
            page.goto(profile_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # 关闭 Cookie 弹窗
            try:
                cookie_btn = page.locator(
                    'button:has-text("Accept")'
                ).first
                if cookie_btn.is_visible(timeout=3000):
                    cookie_btn.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # 填写姓名
            self._emit("正在填写注册信息...")
            name_input = page.locator(
                'form#SignUp input[type="text"]:visible'
            )
            try:
                name_input.wait_for(state="visible", timeout=10000)
                name_input.fill(name)
            except Exception:
                all_text = page.locator('input[type="text"]:visible')
                if all_text.count() > 0:
                    all_text.first.fill(name)
                else:
                    raise RuntimeError(f"找不到姓名输入框, URL: {page.url}")

            page.wait_for_timeout(500)

            # 点击 Continue（发送 OTP）
            continue_btn = page.locator(
                '[data-testid="signup-next-button"]'
            )
            if not continue_btn.is_visible(timeout=3000):
                continue_btn = page.locator(
                    'button:has-text("Continue")'
                ).first
            continue_btn.click()
            self._emit("邮箱已生成，正在发送验证码...")
            page.wait_for_timeout(3000)

            # 获取验证码
            self._emit("正在获取验证码...")
            code = _graph_wait_for_code(
                ms_client_id, ms_refresh_token, email,
                timeout=120, poll_interval=5,
                progress_fn=self._emit,
            )
            self._emit("验证码已获取，正在验证...")

            # 填写验证码
            code_input = page.locator(
                'input[type="text"]:visible'
            ).first
            code_input.wait_for(state="visible", timeout=15000)
            code_input.fill(code)
            page.wait_for_timeout(500)

            verify_btn = page.locator(
                '[data-testid="signup-next-button"]'
            )
            if not verify_btn.is_visible(timeout=3000):
                verify_btn = page.locator(
                    'button:has-text("Verify"), '
                    'button:has-text("Continue"), '
                    'button:has-text("Confirm")'
                ).first
            verify_btn.click()

            # 等待跳转回 signin，提取 registrationCode
            self._emit("正在等待注册确认...")
            try:
                page.wait_for_url("**/signup*registrationCode*", timeout=30000)
            except Exception:
                page.wait_for_timeout(5000)

            final_url = page.url
            self._emit(f"注册确认完成: {final_url[:80]}")

            rc_match = re.search(r"registrationCode=([^&]+)", final_url)
            if not rc_match:
                raise RuntimeError(
                    f"未获取到 registrationCode, URL: {final_url[:120]}"
                )
            reg_code = rc_match.group(1)

            # 立即停止页面加载，防止 signin.aws SPA 阻塞关闭
            try:
                page.close()
            except Exception:
                pass

            return reg_code

        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            try:
                pw_instance.stop()
            except Exception:
                pass

    # ================================================================ Signup 完成（设置密码）

    @staticmethod
    def _encrypt_password_jwe(password: str, public_key_jwk: dict) -> str:
        """用 RSA-OAEP-256 + A256GCM 加密密码为 JWE compact token。"""
        key = jwk.JWK(**public_key_jwk)
        now = int(time.time())
        payload = json.dumps({
            "iss": "client",
            "iat": now,
            "nbf": now,
            "jti": str(uuid.uuid4()),
            "exp": now + 300,
            "aud": f"{REGION}.AWSPasswordService",
            "password": password,
        }).encode("utf-8")

        protected = {
            "alg": "RSA-OAEP-256",
            "enc": "A256GCM",
            "cty": "application/aws+signin+jwe",
        }
        if "kid" in public_key_jwk:
            protected["kid"] = public_key_jwk["kid"]

        token = jwe.JWE(
            plaintext=payload,
            protected=protected,
            recipient=key,
        )
        return token.serialize(compact=True)

    def _send_user_event(
        self, wf_handle: str, event_type: str, step_context: str,
    ):
        """发送用户事件（PAGE_LOAD / PAGE_SUBMIT），模拟真实浏览器行为。"""
        url = f"{SIGNIN_BASE}/platform/user-event/send-event"
        try:
            self.session.post(url, json={
                "workflowStateHandle": wf_handle,
                "userEvents": [{
                    "eventType": event_type,
                    "context": step_context,
                }],
                "directoryId": DIR_ID,
            }, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": SIGNIN_BASE,
            }, timeout=10)
        except Exception:
            pass

    def _submit_registration_and_password(
        self, signup_wf: str, signup_step_id: str,
        registration_code: str, password: str,
    ):
        """提交 registrationCode 并设置密码完成注册。"""
        signup_url = f"{SIGNIN_BASE}/platform/{DIR_ID}/signup/api/execute"

        # 提交 registrationCode
        self._emit("正在提交注册码...")
        d = self._signin_execute(signup_url, {
            "stepId": signup_step_id or "start",
            "workflowStateHandle": signup_wf,
            "actionId": "SUBMIT",
            "inputs": [
                {
                    "input_type": "UserRegistrationRequestInput",
                    "registrationCode": registration_code,
                },
            ],
        })
        step_id = d.get("stepId", "")
        wf = d.get("workflowStateHandle", signup_wf)
        self._emit(f"注册码结果: step={step_id}")

        if d.get("message", {}).get("type") == "ERROR":
            err = d["message"].get("text", "")
            self._emit(f"  响应: {json.dumps(d, ensure_ascii=False)[:300]}")
            raise RuntimeError(f"注册码提交失败: {err}")

        # 检查是否直接完成
        wf_result = d.get("workflowResultHandle", "")
        if wf_result or "end-of" in (step_id or ""):
            self._emit("注册已完成（无需密码）")
            return

        # 密码设置步骤
        if "password" not in (step_id or "").lower():
            self._emit(f"  响应: {json.dumps(d, ensure_ascii=False)[:300]}")
            raise RuntimeError(f"期望密码步骤，实际: {step_id}")

        # 从 workflowResponseData 提取公钥用于 JWE 加密
        resp_data = d.get("workflowResponseData", {})
        public_key_data = resp_data.get("publicKey")
        self._emit(f"密码加密: has_key={bool(public_key_data)}")

        self._send_user_event(wf, "PAGE_LOAD", "CREDENTIAL_COLLECTION")

        if public_key_data:
            try:
                if isinstance(public_key_data, str):
                    public_key_data = json.loads(public_key_data)
                encrypted_pw = self._encrypt_password_jwe(
                    password, public_key_data,
                )
                enc_status = "SUCCESSFUL"
                self._emit("密码已加密")
            except Exception as e:
                self._emit(f"加密失败({e})，尝试明文")
                encrypted_pw = password
                enc_status = "UNSUCCESSFUL"
        else:
            encrypted_pw = password
            enc_status = "UNSUCCESSFUL"

        d = self._signin_execute(signup_url, {
            "stepId": step_id,
            "workflowStateHandle": wf,
            "actionId": "SUBMIT",
            "inputs": [
                {
                    "input_type": "PasswordRequestInput",
                    "password": encrypted_pw,
                    "successfullyEncrypted": enc_status,
                },
            ],
        })
        new_step = d.get("stepId", "")
        wf = d.get("workflowStateHandle", wf)
        wf_result = d.get("workflowResultHandle", "")
        self._emit(f"密码结果: step={new_step} result={bool(wf_result)}")

        self._send_user_event(wf, "PAGE_SUBMIT", "CREDENTIAL_COLLECTION")

        if d.get("message", {}).get("type") == "ERROR":
            err = d["message"].get("text", "")
            raise RuntimeError(f"密码设置失败: {err}")

        if wf_result or "end-of" in (new_step or "") or "success" in (new_step or ""):
            self._emit("注册完成！")
            return

        self._emit(f"最终: step={new_step}")
        self._emit(f"  响应: {json.dumps(d, ensure_ascii=False)[:300]}")
