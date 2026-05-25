"""Kiro 注册进度对话框 — 展示注册日志 + 完成后自动登录"""

from __future__ import annotations

import json
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor


class KiroRegisterDialog(QDialog):
    """模态对话框：展示 Kiro 注册过程的实时日志。

    完成后 result_ready 信号携带凭证 dict（或 None 表示失败）。
    """

    _append_log = Signal(str)
    _set_status = Signal(str, str)  # (text, color_type: "running" | "success" | "error")
    result_ready = Signal(object)

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._result: dict | None = None
        self._finished = False
        self._worker_thread: threading.Thread | None = None

        self.setWindowTitle("Kiro 注册")
        self.setMinimumSize(520, 420)
        self.resize(560, 480)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._build_ui()
        self._append_log.connect(self._on_append_log)
        self._set_status.connect(self._on_set_status)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border-radius: 16px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # 顶部：标题 + 状态
        header = QHBoxLayout()
        header.setSpacing(14)

        title = QLabel("Kiro 注册")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #0f172a; "
            "letter-spacing: -0.3px;"
        )
        header.addWidget(title)

        self._status_label = QLabel("准备中...")
        self._status_label.setStyleSheet(
            "font-size: 13px; font-weight: 500; color: #6366f1; "
            "padding: 2px 0;"
        )
        header.addWidget(self._status_label, 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch()

        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(32, 32)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; color: #64748b; border: none;
                border-radius: 16px; font-size: 18px; font-weight: 600;
            }
            QPushButton:hover { background: #e2e8f0; color: #334155; }
        """)
        self._close_btn.clicked.connect(self._on_close)
        header.addWidget(self._close_btn)

        root.addLayout(header)

        # 分割线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #e2e8f0;")
        root.addWidget(sep)

        # 日志滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._log_container = QWidget()
        self._log_container.setStyleSheet("background: transparent;")
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setContentsMargins(16, 12, 16, 12)
        self._log_layout.setSpacing(4)
        self._log_layout.addStretch()

        scroll.setWidget(self._log_container)
        self._scroll = scroll
        root.addWidget(scroll, 1)

        # 底部按钮区
        self._bottom_row = QHBoxLayout()
        self._bottom_row.setSpacing(12)
        self._bottom_row.addStretch()

        self._action_btn = QPushButton("取消")
        self._action_btn.setFixedHeight(38)
        self._action_btn.setMinimumWidth(100)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;
                border-radius: 10px; font-size: 13px; font-weight: 600;
                padding: 0 24px;
            }
            QPushButton:hover { background: #e2e8f0; }
        """)
        self._action_btn.clicked.connect(self._on_close)
        self._bottom_row.addWidget(self._action_btn)

        root.addLayout(self._bottom_row)

    # ------------------------------------------------------------------ 启动
    def start(self):
        """启动注册流程。"""
        self._set_status.emit("注册中...", "running")
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def _worker(self):
        from core.kiro_protocol_register import KiroProtocolRegister

        runner = KiroProtocolRegister(
            api_client=self.api,
            progress_fn=lambda msg: self._append_log.emit(msg),
        )
        try:
            result = runner.run()
            self._result = result
            self._append_log.emit("注册并登录成功！")
            self._set_status.emit("注册成功", "success")

            # 写入本地 Kiro 认证
            self._append_log.emit("正在写入本地认证...")
            self._write_local_auth(result)

            # 重启 Kiro
            self._append_log.emit("正在启动 Kiro...")
            self._restart_kiro()

            self._append_log.emit("全部完成！")
            self._finished = True
            QMetaObject.invokeMethod(self, "_on_worker_done", Qt.ConnectionType.QueuedConnection)

        except Exception as e:
            err_msg = str(e) or "未知错误，请检查网络连接后重试"
            self._append_log.emit(f"注册失败: {err_msg}")
            self._set_status.emit("注册失败", "error")
            self._finished = True
            QMetaObject.invokeMethod(self, "_on_worker_done", Qt.ConnectionType.QueuedConnection)

    def _write_local_auth(self, result: dict):
        from core.kiro_auth import KiroAuthManager
        auth = KiroAuthManager()
        auth.write_auth(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            client_id=result["client_id"],
            client_secret=result["client_secret"],
            client_id_hash=result["client_id_hash"],
            region=result.get("region", "us-east-1"),
        )

    def _restart_kiro(self):
        from core.kiro_process import exit_kiro, open_kiro
        exit_kiro(timeout=8)
        open_kiro()

    # ------------------------------------------------------------------ Slots
    @Slot(str)
    def _on_append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        label = QLabel(f"[{ts}]  {msg}")
        label.setWordWrap(True)
        label.setStyleSheet(
            "font-size: 13px; color: #334155; font-family: 'Menlo', 'Consolas', monospace; "
            "background: transparent; padding: 2px 0; line-height: 1.5;"
        )
        # 在 stretch 之前插入
        count = self._log_layout.count()
        self._log_layout.insertWidget(count - 1, label)

        # 自动滚动到底部
        vbar = self._scroll.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    @Slot(str, str)
    def _on_set_status(self, text: str, color_type: str):
        colors = {
            "running": "#6366f1",
            "success": "#059669",
            "error": "#dc2626",
        }
        color = colors.get(color_type, "#6366f1")
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {color}; padding: 2px 0;"
        )

    @Slot()
    def _on_worker_done(self):
        self._action_btn.setText("关闭")
        self._action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #f59e0b, stop:1 #f97316);
                color: #fff; border: none;
                border-radius: 10px; font-size: 13px; font-weight: 600;
                padding: 0 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #d97706, stop:1 #f59e0b);
            }
        """)
        self.result_ready.emit(self._result)

    def _on_close(self):
        self.close()

    def get_result(self) -> dict | None:
        return self._result
