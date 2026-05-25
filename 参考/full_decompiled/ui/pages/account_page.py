"""账号管理页面 — 注册、登录、查看激活码"""

import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QScrollArea, QStackedWidget,
    QGraphicsDropShadowEffect, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Signal
from PySide6.QtGui import QColor


def _shadow(w, blur=20, y=4, alpha=18):
    s = QGraphicsDropShadowEffect(w)
    s.setBlurRadius(blur)
    s.setOffset(0, y)
    s.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(s)


def _card(parent=None) -> QFrame:
    c = QFrame(parent)
    c.setStyleSheet(
        "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; }"
    )
    _shadow(c)
    return c


_INPUT_H = 40
_BTN_STYLE_PRIMARY = (
    "QPushButton { "
    "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    "    stop:0 #2563eb, stop:1 #3b82f6);"
    "  color: #fff; border: none; border-radius: 10px; "
    "  padding: 0 28px; font-size: 14px; font-weight: 700; min-height: 40px; }"
    "QPushButton:hover { "
    "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    "    stop:0 #1d4ed8, stop:1 #2563eb); }"
    "QPushButton:pressed { background: #1e40af; }"
    "QPushButton:disabled { background: #94a3b8; }"
)

_BTN_STYLE_OUTLINE = (
    "QPushButton { background: transparent; color: #2563eb; "
    "  border: 1.5px solid #bfdbfe; border-radius: 10px; "
    "  padding: 0 28px; font-size: 14px; font-weight: 600; min-height: 40px; }"
    "QPushButton:hover { background: #eff6ff; border-color: #93c5fd; }"
    "QPushButton:pressed { background: #dbeafe; }"
)

_BTN_STYLE_DANGER = (
    "QPushButton { background: transparent; color: #ef4444; "
    "  border: 1.5px solid #fecaca; border-radius: 10px; "
    "  padding: 0 28px; font-size: 14px; font-weight: 600; min-height: 40px; }"
    "QPushButton:hover { background: #fef2f2; border-color: #fca5a5; }"
    "QPushButton:pressed { background: #fee2e2; }"
)


def _make_input(placeholder: str, echo_mode=QLineEdit.EchoMode.Normal) -> QLineEdit:
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(_INPUT_H)
    inp.setEchoMode(echo_mode)
    inp.setStyleSheet(
        "QLineEdit { "
        "  background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 10px; "
        "  padding: 0 14px; font-size: 14px; color: #0f172a; }"
        "QLineEdit:focus { border-color: #3b82f6; background: #ffffff; }"
    )
    return inp


class AccountPage(QWidget):
    """账号页面，根据登录状态切换 注册/登录 表单 和 账号管理面板"""

    account_state_changed = Signal(bool)

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setStyleSheet("background: #f4f6f9;")
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(40, 20, 40, 36)
        vbox.setSpacing(16)

        hdr_row = QHBoxLayout()
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(2)
        title = QLabel("账号管理")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;"
        )
        sub = QLabel("登录账号后，换设备只需登录即可自动恢复所有激活")
        sub.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addLayout(hdr_col)
        hdr_row.addStretch()
        vbox.addLayout(hdr_row)

        bar = QFrame()
        bar.setFixedHeight(2)
        bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #6366f1, stop:0.5 #8b5cf6, stop:1 #c4b5fd);"
            "border-radius: 1px;"
        )
        vbox.addWidget(bar)

        self._stack = QStackedWidget()
        self._auth_form = self._build_auth_form()
        self._profile_panel = self._build_profile_panel()
        self._stack.addWidget(self._auth_form)
        self._stack.addWidget(self._profile_panel)
        vbox.addWidget(self._stack)

        vbox.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

        self._update_view()

    def _build_auth_form(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(16)

        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 28, 28, 28)
        cl.setSpacing(18)

        self._form_title = QLabel("登录账号")
        self._form_title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none;"
        )
        cl.addWidget(self._form_title)

        self._email_input = _make_input("邮箱地址")
        cl.addWidget(self._email_input)

        self._password_input = _make_input("密码（至少6位）", QLineEdit.EchoMode.Password)
        cl.addWidget(self._password_input)

        self._nickname_input = _make_input("昵称（选填，注册时使用）")
        cl.addWidget(self._nickname_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._login_btn = QPushButton("登  录")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(_BTN_STYLE_PRIMARY)
        self._login_btn.clicked.connect(self._on_login)

        self._register_btn = QPushButton("注  册")
        self._register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._register_btn.setStyleSheet(_BTN_STYLE_OUTLINE)
        self._register_btn.clicked.connect(self._on_register)

        btn_row.addWidget(self._login_btn)
        btn_row.addWidget(self._register_btn)
        cl.addLayout(btn_row)

        hint = QLabel("注册账号后，激活码将自动绑定到您的账号。换电脑只需登录即可。")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "font-size: 12px; color: #64748b; background: transparent; border: none;"
        )
        cl.addWidget(hint)

        vbox.addWidget(card)
        return w

    def _build_profile_panel(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(16)

        profile_card = _card()
        pl = QVBoxLayout(profile_card)
        pl.setContentsMargins(28, 24, 28, 24)
        pl.setSpacing(14)

        profile_hdr = QHBoxLayout()
        profile_hdr.setSpacing(14)

        avatar = QLabel("\U0001f464")
        avatar.setStyleSheet("font-size: 36px; background: transparent; border: none;")
        avatar.setFixedSize(50, 50)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._profile_nickname = QLabel("")
        self._profile_nickname.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none;"
        )
        self._profile_email = QLabel("")
        self._profile_email.setStyleSheet(
            "font-size: 13px; color: #64748b; "
            "background: transparent; border: none;"
        )
        info_col.addWidget(self._profile_nickname)
        info_col.addWidget(self._profile_email)

        profile_hdr.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)
        profile_hdr.addLayout(info_col, 1)
        pl.addLayout(profile_hdr)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self._logout_btn = QPushButton("退出登录")
        self._logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_btn.setStyleSheet(_BTN_STYLE_DANGER)
        self._logout_btn.clicked.connect(self._on_logout)

        action_row.addStretch()
        action_row.addWidget(self._logout_btn)
        pl.addLayout(action_row)

        vbox.addWidget(profile_card)

        sec_hdr = QHBoxLayout()
        sec_hdr.setSpacing(10)
        hdr_bar = QFrame()
        hdr_bar.setFrameShape(QFrame.Shape.NoFrame)
        hdr_bar.setFixedSize(4, 20)
        hdr_bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #059669, stop:1 #10b981);"
            "border-radius: 2px; border: none;"
        )
        sec_tt = QLabel("已绑定的激活码")
        sec_tt.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none; padding: 0;"
        )
        sec_hdr.addWidget(hdr_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_hdr.addWidget(sec_tt, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_hdr.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #2563eb; "
            "  border: 1px solid #bfdbfe; border-radius: 8px; "
            "  padding: 4px 14px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #eff6ff; }"
        )
        refresh_btn.clicked.connect(self._load_activations)
        sec_hdr.addWidget(refresh_btn)
        vbox.addLayout(sec_hdr)

        self._act_table = QTableWidget()
        self._act_table.setColumnCount(4)
        self._act_table.setHorizontalHeaderLabels(["激活码", "状态", "额度", "到期时间"])
        self._act_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._act_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._act_table.verticalHeader().setVisible(False)
        self._act_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._act_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._act_table.setAlternatingRowColors(True)
        self._act_table.setStyleSheet(
            "QTableWidget { background: #ffffff; border: 1px solid #e2e8f0; "
            "  border-radius: 12px; gridline-color: #f1f5f9; }"
            "QTableWidget::item { padding: 8px 12px; }"
            "QHeaderView::section { background: #f8fafc; color: #64748b; "
            "  font-weight: 600; font-size: 12px; border: none; "
            "  border-bottom: 1px solid #e2e8f0; padding: 10px 12px; }"
        )
        self._act_table.setMinimumHeight(200)
        vbox.addWidget(self._act_table)

        hint = QLabel("在首页激活新码后，会自动绑定到您的账号。换电脑只需登录即可。")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none;"
        )
        vbox.addWidget(hint)

        return w

    def _update_view(self):
        if self.api.is_logged_in:
            self._stack.setCurrentWidget(self._profile_panel)
            info = self.api.user_info
            self._profile_nickname.setText(info.get("nickname", ""))
            self._profile_email.setText(info.get("email", ""))
            self._load_activations()
        else:
            self._stack.setCurrentWidget(self._auth_form)

    # ---- actions ----
    def _on_login(self):
        email = self._email_input.text().strip()
        pwd = self._password_input.text()
        if not email or not pwd:
            QMessageBox.warning(self, "提示", "请输入邮箱和密码")
            return
        self._login_btn.setEnabled(False)
        self._login_btn.setText("登录中...")
        threading.Thread(target=self._bg_login, args=(email, pwd), daemon=True).start()

    def _bg_login(self, email, pwd):
        self._login_resp = self.api.login(email, pwd)
        QMetaObject.invokeMethod(self, "_apply_login", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_login(self):
        self._login_btn.setEnabled(True)
        self._login_btn.setText("登  录")
        r = self._login_resp
        if r.get("success"):
            QMessageBox.information(self, "成功", "登录成功！")
            self._email_input.clear()
            self._password_input.clear()
            self._nickname_input.clear()
            self._update_view()
            self.account_state_changed.emit(True)
        else:
            QMessageBox.warning(self, "登录失败", r.get("message", "未知错误"))

    def _on_register(self):
        email = self._email_input.text().strip()
        pwd = self._password_input.text()
        nick = self._nickname_input.text().strip()
        if not email or not pwd:
            QMessageBox.warning(self, "提示", "请输入邮箱和密码")
            return
        if len(pwd) < 6:
            QMessageBox.warning(self, "提示", "密码不能少于6位")
            return
        self._register_btn.setEnabled(False)
        self._register_btn.setText("注册中...")
        threading.Thread(target=self._bg_register, args=(email, pwd, nick), daemon=True).start()

    def _bg_register(self, email, pwd, nick):
        self._register_resp = self.api.register(email, pwd, nick)
        QMetaObject.invokeMethod(self, "_apply_register", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_register(self):
        self._register_btn.setEnabled(True)
        self._register_btn.setText("注  册")
        r = self._register_resp
        if r.get("success"):
            QMessageBox.information(self, "成功", "注册成功，已自动登录！")
            self._email_input.clear()
            self._password_input.clear()
            self._nickname_input.clear()
            self._update_view()
            self.account_state_changed.emit(True)
        else:
            QMessageBox.warning(self, "注册失败", r.get("message", "未知错误"))

    def _on_logout(self):
        reply = QMessageBox.question(
            self, "退出登录", "确认退出当前账号？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.api.logout()
            self._update_view()
            self.account_state_changed.emit(False)

    def _load_activations(self):
        if not self.api.is_logged_in:
            return
        threading.Thread(target=self._bg_load_acts, daemon=True).start()

    def _bg_load_acts(self):
        self._acts_resp = self.api.get_user_activations()
        QMetaObject.invokeMethod(self, "_apply_acts", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_acts(self):
        r = self._acts_resp
        if not r.get("success"):
            return
        acts = r.get("data") or []
        self._act_table.setRowCount(len(acts))
        status_map = {0: "未使用", 1: "已激活", 2: "已过期", 3: "已封禁"}
        for i, a in enumerate(acts):
            key = a.get("card_key", "")
            masked = key[:4] + "****" + key[-4:] if len(key) > 8 else key
            self._act_table.setItem(i, 0, QTableWidgetItem(masked))

            st = a.get("status", 0)
            st_item = QTableWidgetItem(status_map.get(st, str(st)))
            if st == 1:
                st_item.setForeground(QColor("#059669"))
            elif st == 2:
                st_item.setForeground(QColor("#ef4444"))
            self._act_table.setItem(i, 1, st_item)

            if a.get("unlimited"):
                self._act_table.setItem(i, 2, QTableWidgetItem("\u221e"))
            else:
                self._act_table.setItem(i, 2, QTableWidgetItem(
                    f"{a.get('over_count', 0)} / {a.get('sum_count', 0)}"
                ))

            end = a.get("end_time", "\u2014")
            if end and end != "\u2014":
                end = str(end)[:19].replace("T", " ")
            else:
                end = "\u2014"
            self._act_table.setItem(i, 3, QTableWidgetItem(end))
