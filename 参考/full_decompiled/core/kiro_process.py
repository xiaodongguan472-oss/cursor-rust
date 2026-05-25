"""Kiro 进程管理 — 退出、启动（不依赖 psutil）"""
from __future__ import annotations

import errno
import os
import sys
import time
import subprocess
import platform

_STARTUP_NO_WINDOW: dict = {}
if sys.platform == "win32":
    _si = subprocess.STARTUPINFO()
    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _si.wShowWindow = 0
    _STARTUP_NO_WINDOW = {"startupinfo": _si, "creationflags": 0x08000000}


def _is_kiro_running() -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(["pgrep", "-x", "Kiro"], capture_output=True)
            return r.returncode == 0
        elif system == "Windows":
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Kiro.exe"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                **_STARTUP_NO_WINDOW,
            )
            return "Kiro.exe" in (r.stdout or "")
        else:
            r = subprocess.run(["pgrep", "-x", "kiro"], capture_output=True)
            return r.returncode == 0
    except Exception:
        return False


def exit_kiro(timeout: int = 5) -> bool:
    system = platform.system()

    if not _is_kiro_running():
        print("未发现运行中的 Kiro 进程")
        return True

    print("开始退出 Kiro...")

    try:
        if system == "Darwin":
            subprocess.run(["pkill", "-x", "Kiro"], capture_output=True)
        elif system == "Windows":
            subprocess.run(
                ["taskkill", "/IM", "Kiro.exe"],
                capture_output=True, **_STARTUP_NO_WINDOW,
            )
        else:
            subprocess.run(["pkill", "-x", "kiro"], capture_output=True)
    except Exception as e:
        print(f"发送终止信号失败: {e}")

    start = time.time()
    while time.time() - start < timeout:
        if not _is_kiro_running():
            print("所有 Kiro 进程已正常关闭")
            return True
        time.sleep(0.5)

    print("Kiro 未响应，强制结束...")
    try:
        if system == "Darwin":
            subprocess.run(["pkill", "-9", "-x", "Kiro"], capture_output=True)
            subprocess.run(["pkill", "-9", "-f", "Kiro Helper"], capture_output=True)
        elif system == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/IM", "Kiro.exe", "/T"],
                capture_output=True, **_STARTUP_NO_WINDOW,
            )
        else:
            subprocess.run(["pkill", "-9", "-x", "kiro"], capture_output=True)
    except Exception as e:
        print(f"强制结束失败: {e}")

    time.sleep(1)

    if _is_kiro_running():
        print("仍有 Kiro 进程未能关闭")
        return False

    print("所有 Kiro 进程已强制关闭")
    return True


def _find_kiro_executable() -> str | None:
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Kiro.app/Contents/MacOS/Kiro",
            os.path.expanduser("~/Applications/Kiro.app/Contents/MacOS/Kiro"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    elif system == "Windows":
        appdata = os.getenv("LOCALAPPDATA") or ""
        candidates = [
            os.path.join(appdata, "Programs", "kiro", "Kiro.exe"),
            os.path.join(appdata, "Programs", "Kiro", "Kiro.exe"),
            os.path.join(appdata, "kiro", "Kiro.exe"),
            os.path.join(appdata, "Kiro", "Kiro.exe"),
        ]
        pf = os.getenv("PROGRAMFILES", "C:\\Program Files")
        pf86 = os.getenv("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        candidates += [
            os.path.join(pf, "Kiro", "Kiro.exe"),
            os.path.join(pf86, "Kiro", "Kiro.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        import shutil as _shutil
        which = _shutil.which("kiro")
        if which:
            return which
    else:
        import shutil as _shutil
        which = _shutil.which("kiro")
        if which:
            return which
        linux_candidates = [
            "/usr/bin/kiro",
            "/usr/local/bin/kiro",
            os.path.expanduser("~/.local/bin/kiro"),
        ]
        for p in linux_candidates:
            if os.path.isfile(p):
                return p
    return None


def _popen_detached_gui(argv: list) -> subprocess.Popen:
    system = platform.system()
    devnull = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if system == "Windows":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        flags_try = (
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )
        for fl in flags_try:
            try:
                return subprocess.Popen(argv, creationflags=fl, close_fds=True, **devnull)
            except OSError:
                continue
        return subprocess.Popen(argv, **devnull)

    return subprocess.Popen(argv, start_new_session=True, close_fds=True, **devnull)


def open_kiro() -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(
                ["open", "-n", "-a", "Kiro"],
                capture_output=True,
                timeout=30,
            )
            if r.returncode == 0:
                print("Kiro 已启动 (open -a)")
                return True
            exe = _find_kiro_executable()
            if not exe:
                print("未找到 Kiro 安装路径")
                return False
            _popen_detached_gui([exe])
            print(f"Kiro 已启动: {exe}")
            return True

        exe = _find_kiro_executable()
        if not exe:
            print("未找到 Kiro 安装路径")
            return False
        _popen_detached_gui([exe])
        print(f"Kiro 已启动: {exe}")
        return True
    except OSError as e:
        if e.errno == errno.EPIPE:
            print("Error: Broken pipe (EPIPE)")
        else:
            print(f"启动 Kiro 失败: {e}")
        return False
    except Exception as e:
        print(f"启动 Kiro 失败: {e}")
        return False
