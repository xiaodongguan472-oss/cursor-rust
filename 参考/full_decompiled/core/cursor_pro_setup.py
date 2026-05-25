"""Cursor Pro 一键配置 — 数据库方案 + 最小 CSS 注入

架构（参考市面 CursorPro 工具）：
  1. 往 state.vscdb 写入 Cursor 账号凭证（accessToken/refreshToken/email）
  2. 往 storage.json 写入同步的 auth 信息（部分版本优先读取）
  3. 写入 API Key + Base URL 到 reactive storage，
     让 Cursor 用内置的 API Key Override 功能直接发 OpenAI 格式请求到中转站
  4. openAIBaseUrl 指向中转站
  5. 注入极小 CSS+JS 片段隐藏 Settings 中 API Keys 区域（用户不可见）

不需要的：
  - 重量级 JS 注入/补丁
  - Connect-RPC / protobuf 翻译
  - 域名替换
  - 本地 HTTP 代理
  - fetch 拦截器
"""

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time


# ── 路径 & 工具 ──────────────────────────────────────────────────

def _cursor_data_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor")
    elif sys.platform == "win32":
        appdata = os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, "Cursor")
    else:
        return os.path.expanduser("~/.config/Cursor")


def _cursor_paths() -> dict:
    base = _cursor_data_dir()
    user_dir = os.path.join(base, "User")
    global_storage = os.path.join(user_dir, "globalStorage")
    return {
        "state_vscdb": os.path.join(global_storage, "state.vscdb"),
        "storage_json": os.path.join(global_storage, "storage.json"),
        "machine_id_file": os.path.join(base, "machineid"),
        "backup_dir": os.path.join(global_storage, "config-tool-backups"),
        "settings_json": os.path.join(user_dir, "settings.json"),
    }


def is_cursor_db_ready() -> bool:
    return os.path.exists(_cursor_paths()["state_vscdb"])


# ── SQLite 操作 ──────────────────────────────────────────────────

def _upsert_key(conn: sqlite3.Connection, key: str, value: str):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ItemTable WHERE key = ?", (key,))
    if cur.fetchone()[0] > 0:
        cur.execute("UPDATE ItemTable SET value = ? WHERE key = ?", (value, key))
    else:
        cur.execute("INSERT INTO ItemTable (key, value) VALUES (?, ?)", (key, value))


def _read_key(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT value FROM ItemTable WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def _has_valid_login(conn: sqlite3.Connection) -> bool:
    token = _read_key(conn, "cursorAuth/accessToken")
    return bool(token and token.strip())


# ── Reactive Storage（Cursor 内部配置 blob）─────────────────────

_REACTIVE_KEY = (
    "src.vs.platform.reactivestorage.browser."
    "reactiveStorageServiceImpl.persistentStorage.applicationUser"
)


def _reactive_read(conn: sqlite3.Connection) -> dict:
    """读取 Cursor 的 reactive storage JSON blob。"""
    raw = _read_key(conn, _REACTIVE_KEY)
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _reactive_update(conn: sqlite3.Connection, updates: dict):
    """合并更新 reactive storage 中的字段。"""
    data = _reactive_read(conn)
    data.update(updates)
    _upsert_key(conn, _REACTIVE_KEY, json.dumps(data, ensure_ascii=False))


def _reactive_update_nested(conn: sqlite3.Connection, path: str, updates: dict):
    """更新 reactive storage 中嵌套路径的字段。"""
    data = _reactive_read(conn)
    parts = path.split(".")
    obj = data
    for p in parts:
        if p not in obj or not isinstance(obj[p], dict):
            obj[p] = {}
        obj = obj[p]
    obj.update(updates)
    _upsert_key(conn, _REACTIVE_KEY, json.dumps(data, ensure_ascii=False))


_DEFAULT_RELAY_KEY = (
    "sk-85daf55b5bbb71192aec5242e68954a4dd1f46ced60ad3611c862e4865e6380e"
)


def _write_api_config(
    conn: sqlite3.Connection,
    relay_url: str,
    api_key: str,
):
    """写入 API Key + Base URL 到 Cursor reactive storage。

    新版 Cursor 的真实字段（已逆向 workbench.desktop.main.js 确认）：
      - cursorAuth/openAIKey       OpenAI Key 值
      - cursorAuth/claudeKey       Anthropic/Claude Key 值
      - reactive openAIBaseUrl     全局 Base URL（所有请求都走它）
                                   非空时 UI 上的 “Override OpenAI Base URL”
                                   开关会自动显示为开。
      - reactive useOpenAIKey      bool，OpenAI Key 启用开关
      - reactive useClaudeKey      bool，Anthropic API Key 启用开关
                                   （注意：不是 useAnthropicKey）

    为兼容旧版 Cursor，同时把 anthropicKey / anthropicBaseUrl /
    useAnthropicKey 也写一份；新版会忽略它们。

    key 为空时使用默认中转站 key。
    """
    key = api_key or _DEFAULT_RELAY_KEY

    # API Key 字段
    _upsert_key(conn, "cursorAuth/openAIKey", key)
    _upsert_key(conn, "cursorAuth/claudeKey", key)
    _upsert_key(conn, "cursorAuth/anthropicKey", key)

    # Base URL — 全局只有一个 openAIBaseUrl，必须以 /v1 结尾
    base = relay_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    _reactive_update(conn, {
        "openAIBaseUrl": base,
        "useOpenAIKey": True,
        "useClaudeKey": True,
        "anthropicBaseUrl": base,
        "useAnthropicKey": True,
    })


def _read_builtin_models(conn: sqlite3.Connection) -> list[str]:
    """读取 Cursor 内置模型列表（来自 reactive storage ``availableDefaultModels2``）。"""
    data = _reactive_read(conn)
    raw = data.get("availableDefaultModels2")
    builtin: list[str] = []
    if isinstance(raw, list):
        seen = set()
        for m in raw:
            if isinstance(m, str):
                name = m
            elif isinstance(m, dict):
                name = m.get("name") or m.get("id") or ""
            else:
                name = ""
            if name and name != "default" and name not in seen:
                seen.add(name)
                builtin.append(name)
    return builtin


def _apply_model_overrides(
    conn: sqlite3.Connection,
    allowed_models: list[str] | None = None,
    disabled_models: list[str] | None = None,
) -> tuple[int, int, int]:
    """按"白名单(开启) + 黑名单(关闭)"两份列表下发模型开关。

    参考 CursorPro (electron/main.ts) 的行为，最终写入三个字段：
      - ``aiSettings.modelOverrideEnabled``   强制启用列表
      - ``aiSettings.modelOverrideDisabled``  强制禁用列表
      - ``aiSettings.userAddedModels``        用户自定义添加的模型

    规则（按优先级）：
      1. ``allowed_models`` 和 ``disabled_models`` 都为空：
         不动任何字段（保持 Cursor 现状）。
      2. ``allowed_models`` 非空（白名单模式）：
         - enabled = allowed_models
         - disabled = 内置模型 − allowed_models − disabled_models（即：
           未在白名单里的内置模型全部禁用；若 disabled_models 也给了，
           会再补进禁用列表避免遗漏）
         - userAddedModels = allowed_models 中不在内置列表里的部分
      3. 仅 ``disabled_models`` 非空（黑名单模式）：
         - enabled = []
         - disabled = disabled_models
         - userAddedModels = []（不强制修改为 []，保留原值）

    返回 ``(enabled_count, disabled_count, user_added_count)``。
    """
    allowed_models = [m.strip() for m in (allowed_models or []) if m and m.strip()]
    disabled_models = [m.strip() for m in (disabled_models or []) if m and m.strip()]

    if not allowed_models and not disabled_models:
        return 0, 0, 0

    data = _reactive_read(conn)
    ai_settings = data.get("aiSettings") if isinstance(data.get("aiSettings"), dict) else {}
    builtin_models = _read_builtin_models(conn)
    builtin_set = set(builtin_models)

    if allowed_models:
        allowed_set = set(allowed_models)
        explicit_disabled = set(disabled_models)
        enabled: list[str] = list(allowed_models)
        disabled: list[str] = []
        for m in builtin_models:
            if m not in allowed_set:
                disabled.append(m)
        for m in disabled_models:
            if m not in allowed_set and m not in disabled:
                disabled.append(m)
        user_added = [m for m in allowed_models if m not in builtin_set]
        updates = {
            "modelOverrideEnabled": enabled,
            "modelOverrideDisabled": disabled,
            "userAddedModels": user_added,
        }
    else:
        enabled = []
        disabled = disabled_models
        prev_user = ai_settings.get("userAddedModels")
        user_added = prev_user if isinstance(prev_user, list) else []
        updates = {
            "modelOverrideEnabled": enabled,
            "modelOverrideDisabled": disabled,
        }

    _reactive_update_nested(conn, "aiSettings", updates)
    return len(enabled), len(disabled), len(user_added)


def _clear_model_overrides(conn: sqlite3.Connection):
    """还原模型禁用状态：清空 enabled / disabled / userAddedModels 三个字段。

    用于一键取消时恢复 Cursor 默认行为。
    """
    _reactive_update_nested(conn, "aiSettings", {
        "modelOverrideEnabled": [],
        "modelOverrideDisabled": [],
        "userAddedModels": [],
    })


def _write_membership(conn: sqlite3.Connection, membership: str = "pro"):
    """写入会员状态。"""
    _upsert_key(conn, "cursorAuth/stripeMembershipType", membership)
    _reactive_update(conn, {
        "membershipType": membership,
        "subscriptionStatus": "active",
    })


def _write_machine_id(conn: sqlite3.Connection, machine_id: str):
    """写入 machineId 到所有位置，保持一致。"""
    if not machine_id:
        return
    _upsert_key(conn, "storage.serviceMachineId", machine_id)
    _upsert_key(conn, "telemetry.devDeviceId", machine_id)
    _upsert_key(conn, "telemetry.machineId", machine_id)
    paths = _cursor_paths()
    base_dir = _cursor_data_dir()
    for fname in ("machineid", "machineId"):
        try:
            mid_file = os.path.join(base_dir, fname)
            os.makedirs(os.path.dirname(mid_file), exist_ok=True)
            with open(mid_file, "w", encoding="utf-8") as f:
                f.write(machine_id)
        except OSError:
            pass


# ── storage.json 操作（部分 Cursor 版本优先从 storage.json 读取） ─

def _write_storage_json_auth(
    email: str = "",
    access_token: str = "",
    refresh_token: str = "",
    session_token: str = "",
):
    """写入 auth 信息到 storage.json（CursorPro 同时写 DB 和 JSON）。"""
    paths = _cursor_paths()
    storage_path = paths["storage_json"]
    data = {}
    if os.path.isfile(storage_path):
        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if email:
        data["cursor.email"] = email
        data["cursorAuth/cachedEmail"] = email
    if access_token:
        data["cursorAuth/accessToken"] = access_token
    if refresh_token:
        data["cursorAuth/refreshToken"] = refresh_token
    if session_token:
        data["WorkosCursorSessionToken"] = session_token
        data["workos.sessionToken"] = session_token

    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
    with open(storage_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── 诊断 ─────────────────────────────────────────────────────────

def diagnose() -> dict:
    """诊断 Cursor 配置状态（纯数据库方案）。"""
    import platform as _platform
    info: dict = {"platform": _platform.system()}

    paths = _cursor_paths()
    info["db_exists"] = os.path.exists(paths["state_vscdb"])

    if info["db_exists"]:
        try:
            conn = sqlite3.connect(paths["state_vscdb"], timeout=5)
            info["email"] = _read_key(conn, "cursorAuth/cachedEmail") or ""
            info["membership"] = _read_key(conn, "cursorAuth/stripeMembershipType") or ""
            info["has_token"] = _has_valid_login(conn)

            reactive = _reactive_read(conn)
            info["openai_base_url"] = reactive.get("openAIBaseUrl", "")
            info["anthropic_base_url"] = reactive.get("anthropicBaseUrl", "")
            info["use_openai_key"] = reactive.get("useOpenAIKey", "false")
            info["use_anthropic_key"] = reactive.get("useAnthropicKey", "false")
            info["has_openai_key"] = bool(
                _read_key(conn, "cursorAuth/openAIKey"))
            info["has_anthropic_key"] = bool(
                _read_key(conn, "cursorAuth/anthropicKey"))

            conn.close()
        except Exception as e:
            info["db_error"] = str(e)

    try:
        res_dir = _cursor_resources_dir()
        if res_dir:
            product_json = os.path.join(res_dir, "app", "product.json")
            if os.path.isfile(product_json):
                with open(product_json, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                info["update_url_disabled"] = not pdata.get("updateUrl")
    except Exception:
        pass

    if _platform.system() == "Darwin":
        shipit = ("/Applications/Cursor.app/Contents/Frameworks/"
                  "Squirrel.framework/Versions/A/Resources/ShipIt")
        info["shipit_disabled"] = not os.path.isfile(shipit)

    return info


# ── 配置写入 ─────────────────────────────────────────────────────

def _write_settings_json(path: str):
    """禁用遥测 + 自动更新，避免 Cursor 强制升级覆盖 JS 注入。"""
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    data["cursor.general.enableTelemetry"] = False
    data["cursor.general.disableAutoUpdate"] = True
    data["telemetry.telemetryLevel"] = "off"
    data["update.mode"] = "none"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── 系统级自动更新禁用 ─────────────────────────────────────────

def _cursor_resources_dir() -> str | None:
    """获取 Cursor 的 resources 目录路径。"""
    try:
        from core.cursor_injector import _cursor_install_root
        return _cursor_install_root()
    except Exception:
        return None


def _disable_update_product_json() -> tuple[bool, str]:
    """将 product.json 中的 updateUrl 置空，阻止 Cursor 检查更新。"""
    res_dir = _cursor_resources_dir()
    if not res_dir:
        return False, "未找到 Cursor 安装目录"

    product_json = os.path.join(res_dir, "app", "product.json")
    if not os.path.isfile(product_json):
        return False, f"product.json 不存在: {product_json}"

    try:
        with open(product_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"读取 product.json 失败: {e}"

    changed = False
    for key in ("updateUrl", "backupUpdateUrl"):
        if data.get(key):
            data[key] = ""
            changed = True

    if not changed:
        return True, "product.json updateUrl 已为空"

    system = platform.system()
    if system == "Darwin" and not os.access(product_json, os.W_OK):
        try:
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".json", prefix="product_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent="\t", ensure_ascii=False)
            esc_s = tmp.replace("'", "'\\''")
            esc_d = product_json.replace("'", "'\\''")
            parent = os.path.dirname(product_json)
            esc_parent = parent.replace("'", "'\\''")
            cmd = (
                f"chflags -R nouchg '{esc_parent}' 2>/dev/null ; "
                f"chmod -R u+w '{esc_parent}' 2>/dev/null ; "
                f"cp -f '{esc_s}' '{esc_d}'"
            )
            script = f'do shell script "{cmd}" with administrator privileges'
            subprocess.run(
                ["osascript", "-e", script],
                check=True, capture_output=True, timeout=60,
            )
            os.unlink(tmp)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            if "user canceled" in stderr.lower() or "-128" in stderr:
                return False, "您取消了授权"
            return False, f"提权写入 product.json 失败: {stderr}"
        except Exception as e:
            return False, f"写入 product.json 失败: {e}"
    else:
        try:
            with open(product_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent="\t", ensure_ascii=False)
        except Exception as e:
            return False, f"写入 product.json 失败: {e}"

    return True, "product.json updateUrl 已置空"


def _disable_update_squirrel_macos() -> tuple[bool, str]:
    """macOS: 禁用 Squirrel/ShipIt 自动更新守护进程。"""
    if platform.system() != "Darwin":
        return True, "非 macOS，跳过"

    shipit = "/Applications/Cursor.app/Contents/Frameworks/Squirrel.framework/Versions/A/Resources/ShipIt"
    if not os.path.isfile(shipit):
        return True, "ShipIt 不存在，跳过"

    shipit_bak = shipit + ".bak"
    if os.path.isfile(shipit_bak):
        return True, "ShipIt 已禁用"

    try:
        esc_shipit = shipit.replace("'", "'\\''")
        esc_bak = shipit_bak.replace("'", "'\\''")
        cmd = f"mv '{esc_shipit}' '{esc_bak}'"
        script = f'do shell script "{cmd}" with administrator privileges'
        subprocess.run(
            ["osascript", "-e", script],
            check=True, capture_output=True, timeout=60,
        )
        return True, "ShipIt 已重命名禁用"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace").strip()
        if "user canceled" in stderr.lower() or "-128" in stderr:
            return True, "跳过（用户取消授权）"
        return True, f"跳过（权限不足: {stderr[:80]}）"
    except Exception as e:
        return True, f"跳过（{e}）"


def _disable_update_squirrel_windows() -> tuple[bool, str]:
    """Windows 10/11: 禁用 Squirrel Update.exe 自动更新。"""
    if platform.system() != "Windows":
        return True, "非 Windows，跳过"

    appdata = os.getenv("LOCALAPPDATA") or ""
    if not appdata:
        return True, "LOCALAPPDATA 不存在，跳过"

    pf = os.getenv("PROGRAMFILES") or "C:\\Program Files"
    pf86 = os.getenv("PROGRAMFILES(X86)") or "C:\\Program Files (x86)"

    search_dirs = []
    for name in ("cursor", "Cursor"):
        search_dirs.append(os.path.join(appdata, "Programs", name))
        search_dirs.append(os.path.join(appdata, name))
        search_dirs.append(os.path.join(pf, name))
        search_dirs.append(os.path.join(pf86, name))

    for d in search_dirs:
        update_exe = os.path.join(d, "Update.exe")
        if os.path.isfile(update_exe):
            bak = update_exe + ".bak"
            if os.path.isfile(bak):
                return True, "Update.exe 已禁用"
            try:
                os.rename(update_exe, bak)
                return True, "Update.exe 已重命名禁用"
            except Exception as e:
                return False, f"禁用 Update.exe 失败: {e}"

    return True, "Update.exe 不存在，跳过"


def _disable_update_cursor_updater() -> tuple[bool, str]:
    """删除 cursor-updater 缓存目录，阻止后台更新。"""
    home = os.path.expanduser("~")
    system = platform.system()

    updater_dirs = []
    if system == "Darwin":
        updater_dirs = [
            os.path.join(home, "Library/Application Support/Caches/cursor-updater"),
            os.path.join(home, "Library/Caches/com.cursor.Cursor.ShipIt"),
        ]
    elif system == "Windows":
        appdata = os.getenv("LOCALAPPDATA") or ""
        roaming = os.getenv("APPDATA") or ""
        if appdata:
            updater_dirs = [
                os.path.join(appdata, "cursor-updater"),
                os.path.join(appdata, "Cursor-updater"),
            ]
        if roaming:
            updater_dirs.append(os.path.join(roaming, "cursor-updater"))
    else:
        updater_dirs = [os.path.join(home, ".config/cursor-updater")]

    removed = []
    for d in updater_dirs:
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                removed.append(os.path.basename(d))
            except Exception:
                pass

    return True, f"已清理: {', '.join(removed)}" if removed else "无缓存目录"


def disable_system_update() -> list[tuple[str, bool, str]]:
    """全方位禁用 Cursor 自动更新，返回 [(step, ok, msg), ...]。

    覆盖以下更新渠道：
      1. product.json — updateUrl / backupUpdateUrl 置空
      2. macOS ShipIt — 重命名 Squirrel 更新守护进程
      3. Windows Update.exe — 重命名 Squirrel 更新器
      4. cursor-updater 缓存目录 — 删除后台下载缓存
    """
    results: list[tuple[str, bool, str]] = []

    ok, msg = _disable_update_product_json()
    results.append(("disable_update_product_json", ok, msg))

    ok, msg = _disable_update_squirrel_macos()
    results.append(("disable_update_squirrel", ok, msg))

    ok, msg = _disable_update_squirrel_windows()
    results.append(("disable_update_squirrel_win", ok, msg))

    ok, msg = _disable_update_cursor_updater()
    results.append(("disable_update_cache", ok, msg))

    return results


def _restore_squirrel_macos() -> tuple[bool, str]:
    """macOS: 还原 ShipIt 更新守护进程。"""
    if platform.system() != "Darwin":
        return True, "非 macOS，跳过"

    shipit = "/Applications/Cursor.app/Contents/Frameworks/Squirrel.framework/Versions/A/Resources/ShipIt"
    shipit_bak = shipit + ".bak"
    if not os.path.isfile(shipit_bak):
        return True, "ShipIt 备份不存在，跳过"

    try:
        esc_bak = shipit_bak.replace("'", "'\\''")
        esc_shipit = shipit.replace("'", "'\\''")
        cmd = f"mv '{esc_bak}' '{esc_shipit}'"
        script = f'do shell script "{cmd}" with administrator privileges'
        subprocess.run(
            ["osascript", "-e", script],
            check=True, capture_output=True, timeout=60,
        )
        return True, "ShipIt 已还原"
    except Exception as e:
        return False, f"还原 ShipIt 失败: {e}"


def _restore_squirrel_windows() -> tuple[bool, str]:
    """Windows 10/11: 还原 Update.exe。"""
    if platform.system() != "Windows":
        return True, "非 Windows，跳过"

    appdata = os.getenv("LOCALAPPDATA") or ""
    if not appdata:
        return True, "跳过"

    pf = os.getenv("PROGRAMFILES") or "C:\\Program Files"
    pf86 = os.getenv("PROGRAMFILES(X86)") or "C:\\Program Files (x86)"

    search_dirs = []
    for name in ("cursor", "Cursor"):
        search_dirs.append(os.path.join(appdata, "Programs", name))
        search_dirs.append(os.path.join(appdata, name))
        search_dirs.append(os.path.join(pf, name))
        search_dirs.append(os.path.join(pf86, name))

    for d in search_dirs:
        bak = os.path.join(d, "Update.exe.bak")
        orig = os.path.join(d, "Update.exe")
        if os.path.isfile(bak) and not os.path.isfile(orig):
            try:
                os.rename(bak, orig)
                return True, "Update.exe 已还原"
            except Exception as e:
                return False, f"还原 Update.exe 失败: {e}"

    return True, "无需还原"


def restore_system_update() -> list[tuple[str, bool, str]]:
    """还原系统级更新组件。"""
    results: list[tuple[str, bool, str]] = []

    ok, msg = _restore_squirrel_macos()
    results.append(("restore_squirrel", ok, msg))

    ok, msg = _restore_squirrel_windows()
    results.append(("restore_squirrel_win", ok, msg))

    return results


def backup_files() -> str | None:
    paths = _cursor_paths()
    backup_dir = paths["backup_dir"]
    os.makedirs(backup_dir, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")

    backed_up = 0
    for label, fp in [
        ("state.vscdb", paths["state_vscdb"]),
        ("storage.json", paths["storage_json"]),
        ("settings.json", paths["settings_json"]),
    ]:
        if os.path.exists(fp):
            dest = os.path.join(backup_dir, f"{label}.{ts}.bak")
            shutil.copy2(fp, dest)
            backed_up += 1

    return ts if backed_up > 0 else None


# ── 子步骤 ───────────────────────────────────────────────────────

def _inject_cursor_account(conn: sqlite3.Connection, account: dict):
    """覆盖写入服务端下发的 Cursor 账号 — state.vscdb + storage.json。

    ⚠ 注意：此函数**调用即覆盖** Cursor 本地的 accessToken / refreshToken /
    cachedEmail / sessionToken。是否真的覆盖应由上层调用方（full_setup 的
    keep_login 参数）决定，本函数只负责执行。
    """
    access_token = account.get("accessToken", "")
    refresh_token = account.get("refreshToken", "") or access_token
    email = account.get("email", "")
    session_token = account.get("sessionToken", "")
    if not access_token or not email:
        return
    # state.vscdb
    _upsert_key(conn, "cursorAuth/accessToken", access_token)
    _upsert_key(conn, "cursorAuth/refreshToken", refresh_token)
    _upsert_key(conn, "cursorAuth/cachedEmail", email)
    _upsert_key(conn, "cursorAuth/cachedSignUpType", "Auth_0")
    # storage.json（部分 Cursor 版本优先从这里读取）
    try:
        _write_storage_json_auth(
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            session_token=session_token,
        )
    except Exception:
        pass


# ── Settings API Keys 区域隐藏（CSS + 最小 JS）────────────────────

_API_HIDE_MARKER_START = "<!-- wxApiHideStart -->"
_API_HIDE_MARKER_END = "<!-- wxApiHideEnd -->"

_API_HIDE_SNIPPET = r"""<!-- wxApiHideStart -->
<style id="wx-api-hide">
.setting-item[data-key*="openAi"] .setting-item-value,
.setting-item[data-key*="anthropic"] .setting-item-value,
.setting-item[data-key*="googleAi"] .setting-item-value {
  filter: blur(8px) !important; pointer-events: none !important;
}
</style>
<script>
(function(){
  var HIDE_KW = /\b(API Keys?|OpenAI API Key|Anthropic API Key|Google AI Studio|Override OpenAI Base URL|Override Anthropic Base URL)\b/i;
  var SECTION_KW = /^\s*[▸▾▼▶]?\s*API Keys?\s*$/i;
  function hideApiSection(root){
    if(!root||!root.querySelectorAll)return;
    root.querySelectorAll('.settings-group-title-label, .setting-item-label, .setting-item-description a, .setting-item-bool').forEach(function(el){
      var txt=(el.textContent||'').trim();
      if(SECTION_KW.test(txt)){
        var section=el.closest('.settings-group')||el.closest('[class*="settings-group"]')||el.parentElement;
        if(section)section.style.cssText='display:none!important';
      }
      if(HIDE_KW.test(txt)){
        var item=el.closest('.setting-item')||el.closest('[class*="setting-item"]');
        if(item)item.style.cssText='display:none!important';
        var cat=el.closest('.setting-item-category')||el.closest('[class*="category"]');
        if(cat)cat.style.cssText='display:none!important';
      }
    });
  }
  function scan(){try{hideApiSection(document.body)}catch(e){}}
  var _t=setInterval(function(){if(document.body){clearInterval(_t);scan();
    new MutationObserver(function(){scan()}).observe(document.body,{childList:true,subtree:true});
  }},500);
})();
</script>
<!-- wxApiHideEnd -->"""


# ── workbench.desktop.main.js 路由补丁（让 claude-* 走 anthropicBaseUrl）──
#
# Cursor 默认所有模型请求都走 openAIBaseUrl；当中转站对 claude 模型期望
# Anthropic 协议时，这会导致 422/格式错误。该补丁直接改写 minified JS 中
# `openaiApiBaseUrl:...openAIBaseUrl??void 0,bedrockState:...` 处的取值逻辑：
# 模型名以 claude- 开头时优先取 anthropicBaseUrl，否则取 openAIBaseUrl。
#
# 补丁字符串与 cursor_injector.py 中 _ANTHROPIC_PATCH_OLD/NEW 完全一致，
# 标记 `/*wxAnthropicPatch*/` 也共用，因此与"无感换号"的 Pro 注入路径互斥幂等：
# 任一方注入过都不会重复打。

_ANTHROPIC_ROUTE_OLD = (
    'openaiApiBaseUrl:this._reactiveStorageService'
    '.applicationUserPersistentStorage.openAIBaseUrl??void 0,'
    'bedrockState:o,maxMode:t})'
)

_ANTHROPIC_ROUTE_NEW = (
    "openaiApiBaseUrl:(a&&(a.startsWith('claude-')||a.includes('claude')))"
    '?(this._reactiveStorageService.applicationUserPersistentStorage.anthropicBaseUrl'
    '||(this._reactiveStorageService.applicationUserPersistentStorage.openAIBaseUrl??void 0))'
    ':(this._reactiveStorageService.applicationUserPersistentStorage.openAIBaseUrl??void 0),'
    'bedrockState:o,maxMode:t})/*wxAnthropicPatch*/'
)


def _workbench_js_path() -> str | None:
    """定位 Cursor 的 workbench.desktop.main.js。"""
    try:
        from core.cursor_injector import _find_workbench_js
        return _find_workbench_js()
    except Exception:
        return None


def _write_workbench_js(js_path: str, new_content: str) -> tuple[bool, str]:
    """写入 workbench.desktop.main.js，自动处理 macOS 提权 + 备份。"""
    system = platform.system()
    try:
        from core.cursor_injector import (
            _needs_privilege, _mac_privileged_write, _mac_bak_path,
            _ensure_writable,
        )
    except ImportError:
        _needs_privilege = lambda _p: False  # noqa: E731
        _mac_privileged_write = None
        _mac_bak_path = None
        _ensure_writable = None

    if system == "Darwin" and _needs_privilege(js_path):
        try:
            bak = _mac_bak_path(js_path) if _mac_bak_path else (js_path + ".bak")
            if not os.path.exists(bak):
                shutil.copy2(js_path, bak)
        except Exception:
            pass
        try:
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".js", prefix="wb_route_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(new_content)
                _mac_privileged_write(tmp, js_path)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return True, "已写入（提权）"
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            if "user canceled" in stderr.lower() or "-128" in stderr:
                return False, "您取消了授权"
            return False, f"提权写入失败: {stderr[:120]}"
        except Exception as e:
            return False, f"写入失败: {e}"

    if _ensure_writable:
        ok, err = _ensure_writable(js_path)
        if not ok:
            return False, err

    try:
        bak = js_path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(js_path, bak)
    except Exception:
        pass

    try:
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True, "已写入"
    except PermissionError:
        return False, "无写入权限，请以管理员身份运行"
    except Exception as e:
        return False, f"写入失败: {e}"


def _apply_anthropic_route_patch() -> tuple[bool, str]:
    """打开 workbench.desktop.main.js，把 claude-* 模型路由切到 anthropicBaseUrl。

    幂等：已打过补丁直接返回成功；找不到匹配点（Cursor 版本不兼容）返回 False
    但不终止主流程（调用方仅记录告警）。
    """
    js_path = _workbench_js_path()
    if not js_path:
        return False, "未找到 workbench.desktop.main.js"

    try:
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"读取失败: {e}"

    if _ANTHROPIC_ROUTE_NEW in content or "/*wxAnthropicPatch*/" in content:
        return True, "claude 路由补丁已生效"

    if _ANTHROPIC_ROUTE_OLD not in content:
        return False, "Cursor 版本不兼容（未匹配到补丁锚点）"

    new_content = content.replace(
        _ANTHROPIC_ROUTE_OLD, _ANTHROPIC_ROUTE_NEW, 1)
    return _write_workbench_js(js_path, new_content)


def _remove_anthropic_route_patch() -> tuple[bool, str]:
    """还原 workbench.desktop.main.js 中的 claude 路由补丁。"""
    js_path = _workbench_js_path()
    if not js_path:
        return True, "Cursor 安装目录不存在，跳过"

    try:
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return True, "无法读取，跳过"

    if _ANTHROPIC_ROUTE_NEW not in content and "/*wxAnthropicPatch*/" not in content:
        return True, "未注入，无需还原"

    new_content = content.replace(_ANTHROPIC_ROUTE_NEW, _ANTHROPIC_ROUTE_OLD, 1)
    if new_content == content:
        # 兜底：靠标记移除整段
        return True, "未匹配新补丁字符串，跳过"
    return _write_workbench_js(js_path, new_content)


def _workbench_html_path() -> str | None:
    """定位 Cursor 的 workbench.html 文件。"""
    try:
        from core.cursor_injector import _cursor_install_root
        res_root = _cursor_install_root()
    except Exception:
        res_root = None
    if not res_root:
        return None
    html_path = os.path.join(
        res_root, "app", "out", "vs", "code",
        "electron-sandbox", "workbench", "workbench.html",
    )
    if os.path.isfile(html_path):
        return html_path
    html_alt = os.path.join(
        res_root, "app", "out", "vs", "code",
        "electron-browser", "workbench", "workbench.html",
    )
    if os.path.isfile(html_alt):
        return html_alt
    return None


def _inject_api_keys_hide() -> tuple[bool, str]:
    """在 workbench.html 中注入 CSS+JS 隐藏 API Keys 区域。"""
    html_path = _workbench_html_path()
    if not html_path:
        return False, "未找到 workbench.html"

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"读取 workbench.html 失败: {e}"

    if _API_HIDE_MARKER_START in content:
        return True, "API Keys 隐藏已生效"

    insert_pos = content.find("</html>")
    if insert_pos < 0:
        insert_pos = len(content)

    new_content = content[:insert_pos] + _API_HIDE_SNIPPET + "\n" + content[insert_pos:]

    system = platform.system()
    if system == "Darwin":
        try:
            from core.cursor_injector import _needs_privilege, _mac_privileged_write
            if _needs_privilege(html_path):
                import tempfile
                fd, tmp = tempfile.mkstemp(suffix=".html", prefix="wb_hide_")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    _mac_privileged_write(tmp, html_path)
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                return True, "API Keys 区域已隐藏"
        except ImportError:
            pass

    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except PermissionError:
        return False, "无写入权限，请以管理员身份运行"
    except Exception as e:
        return False, f"写入失败: {e}"

    return True, "API Keys 区域已隐藏"


def _remove_api_keys_hide() -> tuple[bool, str]:
    """移除 workbench.html 中的 API Keys 隐藏注入。"""
    html_path = _workbench_html_path()
    if not html_path:
        return True, "workbench.html 不存在，跳过"

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return True, "无法读取 workbench.html，跳过"

    if _API_HIDE_MARKER_START not in content:
        return True, "无需还原"

    start = content.find(_API_HIDE_MARKER_START)
    end = content.find(_API_HIDE_MARKER_END)
    if start >= 0 and end >= 0:
        new_content = content[:start] + content[end + len(_API_HIDE_MARKER_END):]
        new_content = new_content.replace("\n\n\n", "\n\n")

        system = platform.system()
        if system == "Darwin":
            try:
                from core.cursor_injector import _needs_privilege, _mac_privileged_write
                if _needs_privilege(html_path):
                    import tempfile
                    fd, tmp = tempfile.mkstemp(suffix=".html", prefix="wb_restore_")
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        _mac_privileged_write(tmp, html_path)
                    finally:
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass
                    return True, "API Keys 隐藏已还原"
            except ImportError:
                pass

        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return False, f"还原失败: {e}"

    return True, "API Keys 隐藏已还原"


# ── 整体流水线 ───────────────────────────────────────────────────

def full_setup(
    cursor_account: dict | None = None,
    relay_url: str = "",
    relay_api_key: str = "",
    auto_restart_cursor: bool = True,
    allowed_models: list[str] | None = None,
    disabled_models: list[str] | None = None,
    keep_login: bool = True,
) -> list[tuple[str, bool, str]]:
    """一键配置。返回 [(step, ok, msg), ...]。

    步骤：
      0. 关闭 Cursor（写 DB 需要文件不被锁定）
      1. 备份文件
      2. （可选）覆盖写入服务端下发的 Cursor 账号到 state.vscdb / storage.json
      3. 写入 API Key + Base URL 到 reactive storage
      4. 应用模型开关 / 还原旧版残留（API Keys 隐藏 / claude 路由补丁）
      5. 自动打开 Cursor

    Args:
        cursor_account: 服务端下发的 Cursor Pro 账号信息；为 None 时不动登录态。
        keep_login: ``True``（默认）= 保留用户当前 Cursor 登录态，**忽略**
            ``cursor_account`` 中的 accessToken/refreshToken/email；
            ``False`` = 用 ``cursor_account`` 强制覆盖本地登录信息（自动登录共享号）。
        其它参数同名词义。

    说明：
      - 默认 ``keep_login=True`` 下，即使传入 cursor_account 也仅尝试写入
        ``membership`` / ``machineId`` 等元信息（也都跳过，避免影响登录态）。
      - 不再修改 Cursor 设置里 API Keys 区域的可见性（用户可见、可手动开关）。
      - 不再写 settings.json 禁用遥测/自动更新，也不做系统级禁更新。
    """
    results: list[tuple[str, bool, str]] = []

    # Step 0: 关闭 Cursor（SQLite 需要文件不被锁定）
    # Windows 上文件句柄释放比 Unix 慢（杀毒软件/索引器扫描会持锁）；
    # 配合后面 sqlite3.connect(timeout=10) 的等待，足以避免"database is locked"。
    _post_close_wait = 2.5 if platform.system() == "Windows" else 1.0
    try:
        from core.cursor_process import exit_cursor, _is_cursor_running
        if _is_cursor_running():
            ok = exit_cursor(timeout=8)
            if ok:
                results.append(("close_cursor", True, "Cursor 已关闭"))
                time.sleep(_post_close_wait)
            else:
                results.append(("close_cursor", False,
                                "无法关闭 Cursor，请手动关闭后重试"))
                return results
        else:
            results.append(("close_cursor", True, "Cursor 未运行"))
    except Exception as e:
        results.append(("close_cursor", False, str(e)))
        return results

    paths = _cursor_paths()
    if not os.path.exists(paths["state_vscdb"]):
        results.append(("check_db", False,
                        "未找到 state.vscdb，请先启动一次 Cursor"))
        return results

    # Step 1: 备份
    try:
        backup_files()
        results.append(("backup", True, "已备份"))
    except Exception as e:
        results.append(("backup", False, str(e)))

    # Step 2-4: 写入 state.vscdb + storage.json
    conn = None
    try:
        conn = sqlite3.connect(paths["state_vscdb"], timeout=10)

        # Step 2: 注入 Cursor 账号
        # 仅当 (a) 上层提供了 cursor_account 且 (b) 用户显式关闭"保留登录态"时
        # 才覆盖本地 accessToken/refreshToken/email/sessionToken 等凭证。
        # 其余情况下保留用户原 Cursor 登录态，避免误踢已登录用户。
        if cursor_account and not keep_login:
            _inject_cursor_account(conn, cursor_account)
            membership = cursor_account.get("membership", "pro")
            _write_membership(conn, membership)
            machine_id = cursor_account.get("machineId", "")
            if machine_id:
                _write_machine_id(conn, machine_id)
            results.append(("inject_account", True,
                            f"已覆盖登录: {cursor_account.get('email', '')}"))
        else:
            results.append((
                "inject_account", True,
                "保留用户原 Cursor 登录态" if keep_login else "未提供账号，跳过",
            ))

        # Step 3: 写入 API Key + Base URL
        if relay_url or relay_api_key:
            _write_api_config(conn, relay_url, relay_api_key)
            base_url = relay_url.rstrip("/")
            if base_url and not base_url.endswith("/v1"):
                base_url += "/v1"
            results.append(("write_api_config", True,
                            f"baseUrl={base_url}"))

        # Step 4: 按服务端下发的「允许开启 / 强制关闭」两份列表更新模型开关
        # （参考 CursorPro 工具的 aiSettings.modelOverrideEnabled/Disabled 写入）。
        # 两份列表都为空时不动模型，保留用户原有偏好。
        try:
            en_n, dis_n, ua_n = _apply_model_overrides(
                conn,
                allowed_models=allowed_models,
                disabled_models=disabled_models,
            )
            if en_n == 0 and dis_n == 0 and ua_n == 0:
                results.append((
                    "apply_model_overrides", True,
                    "未配置模型开关，保持现状",
                ))
            else:
                results.append((
                    "apply_model_overrides", True,
                    f"已启用 {en_n} 个，禁用 {dis_n} 个，自定义 {ua_n} 个",
                ))
        except Exception as e:
            results.append(("apply_model_overrides", False, str(e)))

        conn.commit()
    except Exception as e:
        results.append(("write_db", False, str(e)))
        return results
    finally:
        if conn:
            conn.close()

    # Step 3: 清理旧版残留的 API Keys 区域隐藏（best-effort，失败不影响）
    try:
        ok, msg = _remove_api_keys_hide()
        results.append(("show_api_keys", ok, msg))
    except Exception as e:
        results.append(("show_api_keys", True, f"跳过: {e}"))

    # Step 3.5: 清理可能存在的 claude 路由补丁（旧版本一键配置会注入这段
    # JS，但它不带完整性校验绕过，会让 Cursor 启动后弹"installation is
    # corrupt"横幅并影响 UI 渲染）。当前中转站已兼容 claude 走 OpenAI 协议，
    # 不再需要此补丁；这里主动还原，让中招用户重新点一键配置即可自愈。
    try:
        ok, msg = _remove_anthropic_route_patch()
        results.append((
            "anthropic_route_patch", True,
            f"已清理旧补丁: {msg}" if ok else f"清理失败（不影响主流程）: {msg}",
        ))
    except Exception as e:
        results.append(("anthropic_route_patch", True, f"跳过: {e}"))

    # Step 4: 自动打开 Cursor
    if auto_restart_cursor:
        try:
            from core.cursor_process import open_cursor
            time.sleep(1)
            ok = open_cursor()
            if ok:
                results.append(("open_cursor", True, "Cursor 已自动启动"))
            else:
                results.append(("open_cursor", False,
                                "自动启动失败，请手动打开 Cursor"))
        except Exception as e:
            results.append(("open_cursor", False, str(e)))

    return results


def full_teardown(auto_restart_cursor: bool = True) -> list[tuple[str, bool, str]]:
    """关闭 Cursor → 清除 API 配置 → 还原更新组件 → 重开 Cursor。"""
    results: list[tuple[str, bool, str]] = []
    _post_close_wait = 2.5 if platform.system() == "Windows" else 1.0

    # 关闭 Cursor
    try:
        from core.cursor_process import exit_cursor, _is_cursor_running
        if _is_cursor_running():
            ok = exit_cursor(timeout=8)
            if ok:
                results.append(("close_cursor", True, "Cursor 已关闭"))
                time.sleep(_post_close_wait)
            else:
                results.append(("close_cursor", False,
                                "无法关闭 Cursor，请手动关闭后重试"))
                return results
        else:
            results.append(("close_cursor", True, "Cursor 未运行"))
    except Exception as e:
        results.append(("close_cursor", False, str(e)))

    # 清除 API Key 和 Base URL 配置
    paths = _cursor_paths()
    if os.path.exists(paths["state_vscdb"]):
        conn = None
        try:
            conn = sqlite3.connect(paths["state_vscdb"], timeout=10)
            _upsert_key(conn, "cursorAuth/openAIKey", "")
            _upsert_key(conn, "cursorAuth/claudeKey", "")
            _upsert_key(conn, "cursorAuth/anthropicKey", "")
            _reactive_update(conn, {
                # openAIBaseUrl=null 让 "Override OpenAI Base URL" 开关自动关
                "openAIBaseUrl": None,
                "useOpenAIKey": False,
                "useClaudeKey": False,
                "anthropicBaseUrl": None,
                "useAnthropicKey": False,
            })
            # 恢复模型禁用状态：清空 enabled/disabled/userAddedModels
            try:
                _clear_model_overrides(conn)
            except Exception:
                pass
            conn.commit()
            results.append(("clear_api_config", True, "已清除 API 配置"))
        except Exception as e:
            results.append(("clear_api_config", False, str(e)))
        finally:
            if conn:
                conn.close()

    # 还原 API Keys 隐藏（best-effort，失败不影响）
    try:
        ok, msg = _remove_api_keys_hide()
        results.append(("restore_api_keys_hide", ok, msg))
    except Exception as e:
        results.append(("restore_api_keys_hide", True, f"跳过: {e}"))

    # 还原 claude 路由补丁（best-effort，失败不阻塞 teardown）
    try:
        ok, msg = _remove_anthropic_route_patch()
        results.append((
            "restore_anthropic_route_patch", True,
            msg if ok else f"未还原（不影响主流程）: {msg}",
        ))
    except Exception as e:
        results.append(("restore_anthropic_route_patch", True, f"跳过: {e}"))

    # 重新打开 Cursor
    if auto_restart_cursor:
        try:
            from core.cursor_process import open_cursor
            time.sleep(1)
            ok = open_cursor()
            if ok:
                results.append(("open_cursor", True, "Cursor 已自动启动"))
            else:
                results.append(("open_cursor", False,
                                "自动启动失败，请手动打开 Cursor"))
        except Exception as e:
            results.append(("open_cursor", False, str(e)))

    return results


# ── 读取 ─────────────────────────────────────────────────────────

def read_current_config() -> dict:
    """UI 状态读取。"""
    paths = _cursor_paths()
    result = {
        "db_exists": os.path.exists(paths["state_vscdb"]),
        "logged_in": False,
        "email": "",
        "membership": "",
        "openai_base_url": "",
        "anthropic_base_url": "",
        "has_openai_key": False,
        "has_anthropic_key": False,
    }

    if result["db_exists"]:
        try:
            conn = sqlite3.connect(paths["state_vscdb"], timeout=5)
            result["logged_in"] = _has_valid_login(conn)
            result["email"] = _read_key(conn, "cursorAuth/cachedEmail") or ""
            result["membership"] = (
                _read_key(conn, "cursorAuth/stripeMembershipType") or "")
            result["has_openai_key"] = bool(
                _read_key(conn, "cursorAuth/openAIKey"))
            result["has_anthropic_key"] = bool(
                _read_key(conn, "cursorAuth/anthropicKey"))

            reactive = _reactive_read(conn)
            result["openai_base_url"] = reactive.get("openAIBaseUrl", "")
            result["anthropic_base_url"] = reactive.get(
                "anthropicBaseUrl", "")

            conn.close()
        except Exception:
            pass

    return result


# ── 向后兼容（旧入口名称） ─────────────────────────────────────

def one_click_setup(
    cursor_account: dict | None = None,
) -> tuple[bool, str]:
    """Legacy entry — 仅注入账号，不做 JS 注入或启动代理。

    保留以兼容调用点。新代码应使用 full_setup()。
    """
    paths = _cursor_paths()
    db_path = paths["state_vscdb"]
    if not os.path.exists(db_path):
        return False, "未检测到 Cursor 本地数据，请确认已安装并至少启动过一次 Cursor。"

    try:
        backup_files()
    except Exception as e:
        print(f"[CursorProSetup] Backup failed: {e}")

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        if cursor_account:
            _inject_cursor_account(conn, cursor_account)
        try:
            _write_settings_json(paths["settings_json"])
        except Exception:
            pass
        conn.commit()
    except sqlite3.Error as e:
        return False, f"数据库写入失败: {e}"
    except Exception as e:
        return False, f"配置写入异常: {e}"
    finally:
        if conn:
            conn.close()

    email = cursor_account.get("email", "") if cursor_account else ""
    detail = f"账号已注入: {email}" if email else "配置已写入"
    return True, f"Cursor 配置成功: {detail}"


def is_js_patched() -> bool:
    """旧 API 兼容：现在总是返回 False（不再需要 JS 注入）。"""
    return False


def is_api_configured() -> bool:
    """检测是否已配置 API Key + Base URL。"""
    cfg = read_current_config()
    return bool(cfg.get("openai_base_url")) and bool(cfg.get("has_openai_key"))
