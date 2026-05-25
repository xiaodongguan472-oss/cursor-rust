"""Windsurf 一键登录 + 无感切号.

整体流程 (参考 chaogei/windsurf-account-manager-simple):

  主路径 — Devin Auth + one-time token + URL callback (无感切号, 无需重启):
    1. POST https://windsurf.com/_devin-auth/password/login
          body: {email, password}
          → auth1_token
    2. POST https://web-backend.windsurf.com/.../WindsurfPostAuth
          body: protobuf(field1=auth1_token)
          header: X-Devin-Auth1-Token: auth1_token
          → session_token + auth1_token + account_id + primary_org_id
    3. POST https://web-backend.windsurf.com/.../GetOneTimeAuthToken
          body: protobuf(field1=devin-session-token$session_token)
          headers: x-auth-token, x-devin-session-token, x-devin-auth1-token, x-devin-account-id, x-devin-primary-org-id
          → one_time_auth_token
    4. 应用无感切号补丁 (修改 extension.js)
    5. 重置机器码
    6. open windsurf://codeium.windsurf#access_token={one_time_auth_token}&...
       → Windsurf 内部处理登录, 无需重启

  备用路径 — Firebase refresh_token (无 App Check):
    仅当主路径 Devin auth 步骤失败且有 refresh_token 时才启用.
    Firebase id_token 无法用于 GetOneTimeAuthToken, 回退到写 state.vscdb.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from typing import Callable, Optional, Tuple

import requests


# ──────────────────────────────────────────────────────── 常量

# Devin Auth
_DEVIN_AUTH_BASE = "https://windsurf.com/_devin-auth"
_WINDSURF_BACKEND = "https://web-backend.windsurf.com"
_WINDSURF_POST_AUTH_URL = (
    f"{_WINDSURF_BACKEND}/exa.seat_management_pb.SeatManagementService/WindsurfPostAuth"
)
_ONE_TIME_AUTH_URL = (
    f"{_WINDSURF_BACKEND}/exa.seat_management_pb.SeatManagementService/GetOneTimeAuthToken"
)

# Firebase refresh (securetoken 不要求 App Check)
_FIREBASE_API_KEY = "AIzaSyDsOl-1XpT5err0Tcnx8FFod1H8gVGIycY"
_FIREBASE_REFRESH_URL = f"https://securetoken.googleapis.com/v1/token?key={_FIREBASE_API_KEY}"

# Windsurf RegisterUser (fallback path)
_REGISTER_USER_URL = (
    "https://register.windsurf.com/exa.seat_management_pb.SeatManagementService/RegisterUser"
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

# 无感切号补丁的三个正则 (与 patch_commands.rs 保持一致)
_PATTERN_URI_HANDLER = (
    r'this\._uriHandler\.event\((\w+)=>\{"'
    r'/refresh-authentication-session"===(\w+)\.path&&'
    r'\(0,(\w+)\.refreshAuthenticationSession\)\(\)\}\)'
)
_PATTERN_TIMEOUT = (
    r',new Promise\(\((\w+),(\w+)\)=>'
    r'setTimeout\(\(\)=>\{(\w+)\(new (\w+)\)\},18e4\)\)'
)
_PATTERN_DIFF_ACCOUNT = (
    r'if\("Yes"===await (\w+)\.window\.showWarningMessage\('
    r'"Are you sure you want to log in using a different account\?",\{modal:!0\},"Yes"\)\)'
)
_PATCH_MARKER = "Failed to handle OAuth callback"


# ──────────────────────────────────────────────────────── 路径

def _windsurf_data_root() -> str:
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise EnvironmentError("APPDATA 环境变量未设置")
        return os.path.join(appdata, "Windsurf")
    if sys.platform == "darwin":
        return os.path.abspath(
            os.path.expanduser("~/Library/Application Support/Windsurf")
        )
    if sys.platform.startswith("linux"):
        return os.path.abspath(os.path.expanduser("~/.config/Windsurf"))
    raise NotImplementedError(f"不支持的操作系统: {sys.platform}")


def _global_storage_dir() -> str:
    return os.path.join(_windsurf_data_root(), "User", "globalStorage")


def _state_vscdb_path() -> str:
    return os.path.join(_global_storage_dir(), "state.vscdb")


def _storage_json_path() -> str:
    return os.path.join(_global_storage_dir(), "storage.json")


def _machine_id_file_path() -> str:
    return os.path.join(_windsurf_data_root(), "machineid")


def _extension_js_path() -> str:
    """extension.js 的绝对路径 (跨平台)."""
    if sys.platform == "darwin":
        return (
            "/Applications/Windsurf.app/Contents/Resources/app"
            "/extensions/windsurf/dist/extension.js"
        )
    if sys.platform == "win32":
        localappdata = os.getenv("LOCALAPPDATA", "")
        return os.path.join(
            localappdata, "Programs", "Windsurf", "resources", "app",
            "extensions", "windsurf", "dist", "extension.js",
        )
    return os.path.expanduser(
        "~/.local/share/Windsurf/resources/app"
        "/extensions/windsurf/dist/extension.js"
    )


# ──────────────────────────────────────────────────────── Protobuf 工具

def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_proto_string(field_no: int, value: str) -> bytes:
    data = value.encode("utf-8")
    tag = (field_no << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(data)) + data


def _decode_varint(data: bytes, offset: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7
    raise ValueError("Unexpected end of varint")


def _decode_proto_strings(data: bytes) -> dict:
    """Decode protobuf response, returns {field_no: value} for wire-type-2 fields."""
    fields: dict = {}
    i = 0
    while i < len(data):
        try:
            tag, i = _decode_varint(data, i)
        except (ValueError, IndexError):
            break
        field_no = tag >> 3
        wire_type = tag & 0x7
        if wire_type == 2:
            try:
                length, i = _decode_varint(data, i)
            except (ValueError, IndexError):
                break
            end = i + length
            if end > len(data):
                break
            payload = data[i:end]
            i = end
            try:
                fields[field_no] = payload.decode("utf-8")
            except UnicodeDecodeError:
                fields[field_no] = payload
        elif wire_type == 0:
            try:
                _, i = _decode_varint(data, i)
            except (ValueError, IndexError):
                break
        elif wire_type == 5:
            i += 4
        elif wire_type == 1:
            i += 8
        else:
            break
    return fields


# ──────────────────────────────────────────────────────── HTTP 步骤

def _common_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": _UA,
        "Origin": "https://windsurf.com",
        "Referer": "https://windsurf.com/account/login",
    }


class _PostAuthResult:
    __slots__ = ("session_token", "auth1_token", "account_id", "primary_org_id")

    def __init__(self, session_token: str, auth1_token: Optional[str] = None,
                 account_id: Optional[str] = None, primary_org_id: Optional[str] = None):
        self.session_token = session_token
        self.auth1_token = auth1_token
        self.account_id = account_id
        self.primary_org_id = primary_org_id


def _devin_password_login(email: str, password: str,
                           timeout: float = 20.0) -> Tuple[bool, str, str]:
    """Step 1: POST /_devin-auth/password/login → auth1_token."""
    url = f"{_DEVIN_AUTH_BASE}/password/login"
    body = {"email": email, "password": password}
    try:
        r = requests.post(url, json=body, headers=_common_headers(), timeout=timeout)
    except requests.RequestException as e:
        return False, f"Devin 登录请求失败: {e}", ""

    if r.status_code != 200:
        text = r.text[:300]
        lower = text.lower()
        if "invalid" in lower and ("password" in lower or "credentials" in lower):
            return False, "邮箱或密码错误", ""
        if "not found" in lower or "no such" in lower:
            return False, "该邮箱未注册 Windsurf 账号", ""
        if "disabled" in lower or "suspended" in lower:
            return False, "账号已被禁用", ""
        if "too many" in lower or "rate" in lower or r.status_code == 429:
            return False, "登录尝试过于频繁，请稍后再试", ""
        return False, f"Windsurf 登录失败 (HTTP {r.status_code}): {text}", ""

    try:
        data = r.json()
    except ValueError:
        return False, "Windsurf 登录返回非 JSON", ""

    auth1_token = data.get("token") or data.get("auth1_token") or ""
    if not auth1_token:
        return False, f"Windsurf 登录响应缺 token: {r.text[:200]}", ""
    return True, "", auth1_token


def _windsurf_post_auth(auth1_token: str,
                        timeout: float = 20.0) -> Tuple[bool, str, Optional[_PostAuthResult]]:
    """Step 2: auth1_token → session_token + extras.

    WindsurfPostAuth 响应字段:
      field 1: session_token (string)
      field 3: auth1_token (string, optional — updated)
      field 4: account_id  (string, optional)
      field 5: primary_org_id (string, optional)
    """
    body = _encode_proto_string(1, auth1_token)
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/proto",
        "connect-protocol-version": "1",
        "User-Agent": _UA,
        "Origin": "https://windsurf.com",
        "Referer": "https://windsurf.com/account/login",
        "X-Devin-Auth1-Token": auth1_token,
    }
    try:
        r = requests.post(_WINDSURF_POST_AUTH_URL, data=body, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return False, f"WindsurfPostAuth 请求失败: {e}", None

    if r.status_code != 200:
        return False, f"WindsurfPostAuth HTTP {r.status_code}: {r.text[:200]}", None

    fields = _decode_proto_strings(r.content)
    session_token = fields.get(1, "")
    if not isinstance(session_token, str) or not session_token:
        return False, (
            f"WindsurfPostAuth 响应未包含 session_token (fields={list(fields.keys())})"
        ), None

    result = _PostAuthResult(
        session_token=session_token,
        auth1_token=fields.get(3) if isinstance(fields.get(3), str) else None,
        account_id=fields.get(4) if isinstance(fields.get(4), str) else None,
        primary_org_id=fields.get(5) if isinstance(fields.get(5), str) else None,
    )
    return True, "", result


def _get_one_time_auth_token(
    devin_session_token: str,
    auth1_token: Optional[str] = None,
    account_id: Optional[str] = None,
    primary_org_id: Optional[str] = None,
    timeout: float = 20.0,
) -> Tuple[bool, str, str]:
    """Step 3: GetOneTimeAuthToken → one-time token for windsurf:// callback.

    For Devin accounts, headers:
      x-auth-token            = devin-session-token$JWT
      x-devin-session-token   = devin-session-token$JWT
      x-devin-auth1-token     = auth1_token  (if available)
      x-devin-account-id      = account_id   (if available)
      x-devin-primary-org-id  = primary_org_id (if available)
    """
    body = _encode_proto_string(1, devin_session_token)
    headers = {
        "Content-Type": "application/proto",
        "Accept": "*/*",
        "connect-protocol-version": "1",
        "User-Agent": _UA,
        "Referer": "https://windsurf.com/",
        "x-auth-token": devin_session_token,
        "x-devin-session-token": devin_session_token,
    }
    if auth1_token:
        headers["x-devin-auth1-token"] = auth1_token
    if account_id:
        headers["x-devin-account-id"] = account_id
    if primary_org_id:
        headers["x-devin-primary-org-id"] = primary_org_id

    try:
        r = requests.post(_ONE_TIME_AUTH_URL, data=body, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return False, f"GetOneTimeAuthToken 请求失败: {e}", ""

    if r.status_code != 200:
        return False, f"GetOneTimeAuthToken HTTP {r.status_code}: {r.text[:200]}", ""

    fields = _decode_proto_strings(r.content)
    one_time_token = fields.get(1, "")
    if not isinstance(one_time_token, str) or not one_time_token:
        return False, "GetOneTimeAuthToken 响应未包含 auth_token", ""
    return True, "", one_time_token


def _firebase_refresh_token(refresh_token: str,
                             timeout: float = 20.0) -> Tuple[bool, str, dict]:
    """备用路径: Firebase refresh_token → id_token (不触发 App Check)."""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": _UA,
        "Origin": "https://windsurf.com",
        "Referer": "https://windsurf.com/",
    }
    body = f"grant_type=refresh_token&refresh_token={requests.utils.quote(refresh_token)}"
    try:
        r = requests.post(_FIREBASE_REFRESH_URL, data=body, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return False, f"Firebase token 刷新失败: {e}", {}
    if r.status_code != 200:
        return False, f"Firebase token 刷新失败 (HTTP {r.status_code}): {r.text[:200]}", {}
    try:
        data = r.json()
    except ValueError:
        return False, "Firebase token 刷新返回非 JSON", {}
    id_token = data.get("id_token")
    if not id_token:
        return False, "Firebase token 刷新响应缺 id_token", {}
    return True, "", data


def _register_user(token: str, timeout: float = 20.0) -> Tuple[bool, str, dict]:
    """备用路径: RegisterUser → api_key (用于直接写 state.vscdb 的回退路径)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _UA,
        "Referer": "https://windsurf.com/",
        "connect-protocol-version": "1",
    }
    body = {"firebase_id_token": token}
    try:
        r = requests.post(_REGISTER_USER_URL, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return False, f"RegisterUser 请求失败: {e}", {}
    if r.status_code != 200:
        return False, f"RegisterUser HTTP {r.status_code}: {r.text[:200]}", {}
    try:
        data = r.json()
    except ValueError:
        return False, "RegisterUser 返回非 JSON", {}
    api_key = data.get("api_key") or data.get("apiKey") or ""
    if not api_key:
        return False, f"RegisterUser 响应缺 api_key: {str(data)[:200]}", data
    return True, "", data


# ──────────────────────────────────────────────────────── 无感切号补丁

def _check_patch_applied() -> bool:
    """检查 extension.js 是否已应用无感切号补丁."""
    ext_path = _extension_js_path()
    if not os.path.exists(ext_path):
        return False
    try:
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False
    p1 = bool(re.search(_PATTERN_URI_HANDLER, content))
    p2 = bool(re.search(_PATTERN_TIMEOUT, content))
    p3 = bool(re.search(_PATTERN_DIFF_ACCOUNT, content))
    return not p1 and not p2 and not p3


def _apply_seamless_patch() -> Tuple[bool, str, bool]:
    """修改 extension.js 实现无感切号.

    返回 (success, message, newly_applied).
    newly_applied=True 表示本次刚刚写入，需要重启 Windsurf 使补丁生效.
    newly_applied=False 表示补丁早已存在，Windsurf 无需重启.
    """
    ext_path = _extension_js_path()
    if not os.path.exists(ext_path):
        return False, f"extension.js 不存在: {ext_path}", False

    try:
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"读取 extension.js 失败: {e}", False

    p1 = re.search(_PATTERN_URI_HANDLER, content)
    p2 = re.search(_PATTERN_TIMEOUT, content)
    p3 = re.search(_PATTERN_DIFF_ACCOUNT, content)

    if not p1 and not p2 and not p3:
        return True, "无感切号补丁已安装", False

    modified = content

    # Patch 1: 重写 URI handler，使其始终处理 windsurf:// 回调
    if p1:
        v1, v2, mod = p1.group(1), p1.group(2), p1.group(3)
        if v1 == v2:
            # Build replacement using string concatenation to avoid f-string brace escaping issues
            replacement = (
                'this._uriHandler.event(async ' + v1 + '=>{'
                'if("/refresh-authentication-session"===' + v1 + '.path){'
                '(0,' + mod + '.refreshAuthenticationSession)()'
                '}else{try{const t=new URLSearchParams(' + v1 + '.fragment)'
                '.get("access_token");'
                'if(!t)throw new Error("No access_token in URI fragment");'
                'await this.handleAuthToken(t)}'
                'catch(e){console.error("[Windsurf] Failed to handle OAuth callback:",e)}'
                '}})'
            )
            modified = modified[:p1.start()] + replacement + modified[p1.end():]

    # Patch 2: 移除 180 秒超时
    p2 = re.search(_PATTERN_TIMEOUT, modified)
    if p2:
        r1, r2 = p2.group(2), p2.group(3)
        if r1 == r2:
            modified = modified[:p2.start()] + modified[p2.end():]

    # Patch 3: 跳过切号确认弹窗
    p3 = re.search(_PATTERN_DIFF_ACCOUNT, modified)
    if p3:
        modified = modified[:p3.start()] + "if(true)" + modified[p3.end():]

    if modified == content:
        return True, "无感切号补丁已安装（无匹配变体，跳过）", False

    # 备份 (轮转, 最多保留 3 份)
    ext_dir = os.path.dirname(ext_path)
    backups = sorted([
        f for f in os.listdir(ext_dir)
        if f.startswith("extension.js.backup.")
    ])
    while len(backups) >= 3:
        try:
            os.remove(os.path.join(ext_dir, backups.pop(0)))
        except Exception:
            break

    backup_path = ext_path + f".backup.{time.strftime('%Y%m%d_%H%M%S')}"
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    try:
        with open(ext_path, "w", encoding="utf-8") as f:
            f.write(modified)
    except PermissionError:
        # extension.js is often read-only; try chmod u+w first
        try:
            import stat
            os.chmod(ext_path, os.stat(ext_path).st_mode | stat.S_IWUSR)
            with open(ext_path, "w", encoding="utf-8") as f:
                f.write(modified)
        except Exception as e2:
            return False, f"写入 extension.js 失败 (权限不足): {e2}", False
    except Exception as e:
        return False, f"写入 extension.js 失败: {e}", False

    return True, "无感切号补丁已成功安装", True


# ──────────────────────────────────────────────────────── Windsurf 进程

def _is_windsurf_running() -> bool:
    try:
        import psutil
        names = {"windsurf.exe", "windsurf"}
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() in names:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def _kill_windsurf():
    """强制结束 Windsurf 进程."""
    try:
        import psutil
        names = {"windsurf.exe", "windsurf"}
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() in names:
                    p.terminate()
            except Exception:
                pass
        time.sleep(1.5)
    except Exception:
        pass


# ──────────────────────────────────────────────────────── URL 回调触发

def _trigger_windsurf_callback(one_time_token: str) -> None:
    """打开 windsurf:// URL, 触发 Windsurf 内部登录流程."""
    state = str(uuid.uuid4())
    params = (
        f"access_token={requests.utils.quote(one_time_token)}"
        f"&state={state}"
        f"&token_type=Bearer"
    )
    url = f"windsurf://codeium.windsurf#{params}"
    print(f"[WindsurfAuth] 触发 URL callback: windsurf://codeium.windsurf#access_token=***")
    if sys.platform == "darwin":
        subprocess.Popen(["open", url])
    elif sys.platform == "win32":
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{url}'"],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    else:
        subprocess.Popen(["xdg-open", url])


# ──────────────────────────────────────────────────────── state.vscdb 写入 (备用)

class _WindsurfStateWriter:
    """备用路径: 直接写 SQLite state.vscdb (仅当 URL callback 不可用时)."""

    _DB_PATH = _state_vscdb_path()

    def write(self, email: str, api_key: str, register_payload: dict) -> bool:
        os.makedirs(os.path.dirname(self._DB_PATH), exist_ok=True)
        conn = None
        try:
            conn = sqlite3.connect(self._DB_PATH, timeout=5)
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value BLOB)"
            )
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            name = register_payload.get("name") or email.split("@", 1)[0]
            api_server_url = (
                register_payload.get("api_server_url")
                or register_payload.get("apiServerUrl")
                or "https://server.self-serve.windsurf.com"
            )
            auth_status = {
                "apiKey": api_key,
                "userEmail": email,
                "name": name,
                "apiServerUrl": api_server_url,
                "loggedInAt": now_iso,
                "isLoggedIn": True,
            }
            auth_status_str = json.dumps(auth_status)

            existing_ws = self._read_value(cur, "windsurfAuthStatus")
            if existing_ws:
                try:
                    ws_data = json.loads(existing_ws)
                    ws_data["apiKey"] = api_key
                    if email:
                        ws_data["userEmail"] = email
                    ws_auth_str = json.dumps(ws_data)
                except Exception:
                    ws_auth_str = auth_status_str
            else:
                ws_auth_str = auth_status_str

            user_blob = {"name": name, "email": email, "isLoggedIn": True}
            self._upsert(cur, "windsurfAuthStatus", ws_auth_str)
            self._upsert(cur, "codeium.windsurfAuthStatus", auth_status_str)
            self._upsert(cur, "codeium.windsurfApiKey", api_key)
            self._upsert(cur, "codeium.windsurf", json.dumps(user_blob))
            self._upsert(cur, "codeium.windsurf-windsurf_auth", name)
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            print(f"[WindsurfAuth] state.vscdb 写入失败: {e}")
            return False
        except Exception as e:
            print(f"[WindsurfAuth] state.vscdb 写入异常: {e}")
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _read_value(cur, key: str):
        try:
            cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    @staticmethod
    def _upsert(cur, key: str, value: str) -> None:
        cur.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ──────────────────────────────────────────────────────── 机器码重置

class _WindsurfMachineResetter:
    _STORAGE = _storage_json_path()
    _MACHINE = _machine_id_file_path()

    @staticmethod
    def _generate_ids() -> dict:
        return {
            "telemetry.devDeviceId":    str(uuid.uuid4()),
            "telemetry.macMachineId":   hashlib.sha512(os.urandom(64)).hexdigest(),
            "telemetry.machineId":      hashlib.sha256(os.urandom(32)).hexdigest(),
            "telemetry.sqmId":          "{" + str(uuid.uuid4()).upper() + "}",
            "storage.serviceMachineId": str(uuid.uuid4()),
        }

    def reset(self) -> bool:
        try:
            new_ids = self._generate_ids()
            os.makedirs(os.path.dirname(self._STORAGE), exist_ok=True)
            try:
                with open(self._MACHINE, "w", encoding="utf-8") as f:
                    f.write(str(uuid.uuid4()))
            except OSError as e:
                print(f"[WindsurfReset] machineid 写入失败: {e}")
            if os.path.exists(self._STORAGE):
                try:
                    with open(self._STORAGE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            else:
                data = {}
            data.update(new_ids)
            with open(self._STORAGE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"[WindsurfReset] 失败: {e}")
            return False


# ──────────────────────────────────────────────────────── 入口

class WindsurfLoginResult:
    def __init__(self, success: bool, message: str = "",
                 email: str = "", api_key: str = "",
                 reset_ok: bool = False, db_ok: bool = False,
                 raw: Optional[dict] = None,
                 seamless: bool = False):
        self.success = success
        self.message = message
        self.email = email
        self.api_key = api_key
        self.reset_ok = reset_ok
        self.db_ok = db_ok
        self.raw = raw or {}
        self.refresh_token: str = ""
        self.seamless = seamless


def login_and_apply(
    email: str,
    password: str,
    reset_machine: bool = True,
    refresh_token: Optional[str] = None,
    on_progress: Optional[Callable[[str, str, bool], None]] = None,
) -> WindsurfLoginResult:
    """完整登录链路 (无感切号).

    on_progress(step, label, ok) 在每个阶段被调用, 可用于 UI 进度更新.
    step 取值: prepare / auth1_token / session_token / one_time_token /
              patch / machine_id / callback / done
    """
    def _prog(step: str, label: str = "", ok: bool = True):
        print(f"[WindsurfAuth] [{step}] {label}")
        if on_progress:
            try:
                on_progress(step, label, ok)
            except Exception:
                pass

    if not email:
        return WindsurfLoginResult(False, "邮箱为空")

    _prog("prepare", f"准备账号信息: {email}")

    # ── Step 1: Devin 登录 (email+password → auth1_token)
    if not password:
        return WindsurfLoginResult(False, "密码为空", email=email)

    _prog("auth1_token", "获取 auth1_token...")
    ok, err, auth1_token = _devin_password_login(email, password)
    if not ok:
        return WindsurfLoginResult(False, err, email=email)

    # ── Step 2: WindsurfPostAuth → session_token + extras
    _prog("session_token", "获取 session_token...")
    ok, err, post_result = _windsurf_post_auth(auth1_token)
    if not ok:
        # 如果有 refresh_token，回退到 Firebase 路径 (写 db 方式)
        if refresh_token:
            _prog("session_token", "Devin auth 失败，尝试 Firebase refresh_token...", False)
            return _fallback_firebase_login(email, refresh_token, reset_machine, _prog)
        return WindsurfLoginResult(False, err, email=email)

    devin_session_token = f"devin-session-token${post_result.session_token}"
    effective_auth1 = post_result.auth1_token or auth1_token

    # ── Step 3: GetOneTimeAuthToken
    _prog("one_time_token", "获取 one-time auth_token...")
    ok, err, one_time_token = _get_one_time_auth_token(
        devin_session_token,
        auth1_token=effective_auth1,
        account_id=post_result.account_id,
        primary_org_id=post_result.primary_org_id,
    )
    if not ok:
        print(f"[WindsurfAuth] GetOneTimeAuthToken 失败: {err}，回退到写 DB 路径")
        _prog("one_time_token", f"获取 one-time token 失败，回退写入模式", False)
        return _fallback_db_write(email, devin_session_token, reset_machine, _prog)

    # ── Step 4: 尝试应用无感切号补丁 (best-effort, 仅需 patch 3 — 跳过确认弹窗)
    # 注: 当前版本 Windsurf 的 extension.js 已自带 URI handler (handleAuthToken 路径),
    # 无需 patch 1/2; 只有 patch 3 (跳过 "Are you sure?" 弹窗) 仍需应用。
    _prog("patch", "检查无感切号补丁...")
    patch_already_installed = _check_patch_applied()
    if not patch_already_installed:
        patch_ok, patch_msg, patch_newly_applied = _apply_seamless_patch()
        print(f"[WindsurfAuth] 补丁: {patch_msg}")
        patch_active = patch_ok and not patch_newly_applied  # 已写入且本轮生效
    else:
        patch_newly_applied = False
        patch_active = True
        print("[WindsurfAuth] 无感切号补丁已安装")

    # ── Step 5: 重置机器码
    reset_ok = False
    if reset_machine:
        _prog("machine_id", "重置机器 ID...")
        reset_ok = _WindsurfMachineResetter().reset()

    # ── Step 6: 触发客户端登录
    _prog("callback", "触发 Windsurf 客户端登录...")
    ws_running = _is_windsurf_running()

    # 策略 (参考 windsurf-account-manager-simple switch_account_commands.rs):
    #
    #  A) Windsurf 正在运行 + 补丁已生效
    #     → 直接打开 windsurf:// URL —— 完全无感切号, 无需重启
    #
    #  B) Windsurf 正在运行 + 补丁未生效 (如 macOS 文件不可写)
    #     → 直接打开 URL —— 当前版本 Windsurf 已内置 maybeHandleUriWithToken,
    #       会弹出 "Are you sure you want to log in using a different account?" 确认框,
    #       用户点 Yes 即可完成登录; 同样无需关闭 Windsurf
    #
    #  C) Windsurf 未运行
    #     → 打开 URL, 由 OS 启动 Windsurf 并在启动后处理 URI 回调
    #
    # 只有补丁刚刚被写入 (patch_newly_applied=True) 时才需要重启, 让新 extension.js 生效
    if patch_newly_applied and ws_running:
        print("[WindsurfAuth] 补丁首次安装，关闭 Windsurf 使其加载新补丁")
        _kill_windsurf()
        ws_running = False

    _trigger_windsurf_callback(one_time_token)

    _prog("done", "完成")

    seamless = patch_active and ws_running  # 真正无感 (已有补丁 + Windsurf 在跑)
    if seamless:
        msg = "已完成无感切号，Windsurf 无需重启"
    elif ws_running:
        msg = "已向 Windsurf 发送登录请求，请在 Windsurf 弹窗中点击「Yes」确认"
    else:
        msg = "Windsurf 正在启动并处理登录请求"
    if reset_ok:
        msg += "，机器码已重置"

    return WindsurfLoginResult(
        success=True,
        message=msg,
        email=email,
        reset_ok=reset_ok,
        db_ok=True,
        seamless=seamless,
    )


def _fallback_db_write(email: str, devin_session_token: str,
                        reset_machine: bool,
                        prog: Callable) -> WindsurfLoginResult:
    """回退: 直接向 state.vscdb 写入 devin-session-token, 并重启 Windsurf."""
    prog("callback", "回退：写入 state.vscdb...")
    prog("machine_id", "重置机器 ID...")
    reset_ok = _WindsurfMachineResetter().reset() if reset_machine else False

    _kill_windsurf()
    db_ok = _WindsurfStateWriter().write(email, devin_session_token, {
        "api_key": devin_session_token,
        "apiServerUrl": "https://server.self-serve.windsurf.com",
    })
    prog("done", "")
    return WindsurfLoginResult(
        success=db_ok,
        message="已写入登录信息，请手动启动 Windsurf" if db_ok else "写入失败",
        email=email,
        reset_ok=reset_ok,
        db_ok=db_ok,
    )


def _fallback_firebase_login(email: str, refresh_token: str,
                              reset_machine: bool,
                              prog: Callable) -> WindsurfLoginResult:
    """Firebase refresh_token → id_token → RegisterUser → 写 state.vscdb."""
    prog("session_token", "Firebase refresh_token 刷新...")
    ok, err, fb = _firebase_refresh_token(refresh_token)
    if not ok:
        return WindsurfLoginResult(False, err, email=email)

    prog("one_time_token", "注册获取 API Key...")
    ok, err, reg = _register_user(fb.get("id_token", ""))
    if not ok:
        return WindsurfLoginResult(False, f"获取 API Key 失败: {err}", email=email)

    api_key = reg.get("api_key") or reg.get("apiKey") or ""
    prog("machine_id", "重置机器 ID...")
    reset_ok = _WindsurfMachineResetter().reset() if reset_machine else False
    _kill_windsurf()
    db_ok = _WindsurfStateWriter().write(email, api_key, reg)
    prog("done", "")
    return WindsurfLoginResult(
        success=db_ok,
        message="登录成功（Firebase 路径）" if db_ok else "写入失败",
        email=email,
        api_key=api_key,
        reset_ok=reset_ok,
        db_ok=db_ok,
    )


def reset_machine_only() -> bool:
    return _WindsurfMachineResetter().reset()


def windsurf_data_dir_exists() -> bool:
    try:
        return os.path.isdir(_windsurf_data_root())
    except Exception:
        return False
