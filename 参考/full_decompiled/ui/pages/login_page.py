"""登录/注册页面 — 专业现代设计"""

import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QGraphicsDropShadowEffect, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor

from ui.dialogs.policy_dialog import PolicyDialog


_INPUT_H = 46


def _make_input(placeholder: str, echo=QLineEdit.EchoMode.Normal) -> QLineEdit:
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(_INPUT_H)
    inp.setEchoMode(echo)
    inp.setStyleSheet(
        "QLineEdit { "
        "  background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 14px; "
        "  padding: 0 18px; font-size: 14px; color: #0f172a; }"
        "QLineEdit:hover { border-color: #cbd5e1; background: #ffffff; }"
        "QLineEdit:focus { border-color: #6366f1; background: #ffffff; "
        "  }"
    )
    return inp


class LoginPage(QWidget):
    login_success = Signal()

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._is_register = False
        self._build()

    def _build(self):
        self.setStyleSheet("background: #0f172a;")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ==================== Left: Branding Panel ====================
        left = QWidget()
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "  stop:0 #1e1b4b, stop:0.3 #312e81, stop:0.7 #3730a3, stop:1 #4338ca); }"
        )
        lv = QVBoxLayout(left)
        lv.setContentsMargins(48, 0, 48, 0)
        lv.setSpacing(0)
        lv.addStretch(3)

        app_title = QLabel("AI助手")
        app_title.setStyleSheet(
            "font-size: 28px; font-weight: 800; color: #ffffff; "
            "letter-spacing: -0.5px; background: transparent; border: none;"
        )
        app_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lv.addWidget(app_title)
        lv.addSpacing(16)

        tagline = QLabel("聚合 AI 编程工具，一站式管理")
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            "font-size: 16px; color: rgba(255,255,255,0.7); font-weight: 400;"
            "line-height: 1.6; background: transparent; border: none;"
        )
        lv.addWidget(tagline)
        lv.addSpacing(32)

        features = [
            ("→", "Cursor", "智能代码编辑器", "#818cf8"),
            ("→", "Kiro", "AWS AI 编程助手", "#22d3ee"),
            ("→", "Codex / Claude / Gemini", "多平台 API 密钥管理", "#34d399"),
        ]
        for arrow, name, desc, dot_color in features:
            fr = QHBoxLayout()
            fr.setSpacing(12)
            dot = QFrame()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background: {dot_color}; border-radius: 4px; border: none;"
            )
            tc = QVBoxLayout()
            tc.setSpacing(2)
            n = QLabel(name)
            n.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #e0e7ff;"
                "background: transparent; border: none;"
            )
            d = QLabel(desc)
            d.setStyleSheet(
                "font-size: 12px; color: rgba(255,255,255,0.45); font-weight: 400;"
                "background: transparent; border: none;"
            )
            tc.addWidget(n)
            tc.addWidget(d)
            fr.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
            fr.addLayout(tc, 1)
            lv.addLayout(fr)
            lv.addSpacing(14)

        lv.addStretch(4)

        copyright_lbl = QLabel("© 2026 AI助手  ·  安全登录")
        copyright_lbl.setStyleSheet(
            "font-size: 11px; color: rgba(255,255,255,0.25); "
            "background: transparent; border: none;"
        )
        lv.addWidget(copyright_lbl)
        lv.addSpacing(24)

        root.addWidget(left, 5)

        # ==================== Right: Form Panel ====================
        right = QWidget()
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "  stop:0 #f8fafc, stop:1 #f1f5f9); }"
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addStretch(2)

        form_wrap = QHBoxLayout()
        form_wrap.addStretch(1)

        card = QFrame()
        card.setFixedWidth(380)
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 24px; }"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 18))
        card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(36, 44, 36, 36)
        cl.setSpacing(0)

        self._title = QLabel("欢迎回来")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; "
            "letter-spacing: -0.5px; background: transparent; border: none;"
        )
        cl.addWidget(self._title)

        self._subtitle = QLabel("登录您的账号以继续")
        self._subtitle.setStyleSheet(
            "font-size: 13px; color: #94a3b8; font-weight: 400; "
            "background: transparent; border: none; margin-top: 4px;"
        )
        cl.addWidget(self._subtitle)
        cl.addSpacing(28)

        # Username / Email
        email_lbl = QLabel("邮箱")
        email_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #475569; "
            "background: transparent; border: none; margin-bottom: 6px;"
        )
        cl.addWidget(email_lbl)
        self._email = _make_input("请输入邮箱地址")
        cl.addWidget(self._email)
        cl.addSpacing(16)

        # Password
        pwd_lbl = QLabel("密码")
        pwd_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #475569; "
            "background: transparent; border: none; margin-bottom: 6px;"
        )
        cl.addWidget(pwd_lbl)
        self._password = _make_input("至少 6 位", QLineEdit.EchoMode.Password)
        cl.addWidget(self._password)
        cl.addSpacing(16)

        # Confirm password (register only)
        self._confirm_lbl = QLabel("确认密码")
        self._confirm_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #475569; "
            "background: transparent; border: none; margin-bottom: 6px;"
        )
        self._confirm_lbl.setVisible(False)
        cl.addWidget(self._confirm_lbl)
        self._confirm_pwd = _make_input("再次输入密码", QLineEdit.EchoMode.Password)
        self._confirm_pwd.setVisible(False)
        cl.addWidget(self._confirm_pwd)
        self._confirm_spacer = QWidget()
        self._confirm_spacer.setFixedHeight(16)
        self._confirm_spacer.setVisible(False)
        self._confirm_spacer.setStyleSheet("background: transparent; border: none;")
        cl.addWidget(self._confirm_spacer)

        # Error
        self._error_lbl = QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            "color: #ef4444; font-size: 13px; font-weight: 500; "
            "background: #fef2f2; border: 1px solid #fecaca; "
            "border-radius: 10px; padding: 10px 14px;"
        )
        self._error_lbl.setVisible(False)
        cl.addWidget(self._error_lbl)

        cl.addSpacing(4)

        # Primary button
        self._primary_btn = QPushButton("登  录")
        self._primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._primary_btn.setFixedHeight(48)
        self._primary_btn.setStyleSheet(
            "QPushButton { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4f46e5, stop:1 #6366f1);"
            "  color: #fff; border: none; border-radius: 14px; "
            "  font-size: 15px; font-weight: 700; letter-spacing: 1px; }"
            "QPushButton:hover { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4338ca, stop:1 #4f46e5); }"
            "QPushButton:pressed { background: #3730a3; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        btn_shadow = QGraphicsDropShadowEffect(self._primary_btn)
        btn_shadow.setBlurRadius(20)
        btn_shadow.setOffset(0, 6)
        btn_shadow.setColor(QColor(99, 102, 241, 80))
        self._primary_btn.setGraphicsEffect(btn_shadow)
        self._primary_btn.clicked.connect(self._on_primary)
        cl.addWidget(self._primary_btn)

        cl.addSpacing(16)

        # Divider
        div_row = QHBoxLayout()
        div_row.setSpacing(12)
        line1 = QFrame()
        line1.setFixedHeight(1)
        line1.setStyleSheet("background: #e2e8f0; border: none;")
        or_lbl = QLabel("或")
        or_lbl.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none;"
        )
        line2 = QFrame()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background: #e2e8f0; border: none;")
        div_row.addWidget(line1, 1)
        div_row.addWidget(or_lbl)
        div_row.addWidget(line2, 1)
        cl.addLayout(div_row)

        cl.addSpacing(16)

        # Toggle link
        self._toggle_btn = QPushButton("没有账号？立即注册")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setFixedHeight(44)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: #f8fafc; color: #4f46e5; "
            "  border: 1.5px solid #e2e8f0; border-radius: 14px; "
            "  font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #eef2ff; border-color: #c7d2fe; }"
            "QPushButton:pressed { background: #e0e7ff; }"
        )
        self._toggle_btn.clicked.connect(self._toggle_mode)
        cl.addWidget(self._toggle_btn)

        cl.addSpacing(16)

        policy_row = QHBoxLayout()
        policy_row.setSpacing(0)
        policy_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        _link_style = (
            "QPushButton { background: transparent; border: none; "
            "  color: #94a3b8; font-size: 11px; font-weight: 500; "
            "  padding: 2px 4px; }"
            "QPushButton:hover { color: #6366f1; }"
        )
        _sep_style = (
            "color: #cbd5e1; font-size: 11px; "
            "background: transparent; border: none;"
        )

        terms_btn = QPushButton("服务条款")
        terms_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        terms_btn.setStyleSheet(_link_style)
        terms_btn.clicked.connect(lambda: self._show_policy("terms"))

        sep1 = QLabel("·")
        sep1.setStyleSheet(_sep_style)

        privacy_btn = QPushButton("隐私政策")
        privacy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        privacy_btn.setStyleSheet(_link_style)
        privacy_btn.clicked.connect(lambda: self._show_policy("privacy"))

        sep2 = QLabel("·")
        sep2.setStyleSheet(_sep_style)

        usage_btn = QPushButton("使用政策")
        usage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        usage_btn.setStyleSheet(_link_style)
        usage_btn.clicked.connect(lambda: self._show_policy("usage"))

        policy_row.addWidget(terms_btn)
        policy_row.addWidget(sep1)
        policy_row.addWidget(privacy_btn)
        policy_row.addWidget(sep2)
        policy_row.addWidget(usage_btn)
        cl.addLayout(policy_row)

        form_wrap.addWidget(card)
        form_wrap.addStretch(1)
        rv.addLayout(form_wrap)
        rv.addStretch(3)

        root.addWidget(right, 4)

        self._email.returnPressed.connect(lambda: self._password.setFocus())
        self._password.returnPressed.connect(
            lambda: self._confirm_pwd.setFocus() if self._is_register else self._on_primary()
        )
        self._confirm_pwd.returnPressed.connect(self._on_primary)

    def _toggle_mode(self):
        self._is_register = not self._is_register
        self._error_lbl.setVisible(False)
        if self._is_register:
            self._title.setText("创建账号")
            self._subtitle.setText("注册一个新账号开始使用")
            self._primary_btn.setText("注  册")
            self._toggle_btn.setText("已有账号？返回登录")
            self._confirm_pwd.setVisible(True)
            self._confirm_lbl.setVisible(True)
            self._confirm_spacer.setVisible(True)
        else:
            self._title.setText("欢迎回来")
            self._subtitle.setText("登录您的账号以继续")
            self._primary_btn.setText("登  录")
            self._toggle_btn.setText("没有账号？立即注册")
            self._confirm_pwd.setVisible(False)
            self._confirm_lbl.setVisible(False)
            self._confirm_spacer.setVisible(False)

    def _on_primary(self):
        email = self._email.text().strip()
        pwd = self._password.text()
        if not email or not pwd:
            self._show_error("请输入邮箱和密码")
            return
        import re
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            self._show_error("请输入有效的邮箱地址")
            return
        if self._is_register:
            if len(pwd) < 6:
                self._show_error("密码不能少于6位")
                return
            if pwd != self._confirm_pwd.text():
                self._show_error("两次输入的密码不一致")
                return
        self._primary_btn.setEnabled(False)
        self._primary_btn.setText("请稍候...")
        self._error_lbl.setVisible(False)
        threading.Thread(
            target=self._bg_auth, args=(email, pwd, ""), daemon=True
        ).start()

    def _bg_auth(self, email, pwd, nick):
        if self._is_register:
            self._auth_resp = self.api.register(email, pwd, nick)
        else:
            self._auth_resp = self.api.login(email, pwd)
        QMetaObject.invokeMethod(self, "_apply_auth", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_auth(self):
        self._primary_btn.setEnabled(True)
        self._primary_btn.setText("注  册" if self._is_register else "登  录")
        r = self._auth_resp
        if r.get("success"):
            self._email.clear()
            self._password.clear()
            self._confirm_pwd.clear()
            self.login_success.emit()
        else:
            self._show_error(r.get("message", "操作失败，请重试"))

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    def _show_policy(self, key: str):
        dlg = PolicyDialog(key, self)
        dlg.exec()
