"""Cursor 进程管理 — 退出、启动、清缓存、安装卸载（不依赖 psutil）"""
from __future__ import annotations

import errno
import glob as _glob
import json as _json
import os
import sys
import tempfile
import time
import shutil
import subprocess
import platform
import urllib.request

# Windows 下隐藏子进程的控制台黑窗口
_STARTUP_NO_WINDOW: dict = {}
if sys.platform == "win32":
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = 0  # SW_HIDE
    _STARTUP_NO_WINDOW = {"startupinfo": _si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW


def _run_quiet(args, timeout=120, **extra):
    """Run a subprocess, suppressing output and avoiding GBK decode errors on Windows."""
    kw = dict(_STARTUP_NO_WINDOW, **extra)
    kw["stdout"] = subprocess.DEVNULL
    kw["stderr"] = subprocess.DEVNULL
    return subprocess.run(args, timeout=timeout, **kw)


def _run_capture(args, timeout=60, **extra):
    """Run a subprocess and capture output safely (UTF-8 with replace on Windows)."""
    kw = dict(_STARTUP_NO_WINDOW, **extra)
    kw["capture_output"] = True
    if sys.platform == "win32":
        kw["encoding"] = "utf-8"
        kw["errors"] = "replace"
    else:
        kw["text"] = True
    return subprocess.run(args, timeout=timeout, **kw)


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


def clear_cursor_cache() -> bool:
    """删除 Cursor 数据目录下所有包含 'Cache' 的子目录。
    Windows 上同时清除 %APPDATA% 和 %LOCALAPPDATA% 下的缓存。"""
    roots: list[str] = []
    try:
        roots.append(_cursor_data_root())
    except Exception:
        pass

    if sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA")
        if local:
            p = os.path.join(local, "Cursor")
            if os.path.isdir(p) and p not in roots:
                roots.append(p)

    count = 0
    errors = 0
    for root in roots:
        if not os.path.exists(root):
            continue
        try:
            for item in os.listdir(root):
                full = os.path.join(root, item)
                if os.path.isdir(full) and "Cache" in item:
                    try:
                        shutil.rmtree(full)
                        count += 1
                        print(f"[Cache] Deleted: {full}")
                    except Exception as e:
                        errors += 1
                        print(f"[Cache] Failed to delete {full}: {e}")
        except Exception as e:
            print(f"[Cache] Failed to list {root}: {e}")

    print(f"已清除 {count} 个 Cursor 缓存目录" + (f" ({errors} 个失败)" if errors else ""))
    return True


def disable_cursor_auto_update() -> bool:
    """禁用 Cursor 自动更新：在 User/settings.json 中设置 update.mode = none"""
    import json as _json
    try:
        settings_path = os.path.join(_cursor_data_root(), "User", "settings.json")
        settings: dict = {}
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = _json.load(f)

        if settings.get("update.mode") == "none":
            return True

        settings["update.mode"] = "none"
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            _json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def _is_cursor_running() -> bool:
    """检查 Cursor 是否在运行"""
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(
                ["pgrep", "-x", "Cursor"],
                capture_output=True,
            )
            return r.returncode == 0
        elif system == "Windows":
            r = _run_capture(["tasklist", "/FI", "IMAGENAME eq Cursor.exe"], timeout=10)
            return "Cursor.exe" in (r.stdout or "")
        else:
            r = subprocess.run(
                ["pgrep", "-x", "cursor"],
                capture_output=True,
            )
            return r.returncode == 0
    except Exception:
        return False


def exit_cursor(timeout: int = 5) -> bool:
    """关闭 Cursor，先温和退出，再强杀（含所有 Helper 子进程）"""
    system = platform.system()

    if not _is_cursor_running():
        print("未发现运行中的 Cursor 进程")
        return True

    print("开始退出 Cursor...")

    try:
        if system == "Darwin":
            subprocess.run(["pkill", "-x", "Cursor"], capture_output=True)
        elif system == "Windows":
            # Windows 直接用 /F 强杀 + /T 终止整个进程树，
            # 等价于 psutil.TerminateProcess()，避免 WM_CLOSE 路径带来的延迟
            for proc in ("Cursor.exe", "cursor.exe"):
                _run_quiet(["taskkill", "/F", "/IM", proc, "/T"], timeout=10)
            for helper in (
                "Cursor Helper.exe",
                "Cursor Helper (GPU).exe",
                "Cursor Helper (Renderer).exe",
                "Cursor Helper (Plugin).exe",
                "Cursor Crash Reporter.exe",
                "cursor_crashpad_handler.exe",
                "CursorCrashpadHandler.exe",
            ):
                try:
                    _run_quiet(["taskkill", "/F", "/IM", helper, "/T"], timeout=5)
                except Exception:
                    pass
        else:
            subprocess.run(["pkill", "-x", "cursor"], capture_output=True)
    except Exception as e:
        print(f"发送终止信号失败: {e}")

    start = time.time()
    while time.time() - start < timeout:
        if not _is_cursor_running():
            print("所有 Cursor 进程已正常关闭")
            # Windows 强杀后仍需等待 OS 回收文件句柄（SQLite WAL 等）
            time.sleep(2.0 if system == "Windows" else 0.8)
            return True
        time.sleep(0.5)

    print("Cursor 进程仍在运行，追加强杀...")
    try:
        if system == "Darwin":
            subprocess.run(["pkill", "-9", "-x", "Cursor"], capture_output=True)
            subprocess.run(["pkill", "-9", "-f", "Cursor Helper"], capture_output=True)
        elif system == "Windows":
            for proc in ("Cursor.exe", "cursor.exe"):
                _run_quiet(["taskkill", "/F", "/IM", proc, "/T"], timeout=10)
        else:
            subprocess.run(["pkill", "-9", "-x", "cursor"], capture_output=True)
    except Exception as e:
        print(f"强制结束失败: {e}")

    time.sleep(2.5 if system == "Windows" else 1.5)

    if _is_cursor_running():
        print("仍有 Cursor 进程未能关闭")
        return False

    print("所有 Cursor 进程已强制关闭")
    return True


# ──────────────────────────────────────────────────────────────────
# Cursor 路径检测（严格模式）
#
# 历史问题：曾经有"路径缓存 + 全盘搜索"的策略，结果 Downloads / Desktop 里
# 的旧拷贝、被误删后的残留软链都会被当成正主，导致注入打错地方。现在统一
# 改为：只信"标准官方安装路径"，其它一律不识别。
#
# • macOS：/Applications/Cursor.app
# • Windows：%LOCALAPPDATA%\Programs\cursor\
#     - launcher 在根目录（Cursor.exe / cursor.exe）
#     - resources 既可能在根目录 resources/，也可能在 app-x.y.z/resources/
# • Linux：/usr/{share,lib}/cursor、/usr/local/{share,lib}/cursor、
#          ~/.local/{share,lib}/cursor
#
# `_find_cursor_executable()`  → 启动 / 卸载 / 检测安装用
# `_cursor_install_root()`     → 注入用，返回包含 workbench JS 的 resources 目录
# ──────────────────────────────────────────────────────────────────

_WORKBENCH_REL = os.path.join(
    "app", "out", "vs", "workbench", "workbench.desktop.main.js"
)


def _has_workbench(resources_dir: str) -> bool:
    return os.path.isfile(os.path.join(resources_dir, _WORKBENCH_REL))


# ── 用户手动指定的 Cursor 安装位置（只在自动检测失败时由用户在 UI 里点"检测"
#    手动选择，写入文件后所有模块共享。区别于历史"自动缓存"，这是用户主动行为。）
def _user_override_file() -> str:
    try:
        from api.client import CONFIG_DIR
    except Exception:
        CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
    return os.path.join(CONFIG_DIR, "cursor_install_override.json")


def load_user_cursor_path() -> str | None:
    """读取用户手动指定的 Cursor 安装根目录，无效则返回 None。"""
    try:
        path = _user_override_file()
        if not os.path.isfile(path):
            return None
        import json as _json
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f) or {}
        root = (data.get("install_root") or "").strip()
        if root and os.path.isdir(root):
            return root
    except Exception:
        pass
    return None


def save_user_cursor_path(install_root: str) -> bool:
    """保存用户手动选择的 Cursor 安装根目录。"""
    try:
        import json as _json
        path = _user_override_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump({"install_root": install_root}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def clear_user_cursor_path() -> None:
    try:
        path = _user_override_file()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def _resolve_user_root_to_executable(install_root: str) -> str | None:
    """把用户选择的目录解析为可执行文件。
    支持：/path/to/Cursor.app（mac），%LOCALAPPDATA%\\Programs\\cursor（win），
    或任意包含 Cursor.exe 的目录、或 app-x.y.z 的父目录。"""
    if not install_root or not os.path.isdir(install_root):
        return None
    system = platform.system()
    if system == "Darwin":
        if install_root.endswith(".app"):
            exe = os.path.join(install_root, "Contents", "MacOS", "Cursor")
            return exe if os.path.isfile(exe) else None
        # 用户可能选了 .app 的父目录
        nested = os.path.join(install_root, "Cursor.app", "Contents", "MacOS", "Cursor")
        return nested if os.path.isfile(nested) else None
    if system == "Windows":
        for name in ("Cursor.exe", "cursor.exe"):
            p = os.path.join(install_root, name)
            if os.path.isfile(p):
                return p
        try:
            app_dirs = sorted(
                (it for it in os.listdir(install_root)
                 if it.lower().startswith("app-")
                 and os.path.isdir(os.path.join(install_root, it))),
                reverse=True,
            )
        except OSError:
            app_dirs = []
        for it in app_dirs:
            for name in ("Cursor.exe", "cursor.exe"):
                p = os.path.join(install_root, it, name)
                if os.path.isfile(p):
                    return p
        return None
    for name in ("cursor", "Cursor"):
        p = os.path.join(install_root, name)
        if os.path.isfile(p):
            return p
    return None


def _resolve_user_root_to_resources(install_root: str) -> str | None:
    """把用户选择的目录解析为 resources/ 子目录（包含 workbench JS 的那一层）。"""
    if not install_root or not os.path.isdir(install_root):
        return None
    system = platform.system()
    if system == "Darwin":
        candidate = os.path.join(install_root, "Contents", "Resources")
        if _has_workbench(candidate):
            return candidate
        nested = os.path.join(install_root, "Cursor.app", "Contents", "Resources")
        if _has_workbench(nested):
            return nested
        return None
    candidate = os.path.join(install_root, "resources")
    if _has_workbench(candidate):
        return candidate
    try:
        app_dirs = sorted(
            (it for it in os.listdir(install_root)
             if it.lower().startswith("app-")
             and os.path.isdir(os.path.join(install_root, it))),
            reverse=True,
        )
    except OSError:
        app_dirs = []
    for it in app_dirs:
        candidate2 = os.path.join(install_root, it, "resources")
        if _has_workbench(candidate2):
            return candidate2
    return None


def validate_user_cursor_path(install_root: str) -> bool:
    """校验用户选择的目录确实是 Cursor 安装位置（含 workbench JS）。"""
    return _resolve_user_root_to_resources(install_root) is not None


def _windows_cursor_root() -> str | None:
    """Windows 标准安装根目录：%LOCALAPPDATA%\\Programs\\cursor"""
    appdata = os.getenv("LOCALAPPDATA") or ""
    if not appdata:
        userprofile = os.getenv("USERPROFILE") or ""
        if not userprofile:
            return None
        appdata = os.path.join(userprofile, "AppData", "Local")
    root = os.path.join(appdata, "Programs", "cursor")
    return root if os.path.isdir(root) else None


def _find_cursor_executable() -> str | None:
    """跨平台查找 Cursor 可执行文件 —— 严格模式，只认标准安装路径。
    若用户在 UI 里手动指定过路径（点击「检测」按钮），优先使用该路径。"""
    override = load_user_cursor_path()
    if override:
        exe = _resolve_user_root_to_executable(override)
        if exe:
            return exe

    system = platform.system()
    if system == "Darwin":
        p = "/Applications/Cursor.app/Contents/MacOS/Cursor"
        return p if os.path.isfile(p) else None

    if system == "Windows":
        root = _windows_cursor_root()
        if not root:
            return None
        for name in ("Cursor.exe", "cursor.exe"):
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
        return None

    for p in ("/usr/bin/cursor", "/usr/local/bin/cursor",
              os.path.expanduser("~/.local/bin/cursor")):
        if os.path.isfile(p):
            return p
    return None


def _cursor_install_root() -> str | None:
    """返回包含 workbench JS 的 resources 目录 —— 严格模式。
    若用户手动指定过路径（点击「检测」按钮），优先使用该路径。"""
    override = load_user_cursor_path()
    if override:
        res = _resolve_user_root_to_resources(override)
        if res:
            return res

    system = platform.system()

    if system == "Darwin":
        p = "/Applications/Cursor.app/Contents/Resources"
        return p if _has_workbench(p) else None

    if system == "Windows":
        root = _windows_cursor_root()
        if not root:
            return None
        direct = os.path.join(root, "resources")
        if _has_workbench(direct):
            return direct
        # Squirrel 安装：app-x.y.z/resources/
        try:
            app_dirs = sorted(
                (item for item in os.listdir(root)
                 if item.lower().startswith("app-")
                 and os.path.isdir(os.path.join(root, item))),
                reverse=True,
            )
        except OSError:
            app_dirs = []
        for item in app_dirs:
            candidate = os.path.join(root, item, "resources")
            if _has_workbench(candidate):
                return candidate
        return None

    for prefix in ("/usr", "/usr/local", os.path.expanduser("~/.local")):
        for sub in ("share", "lib"):
            candidate = os.path.join(prefix, sub, "cursor", "resources")
            if _has_workbench(candidate):
                return candidate
    return None


def _popen_detached_gui(argv: list) -> subprocess.Popen:
    """启动 GUI 程序并尽量与当前 Python/调试器进程树脱钩，避免关 IDE 时子进程被一并结束。"""
    system = platform.system()
    devnull = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if system == "Windows":
        # 脱离调试器常用的 Job Object（PyCharm / VS 等停止调试时会结束作业内子进程）
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags_try = (
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )
        for fl in flags_try:
            try:
                return subprocess.Popen(
                    argv, creationflags=fl, close_fds=True, **devnull
                )
            except OSError:
                continue
        return subprocess.Popen(argv, **devnull)

    return subprocess.Popen(
        argv, start_new_session=True, close_fds=True, **devnull
    )


def open_cursor(after_inject: bool = False) -> bool:
    """启动 Cursor（不与助手进程绑在同一调试/进程组下，便于从 IDE 停止运行时不误关 Cursor）

    after_inject: 注入后首次启动时传 True，会附加 --no-cached-data --disable-gpu
                  参数来绕过 V8 字节码缓存（Windows 上修改 JS 后缓存不失效会导致黑屏）。
    """
    extra_args: list[str] = []
    if after_inject:
        extra_args = ["--no-cached-data", "--disable-gpu"]
        print(f"[open_cursor] post-inject launch with: {extra_args}")

    system = platform.system()
    try:
        if system == "Darwin":
            if extra_args:
                exe = _find_cursor_executable()
                if exe:
                    _popen_detached_gui([exe] + extra_args)
                    print(f"Cursor 已启动 (post-inject): {exe}")
                    return True
            r = subprocess.run(
                ["open", "-n", "-a", "Cursor"],
                capture_output=True,
                timeout=30,
            )
            if r.returncode == 0:
                print("Cursor 已启动 (open -a)")
                return True
            exe = _find_cursor_executable()
            if not exe:
                print("未找到 Cursor 安装路径")
                return False
            _popen_detached_gui([exe] + extra_args)
            print(f"Cursor 已启动: {exe}")
            return True

        exe = _find_cursor_executable()
        if not exe:
            print("未找到 Cursor 安装路径")
            return False
        _popen_detached_gui([exe] + extra_args)
        print(f"Cursor 已启动: {exe}")
        return True
    except OSError as e:
        if e.errno == errno.EPIPE:
            print("Error: Broken pipe (EPIPE)")
        else:
            print(f"启动 Cursor 失败: {e}")
        return False
    except Exception as e:
        print(f"启动 Cursor 失败: {e}")
        return False


# ------------------------------------------------------------------ 安装 / 卸载

_FALLBACK_URLS = {
    "darwin_arm64": "https://downloader.cursor.sh/arm64",
    "darwin_x64":   "https://downloader.cursor.sh/darwin/x64",
    "win32_x64":    "https://downloader.cursor.sh/windows",
    "linux_x64":    "https://downloader.cursor.sh/linux",
}

_CURSOR_API_PLATFORMS = {
    "darwin_arm64": "darwin-arm64",
    "darwin_x64":   "darwin-x64",
    "win32_x64":    "win32-x64-user",
    "linux_x64":    "linux-x64",
}

_backend_download_urls: dict[str, str] = {}


def set_cursor_download_urls(urls: dict[str, str]):
    """Called by the UI layer to inject backend-configured download URLs."""
    _backend_download_urls.clear()
    _backend_download_urls.update(urls)


def _download_key() -> str:
    system = platform.system()
    if system == "Darwin":
        arch = platform.machine().lower()
        return "darwin_arm64" if "arm" in arch else "darwin_x64"
    if system == "Windows":
        return "win32_x64"
    return "linux_x64"


def _resolve_download_url(key: str) -> str | None:
    """Resolve download URL: backend config -> Cursor official API -> fallback."""
    if key in _backend_download_urls and _backend_download_urls[key]:
        print(f"[Download] Using backend-configured URL for {key}")
        return _backend_download_urls[key]

    api_platform = _CURSOR_API_PLATFORMS.get(key)
    if api_platform:
        api_url = f"https://www.cursor.com/api/download?platform={api_platform}&releaseTrack=stable"
        import json
        # Try requests first (better proxy support on Windows)
        try:
            import requests as _req
            resp = _req.get(api_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()
            url = data.get("downloadUrl")
            if url:
                print(f"[Download] Using Cursor official URL for {key}: v{data.get('version', '?')}")
                return url
        except Exception:
            pass
        # Fallback to urllib
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                url = data.get("downloadUrl")
                if url:
                    print(f"[Download] Using Cursor official URL for {key}: v{data.get('version', '?')}")
                    return url
        except Exception as e:
            print(f"[Download] Cursor official API failed for {key}: {e}")

    return _FALLBACK_URLS.get(key)


def is_cursor_installed() -> bool:
    return _find_cursor_executable() is not None


def get_cursor_version() -> str | None:
    """Attempt to detect the installed Cursor version."""
    system = platform.system()
    try:
        if system == "Darwin":
            plist = "/Applications/Cursor.app/Contents/Info.plist"
            if os.path.isfile(plist):
                r = subprocess.run(
                    ["defaults", "read", plist, "CFBundleShortVersionString"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            alt = os.path.expanduser("~/Applications/Cursor.app/Contents/Info.plist")
            if os.path.isfile(alt):
                r = subprocess.run(
                    ["defaults", "read", alt, "CFBundleShortVersionString"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
        elif system == "Windows":
            exe = _find_cursor_executable()
            if exe:
                pkg = os.path.join(os.path.dirname(exe), "resources", "app", "package.json")
                if os.path.isfile(pkg):
                    with open(pkg, "r", encoding="utf-8") as f:
                        return _json.load(f).get("version")
    except Exception:
        pass
    return None


def install_cursor(progress_cb=None) -> tuple[bool, str]:
    """Download and install Cursor. Returns (success, message).
    progress_cb(percent, status_text) is called periodically if provided.
    """
    system = platform.system()
    key = _download_key()
    url = _resolve_download_url(key)
    if not url:
        return False, f"不支持当前系统架构: {key}"

    if progress_cb:
        progress_cb(0, "正在下载 Cursor...")

    try:
        if system == "Darwin":
            return _install_macos(url, progress_cb)
        elif system == "Windows":
            return _install_windows(url, progress_cb)
        else:
            return _install_linux(url, progress_cb)
    except Exception as e:
        return False, f"安装失败: {e}"


def _download_file(url: str, dest: str, progress_cb=None) -> bool:
    """Download a URL to dest, following redirects. Returns True on success."""
    try:
        import requests as _req
        resp = _req.get(url, stream=True, timeout=300, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 256
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total > 0:
                    pct = min(int(downloaded * 80 / total), 80)
                    mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    progress_cb(pct, f"下载中... {mb:.0f}/{total_mb:.0f} MB")
        return True
    except Exception as e:
        print(f"[Download] requests failed ({e}), falling back to urllib...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 256
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        pct = min(int(downloaded * 80 / total), 80)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        progress_cb(pct, f"下载中... {mb:.0f}/{total_mb:.0f} MB")
        return True
    except Exception as e:
        print(f"[Download] urllib also failed: {e}")
        return False


def _install_macos(url: str, progress_cb) -> tuple[bool, str]:
    tmpdir = tempfile.mkdtemp(prefix="cursor_install_")
    dmg_path = os.path.join(tmpdir, "Cursor.dmg")

    try:
        if not _download_file(url, dmg_path, progress_cb):
            return False, (
                "下载 Cursor 安装包失败。\n\n"
                "可能原因：\n"
                "• 网络代理/VPN 阻止了下载地址\n"
                "• 网络连接不稳定\n\n"
                "解决方案：\n"
                "1. 尝试关闭/切换代理后重试\n"
                "2. 或手动访问 https://cursor.sh 下载安装"
            )

        if progress_cb:
            progress_cb(82, "正在挂载安装包...")

        r = subprocess.run(
            ["hdiutil", "attach", dmg_path, "-nobrowse", "-quiet"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return False, f"挂载 DMG 失败: {r.stderr.strip()}"

        mount_point = None
        for line in r.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                mount_point = parts[-1].strip()

        if not mount_point:
            list_r = subprocess.run(
                ["hdiutil", "info"], capture_output=True, text=True, timeout=10,
            )
            for line in (list_r.stdout or "").splitlines():
                if "Cursor" in line and "/Volumes/" in line:
                    idx = line.find("/Volumes/")
                    if idx >= 0:
                        mount_point = line[idx:].strip()
                        break

        if not mount_point or not os.path.isdir(mount_point):
            mount_candidates = _glob.glob("/Volumes/Cursor*")
            if mount_candidates:
                mount_point = mount_candidates[0]

        if not mount_point or not os.path.isdir(mount_point):
            return False, "无法找到 DMG 挂载点"

        app_src = os.path.join(mount_point, "Cursor.app")
        if not os.path.isdir(app_src):
            for item in os.listdir(mount_point):
                if item.endswith(".app") and "cursor" in item.lower():
                    app_src = os.path.join(mount_point, item)
                    break

        if not os.path.isdir(app_src):
            subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], timeout=30)
            return False, f"DMG 中未找到 Cursor.app: {os.listdir(mount_point)}"

        if progress_cb:
            progress_cb(88, "正在安装到 Applications...")

        dest = "/Applications/Cursor.app"
        if os.path.exists(dest):
            shutil.rmtree(dest)

        subprocess.run(
            ["cp", "-R", app_src, dest],
            capture_output=True, timeout=120,
        )

        if progress_cb:
            progress_cb(96, "正在清理...")

        subprocess.run(["hdiutil", "detach", mount_point, "-quiet"],
                       capture_output=True, timeout=30)

        if not os.path.isdir(dest):
            return False, "复制 Cursor.app 到 /Applications 失败"

        subprocess.run(["xattr", "-cr", dest], capture_output=True, timeout=30)

        if progress_cb:
            progress_cb(100, "安装完成")

        return True, "Cursor 已成功安装到 /Applications"

    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def _install_windows(url: str, progress_cb) -> tuple[bool, str]:
    tmpdir = tempfile.mkdtemp(prefix="cursor_install_")
    exe_path = os.path.join(tmpdir, "CursorSetup.exe")

    try:
        if not _download_file(url, exe_path, progress_cb):
            return False, (
                "下载 Cursor 安装包失败。\n\n"
                "可能原因：\n"
                "• 网络代理/VPN 阻止了下载地址\n"
                "• 网络连接不稳定\n\n"
                "解决方案：\n"
                "1. 尝试关闭/切换代理后重试\n"
                "2. 或手动访问 https://cursor.sh 下载安装"
            )

        if progress_cb:
            progress_cb(85, "正在运行安装程序...")

        r = _run_quiet([exe_path, "/S"], timeout=300)

        if progress_cb:
            progress_cb(100, "安装完成")

        if r.returncode == 0:
            return True, "Cursor 已成功安装"
        return False, f"安装程序异常退出 (code={r.returncode})"
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def _install_linux(url: str, progress_cb) -> tuple[bool, str]:
    tmpdir = tempfile.mkdtemp(prefix="cursor_install_")
    appimage_path = os.path.join(tmpdir, "Cursor.AppImage")

    try:
        if not _download_file(url, appimage_path, progress_cb):
            return False, (
                "下载 Cursor 安装包失败。\n\n"
                "可能原因：\n"
                "• 网络代理/VPN 阻止了下载地址\n"
                "• 网络连接不稳定\n\n"
                "解决方案：\n"
                "1. 尝试关闭/切换代理后重试\n"
                "2. 或手动访问 https://cursor.sh 下载安装"
            )

        if progress_cb:
            progress_cb(85, "正在安装...")

        dest = os.path.expanduser("~/.local/bin/cursor")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(appimage_path, dest)
        os.chmod(dest, 0o755)

        if progress_cb:
            progress_cb(100, "安装完成")

        return True, f"Cursor 已安装到 {dest}"
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def uninstall_cursor(clean_data: bool = False) -> tuple[bool, str]:
    """Uninstall Cursor. If clean_data=True, also remove user data."""
    system = platform.system()
    try:
        exit_cursor(timeout=8)
        time.sleep(1)

        if system == "Darwin":
            return _uninstall_macos(clean_data)
        elif system == "Windows":
            return _uninstall_windows(clean_data)
        else:
            return _uninstall_linux(clean_data)
    except Exception as e:
        return False, f"卸载失败: {e}"


def _uninstall_macos(clean_data: bool) -> tuple[bool, str]:
    removed = []
    home = os.path.expanduser("~")

    # 1) 强杀所有 Cursor 相关进程
    for pattern in ["Cursor", "Cursor Helper", "Cursor Helper (GPU)",
                     "Cursor Helper (Renderer)", "Cursor Helper (Plugin)"]:
        try:
            subprocess.run(["pkill", "-9", "-f", pattern],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    time.sleep(1)

    # 2) 移除 .app 本体
    for app_path in [
        "/Applications/Cursor.app",
        os.path.expanduser("~/Applications/Cursor.app"),
    ]:
        if os.path.exists(app_path):
            shutil.rmtree(app_path)
            removed.append(app_path)

    # 3) 移除 CLI 符号链接
    for cli_path in ["/usr/local/bin/cursor", os.path.expanduser("~/.local/bin/cursor")]:
        try:
            if os.path.exists(cli_path) or os.path.islink(cli_path):
                os.remove(cli_path)
                removed.append(cli_path)
        except Exception:
            pass

    # 4) 删除所有数据、缓存、配置目录（始终清理，彻底卸载）
    data_dirs = [
        os.path.join(home, "Library/Application Support/Cursor"),
        os.path.join(home, "Library/Application Support/Caches/cursor-updater"),
        os.path.join(home, "Library/Caches/Cursor"),
        os.path.join(home, "Library/Caches/com.cursor.Cursor"),
        os.path.join(home, "Library/Caches/com.cursor.Cursor.ShipIt"),
        os.path.join(home, "Library/HTTPStorages/com.cursor.Cursor"),
        os.path.join(home, "Library/Logs/Cursor"),
        os.path.join(home, "Library/Preferences/com.cursor.Cursor.plist"),
        os.path.join(home, "Library/Saved Application State/com.cursor.Cursor.savedState"),
        os.path.join(home, ".cursor"),
        os.path.join(home, ".cursor-server"),
    ]
    for pattern in _glob.glob(os.path.join(home, "Library/Preferences/com.cursor*")):
        if pattern not in data_dirs:
            data_dirs.append(pattern)
    for pattern in _glob.glob(os.path.join(home, "Library/Preferences/com.todesktop.*cursor*")):
        if pattern not in data_dirs:
            data_dirs.append(pattern)
    for pattern in _glob.glob(os.path.join(home, ".cursor*")):
        if pattern not in data_dirs:
            data_dirs.append(pattern)

    for d in data_dirs:
        try:
            if os.path.islink(d):
                os.remove(d)
                removed.append(d)
            elif os.path.isdir(d):
                shutil.rmtree(d)
                removed.append(d)
            elif os.path.isfile(d):
                os.remove(d)
                removed.append(d)
        except Exception:
            pass

    # 5) 清理 Keychain 中的 Cursor 条目
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-s", "Cursor Safe Storage"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass

    # 6) 刷新 LaunchServices 缓存
    try:
        subprocess.run(
            ["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
             "LaunchServices.framework/Support/lsregister",
             "-kill", "-r", "-domain", "local", "-domain", "system", "-domain", "user"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass

    if not removed:
        return False, "未找到 Cursor 安装，无需卸载"

    return True, f"已彻底卸载 Cursor，清理了 {len(removed)} 个项目"


def _uninstall_windows(clean_data: bool) -> tuple[bool, str]:
    removed = []
    appdata = os.getenv("LOCALAPPDATA") or ""
    roaming = os.getenv("APPDATA") or ""
    userprofile = os.getenv("USERPROFILE") or os.path.expanduser("~")

    # 0) 先通过 _find_cursor_executable 定位实际安装路径
    actual_exe = _find_cursor_executable()
    actual_install_dir: str | None = None
    if actual_exe:
        exe_dir = os.path.dirname(actual_exe)
        # Squirrel layout: ...\cursor\app-x.y.z\Cursor.exe -> parent is the install root
        parent = os.path.dirname(exe_dir)
        parent_name = os.path.basename(parent).lower()
        if os.path.basename(exe_dir).lower().startswith("app-") and parent_name in ("cursor", "programs"):
            actual_install_dir = parent
        else:
            actual_install_dir = exe_dir

    # 1) 强杀所有 Cursor 相关进程
    for proc_name in ["Cursor.exe", "cursor.exe"]:
        try:
            _run_quiet(["taskkill", "/F", "/IM", proc_name, "/T"], timeout=10)
        except Exception:
            pass
    time.sleep(2)

    # 2) 收集所有可能的安装目录
    install_dirs: list[str] = []
    for dirname in ("cursor", "Cursor"):
        install_dirs.append(os.path.join(appdata, "Programs", dirname))
        install_dirs.append(os.path.join(appdata, dirname))
    if actual_install_dir and actual_install_dir not in install_dirs:
        install_dirs.insert(0, actual_install_dir)

    # 3) 运行官方卸载程序 (Squirrel / NSIS)
    uninstaller_candidates = []
    for base in install_dirs:
        if not os.path.isdir(base):
            continue
        uninstaller_candidates.append(os.path.join(base, "Uninstall Cursor.exe"))
        uninstaller_candidates.append(os.path.join(base, "unins000.exe"))
        uninstaller_candidates.append(os.path.join(base, "Update.exe"))

    for uninstaller in uninstaller_candidates:
        if not os.path.isfile(uninstaller):
            continue
        try:
            name = os.path.basename(uninstaller).lower()
            if "update.exe" in name:
                _run_quiet([uninstaller, "--uninstall", "-s"], timeout=120)
            else:
                _run_quiet([uninstaller, "/S"], timeout=120)
            time.sleep(2)
        except Exception:
            pass

    # wait for uninstaller to release files
    time.sleep(2)

    # 4) 删除安装目录
    for d in install_dirs:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            if not os.path.isdir(d):
                removed.append(d)

    # If the exe still exists, force-delete the file and its parent directory
    if actual_exe and os.path.isfile(actual_exe):
        try:
            os.remove(actual_exe)
        except Exception:
            pass
        parent_dir = os.path.dirname(actual_exe)
        if os.path.isdir(parent_dir):
            shutil.rmtree(parent_dir, ignore_errors=True)
            if not os.path.isdir(parent_dir):
                removed.append(parent_dir)
        # Also try the install root (one level up for app-x.y.z)
        if actual_install_dir and os.path.isdir(actual_install_dir):
            shutil.rmtree(actual_install_dir, ignore_errors=True)
            if not os.path.isdir(actual_install_dir):
                removed.append(actual_install_dir)

    # 5) 删除数据、缓存、配置目录（始终清理，彻底卸载）
    data_dirs = [
        os.path.join(roaming, "Cursor"),
        os.path.join(appdata, "Cursor"),
        os.path.join(appdata, "cursor-updater"),
        os.path.join(userprofile, ".cursor"),
        os.path.join(userprofile, ".cursor-server"),
    ]
    for pattern in _glob.glob(os.path.join(appdata, "Cursor*")):
        if os.path.isdir(pattern) and pattern not in data_dirs:
            data_dirs.append(pattern)
    for pattern in _glob.glob(os.path.join(userprofile, ".cursor*")):
        if os.path.isdir(pattern) and pattern not in data_dirs:
            data_dirs.append(pattern)

    for d in data_dirs:
        try:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                removed.append(d)
            elif os.path.isfile(d):
                os.remove(d)
                removed.append(d)
        except Exception:
            pass

    # 6) 清理桌面和开始菜单快捷方式
    shortcut_dirs = [
        os.path.join(userprofile, "Desktop"),
        os.path.join(roaming, "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(roaming, "Microsoft", "Windows", "Start Menu", "Programs", "Cursor"),
    ]
    for shortcut_dir in shortcut_dirs:
        if not os.path.isdir(shortcut_dir):
            continue
        try:
            for f in os.listdir(shortcut_dir):
                fp = os.path.join(shortcut_dir, f)
                if "cursor" in f.lower() and (f.endswith(".lnk") or os.path.isdir(fp)):
                    try:
                        if os.path.isdir(fp):
                            shutil.rmtree(fp, ignore_errors=True)
                        else:
                            os.remove(fp)
                        removed.append(fp)
                    except Exception:
                        pass
        except Exception:
            pass

    # 7) 清理 PATH 中的 cursor 命令
    which_cursor = shutil.which("cursor")
    if which_cursor:
        try:
            os.remove(which_cursor)
            removed.append(which_cursor)
        except Exception:
            pass

    # 8) 清理注册表中的 Cursor 条目
    try:
        import winreg
        for hive_name, hive in [("HKCU", winreg.HKEY_CURRENT_USER)]:
            for subkey_path in [
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                r"Software",
            ]:
                try:
                    with winreg.OpenKey(hive, subkey_path) as key:
                        i = 0
                        keys_to_delete = []
                        while True:
                            try:
                                name = winreg.EnumKey(key, i)
                                if "cursor" in name.lower():
                                    keys_to_delete.append(name)
                                i += 1
                            except OSError:
                                break
                        for name in keys_to_delete:
                            try:
                                winreg.DeleteKey(key, name)
                                removed.append(f"registry:{hive_name}\\{subkey_path}\\{name}")
                            except Exception:
                                pass
                except Exception:
                    pass
    except ImportError:
        pass

    if not removed:
        return False, "未找到 Cursor 安装，无需卸载"

    return True, f"已彻底卸载 Cursor，清理了 {len(removed)} 个项目"


def _uninstall_linux(clean_data: bool) -> tuple[bool, str]:
    removed = []
    home = os.path.expanduser("~")

    # 1) 强杀 Cursor 进程
    try:
        subprocess.run(["pkill", "-9", "-x", "cursor"], capture_output=True, timeout=5)
        subprocess.run(["pkill", "-9", "-f", "Cursor"], capture_output=True, timeout=5)
    except Exception:
        pass
    time.sleep(1)

    # 2) 移除可执行文件 / symlinks
    bin_paths = [
        os.path.expanduser("~/.local/bin/cursor"),
        "/usr/bin/cursor",
        "/usr/local/bin/cursor",
    ]
    for p in bin_paths:
        try:
            if os.path.exists(p) or os.path.islink(p):
                os.remove(p)
                removed.append(p)
        except Exception:
            pass

    # 3) 移除安装目录
    install_dirs = [
        "/opt/Cursor-patched",
        "/opt/cursor",
        "/usr/share/cursor",
        os.path.join(home, ".local/share/cursor"),
    ]
    for d in install_dirs:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d)

    # 4) 移除 AppImage 文件
    for downloads in [os.path.join(home, "Downloads"), os.path.join(home, "下载")]:
        if os.path.isdir(downloads):
            for f in _glob.glob(os.path.join(downloads, "Cursor*.AppImage")):
                try:
                    os.remove(f)
                    removed.append(f)
                except Exception:
                    pass
    squashfs = os.path.join(home, "squashfs-root")
    if os.path.isdir(squashfs):
        shutil.rmtree(squashfs, ignore_errors=True)
        removed.append(squashfs)

    # 5) 尝试 dpkg/apt 卸载
    try:
        r = subprocess.run(["dpkg", "-l", "cursor"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "cursor" in (r.stdout or ""):
            subprocess.run(["sudo", "apt", "remove", "-y", "cursor"],
                           capture_output=True, timeout=60)
            removed.append("apt:cursor")
    except Exception:
        pass

    # 6) 删除所有数据、缓存、配置目录
    data_dirs = [
        os.path.join(home, ".config/Cursor"),
        os.path.join(home, ".config/cursor-updater"),
        os.path.join(home, ".cache/Cursor"),
        os.path.join(home, ".local/share/Cursor"),
        os.path.join(home, ".cursor"),
        os.path.join(home, ".cursor-server"),
    ]
    for pattern in _glob.glob(os.path.join(home, ".cursor*")):
        if pattern not in data_dirs:
            data_dirs.append(pattern)

    for d in data_dirs:
        try:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                removed.append(d)
            elif os.path.isfile(d):
                os.remove(d)
                removed.append(d)
        except Exception:
            pass

    # 7) 移除 Desktop Entry 和 Icon
    desktop_dirs = [
        os.path.join(home, ".local/share/applications"),
        "/usr/share/applications",
    ]
    for dd in desktop_dirs:
        if not os.path.isdir(dd):
            continue
        for pattern in ["cursor*.desktop", "co.anysphere.cursor*.desktop"]:
            for f in _glob.glob(os.path.join(dd, pattern)):
                try:
                    os.remove(f)
                    removed.append(f)
                except Exception:
                    pass

    icon_dirs = [
        os.path.join(home, ".local/share/icons"),
        "/usr/share/icons/hicolor/512x512/apps",
        "/usr/share/icons/hicolor/256x256/apps",
        "/usr/share/icons/hicolor/128x128/apps",
        "/usr/share/pixmaps",
    ]
    for icon_dir in icon_dirs:
        if not os.path.isdir(icon_dir):
            continue
        for f in _glob.glob(os.path.join(icon_dir, "cursor*")):
            try:
                os.remove(f)
                removed.append(f)
            except Exception:
                pass
        for f in _glob.glob(os.path.join(icon_dir, "co.anysphere.cursor*")):
            try:
                os.remove(f)
                removed.append(f)
            except Exception:
                pass

    # 8) 刷新桌面数据库
    try:
        subprocess.run(["update-desktop-database",
                        os.path.join(home, ".local/share/applications")],
                       capture_output=True, timeout=10)
    except Exception:
        pass

    if not removed:
        return False, "未找到 Cursor 安装，无需卸载"

    return True, f"已彻底卸载 Cursor，清理了 {len(removed)} 个项目"
