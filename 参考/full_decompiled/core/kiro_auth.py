"""Kiro 认证信息管理 — 写入 ~/.aws/sso/cache/ 以实现自动登录"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _sso_cache_dir() -> Path:
    if sys.platform == "win32":
        home = os.environ.get("USERPROFILE") or str(Path.home())
    else:
        home = os.environ.get("HOME") or str(Path.home())
    cache = Path(home) / ".aws" / "sso" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _expires_at(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class KiroAuthManager:
    def __init__(self):
        self._cache_dir = _sso_cache_dir()

    def cache_dir_exists(self) -> bool:
        return self._cache_dir.exists()

    def write_auth(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        client_id_hash: str,
        region: str = "us-east-1",
    ) -> bool:
        try:
            token_data = {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresAt": _expires_at(1),
                "authMethod": "IdC",
                "provider": "BuilderId",
                "clientIdHash": client_id_hash,
                "region": region,
            }
            _atomic_write(self._cache_dir / "kiro-auth-token.json", token_data)

            reg_data = {
                "clientId": client_id,
                "clientSecret": client_secret,
                "expiresAt": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            }
            _atomic_write(self._cache_dir / f"{client_id_hash}.json", reg_data)

            print("[KiroAuth] 认证文件已写入")
            return True
        except Exception as e:
            print(f"[KiroAuth] 写入失败: {e}")
            return False

    def get_current_email(self) -> str:
        """尝试从现有 token 文件中读取状态（仅作展示用）"""
        token_path = self._cache_dir / "kiro-auth-token.json"
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text(encoding="utf-8"))
                if data.get("accessToken"):
                    return "已有认证"
            except Exception:
                pass
        return ""
