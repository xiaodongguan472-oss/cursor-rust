"""公告弹窗 — 仿 Sub2API 风格的公告通知"""
from __future__ import annotations

import json
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


def _seen_file_path() -> str:
    """返回已读公告 ID 的持久化文件路径（跨平台，复用 api.client 的 CONFIG_DIR）"""
    try:
        from api.client import CONFIG_DIR
    except Exception:
        CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
    return os.path.join(CONFIG_DIR, "announcements_seen.json")


def _load_seen_ids() -> set:
    try:
        path = _seen_file_path()
        if not os.path.exists(path):
            return set()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        ids = data.get("ids", [])
        return {str(x) for x in ids}
    except Exception:
        return set()


def _save_seen_ids(ids: set) -> None:
    try:
        path = _seen_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ids": sorted(ids)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class AnnouncementDialog(QDialog):
    """Show announcements in a beautiful popup dialog, one at a time."""

    def __init__(self, announcements: list[dict], parent=None):
        super().__init__(parent)
        self._announcements = [a for a in announcements if a.get("notifyMode", "popup") == "popup"]
        self._index = 0

        self.setWindowTitle("公告")
        self.setMinimumSize(560, 400)
        self.resize(620, 480)
        self.setModal(True)
        self.setStyleSheet("QDialog { background: #ffffff; border-radius: 16px; }")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._build()
        if self._announcements:
            self._show_announcement(0)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #eef2ff, stop:0.5 #e0e7ff, stop:1 #f5f3ff); }"
        )
        hdr_layout = QVBoxLayout(self._header)
        hdr_layout.setContentsMargins(28, 24, 28, 20)
        hdr_layout.setSpacing(10)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)

        icon_frame = QFrame()
        icon_frame.setFixedSize(42, 42)
        icon_frame.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4f46e5, stop:1 #6366f1);"
            "border-radius: 14px; }"
        )
        icon_lbl = QLabel("🔔")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        icon_inner = QVBoxLayout(icon_frame)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        icon_inner.addWidget(icon_lbl)

        badge = QLabel("公告通知")
        badge.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #4f46e5, stop:1 #6366f1);"
            "color: white; font-size: 11px; font-weight: 700;"
            "border-radius: 10px; padding: 4px 14px;"
        )

        badge_row.addWidget(icon_frame)
        badge_row.addWidget(badge)
        badge_row.addStretch()

        self._counter_lbl = QLabel()
        self._counter_lbl.setStyleSheet(
            "font-size: 11px; color: #4f46e5; font-weight: 600;"
            "background: transparent; border: none;"
        )
        badge_row.addWidget(self._counter_lbl)
        hdr_layout.addLayout(badge_row)

        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #0f172a;"
            "letter-spacing: -0.3px; background: transparent; border: none;"
        )
        hdr_layout.addWidget(self._title_lbl)

        self._time_lbl = QLabel()
        self._time_lbl.setStyleSheet(
            "font-size: 12px; color: #78716c; background: transparent; border: none;"
        )
        hdr_layout.addWidget(self._time_lbl)

        root.addWidget(self._header)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #c7d2fe; border: none;")
        root.addWidget(sep)

        # Body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: white; border: none; }"
        )

        body_widget = QWidget()
        body_widget.setStyleSheet("background: white;")
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(28, 24, 28, 24)
        body_layout.setSpacing(16)

        accent_bar = QFrame()
        accent_bar.setFixedWidth(3)
        accent_bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #4f46e5, stop:0.5 #6366f1, stop:1 #a78bfa);"
            "border-radius: 2px; border: none;"
        )
        body_layout.addWidget(accent_bar, 0, Qt.AlignmentFlag.AlignTop)

        self._content_lbl = QLabel()
        self._content_lbl.setWordWrap(True)
        self._content_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._content_lbl.setStyleSheet(
            "font-size: 14px; color: #334155; line-height: 1.7;"
            "background: transparent; border: none; padding: 0;"
        )
        self._content_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        body_layout.addWidget(self._content_lbl, 1)

        scroll.setWidget(body_widget)
        root.addWidget(scroll, 1)

        # Footer
        footer = QWidget()
        footer.setStyleSheet("background: #fafbfc; border-top: 1px solid #f1f5f9;")
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(28, 14, 28, 14)
        ft_layout.setSpacing(12)

        self._prev_btn = QPushButton("上一条")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #64748b; border: 1.5px solid #e2e8f0;"
            "  border-radius: 10px; padding: 8px 18px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #f1f5f9; border-color: #cbd5e1; }"
            "QPushButton:disabled { color: #cbd5e1; border-color: #f1f5f9; }"
        )
        self._prev_btn.clicked.connect(self._go_prev)

        self._next_btn = QPushButton("下一条")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #64748b; border: 1.5px solid #e2e8f0;"
            "  border-radius: 10px; padding: 8px 18px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #f1f5f9; border-color: #cbd5e1; }"
            "QPushButton:disabled { color: #cbd5e1; border-color: #f1f5f9; }"
        )
        self._next_btn.clicked.connect(self._go_next)

        self._ok_btn = QPushButton("我知道了")
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #4f46e5, stop:1 #6366f1);"
            "  color: white; border: none; border-radius: 12px;"
            "  padding: 9px 26px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #4338ca, stop:1 #4f46e5); }"
        )
        shadow = QGraphicsDropShadowEffect(self._ok_btn)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(99, 102, 241, 80))
        self._ok_btn.setGraphicsEffect(shadow)
        self._ok_btn.clicked.connect(self.accept)

        ft_layout.addWidget(self._prev_btn)
        ft_layout.addWidget(self._next_btn)
        ft_layout.addStretch()
        ft_layout.addWidget(self._ok_btn)

        root.addWidget(footer)

    def _show_announcement(self, idx: int):
        if idx < 0 or idx >= len(self._announcements):
            return
        self._index = idx
        a = self._announcements[idx]

        self._title_lbl.setText(a.get("title", ""))
        self._content_lbl.setText(a.get("content", ""))

        ct = a.get("createTime", "")
        if ct:
            self._time_lbl.setText(str(ct)[:16].replace("T", " "))
        else:
            self._time_lbl.setText("")

        total = len(self._announcements)
        if total > 1:
            self._counter_lbl.setText(f"{idx + 1} / {total}")
            self._prev_btn.setVisible(True)
            self._next_btn.setVisible(True)
            self._prev_btn.setEnabled(idx > 0)
            self._next_btn.setEnabled(idx < total - 1)
        else:
            self._counter_lbl.setText("")
            self._prev_btn.setVisible(False)
            self._next_btn.setVisible(False)

    def _go_prev(self):
        if self._index > 0:
            self._show_announcement(self._index - 1)

    def _go_next(self):
        if self._index < len(self._announcements) - 1:
            self._show_announcement(self._index + 1)

    def _mark_all_seen(self) -> None:
        """把当前对话框里所有公告 ID 记为已读，持久化到本地。"""
        seen = _load_seen_ids()
        for a in self._announcements:
            aid = a.get("id")
            if aid is None:
                continue
            seen.add(str(aid))
        _save_seen_ids(seen)

    def accept(self):
        self._mark_all_seen()
        super().accept()

    def reject(self):
        # 用户按 ESC / 点 X 关闭也算已读，避免下次再弹
        self._mark_all_seen()
        super().reject()

    @staticmethod
    def show_announcements(announcements: list[dict], parent=None):
        popup_list = [a for a in announcements if a.get("notifyMode", "popup") == "popup"]
        if not popup_list:
            return

        # 过滤掉已读过的公告；无 id 的视为"无法标记"，只展示一次即可（本次会话之后会被记入 seen，但没有 id 就无从记录，仍然会再弹——这里直接不弹，避免骚扰）
        seen = _load_seen_ids()
        unseen = [
            a for a in popup_list
            if a.get("id") is not None and str(a.get("id")) not in seen
        ]
        if not unseen:
            return

        dlg = AnnouncementDialog(unseen, parent)
        dlg.exec()
