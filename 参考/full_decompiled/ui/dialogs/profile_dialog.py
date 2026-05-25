"""用户个人资料编辑弹窗"""
from __future__ import annotations

import threading

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QGraphicsDropShadowEffect, QWidget,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor

_AVATAR_GRADIENTS = [
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6366f1, stop:1 #8b5cf6)",
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0ea5e9, stop:1 #6366f1)",
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #10b981, stop:1 #059669)",
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #f59e0b, stop:1 #ef4444)",
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ec4899, stop:1 #8b5cf6)",
    "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #14b8a6, stop:1 #0ea5e9)",
]


def _avatar_gradient(name: str) -> str:
    h = sum(ord(c) for c in name) if name else 0
    return _AVATAR_GRADIENTS[h % len(_AVATAR_GRADIENTS)]


def _user_initials(name: str) -> str:
    if not name:
        return "U"
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    s = name.strip()
    if len(s) >= 2 and all(ord(c) < 128 for c in s[:2]):
        return s[:2].upper()
    return s[0].upper()


_INPUT_STYLE = (
    "QLineEdit { "
    "  background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px; "
    "  padding: 0 14px; font-size: 13px; color: #0f172a; }"
    "QLineEdit:hover { border-color: #cbd5e1; background: #ffffff; }"
    "QLineEdit:focus { border-color: #6366f1; background: #ffffff; }"
)


class ProfileDialog(QDialog):
    nickname_changed = Signal(str)

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self.setWindowTitle("个人设置")
        self.setFixedSize(420, 620)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(
            "QDialog { background: #f8fafc; }"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        info = self.api.user_info
        email_str = info.get("email", "")
        nick_str = info.get("nickname", email_str.split("@")[0] if email_str else "")

        # Header with avatar
        header = QWidget()
        header.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "  stop:0 #312e81, stop:0.5 #4338ca, stop:1 #6366f1); }"
        )
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 28, 0, 24)
        hl.setSpacing(10)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        initials = _user_initials(nick_str)
        avatar_bg = _avatar_gradient(nick_str)
        self._header_avatar = QLabel(initials)
        self._header_avatar.setFixedSize(64, 64)
        self._header_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header_avatar.setStyleSheet(
            f"background: rgba(255,255,255,0.2); color: #ffffff; font-size: 24px; "
            f"font-weight: 800; border-radius: 32px; border: 2.5px solid rgba(255,255,255,0.3);"
        )
        hl.addWidget(self._header_avatar, 0, Qt.AlignmentFlag.AlignCenter)

        self._header_name = QLabel(nick_str)
        self._header_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header_name.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 700; background: transparent;"
        )
        hl.addWidget(self._header_name)

        email_lbl = QLabel(email_str)
        email_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        email_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 12px; background: transparent;"
        )
        hl.addWidget(email_lbl)

        root.addWidget(header)

        # Body
        body = QWidget()
        body.setStyleSheet("background: #f8fafc;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 28, 28, 24)
        bl.setSpacing(0)

        # ---- Section: Change Nickname ----
        sec1_title = QLabel("修改昵称")
        sec1_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1e293b; "
            "background: transparent; margin-bottom: 8px;"
        )
        bl.addWidget(sec1_title)

        self._nick_input = QLineEdit()
        self._nick_input.setPlaceholderText("输入新昵称")
        self._nick_input.setText(nick_str)
        self._nick_input.setFixedHeight(40)
        self._nick_input.setStyleSheet(_INPUT_STYLE)
        bl.addWidget(self._nick_input)
        bl.addSpacing(12)

        self._nick_btn = QPushButton("保存昵称")
        self._nick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nick_btn.setFixedHeight(38)
        self._nick_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: #fff; border: none; "
            "  border-radius: 10px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #4338ca; }"
            "QPushButton:pressed { background: #3730a3; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self._nick_btn.clicked.connect(self._save_nickname)
        bl.addWidget(self._nick_btn)

        self._nick_msg = QLabel()
        self._nick_msg.setWordWrap(True)
        self._nick_msg.setVisible(False)
        self._nick_msg.setStyleSheet(
            "font-size: 12px; padding: 6px 10px; border-radius: 8px; "
            "background: transparent; margin-top: 4px;"
        )
        bl.addWidget(self._nick_msg)
        bl.addSpacing(20)

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #e2e8f0; border: none;")
        bl.addWidget(div)
        bl.addSpacing(20)

        # ---- Section: Change Password ----
        sec2_title = QLabel("修改密码")
        sec2_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1e293b; "
            "background: transparent; margin-bottom: 8px;"
        )
        bl.addWidget(sec2_title)

        self._old_pwd = QLineEdit()
        self._old_pwd.setPlaceholderText("当前密码")
        self._old_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._old_pwd.setFixedHeight(40)
        self._old_pwd.setStyleSheet(_INPUT_STYLE)
        bl.addWidget(self._old_pwd)
        bl.addSpacing(10)

        self._new_pwd = QLineEdit()
        self._new_pwd.setPlaceholderText("新密码（至少6位）")
        self._new_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pwd.setFixedHeight(40)
        self._new_pwd.setStyleSheet(_INPUT_STYLE)
        bl.addWidget(self._new_pwd)
        bl.addSpacing(10)

        self._confirm_pwd = QLineEdit()
        self._confirm_pwd.setPlaceholderText("确认新密码")
        self._confirm_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_pwd.setFixedHeight(40)
        self._confirm_pwd.setStyleSheet(_INPUT_STYLE)
        bl.addWidget(self._confirm_pwd)
        bl.addSpacing(14)

        self._pwd_btn = QPushButton("修改密码")
        self._pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pwd_btn.setFixedHeight(38)
        self._pwd_btn.setStyleSheet(
            "QPushButton { background: #0f172a; color: #fff; border: none; "
            "  border-radius: 10px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #1e293b; }"
            "QPushButton:pressed { background: #334155; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self._pwd_btn.clicked.connect(self._save_password)
        bl.addWidget(self._pwd_btn)

        self._pwd_msg = QLabel()
        self._pwd_msg.setWordWrap(True)
        self._pwd_msg.setVisible(False)
        self._pwd_msg.setStyleSheet(
            "font-size: 12px; padding: 6px 10px; border-radius: 8px; "
            "background: transparent; margin-top: 4px;"
        )
        bl.addWidget(self._pwd_msg)
        bl.addStretch()

        # Logout button at bottom
        logout_btn = QPushButton("退出登录")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFixedHeight(38)
        logout_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: 1.5px solid #fecaca; "
            "  border-radius: 10px; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: #fef2f2; border-color: #ef4444; }"
            "QPushButton:pressed { background: #fee2e2; }"
        )
        logout_btn.clicked.connect(self._do_logout)
        bl.addWidget(logout_btn)

        root.addWidget(body, 1)

    def _show_msg(self, label: QLabel, text: str, is_error: bool):
        label.setText(text)
        if is_error:
            label.setStyleSheet(
                "font-size: 12px; padding: 6px 10px; border-radius: 8px; "
                "color: #dc2626; background: #fef2f2; margin-top: 4px;"
            )
        else:
            label.setStyleSheet(
                "font-size: 12px; padding: 6px 10px; border-radius: 8px; "
                "color: #059669; background: #ecfdf5; margin-top: 4px;"
            )
        label.setVisible(True)

    def _save_nickname(self):
        nick = self._nick_input.text().strip()
        if not nick:
            self._show_msg(self._nick_msg, "昵称不能为空", True)
            return
        self._nick_btn.setEnabled(False)
        self._nick_btn.setText("保存中...")
        threading.Thread(target=self._bg_save_nick, args=(nick,), daemon=True).start()

    def _bg_save_nick(self, nick):
        self._nick_resp = self.api.update_nickname(nick)
        QMetaObject.invokeMethod(self, "_apply_nick", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_nick(self):
        self._nick_btn.setEnabled(True)
        self._nick_btn.setText("保存昵称")
        r = self._nick_resp
        if r.get("success"):
            new_nick = r.get("data", {}).get("nickname", self._nick_input.text().strip())
            self._header_name.setText(new_nick)
            self._header_avatar.setText(_user_initials(new_nick))
            self._show_msg(self._nick_msg, "昵称已更新", False)
            self.nickname_changed.emit(new_nick)
        else:
            self._show_msg(self._nick_msg, r.get("message", "更新失败"), True)

    def _save_password(self):
        old_pwd = self._old_pwd.text()
        new_pwd = self._new_pwd.text()
        confirm = self._confirm_pwd.text()
        if not old_pwd:
            self._show_msg(self._pwd_msg, "请输入当前密码", True)
            return
        if len(new_pwd) < 6:
            self._show_msg(self._pwd_msg, "新密码不能少于6位", True)
            return
        if new_pwd != confirm:
            self._show_msg(self._pwd_msg, "两次输入的新密码不一致", True)
            return
        self._pwd_btn.setEnabled(False)
        self._pwd_btn.setText("修改中...")
        threading.Thread(target=self._bg_save_pwd, args=(old_pwd, new_pwd), daemon=True).start()

    def _bg_save_pwd(self, old_pwd, new_pwd):
        self._pwd_resp = self.api.update_password(old_pwd, new_pwd)
        QMetaObject.invokeMethod(self, "_apply_pwd", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_pwd(self):
        self._pwd_btn.setEnabled(True)
        self._pwd_btn.setText("修改密码")
        r = self._pwd_resp
        if r.get("success"):
            self._show_msg(self._pwd_msg, "密码已修改", False)
            self._old_pwd.clear()
            self._new_pwd.clear()
            self._confirm_pwd.clear()
        else:
            self._show_msg(self._pwd_msg, r.get("message", "修改失败"), True)

    def _do_logout(self):
        self._logout_requested = True
        self.accept()
