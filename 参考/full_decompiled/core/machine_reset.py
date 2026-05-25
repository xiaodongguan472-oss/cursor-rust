"""重置 Cursor 机器标识 — 复用登录助手(totally_reset_cursor1.py)逻辑"""

import json
import os
import sys
import time
import uuid
import hashlib
import sqlite3


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


def _storage_json_path() -> str:
    return os.path.join(
        _cursor_data_root(), "User", "globalStorage", "storage.json"
    )


def _machine_id_file_path() -> str:
    return os.path.join(_cursor_data_root(), "machineId")


def _vscdb_path() -> str:
    return os.path.join(
        _cursor_data_root(), "User", "globalStorage", "state.vscdb"
    )


class MachineIDResetter:
    """复用登录助手 totally_reset_cursor1.py 的 MachineIDResetter"""

    def __init__(self):
        self.storage_path = _storage_json_path()
        self._machine_id_path = _machine_id_file_path()
        self._sqlite_path = _vscdb_path()

    @staticmethod
    def _generate_ids() -> dict:
        return {
            "telemetry.devDeviceId": str(uuid.uuid4()),
            "telemetry.macMachineId": hashlib.sha512(os.urandom(64)).hexdigest(),
            "telemetry.machineId": hashlib.sha256(os.urandom(32)).hexdigest(),
            "telemetry.sqmId": "{" + str(uuid.uuid4()).upper() + "}",
            "storage.serviceMachineId": str(uuid.uuid4()),
        }

    def _update_sqlite_db(self, new_ids: dict) -> bool:
        """将 telemetry ID 同步写入 state.vscdb（与登录助手 totally_reset 一致）"""
        if not os.path.exists(self._sqlite_path):
            return True
        conn = None
        # Windows 上 SQLite 释放句柄可能滞后，最多重试 5 次
        for attempt in range(5):
            try:
                conn = sqlite3.connect(self._sqlite_path, timeout=10)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=8000")
                cursor = conn.cursor()
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS itemTable (key TEXT PRIMARY KEY, value TEXT)"
                )
                for key, value in new_ids.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO itemTable VALUES (?, ?)", (key, value)
                    )
                conn.commit()
                print("SQLite数据库更新成功")
                return True
            except sqlite3.OperationalError as e:
                print(f"SQLite操作错误 (尝试 {attempt + 1}/5): {e}")
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                if attempt < 4:
                    time.sleep(1.0)
            except Exception as e:
                print(f"SQLite数据库更新失败: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
        print("SQLite数据库更新最终失败")
        return False

    @staticmethod
    def _write_with_retry(path: str, writer, retries: int = 6, delay: float = 1.0):
        """对文件写操作加重试，缓解 Windows 进程退出后文件句柄短暂未释放的问题。
        默认 6 次重试、每次 1s，总等待最长 6 秒，覆盖大多数 Windows 慢释放场景。"""
        last_exc = None
        for attempt in range(retries):
            try:
                writer(path)
                return True
            except (PermissionError, OSError) as e:
                last_exc = e
                print(f"写入失败 (尝试 {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
        print(f"写入最终失败: {last_exc}")
        return False

    def reset(self) -> bool:
        """重置机器标识：machineId 文件 + storage.json + state.vscdb"""
        try:
            new_ids = self._generate_ids()

            # 1. machineId 文件（确保目录存在，带重试）
            def _write_machine_id(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(str(uuid.uuid4()))

            if not self._write_with_retry(self._machine_id_path, _write_machine_id):
                print("machineId 文件写入失败")
                return False
            print("machineId 文件已更新")

            # 2. storage.json（带重试）
            def _write_storage_json(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data.update(new_ids)
                else:
                    data = dict(new_ids)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)

            if not self._write_with_retry(self.storage_path, _write_storage_json):
                print("storage.json 写入失败，继续尝试其余步骤")
            else:
                print("storage.json 已更新")

            # 3. state.vscdb
            self._update_sqlite_db(new_ids)

            print("机器标识重置成功")
            return True
        except Exception as e:
            print(f"重置机器标识失败: {e}")
            return False

    def file_exists(self) -> bool:
        root = _cursor_data_root()
        return os.path.exists(self.storage_path) or os.path.isdir(root)
