"""Cursor 认证信息管理 — 复用登录助手(CursorAuthManager.py)逻辑"""

import sqlite3
import os
import sys


def _vscdb_path() -> str:
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise EnvironmentError("APPDATA 环境变量未设置")
        return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")
    elif sys.platform == "darwin":
        return os.path.abspath(os.path.expanduser(
            "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
        ))
    elif sys.platform.startswith("linux"):
        return os.path.abspath(os.path.expanduser(
            "~/.config/Cursor/User/globalStorage/state.vscdb"
        ))
    raise NotImplementedError(f"不支持的操作系统: {sys.platform}")


class CursorAuthManager:
    def __init__(self):
        self.db_path = _vscdb_path()

    def _read_key(self, key: str):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT value FROM itemTable WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

    def get_token(self) -> str:
        return self._read_key("cursorAuth/accessToken") or ""

    def get_email(self) -> str:
        return self._read_key("cursorAuth/cachedEmail") or ""

    def update_auth(self, email=None, access_token=None, refresh_token=None) -> bool:
        """复用登录助手 CursorAuthManager.update_auth 逻辑"""
        updates = []
        updates.append(("cursorAuth/cachedSignUpType", "Auth_0"))

        if email is not None:
            updates.append(("cursorAuth/cachedEmail", email))
        if access_token is not None:
            updates.append(("cursorAuth/accessToken", access_token))
        if refresh_token is not None:
            updates.append(("cursorAuth/refreshToken", refresh_token))

        if not updates:
            print("没有提供任何要更新的值")
            return False

        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()

            for key, value in updates:
                check_query = "SELECT COUNT(*) FROM itemTable WHERE key = ?"
                cursor.execute(check_query, (key,))
                if cursor.fetchone()[0] == 0:
                    insert_query = "INSERT INTO itemTable (key, value) VALUES (?, ?)"
                    cursor.execute(insert_query, (key, value))
                else:
                    update_query = "UPDATE itemTable SET value = ? WHERE key = ?"
                    cursor.execute(update_query, (value, key))

                if cursor.rowcount > 0:
                    print(f"成功更新 {key.split('/')[-1]}")
                else:
                    print(f"未找到 {key.split('/')[-1]} 或值未变化")

            conn.commit()
            return True

        except sqlite3.Error as e:
            print("数据库错误:", str(e))
            return False
        except Exception as e:
            print("发生错误:", str(e))
            return False
        finally:
            if conn:
                conn.close()

    def db_exists(self) -> bool:
        return os.path.exists(self.db_path)
