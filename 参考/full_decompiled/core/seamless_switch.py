"""无感换号核心逻辑 — 生成 machineIds + 写状态文件 + 更新磁盘"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
import threading


def _cursor_data_root() -> str:
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise EnvironmentError("APPDATA 环境变量未设置")
        return os.path.join(appdata, "Cursor")
    if sys.platform == "darwin":
        return os.path.abspath(
            os.path.expanduser("~/Library/Application Support/Cursor")
        )
    if sys.platform.startswith("linux"):
        return os.path.abspath(os.path.expanduser("~/.config/Cursor"))
    raise NotImplementedError(f"不支持的操作系统: {sys.platform}")


def generate_machine_ids() -> dict:
    """生成一组新的机器标识（与 machine_reset.py 一致的格式）"""
    return {
        "devDeviceId": str(uuid.uuid4()),
        "macMachineId": hashlib.sha512(os.urandom(64)).hexdigest(),
        "machineId": hashlib.sha256(os.urandom(32)).hexdigest(),
        "sqmId": "{" + str(uuid.uuid4()).upper() + "}",
    }


def _update_disk_files(machine_ids: dict):
    """后台更新磁盘上的 machineId 文件和 storage.json（不需要 Cursor 退出）"""
    try:
        root = _cursor_data_root()

        # machineId 文件
        mid_path = os.path.join(root, "machineId")
        try:
            os.makedirs(root, exist_ok=True)
            with open(mid_path, "w", encoding="utf-8") as f:
                f.write(machine_ids["machineId"])
        except OSError:
            pass

        # storage.json — 合并 telemetry 字段
        storage_path = os.path.join(root, "User", "globalStorage", "storage.json")
        if os.path.exists(storage_path):
            telemetry_map = {
                "telemetry.devDeviceId": machine_ids["devDeviceId"],
                "telemetry.macMachineId": machine_ids["macMachineId"],
                "telemetry.machineId": machine_ids["machineId"],
                "telemetry.sqmId": machine_ids["sqmId"],
                "storage.serviceMachineId": str(uuid.uuid4()),
            }
            try:
                with open(storage_path, "r+", encoding="utf-8") as f:
                    data = json.load(f)
                    data.update(telemetry_map)
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
            except (OSError, json.JSONDecodeError):
                pass

    except Exception as e:
        print(f"[SeamlessSwitch] Disk update error: {e}")


def seamless_switch(email: str, token: str, refresh_token: str | None = None) -> bool:
    """
    无感换号：写入 seamless_state.json 供注入 JS 轮询拾取，
    同时后台更新磁盘文件保持一致性。
    """
    from core.seamless_server import write_state

    machine_ids = generate_machine_ids()

    state = {
        "config": {"enabled": True},
        "accessToken": token,
        "refreshToken": refresh_token or token,
        "email": email,
        "is_new": True,
        "machineIds": machine_ids,
    }

    try:
        write_state(state)
    except Exception as e:
        print(f"[SeamlessSwitch] Failed to write state: {e}")
        return False

    # 磁盘文件更新放在后台线程，不阻塞主流程
    threading.Thread(
        target=_update_disk_files,
        args=(machine_ids,),
        daemon=True,
    ).start()

    print(f"[SeamlessSwitch] Token queued for: {email}")
    return True


def is_seamless_ready() -> bool:
    """检查无感换号是否就绪（注入已生效 + 本地服务运行中）"""
    try:
        from core.cursor_injector import CursorInjector
        from core.seamless_server import is_server_running

        injector = CursorInjector()
        return injector.is_injected() and is_server_running()
    except Exception:
        return False
