"""AI助手 API 客户端

后端响应格式: {"success": true/false, "message": "...", "data": ...}
兼容 macOS (Intel / Apple Silicon) 和 Windows。
"""

from __future__ import annotations

import uuid
import os
import json
import platform
import sys
import hashlib
import base64
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


def _config_dir() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "WuxianAssistant")
    elif system == "Darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library", "Application Support", "WuxianAssistant",
        )
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = xdg if xdg else os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "WuxianAssistant")


CONFIG_DIR = _config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, "device.json")
USER_FILE = os.path.join(CONFIG_DIR, "user.json")
MENU_CACHE_FILE = os.path.join(CONFIG_DIR, "menu_cache.json")

_LEGACY_DIR = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
_LEGACY_FILE = os.path.join(_LEGACY_DIR, "device.json")


class DeviceInfo:

    def __init__(self):
        self._device_code: str = ""
        self._load_or_generate()

    def _load_or_generate(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        for path in (CONFIG_FILE, _LEGACY_FILE):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._device_code = data["device_code"]
                    if path == _LEGACY_FILE:
                        self._save()
                    return
                except Exception:
                    pass
        self._generate_new()

    def _generate_new(self):
        self._device_code = uuid.uuid4().hex
        self._save()

    def _save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"device_code": self._device_code}, f, indent=2)
        except OSError:
            pass

    @property
    def code(self) -> str:
        return self._device_code


class ApiClient:
    _AUTH_EXPIRED_KEYWORDS = ("未登录", "登录已过期", "请重新登录")
    _BANNED_KEYWORDS = ("已被封禁",)

    def _parse_response(self, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            snippet = (resp.text or "").strip().replace("\n", " ")[:240]
            return {
                "success": False,
                "message": snippet or f"HTTP {resp.status_code}",
                "data": None,
            }
        if not isinstance(data, dict):
            return {"success": resp.ok, "message": "", "data": data}
        result = {
            "success": bool(data.get("success")),
            "message": data.get("message", ""),
            "data": data.get("data"),
        }
        if not result["success"]:
            msg = result["message"]
            if msg and any(kw in msg for kw in self._AUTH_EXPIRED_KEYWORDS):
                result["auth_expired"] = True
            if msg and any(kw in msg for kw in self._BANNED_KEYWORDS):
                result["user_banned"] = True
        return result

    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url
        self.timeout = 15
        self.device = DeviceInfo()
        self._user_token: str = ""
        self._user_info: dict = {}
        self._load_user_session()

    # ---- Menu config local cache ----
    @staticmethod
    def load_menu_cache() -> dict:
        """Load cached menu config from disk. Returns dict with keys:
        menu_config, menu_order, show_renew, show_tutorial, env_config.
        Returns empty dict if no cache exists."""
        if not os.path.exists(MENU_CACHE_FILE):
            return {}
        try:
            with open(MENU_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def save_menu_cache(menu_config: dict, menu_order: list,
                        show_renew: bool, show_tutorial: bool,
                        env_config: dict, platform_guides: dict | None = None):
        """Persist menu config to disk for fast startup."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            payload = {
                "menu_config": menu_config,
                "menu_order": menu_order,
                "show_renew": show_renew,
                "show_tutorial": show_tutorial,
                "env_config": env_config,
            }
            if platform_guides is not None:
                payload["platform_guides"] = platform_guides
            with open(MENU_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_user_session(self):
        if os.path.exists(USER_FILE):
            try:
                with open(USER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._user_token = data.get("token", "")
                    self._user_info = data.get("user", {})
            except Exception:
                pass

    def _save_user_session(self, token: str, user: dict):
        self._user_token = token
        self._user_info = user
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(USER_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": token, "user": user}, f, indent=2)
        except OSError:
            pass

    def clear_user_session(self):
        self._user_token = ""
        self._user_info = {}
        try:
            if os.path.exists(USER_FILE):
                os.remove(USER_FILE)
        except OSError:
            pass

    @property
    def is_logged_in(self) -> bool:
        return bool(self._user_token)

    @property
    def user_info(self) -> dict:
        return self._user_info

    @property
    def user_token(self) -> str:
        return self._user_token

    def _user_headers(self) -> dict:
        h = {}
        if self._user_token:
            h["X-User-Token"] = self._user_token
        return h

    def _get(self, path: str, params: dict = None, timeout: float | None = None) -> dict:
        try:
            r = requests.get(f"{self.base_url}{path}", params=params,
                             headers=self._user_headers(), timeout=timeout or self.timeout)
            return self._parse_response(r)
        except (requests.ConnectionError, requests.Timeout):
            return {"success": False, "message": "无法连接服务器，请检查网络连接后重试", "data": None}
        except Exception as e:
            return {"success": False, "message": f"请求异常: {e}", "data": None}

    def _post(self, path: str, data: dict = None, timeout: float | None = None) -> dict:
        try:
            r = requests.post(f"{self.base_url}{path}", json=data,
                              headers=self._user_headers(), timeout=timeout or self.timeout)
            return self._parse_response(r)
        except (requests.ConnectionError, requests.Timeout):
            return {"success": False, "message": "无法连接服务器，请检查网络连接后重试", "data": None}
        except Exception as e:
            return {"success": False, "message": f"请求异常: {e}", "data": None}

    def _put(self, path: str, data: dict = None) -> dict:
        try:
            r = requests.put(f"{self.base_url}{path}", json=data,
                             headers=self._user_headers(), timeout=self.timeout)
            return self._parse_response(r)
        except (requests.ConnectionError, requests.Timeout):
            return {"success": False, "message": "无法连接服务器，请检查网络连接后重试", "data": None}
        except Exception as e:
            return {"success": False, "message": f"请求异常: {e}", "data": None}

    _SHARED_SECRET = "WuxianAssistant@2026#Sec"
    _AES_KEY = hashlib.sha256(_SHARED_SECRET.encode()).digest()[:16]

    @classmethod
    def _encrypt(cls, plaintext: str) -> str:
        iv = os.urandom(16)
        cipher = AES.new(cls._AES_KEY, AES.MODE_CBC, iv)
        ct = cipher.encrypt(pad(plaintext.encode(), AES.block_size))
        return base64.b64encode(iv + ct).decode()

    @classmethod
    def _decrypt(cls, ciphertext: str) -> str:
        raw = base64.b64decode(ciphertext)
        iv, ct = raw[:16], raw[16:]
        cipher = AES.new(cls._AES_KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode()

    # ---- 设备初始化（通过用户Token查找激活码）----
    def init_device(self, refresh: bool = False) -> dict:
        params = {"refresh": "true"} if refresh else None
        return self._get("/api/v2/device/init", params=params)

    # ---- Cursor 凭证（加密传输）----
    def get_credentials(self) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({"device_code": self.device.code}))
            resp = self._post("/api/v2/cursor/credentials", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    # ---- Kiro 凭证（加密传输）----
    def get_kiro_credentials(self) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({"device_code": self.device.code}))
            resp = self._post("/api/v2/kiro/credentials", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    def reuse_kiro_history_account(self, email: str) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({
                "device_code": self.device.code,
                "email": email,
            }))
            resp = self._post("/api/v2/kiro/reuse", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    def get_kiro_history(self) -> dict:
        return self._get("/api/v2/kiro/history")

    def refresh_kiro_count(self) -> dict:
        return self._get("/api/v2/kiro/count")

    def fetch_kiro_register_email(self) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({"device_code": self.device.code}))
            resp = self._post("/api/v2/kiro/register-fetch", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    def push_kiro_register_result(self, result_data: dict) -> dict:
        try:
            result_data["device_code"] = self.device.code
            encrypted_req = self._encrypt(json.dumps(result_data))
            resp = self._post("/api/v2/kiro/register-complete", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    # ---- Windsurf 账号分配 ----
    def get_windsurf_account(self) -> dict:
        """从后端拿到当前用户绑定的 Windsurf 账号 (email/password). 会扣 1 次额度."""
        return self._get("/api/v2/windsurf/account")

    def refresh_windsurf_count(self) -> dict:
        return self._get("/api/v2/windsurf/count")

    def get_windsurf_history(self) -> dict:
        """该用户绑定过的所有 Windsurf 账号 (email/password/lastUsedTime)."""
        return self._get("/api/v2/windsurf/history")

    def reuse_windsurf_account(self, email: str) -> dict:
        """复用历史账号 (email 必须在用户绑定历史里), 不扣额度."""
        return self._post("/api/v2/windsurf/reuse", {"email": email})

    def cursor_heartbeat(self) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({"device_code": self.device.code}))
            return self._post("/api/v2/cursor/heartbeat", {"data": encrypted_req})
        except Exception:
            return {"success": False}

    # ---- 历史账号一键登录（不扣额度）----
    def reuse_history_account(self, email: str) -> dict:
        try:
            encrypted_req = self._encrypt(json.dumps({
                "device_code": self.device.code,
                "email": email,
            }))
            resp = self._post("/api/v2/cursor/reuse", {"data": encrypted_req})
            if not resp.get("success"):
                return resp
            encrypted_data = resp.get("data")
            if not encrypted_data or not isinstance(encrypted_data, str):
                return resp
            decrypted = self._decrypt(encrypted_data)
            resp["data"] = json.loads(decrypted)
            return resp
        except Exception as e:
            return {"success": False, "message": f"数据通信异常: {e}", "data": None}

    # ---- 额度刷新 ----
    def refresh_count(self) -> dict:
        return self._get("/api/v2/cursor/count")

    # ---- 历史账号 ----
    def get_history_account(self) -> dict:
        return self._get("/api/v2/cursor/history")

    # ---- 公告 ----
    def get_type_msg(self) -> dict:
        return self._get("/api/v2/notice/list")

    # ---- 检查更新 ----
    def check_update(self, app_version: str = "2.0.6") -> dict:
        return self._get("/api/v2/app/check-update", {
            "version": app_version,
            "platform": platform.system(),
            "arch": platform.machine(),
        })

    def _get_config_value(self, path: str, timeout: float | None = None):
        """Fetch a config value from backend using authenticated _get()."""
        r = self._get(path, timeout=timeout)
        if r.get("success") and r.get("data") is not None:
            return r["data"]
        return None

    def _get_config_dict(self, path: str, timeout: float | None = None) -> dict:
        raw = self._get_config_value(path, timeout=timeout)
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return {}
        if isinstance(raw, dict):
            return raw
        return {}

    # ---- 无感换号开关配置 ----
    def get_seamless_switch_config(self) -> dict:
        return self._get_config_dict("/api/v2/config/seamless-switch")

    # ---- 合并配置接口 ----
    def get_all_config(self, timeout: float | None = None) -> dict:
        """Single request to fetch all client config. Returns parsed dict with keys:
        menu_config, menu_order, show_renew, show_tutorial, env_config, redeem_placeholder, seamless_switch_config."""
        r = self._get("/api/v2/config/all", timeout=timeout)
        if not r.get("success") or not r.get("data"):
            return {}
        d = r["data"]
        result = {}
        # menu_config
        mc = d.get("client_menus", "{}")
        if isinstance(mc, str):
            try:
                result["menu_config"] = json.loads(mc)
            except (json.JSONDecodeError, ValueError):
                result["menu_config"] = {}
        elif isinstance(mc, dict):
            result["menu_config"] = mc
        else:
            result["menu_config"] = {}
        # menu_order
        mo = d.get("client_menu_order", "[]")
        if isinstance(mo, str):
            try:
                parsed = json.loads(mo)
                result["menu_order"] = parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                result["menu_order"] = []
        elif isinstance(mo, list):
            result["menu_order"] = mo
        else:
            result["menu_order"] = []
        # show_renew / show_tutorial
        result["show_renew"] = str(d.get("show_renew", "true")).lower() != "false"
        result["show_tutorial"] = str(d.get("show_tutorial", "true")).lower() != "false"
        # env_config
        ec = d.get("env_config", "{}")
        if isinstance(ec, str):
            try:
                result["env_config"] = json.loads(ec)
            except (json.JSONDecodeError, ValueError):
                result["env_config"] = {}
        elif isinstance(ec, dict):
            result["env_config"] = ec
        else:
            result["env_config"] = {}
        # redeem_placeholder
        result["redeem_placeholder"] = str(d.get("redeem_placeholder", "输入兑换码"))
        # seamless_switch_config
        sc = d.get("seamless_switch_config", "{}")
        if isinstance(sc, str):
            try:
                result["seamless_switch_config"] = json.loads(sc)
            except (json.JSONDecodeError, ValueError):
                result["seamless_switch_config"] = {}
        elif isinstance(sc, dict):
            result["seamless_switch_config"] = sc
        else:
            result["seamless_switch_config"] = {}
        # platform_guides
        pg = d.get("platform_guides", "{}")
        if isinstance(pg, str):
            try:
                result["platform_guides"] = json.loads(pg)
            except (json.JSONDecodeError, ValueError):
                result["platform_guides"] = {}
        elif isinstance(pg, dict):
            result["platform_guides"] = pg
        else:
            result["platform_guides"] = {}
        return result

    # ---- 客户端菜单配置 ----
    def get_client_menus(self, timeout: float | None = None) -> dict:
        return self._get_config_dict("/api/v2/config/client-menus", timeout=timeout)

    def get_client_menu_order(self, timeout: float | None = None) -> list:
        raw = self._get_config_value("/api/v2/config/client-menu-order", timeout=timeout)
        if raw is None:
            return []
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(raw, list):
            return raw
        return []

    # ---- 教程链接 ----
    def get_tutorial_url(self) -> str:
        val = self._get_config_value("/api/v2/config/tutorial-url")
        return str(val) if val else ""

    # ---- 续费链接 ----
    def get_renew_url(self) -> str:
        val = self._get_config_value("/api/v2/config/renew-url")
        return str(val) if val else ""

    def get_show_renew(self, timeout: float | None = None) -> bool:
        val = self._get_config_value("/api/v2/config/show-renew", timeout=timeout)
        if val is None:
            return True
        return str(val).lower() != "false"

    def get_show_tutorial(self, timeout: float | None = None) -> bool:
        val = self._get_config_value("/api/v2/config/show-tutorial", timeout=timeout)
        if val is None:
            return True
        return str(val).lower() != "false"

    # ---- 统一兑换（通过用户Token）----
    def unified_redeem(self, code: str) -> dict:
        return self._post("/api/v2/device/unified-redeem", {"code": code})

    def get_redeem_placeholder(self) -> str:
        val = self._get_config_value("/api/v2/config/redeem-placeholder")
        return str(val) if val else "输入兑换码"

    # ---- 环境配置显隐 ----
    def get_env_config(self, timeout: float | None = None) -> dict:
        return self._get_config_dict("/api/v2/config/env-config", timeout=timeout)

    # ---- Cursor 安装包下载地址 ----
    def get_cursor_download_urls(self) -> dict:
        """Returns dict like {win32_x64: url, darwin_arm64: url, ...}"""
        r = self._get("/api/v2/config/cursor-download-urls")
        if r.get("success") and isinstance(r.get("data"), dict):
            return {k: v for k, v in r["data"].items() if v}
        return {}

    # ---- Sub2API 代理 ----
    def sub2api_generate_key(self, tool: str = "codex") -> dict:
        return self._post("/api/v2/sub2api/generate-key", {"tool": tool})

    def sub2api_list_keys(self, tool: str | None = None) -> dict:
        params: dict = {}
        if tool:
            params["tool"] = tool
        return self._get("/api/v2/sub2api/keys", params)

    def sub2api_get_balance(self, timeout: float | None = None) -> dict:
        return self._get("/api/v2/sub2api/balance", timeout=timeout)

    def sub2api_get_usage(self, page: int = 1, page_size: int = 20, api_key_id: int | None = None) -> dict:
        params: dict = {"page": page, "pageSize": page_size}
        if api_key_id is not None:
            params["apiKeyId"] = api_key_id
        return self._get("/api/v2/sub2api/usage", params)

    def sub2api_get_usage_stats(self, period: str = "month", api_key_id: int | None = None) -> dict:
        params: dict = {"period": period}
        if api_key_id is not None:
            params["apiKeyId"] = api_key_id
        return self._get("/api/v2/sub2api/usage-stats", params)

    def sub2api_sync_keys(self) -> dict:
        return self._post("/api/v2/sub2api/sync-keys", {})

    def sub2api_refresh_key(self, tool: str = "codex") -> dict:
        return self._post("/api/v2/sub2api/refresh-key", {"tool": tool})

    def sub2api_get_endpoint(self) -> dict:
        return self._get("/api/v2/sub2api/endpoint")

    def sub2api_redeem(self, code: str) -> dict:
        return self._post("/api/v2/sub2api/redeem", {"code": code})

    # ---- 用户账号 ----
    def register(self, email: str, password: str, nickname: str = "") -> dict:
        resp = self._post("/api/v2/user/register", {
            "email": email, "password": password, "nickname": nickname,
        })
        if resp.get("success") and resp.get("data"):
            d = resp["data"]
            self._save_user_session(d.get("token", ""), {
                "user_id": d.get("user_id"),
                "email": d.get("email"),
                "nickname": d.get("nickname"),
            })
        return resp

    def login(self, email: str, password: str) -> dict:
        resp = self._post("/api/v2/user/login", {"email": email, "password": password})
        if resp.get("success") and resp.get("data"):
            d = resp["data"]
            self._save_user_session(d.get("token", ""), {
                "user_id": d.get("user_id"),
                "email": d.get("email"),
                "nickname": d.get("nickname"),
            })
        return resp

    def logout(self):
        self.clear_user_session()

    def get_user_activations(self) -> dict:
        return self._get("/api/v2/user/activations")

    def update_nickname(self, nickname: str) -> dict:
        resp = self._put("/api/v2/user/nickname", {"nickname": nickname})
        if resp.get("success") and resp.get("data"):
            self._user_info["nickname"] = resp["data"].get("nickname", nickname)
            self._save_user_session(self._user_token, self._user_info)
        return resp

    def update_password(self, old_password: str, new_password: str) -> dict:
        return self._put("/api/v2/user/password", {
            "oldPassword": old_password, "newPassword": new_password,
        })

    # ---- Cursor Pro ----
    def get_cursor_pro_config(self, with_account: bool = False) -> dict:
        """拉取 Cursor Pro 一键配置。

        Args:
            with_account: True 时让服务端从账号池分配一个 Pro 账号
                          （会递增 assigned_count）。默认 False 仅返回 Key/模型/baseUrl
                          等元信息，不消耗账号池配额。
        """
        path = "/api/v2/cursor-pro/config"
        if with_account:
            path += "?withAccount=true"
        return self._get(path)

    # ---- 设备码 ----
    def get_device_code(self) -> str:
        return self.device.code
