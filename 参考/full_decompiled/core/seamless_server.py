"""本地 Token HTTP 服务 — 供 Cursor 注入 JS 轮询获取最新凭证 + 自动换号"""
from __future__ import annotations

import json
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

_PORT = 14520
_HOST = "127.0.0.1"

_api_client = None
_auto_switch_lock = threading.Lock()
_last_auto_switch: float = 0.0
_AUTO_SWITCH_COOLDOWN = 10  # 秒
_on_switch_callback = None
_seamless_disabled_for_platform = False


def set_api_client(client):
    """绑定 API 客户端，供自动换号使用"""
    global _api_client
    _api_client = client


def set_on_switch_callback(callback):
    """注册自动换号成功后的回调，callback(email: str)"""
    global _on_switch_callback
    _on_switch_callback = callback


def set_seamless_disabled(disabled: bool):
    global _seamless_disabled_for_platform
    _seamless_disabled_for_platform = disabled


def _state_file_path() -> str:
    home = os.path.expanduser("~")
    d = os.path.join(home, ".wuxian-assistant")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "seamless_state.json")


STATE_FILE = _state_file_path()


def read_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "config": {"enabled": False},
            "accessToken": "",
            "refreshToken": "",
            "email": "",
            "is_new": False,
            "machineIds": {},
        }


def write_state(state: dict):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def _handle_auto_switch() -> dict:
    """处理自动换号请求，返回 JSON 响应体"""
    global _last_auto_switch

    if _seamless_disabled_for_platform:
        return {"success": False, "message": "当前系统已关闭无感换号功能"}

    if _api_client is None:
        return {"success": False, "message": "客户端未就绪，请稍后重试"}

    now = time.time()
    if not _auto_switch_lock.acquire(blocking=False):
        return {"success": False, "message": "换号进行中，请稍候"}

    try:
        if now - _last_auto_switch < _AUTO_SWITCH_COOLDOWN:
            remaining = int(_AUTO_SWITCH_COOLDOWN - (now - _last_auto_switch))
            return {"success": False, "message": f"冷却中，{remaining}秒后可再次切换"}

        try:
            device_r = _api_client.init_device()
            if device_r.get("success"):
                d = device_r.get("data") or {}
                if d.get("banned"):
                    _last_auto_switch = time.time() + 50
                    return {"success": False, "expired": True,
                            "message": "设备已被封禁，请联系客服处理"}
                if not d.get("activated"):
                    _last_auto_switch = time.time() + 50
                    return {"success": False, "expired": True,
                            "message": "激活码已到期，请联系客服续费"}
        except Exception:
            pass

        try:
            quota_r = _api_client.refresh_count()
            if quota_r.get("success"):
                qd = quota_r.get("data") or {}
                if not qd.get("unlimited"):
                    remain = int(qd.get("over_count", 0))
                    if remain <= 0:
                        _last_auto_switch = time.time() + 120
                        return {"success": False, "expired": True,
                                "message": "换号额度已用完，请联系客服充值"}
        except Exception:
            pass

        r = _api_client.get_credentials()
        if not r.get("success"):
            return {"success": False, "message": r.get("message", "服务器未返回有效数据")}

        data = r.get("data") or {}
        email = data.get("email", "")
        token = data.get("token", "")

        if not email or not token:
            return {"success": False, "message": data.get("message", "当前暂无可分配账号")}

        from core.seamless_switch import seamless_switch
        if not seamless_switch(email, token):
            return {"success": False, "message": "写入状态失败"}

        _last_auto_switch = time.time()
        print(f"[SeamlessServer] Auto-switched to: {email}")

        if _on_switch_callback:
            try:
                _on_switch_callback(email)
            except Exception as e:
                print(f"[SeamlessServer] Callback error: {e}")

        return {"success": True, "email": email, "message": "自动换号成功"}

    except Exception as e:
        print(f"[SeamlessServer] Auto-switch error: {e}")
        return {"success": False, "message": f"换号异常: {e}"}
    finally:
        _auto_switch_lock.release()


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/api/get-token":
            data = read_state()
            self._json_response(200, data)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/auto-switch":
            result = _handle_auto_switch()
            self._json_response(200, result)
        elif self.path == "/api/ack-new":
            try:
                state = read_state()
                if state.get("is_new"):
                    state["is_new"] = False
                    write_state(state)
            except Exception:
                pass
            self._json_response(200, {"ok": True})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class SeamlessTokenServer:
    """可在 daemon 线程中运行的本地 Token 服务"""

    def __init__(self, host: str = _HOST, port: int = _PORT):
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return
        try:
            self._server = HTTPServer((self._host, self._port), _Handler)
        except OSError as e:
            print(f"[SeamlessServer] Failed to bind {self._host}:{self._port}: {e}")
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="SeamlessTokenServer",
        )
        self._thread.start()
        print(f"[SeamlessServer] Listening on {self._host}:{self._port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        print("[SeamlessServer] Stopped")


_global_server: SeamlessTokenServer | None = None


def start_server():
    global _global_server
    if _global_server is None:
        _global_server = SeamlessTokenServer()
    if not _global_server.is_running:
        _global_server.start()


def stop_server():
    global _global_server
    if _global_server:
        _global_server.stop()


def is_server_running() -> bool:
    return _global_server is not None and _global_server.is_running
