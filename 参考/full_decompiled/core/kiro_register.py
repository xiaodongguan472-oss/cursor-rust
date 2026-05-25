"""Kiro 客户端本地注册 — Playwright 自动化 + OAuth 设备流"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import random
import string
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

REGION = "us-east-1"
OIDC_BASE = f"https://oidc.{REGION}.amazonaws.com"

_RANDOM_NAMES = [
    "Zhang Wei", "Wang Fang", "Li Na", "Liu Yang", "Chen Jing",
    "Zhang Min", "Wang Lei", "Li Qiang", "Liu Min", "Chen Wei",
    "Maria José Silva", "João Santos", "Ana Oliveira",
    "James Smith", "Emily Johnson", "Michael Brown",
]

_CODE_RE = re.compile(r"\b(\d{6})\b")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SENDER_KEYWORDS = (
    "signin.aws", "no-reply", "noreply", "kiro.dev", "kiro", "aws",
)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}};
"""


def _gen_password(length: int = 16) -> str:
    upper = random.choices(string.ascii_uppercase, k=2)
    lower = random.choices(string.ascii_lowercase, k=2)
    digits = random.choices(string.digits, k=2)
    special = random.choices("!@#$%^&*", k=2)
    rest = random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=length - 8)
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


def _graph_fetch_emails(access_token: str, user_email: str, top: int = 5) -> list[dict]:
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


def graph_wait_for_code(
    client_id: str, refresh_token: str, user_email: str,
    timeout: int = 120, poll_interval: int = 5,
) -> str:
    access_token = _graph_get_token(client_id, refresh_token)

    seen: set[str] = set()
    for msg in _graph_fetch_emails(access_token, user_email, top=10):
        code = _extract_verification_code(msg.get("body", {}).get("content", ""))
        if code:
            seen.add(code)

    deadline = time.time() + timeout
    while time.time() < deadline:
        for msg in _graph_fetch_emails(access_token, user_email):
            from_addr = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            if any(kw in from_addr.lower() for kw in _SENDER_KEYWORDS):
                code = _extract_verification_code(msg.get("body", {}).get("content", ""))
                if code and code not in seen:
                    return code
        time.sleep(poll_interval)
    raise TimeoutError(f"超时 {timeout}s 未收到验证码")


# ---------------------------------------------------------------------------
# OIDC OAuth 设备流
# ---------------------------------------------------------------------------

def oidc_register_client() -> tuple[str, str]:
    resp = requests.post(
        f"{OIDC_BASE}/client/register",
        json={
            "clientName": "Kiro IDE Auto Registration",
            "clientType": "public",
            "scopes": [
                "codewhisperer:completions", "codewhisperer:analysis",
                "codewhisperer:conversations", "codewhisperer:transformations",
                "codewhisperer:taskassist",
            ],
            "grantTypes": ["urn:ietf:params:oauth:grant-type:device_code", "refresh_token"],
            "issuerUrl": f"https://oidc.{REGION}.amazonaws.com",
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    d = resp.json()
    return d["clientId"], d["clientSecret"]


def oidc_device_auth(client_id: str, client_secret: str) -> dict:
    resp = requests.post(
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


def oidc_poll_token(
    client_id: str, client_secret: str, device_code: str,
    interval: int = 5, max_attempts: int = 60,
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
        resp = requests.post(
            f"{OIDC_BASE}/token", json=body,
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        if resp.status_code == 200:
            d = resp.json()
            return d["accessToken"], d["refreshToken"]
        err = resp.json().get("error", "") if resp.status_code < 500 else ""
        if err == "authorization_pending":
            continue
        elif err == "slow_down":
            wait = interval + 5
        elif err == "expired_token":
            raise RuntimeError("设备码已过期")
        elif err == "access_denied":
            raise RuntimeError("授权被拒绝")
        elif err:
            raise RuntimeError(f"OAuth 错误: {err}")
    raise TimeoutError("Token 轮询超时")


# ---------------------------------------------------------------------------
# Playwright 浏览器自动化
# ---------------------------------------------------------------------------

async def _race_visible(candidates: list, timeout: int = 30_000) -> str:
    async def _check(loc, label):
        try:
            await loc.wait_for(state="visible", timeout=timeout)
            return label
        except Exception:
            return None

    tasks = [asyncio.create_task(_check(loc, label)) for loc, label in candidates]
    while tasks:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        tasks = list(pending)
        for t in done:
            result = t.result()
            if result:
                for r in tasks:
                    r.cancel()
                return result
    raise RuntimeError("所有候选元素均未出现")


async def _click_primary(page, label="提交") -> None:
    for btn in [
        page.get_by_test_id("test-primary-button"),
        page.get_by_test_id("signup-next-button"),
        page.get_by_test_id("email-verification-verify-button"),
        page.locator("button[type='submit']").first,
    ]:
        try:
            await btn.wait_for(state="visible", timeout=5_000)
            await btn.click()
            return
        except Exception:
            continue
    raise RuntimeError(f"未找到{label}按钮")


async def _click_oauth_confirm(page) -> None:
    for btn in [
        page.get_by_role("button", name="Confirm and continue"),
        page.locator("#cli_verification_btn"),
        page.get_by_role("button", name=re.compile(r"Confirm|确认", re.I)),
    ]:
        try:
            await btn.wait_for(state="visible", timeout=8_000)
            await btn.click()
            return
        except Exception:
            continue


async def _click_oauth_allow(page) -> None:
    for btn in [
        page.get_by_role("button", name="Allow access"),
        page.get_by_role("button", name=re.compile(r"Allow|允许", re.I)),
    ]:
        try:
            await btn.wait_for(state="visible", timeout=15_000)
            await btn.click()
            return
        except Exception:
            continue


async def _dismiss_cookie(page) -> None:
    try:
        btn = page.locator("[data-id='awsccc-cb-btn-accept']")
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass


async def _recover_blank(page, max_retries: int = 4) -> bool:
    for attempt in range(max_retries):
        await page.wait_for_timeout(2000)
        visible_inputs = await page.locator("input:visible").count()
        body_text = await page.evaluate("document.body?.innerText?.trim() || ''")
        if visible_inputs > 0 or len(body_text) > 80:
            return True
        url = page.url
        if attempt == 0:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        elif attempt == 1:
            await page.goto("about:blank")
            await page.wait_for_timeout(1000)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        else:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
    return await page.locator("input:visible").count() > 0


# ---------------------------------------------------------------------------
# 主注册流程
# ---------------------------------------------------------------------------

class KiroRegisterRunner:
    """在客户端本地执行 Kiro 注册 + OAuth 的完整流程。

    progress_fn: 可选回调 (message: str) -> None，用于向 UI 推送进度日志。
    """

    def __init__(self, api_client, progress_fn: Optional[Callable[[str], None]] = None):
        self.api = api_client
        self._log = progress_fn or (lambda m: None)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _emit(self, msg: str):
        self._log(msg)

    def run(self) -> dict:
        """同步入口，在工作线程中调用。返回结果 dict 或抛异常。"""
        return asyncio.run(self._run_async())

    async def _run_async(self) -> dict:
        self._emit("正在初始化注册...")

        # 1) 从后端获取邮箱
        self._emit("正在获取注册邮箱...")
        r = self.api.fetch_kiro_register_email()
        if not r.get("success"):
            msg = r.get("message") or "获取注册邮箱失败，请检查网络或联系客服"
            raise RuntimeError(msg)

        data = r.get("data")
        if not data or not isinstance(data, dict):
            raise RuntimeError("服务器返回数据异常，请稍后重试")

        email = data.get("email")
        ms_client_id = data.get("ms_client_id")
        ms_refresh_token = data.get("ms_refresh_token")
        if not email or not ms_client_id or not ms_refresh_token:
            raise RuntimeError("注册邮箱信息不完整，请稍后重试")
        existing_pw = data.get("existing_password")

        self._emit(f"邮箱已分配: {email[:6]}***")

        if self._cancelled:
            raise RuntimeError("用户取消")

        # 2) 浏览器注册
        self._emit("正在启动浏览器...")
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = None
        try:
            browser = await pw.chromium.launch(
                headless=True,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled", "--lang=zh-CN"],
            )
            context = await browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
            await context.add_init_script(_STEALTH_JS)
            page = await context.new_page()

            password, already_existed = await self._do_register(
                page, email, ms_client_id, ms_refresh_token, existing_pw,
            )

            if self._cancelled:
                raise RuntimeError("用户取消")

            # 3) OAuth 设备流
            self._emit("正在注册 OIDC 客户端...")
            client_id, client_secret = oidc_register_client()

            self._emit("正在发起设备授权...")
            da = oidc_device_auth(client_id, client_secret)
            verification_url = da.get("verificationUriComplete") or da["verificationUri"]

            self._emit("正在完成 OAuth 授权...")
            await self._do_oauth(browser, context, verification_url)

            self._emit("正在获取访问令牌...")
            access_token, refresh_token = oidc_poll_token(
                client_id, client_secret, da["deviceCode"], da.get("interval", 5),
            )

            self._emit("正在生成认证信息...")
            cid_hash = hashlib.sha256(client_id.encode()).hexdigest()
            oauth_info = json.dumps({
                "accessToken": access_token, "refreshToken": refresh_token,
                "provider": "BuilderId", "authMethod": "IdC", "expiresAt": "",
                "clientIdHash": cid_hash, "region": REGION,
                "clientId": client_id, "clientSecret": client_secret,
            })

            await browser.close()
            browser = None

            # 4) 推送结果到后端
            self._emit("正在同步注册结果...")
            push_r = self.api.push_kiro_register_result({
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

            self._emit("注册完成！正在登录 Kiro...")

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

        except Exception as exc:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            try:
                self.api.push_kiro_register_result({
                    "email": email,
                    "status": "error",
                    "error_reason": str(exc),
                })
            except Exception:
                pass
            raise

    async def _do_register(
        self, page, email: str,
        ms_client_id: str, ms_refresh_token: str,
        existing_pw: Optional[str],
    ) -> tuple[str, bool]:
        """执行浏览器注册流程，返回 (password, already_existed)。"""
        self._emit("正在连接 Kiro 服务...")
        await page.goto("https://app.kiro.dev/signin", wait_until="domcontentloaded")

        self._emit("正在跳转注册页面...")
        builder_btn = page.get_by_role("button", name=re.compile(r"Builder ID", re.I))
        await builder_btn.wait_for(state="visible", timeout=60_000)
        await builder_btn.click()

        self._emit("正在加载注册页面...")
        email_input = page.locator("input[type='email'], div[data-testid='test-input'] input").first
        await email_input.wait_for(state="visible", timeout=30_000)
        await email_input.fill(email)

        self._emit("正在提交邮箱...")
        await _click_primary(page, "继续")

        name_loc = page.locator("div[data-testid='signup-full-name-input'] input").first
        code_loc = page.locator("div[data-testid='email-verification-form-code-input'] input").first
        pw_loc = page.locator("input[type='password']").first
        login_code_loc = page.locator("input[placeholder='6-digit']").first

        landed = await _race_visible([
            (name_loc, "name"), (code_loc, "code"),
            (pw_loc, "password"), (login_code_loc, "login_code"),
        ], timeout=30_000)

        already_existed = False
        password = existing_pw or ""

        # 登录验证码页
        if landed == "login_code":
            already_existed = True
            self._emit("账号已存在，正在获取登录验证码...")
            code = graph_wait_for_code(ms_client_id, ms_refresh_token, email)
            self._emit("验证码已获取，正在验证...")
            await login_code_loc.fill(code)
            cont_btn = page.get_by_role("button", name=re.compile(r"继续|Continue|Verify", re.I))
            try:
                await cont_btn.first.wait_for(state="visible", timeout=5_000)
                await cont_btn.first.click()
            except Exception:
                await _click_primary(page, "继续")
            await page.wait_for_timeout(3000)

            await _recover_blank(page, max_retries=4)
            try:
                await pw_loc.wait_for(state="visible", timeout=10_000)
                landed = "password"
                already_existed = False
            except Exception:
                pass

        # 姓名页
        if landed == "name":
            name = random.choice(_RANDOM_NAMES)
            self._emit("正在填写注册信息...")
            await name_loc.fill(name)
            await _click_primary(page, "继续")

            self._emit("正在等待页面跳转...")
            await page.wait_for_timeout(3000)

            recovered = await _recover_blank(page, max_retries=6)
            if not recovered:
                self._emit(f"页面加载缓慢，继续等待... (URL: {page.url[:60]})")
                await page.wait_for_timeout(5000)

            try:
                next_page = await _race_visible([
                    (code_loc, "code"), (pw_loc, "password"), (login_code_loc, "login_code"),
                ], timeout=30_000)
                landed = next_page
            except RuntimeError:
                self._emit(f"检测页面状态... URL: {page.url[:80]}")
                body = await page.evaluate("document.body?.innerText?.trim()?.substring(0, 200) || ''")
                if body:
                    self._emit(f"页面内容: {body[:100]}")

                await page.reload(wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)

                try:
                    next_page = await _race_visible([
                        (code_loc, "code"), (pw_loc, "password"),
                        (login_code_loc, "login_code"), (name_loc, "name"),
                    ], timeout=20_000)
                    if next_page == "name":
                        self._emit("页面回退到姓名页，重新提交...")
                        await name_loc.fill(name)
                        await _click_primary(page, "继续")
                        await page.wait_for_timeout(5000)
                        await _recover_blank(page, max_retries=4)
                        next_page = await _race_visible([
                            (code_loc, "code"), (pw_loc, "password"),
                            (login_code_loc, "login_code"),
                        ], timeout=30_000)
                    landed = next_page
                except RuntimeError:
                    raise RuntimeError(
                        f"姓名提交后页面未响应，URL: {page.url[:80]}"
                    )

        # 验证码页
        if landed == "code":
            self._emit("正在获取验证码...")
            code = graph_wait_for_code(ms_client_id, ms_refresh_token, email)
            self._emit("验证码已获取，正在验证...")
            await code_loc.fill(code)
            await _click_primary(page, "验证")
            await page.wait_for_timeout(3000)
            await _recover_blank(page, max_retries=4)
            await pw_loc.wait_for(state="visible", timeout=15_000)
            landed = "password"

        # 密码页
        if landed == "password":
            pw_inputs = page.locator("input[type='password']")
            count = await pw_inputs.count()
            if count >= 2:
                password = _gen_password()
                self._emit("正在设置密码...")
                await pw_inputs.nth(0).fill(password)
                await pw_inputs.nth(1).fill(password)
                await _click_primary(page, "创建")
            else:
                already_existed = True
                if not existing_pw:
                    raise RuntimeError("账号已注册但无已知密码，无法登录")
                self._emit("正在使用已知密码登录...")
                password = existing_pw
                await pw_inputs.first.fill(password)
                await _click_primary(page, "登录")

        self._emit("正在完成登录...")
        try:
            await page.wait_for_url("**/start*", timeout=15_000)
        except Exception:
            try:
                await page.wait_for_selector("text=/successfully|成功/i", timeout=5_000)
            except Exception:
                pass

        return password, already_existed

    async def _do_oauth(self, browser, context, verification_url: str) -> None:
        """在已登录的浏览器会话中完成 OAuth 授权。"""
        page = await context.new_page()
        try:
            await page.goto(verification_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await _dismiss_cookie(page)
            await _click_oauth_confirm(page)
            await page.wait_for_timeout(2000)
            await _dismiss_cookie(page)
            await _click_oauth_allow(page)
            await page.wait_for_timeout(2000)
        finally:
            await page.close()
