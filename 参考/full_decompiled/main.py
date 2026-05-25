"""AI助手 - 入口文件（兼容 macOS Intel/Apple Silicon + Windows）"""

import sys
import os
import platform
import traceback
import logging


def _log_dir() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "WuxianAssistant", "logs")
    elif system == "Darwin":
        d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "WuxianAssistant", "logs")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "WuxianAssistant", "logs")
    os.makedirs(d, exist_ok=True)
    return d


def _setup_logging() -> str:
    log_path = os.path.join(_log_dir(), "app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


_LOG_PATH = _setup_logging()
logging.info(f"日志路径: {_LOG_PATH}")


def _show_fatal_error(title: str, msg: str):
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, msg)
    except Exception:
        print(f"[FATAL] {title}: {msg}")


if __name__ == "__main__":
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon

        app = QApplication(sys.argv)
        app.setApplicationName("AI助手")

        # 高DPI支持
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"启动失败: {traceback.format_exc()}")
        _show_fatal_error("启动失败", f"程序启动异常:\n{e}\n\n详细日志: {_LOG_PATH}")
        sys.exit(1)
