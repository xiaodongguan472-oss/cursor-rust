"""Windsurf 管理页面 — 获取账号 + 展示凭据供用户手动登录."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, QUrl, Signal, Slot, QMetaObject, QTimer
from PySide6.QtGui import QDesktopServices, QGuiApplication, QShowEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.platform_icons import platform_icon_label
from ui.widgets import SectionPanel


# ------------------------------------------------------------------ credential dialog
class _CredentialDialog(QDialog):
    def __init__(self, email: str, password: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("账号已获取")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build(email, password)

    def _build(self, email: str, password: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)

        # 标题
        row = QHBoxLayout()
        row.setSpacing(10)
        icon_lbl = platform_icon_label("Windsurf", 24)
        title = QLabel("账号已获取，请手动登录 Windsurf")
        title.setStyleSheet(
            "font-size: 15px; font-weight: 800; color: #0f172a;"
            " background: transparent; border: none;"
        )
        row.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(title, 1)
        layout.addLayout(row)

        # 凭据卡片
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #f0f9ff; border: 1.5px solid #bae6fd; border-radius: 14px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(12)
        cl.addLayout(self._cred_row("邮箱", email))

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #e0f2fe; border: none;")
        cl.addWidget(sep)

        cl.addLayout(self._cred_row("密码", password))
        layout.addWidget(card)

        # 提示
        tip = QLabel("打开 Windsurf → 登录 → 使用邮箱 + 密码登录")
        tip.setStyleSheet(
            "color: #64748b; font-size: 12px; background: transparent; border: none;"
        )
        layout.addWidget(tip)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("知道了")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setFixedHeight(38)
        ok_btn.setMinimumWidth(100)
        ok_btn.setStyleSheet(
            "QPushButton { background: #0891b2; color: #fff; border: none;"
            " border-radius: 10px; font-size: 13px; font-weight: 700; padding: 0 20px; }"
            "QPushButton:hover { background: #0e7490; }"
            "QPushButton:pressed { background: #155e75; }"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _cred_row(label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label)
        lbl.setFixedWidth(40)
        lbl.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
            " background: transparent; border: none;"
        )
        val = QLabel(value or "—")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        val.setStyleSheet(
            "color: #0f172a; font-size: 13px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        val.setWordWrap(True)
        copy_btn = QPushButton("复制")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFixedSize(52, 28)
        copy_btn.setStyleSheet(
            "QPushButton { background: #0891b2; color: #fff; border: none;"
            " border-radius: 7px; font-size: 11px; font-weight: 700; }"
            "QPushButton:hover { background: #0e7490; }"
        )

        def _copy(_=False, t=value, b=copy_btn):
            QGuiApplication.clipboard().setText(t)
            b.setText("✓ 已复制")
            b.setEnabled(False)
            QTimer.singleShot(1500, lambda: (b.setText("复制"), b.setEnabled(True)))

        copy_btn.clicked.connect(_copy)
        row.addWidget(lbl)
        row.addWidget(val, 1)
        row.addWidget(copy_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return row


# ------------------------------------------------------------------ main page
class WindsurfPage(QWidget):
    _show_msg      = Signal(str, str, str)
    _apply_login   = Signal(dict)
    _apply_history = Signal(list)
    navigate_to    = Signal(str)

    HIST_PAGE_SIZE = 5

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._working = False
        self._current_email = ""
        self._last_refresh_ts: float = 0.0
        self._hist_items: list = []
        self._hist_page: int = 0
        self._hist_loaded: bool = False
        self._show_msg.connect(self._do_show_msg)
        self._apply_login.connect(self._on_login_done)
        self._apply_history.connect(self._on_history_done)
        self._build()

    # ---------------------------------------------------------------- empty state
    def _build_empty_state(self):
        empty = QWidget()
        empty.setStyleSheet("background: #f4f6f9;")
        v = QVBoxLayout(empty)
        v.setContentsMargins(0, 0, 0, 0)
        v.addStretch(2)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_bg = QFrame()
        icon_bg.setFixedSize(80, 80)
        icon_bg.setStyleSheet(
            "background: #ecfeff; border: 2px solid rgba(8,145,178,0.12); border-radius: 40px;"
        )
        ib = QVBoxLayout(icon_bg)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.addWidget(platform_icon_label("Windsurf", 42), 0, Qt.AlignmentFlag.AlignCenter)
        wrap = QHBoxLayout()
        wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrap.addWidget(icon_bg)
        center.addLayout(wrap)
        center.addSpacing(20)

        title = QLabel("暂未开通 Windsurf")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1e293b; background: transparent; border: none;"
        )
        center.addWidget(title)
        center.addSpacing(6)

        desc = QLabel("激活包含 Windsurf 权限的激活码后，即可获取专属账号")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "font-size: 13px; color: #94a3b8; background: transparent; border: none; padding: 0 60px;"
        )
        center.addWidget(desc)
        center.addSpacing(24)

        row = QHBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.setSpacing(12)
        ab = QPushButton("前往激活")
        ab.setCursor(Qt.CursorShape.PointingHandCursor)
        ab.setFixedHeight(42)
        ab.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 #0891b2, stop:1 #06b6d4); color: white; border: none;"
            " border-radius: 12px; padding: 0 28px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #0e7490; }"
        )
        ab.clicked.connect(lambda: self.navigate_to.emit("首页"))
        rb = QPushButton("前往购买")
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.setFixedHeight(42)
        rb.setStyleSheet(
            "QPushButton { background: #fff; color: #0891b2;"
            " border: 1.5px solid rgba(8,145,178,0.3); border-radius: 12px;"
            " padding: 0 28px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #ecfeff; }"
        )
        rb.clicked.connect(self._go_renew)
        row.addWidget(ab)
        row.addWidget(rb)
        center.addLayout(row)

        v.addLayout(center)
        v.addStretch(3)
        self._page_stack.addWidget(empty)

    def _go_renew(self):
        url = self.api.get_renew_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "购买", "暂未配置购买链接，请联系客服。")

    # ---------------------------------------------------------------- main panel
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._page_stack = QStackedWidget()
        self._build_empty_state()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet("background: #f4f6f9;")
        v = QVBoxLayout(body)
        v.setContentsMargins(28, 22, 28, 32)
        v.setSpacing(16)

        # ── 页头
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        hdr.addWidget(platform_icon_label("Windsurf", 30), 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Windsurf")
        t.setStyleSheet("font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.4px;")
        s = QLabel("AI 编程助手 · 获取账号后手动登录使用")
        s.setStyleSheet("font-size: 12px; color: #94a3b8;")
        col.addWidget(t)
        col.addWidget(s)
        hdr.addLayout(col)
        hdr.addStretch()
        v.addLayout(hdr)

        # ── 账号状态卡
        acct_card = QFrame()
        acct_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1.5px solid #e8ecf1;"
            " border-radius: 18px; }"
        )
        acl = QVBoxLayout(acct_card)
        acl.setContentsMargins(22, 18, 22, 18)
        acl.setSpacing(14)

        # 顶部：账号 + 额度
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        # 账号信息区
        acct_info = QVBoxLayout()
        acct_info.setSpacing(4)
        acct_title = QLabel("当前账号")
        acct_title.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: 0.5px;"
            " background: transparent; border: none;"
        )
        self._acct_email_lbl = QLabel("尚未分配账号")
        self._acct_email_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #334155;"
            " background: transparent; border: none;"
        )
        self._acct_email_lbl.setWordWrap(True)
        acct_info.addWidget(acct_title)
        acct_info.addWidget(self._acct_email_lbl)
        top_row.addLayout(acct_info, 1)

        # 额度 badge
        self._quota_badge = _QuotaBadge()
        top_row.addWidget(self._quota_badge, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        acl.addLayout(top_row)

        # 分隔线
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #f1f5f9; border: none;")
        acl.addWidget(div)

        # 状态行
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_dot = QLabel("●")
        status_dot.setObjectName("StatusDot")
        status_dot.setStyleSheet("color: #cbd5e1; font-size: 10px; background: transparent; border: none;")
        self._status_dot = status_dot
        self._status_text = QLabel("未获取账号")
        self._status_text.setStyleSheet(
            "font-size: 12px; color: #94a3b8; background: transparent; border: none;"
        )
        status_row.addWidget(status_dot)
        status_row.addWidget(self._status_text)
        status_row.addStretch()
        acl.addLayout(status_row)

        # 获取按钮
        self._login_btn = QPushButton("获取账号")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setFixedHeight(48)
        self._login_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 #0891b2, stop:1 #06b6d4);"
            " color: #fff; border: none; border-radius: 14px;"
            " font-size: 15px; font-weight: 800; letter-spacing: 0.5px; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 #0e7490, stop:1 #0891b2); }"
            "QPushButton:pressed { background: #155e75; }"
            "QPushButton:disabled { background: #cbd5e1; color: #fff; }"
        )
        self._login_btn.clicked.connect(self._on_login_clicked)
        acl.addWidget(self._login_btn)

        v.addWidget(acct_card)

        # ── 历史账号
        hist = SectionPanel("历史账号")
        hist_body = QWidget()
        hbl = QVBoxLayout(hist_body)
        hbl.setContentsMargins(0, 0, 0, 0)
        hbl.setSpacing(8)

        self._hist_cards_wrap = QWidget()
        self._hist_cards_layout = QVBoxLayout(self._hist_cards_wrap)
        self._hist_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._hist_cards_layout.setSpacing(8)

        self._hist_empty_lbl = QLabel("暂无历史账号 — 点「获取账号」分配后即可在此看到")
        self._hist_empty_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 12px; padding: 10px 2px;"
            " background: transparent; border: none;"
        )
        self._hist_empty_lbl.setVisible(False)

        self._hist_pager = QWidget()
        pl = QHBoxLayout(self._hist_pager)
        pl.setContentsMargins(0, 4, 0, 0)
        pl.setSpacing(10)
        self._hist_prev = QPushButton("上一页")
        self._hist_prev.setObjectName("SectionToolBtn")
        self._hist_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_prev.clicked.connect(self._on_hist_prev)
        self._hist_page_lbl = QLabel("")
        self._hist_page_lbl.setStyleSheet("color: #64748b; font-size: 12px; background: transparent;")
        self._hist_next = QPushButton("下一页")
        self._hist_next.setObjectName("SectionToolBtn")
        self._hist_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_next.clicked.connect(self._on_hist_next)
        pl.addStretch()
        pl.addWidget(self._hist_prev)
        pl.addWidget(self._hist_page_lbl)
        pl.addWidget(self._hist_next)
        pl.addStretch()
        self._hist_pager.setVisible(False)

        hbl.addWidget(self._hist_cards_wrap)
        hbl.addWidget(self._hist_empty_lbl)
        hbl.addWidget(self._hist_pager)
        hist.add_body_widget(hist_body)
        v.addWidget(hist)

        v.addStretch()
        scroll.setWidget(body)
        self._page_stack.addWidget(scroll)
        self._page_stack.setCurrentIndex(0)
        outer.addWidget(self._page_stack)

    # ---------------------------------------------------------------- quota / status helpers
    def _apply_quota_from_data(self, data: dict):
        if data.get("windsurf_unlimited"):
            self._quota_badge.set_value("∞", unlimited=True)
        else:
            remain = data.get("windsurf_over_count")
            if remain is not None:
                self._quota_badge.set_value(str(remain), unlimited=False)

    def _set_status(self, text: str, active: bool):
        color = "#22c55e" if active else "#cbd5e1"
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent; border: none;"
        )
        self._status_text.setStyleSheet(
            f"font-size: 12px; color: {'#22c55e' if active else '#94a3b8'};"
            " background: transparent; border: none;"
        )
        self._status_text.setText(text)

    # ---------------------------------------------------------------- common helpers
    def _do_show_msg(self, kind: str, title: str, msg: str):
        if kind == "info":
            QMessageBox.information(self, title, msg)
        else:
            QMessageBox.warning(self, title, msg)

    def _emit_warn(self, title: str, msg: str):
        self._show_msg.emit("warn", title, msg)

    def _show_cred_dialog(self, email: str, password: str):
        dlg = _CredentialDialog(email, password, self)
        dlg.setModal(False)
        dlg.show()

    # ---------------------------------------------------------------- lifecycle
    def showEvent(self, ev: QShowEvent):
        super().showEvent(ev)
        now = time.monotonic()
        if now - self._last_refresh_ts > 10:
            self._last_refresh_ts = now
            threading.Thread(target=self._bg_refresh, daemon=True).start()

    def _bg_refresh(self):
        try:
            r = self.api.init_device()
        except Exception:
            return
        self._init_data = r
        QMetaObject.invokeMethod(self, "_apply_init_data", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_init_data(self):
        r = getattr(self, "_init_data", None) or {}
        if not r.get("success"):
            return
        data = r.get("data") or {}
        if data.get("banned") or not data.get("activated"):
            self._page_stack.setCurrentIndex(0)
            return
        perms = self._parse_perms(data.get("platform_permissions"))
        if perms and "windsurf" not in perms:
            self._page_stack.setCurrentIndex(0)
            return
        self._page_stack.setCurrentIndex(1)
        self._apply_quota_from_data(data)
        self._fetch_history_async()

    def load_init_data(self, data: dict):
        if not data:
            return
        if data.get("banned") or not data.get("activated"):
            self._page_stack.setCurrentIndex(0)
            return
        perms = self._parse_perms(data.get("platform_permissions"))
        if perms and "windsurf" not in perms:
            self._page_stack.setCurrentIndex(0)
            return
        self._page_stack.setCurrentIndex(1)
        self._apply_quota_from_data(data)
        self._fetch_history_async()

    @staticmethod
    def _parse_perms(raw):
        if not raw:
            return set()
        if isinstance(raw, list):
            return set(raw)
        if isinstance(raw, str):
            try:
                import json as _j
                arr = _j.loads(raw)
                if isinstance(arr, list):
                    return set(arr)
            except Exception:
                return set()
        return set()

    # ---------------------------------------------------------------- 获取账号
    def _on_login_clicked(self):
        if self._working:
            return
        self._working = True
        self._login_btn.setEnabled(False)
        self._login_btn.setText("获取中…")
        threading.Thread(target=self._bg_login, daemon=True).start()

    def _bg_login(self):
        try:
            r = self.api.get_windsurf_account()
            if not r.get("success"):
                self._apply_login.emit({"ok": False, "msg": r.get("message") or "未取到账号"})
                return
            data = r.get("data") or {}
            email = data.get("email") or ""
            password = data.get("password") or ""
            if not email:
                self._apply_login.emit({"ok": False, "msg": "后台返回的账号信息不完整"})
                return
            quota = {}
            try:
                cr = self.api.refresh_windsurf_count()
                if cr and cr.get("success"):
                    quota = cr.get("data") or {}
            except Exception:
                pass
            self._apply_login.emit({"ok": True, "email": email, "password": password, "quota": quota})
        except Exception as e:
            self._apply_login.emit({"ok": False, "msg": f"获取异常: {e}"})

    @Slot(dict)
    def _on_login_done(self, payload: dict):
        self._working = False
        self._login_btn.setEnabled(True)
        self._login_btn.setText("获取账号")
        if not payload.get("ok"):
            self._emit_warn("获取失败", payload.get("msg") or "未知错误")
            return

        email = payload.get("email", "")
        password = payload.get("password", "")
        self._current_email = email
        self._acct_email_lbl.setText(email)
        self._set_status("账号已获取", True)

        quota = payload.get("quota") or {}
        if quota:
            self._apply_quota_from_data(quota)

        import datetime as _dt
        now_str = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self._hist_items = [x for x in self._hist_items if x.get("email") != email]
        self._hist_items.insert(0, {"email": email, "password": password, "createTime": now_str})
        self._hist_loaded = True
        self._hist_page = 0
        self._render_hist_page()

        self._fetch_history_async()
        self._show_cred_dialog(email, password)

    # ---------------------------------------------------------------- 历史账号
    def _fetch_history_async(self):
        threading.Thread(target=self._bg_fetch_history, daemon=True).start()

    def _bg_fetch_history(self):
        try:
            r = self.api.get_windsurf_history()
        except Exception:
            self._apply_history.emit([])
            return
        items = []
        if r and r.get("success"):
            data = r.get("data")
            if isinstance(data, list):
                items = [x for x in data if isinstance(x, dict)]
        self._apply_history.emit(items)

    @Slot(list)
    def _on_history_done(self, items: list):
        self._hist_loaded = True
        self._hist_items = items or []
        self._hist_page = 0
        self._render_hist_page()

    def _clear_hist_cards(self):
        while self._hist_cards_layout.count():
            it = self._hist_cards_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _render_hist_page(self):
        self._clear_hist_cards()
        if not self._hist_items:
            self._hist_pager.setVisible(False)
            self._hist_empty_lbl.setVisible(self._hist_loaded)
            return
        self._hist_empty_lbl.setVisible(False)

        total = len(self._hist_items)
        total_pages = max(1, (total + self.HIST_PAGE_SIZE - 1) // self.HIST_PAGE_SIZE)
        self._hist_page = max(0, min(self._hist_page, total_pages - 1))

        start = self._hist_page * self.HIST_PAGE_SIZE
        for item in self._hist_items[start:start + self.HIST_PAGE_SIZE]:
            email = item.get("email", "")
            password = item.get("password", "")
            raw_ct = (item.get("createTime") or item.get("lastUsedTime") or "").replace("T", " ")
            create_time = raw_ct[:16] if len(raw_ct) >= 16 else raw_ct
            self._hist_cards_layout.addWidget(
                self._build_hist_card(email, password, create_time)
            )

        self._hist_page_lbl.setText(f"{self._hist_page + 1} / {total_pages}  共 {total} 条")
        self._hist_pager.setVisible(total_pages > 1)
        self._hist_prev.setEnabled(self._hist_page > 0)
        self._hist_next.setEnabled(self._hist_page < total_pages - 1)

    def _on_hist_prev(self):
        if self._hist_page > 0:
            self._hist_page -= 1
            self._render_hist_page()

    def _on_hist_next(self):
        total = len(self._hist_items)
        total_pages = max(1, (total + self.HIST_PAGE_SIZE - 1) // self.HIST_PAGE_SIZE)
        if self._hist_page < total_pages - 1:
            self._hist_page += 1
            self._render_hist_page()

    def _build_hist_card(self, email: str, password: str, create_time: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1.5px solid #e8ecf1; border-radius: 14px; }"
            "QFrame:hover { border-color: #bae6fd; background: #f8fdff; }"
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 14, 12)
        row.setSpacing(12)

        # 左：图标
        icon_w = QFrame()
        icon_w.setFixedSize(40, 40)
        icon_w.setStyleSheet(
            "QFrame { background: #ecfeff; border: 1.5px solid rgba(8,145,178,0.15);"
            " border-radius: 12px; }"
        )
        il = QVBoxLayout(icon_w)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(platform_icon_label("Windsurf", 22), 0, Qt.AlignmentFlag.AlignCenter)
        row.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignVCenter)

        # 中：信息
        info = QVBoxLayout()
        info.setSpacing(3)
        em_lbl = QLabel(email or "—")
        em_lbl.setStyleSheet(
            "color: #0f172a; font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        em_lbl.setWordWrap(True)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        masked = "•" * min(len(password), 10) if password else "—"
        pw_lbl = QLabel(masked)
        pw_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 11px; letter-spacing: 2px; background: transparent; border: none;"
        )
        if create_time:
            time_lbl = QLabel(create_time)
            time_lbl.setStyleSheet(
                "color: #cbd5e1; font-size: 11px; background: transparent; border: none;"
            )
            sub_row.addWidget(pw_lbl)
            sub_row.addWidget(QLabel("·") if False else self._dot_sep(), 0)
            sub_row.addWidget(time_lbl)
        else:
            sub_row.addWidget(pw_lbl)
        sub_row.addStretch()

        info.addWidget(em_lbl)
        info.addLayout(sub_row)
        row.addLayout(info, 1)

        # 右：操作按钮
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        view_btn = QPushButton("查看账号")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setFixedHeight(32)
        view_btn.setFixedWidth(80)
        view_btn.setStyleSheet(
            "QPushButton { background: #0891b2; color: #fff; border: none;"
            " border-radius: 9px; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background: #0e7490; }"
        )
        view_btn.clicked.connect(
            lambda _=False, e=email, p=password: self._show_cred_dialog(e, p)
        )

        copy_em = self._small_copy_btn(email, "复制邮箱")
        btn_col.addWidget(view_btn)
        btn_col.addWidget(copy_em)
        row.addLayout(btn_col)
        return card

    @staticmethod
    def _dot_sep() -> QLabel:
        lbl = QLabel("·")
        lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; background: transparent; border: none;")
        return lbl

    @staticmethod
    def _small_copy_btn(text: str, tip: str) -> QPushButton:
        btn = QPushButton("复制邮箱")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.setFixedWidth(80)
        btn.setStyleSheet(
            "QPushButton { background: #f1f5f9; color: #475569; border: none;"
            " border-radius: 8px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #e2e8f0; }"
        )

        def _copy(_=False, t=text, b=btn):
            QGuiApplication.clipboard().setText(t)
            b.setText("✓ 已复制")
            b.setEnabled(False)
            QTimer.singleShot(1500, lambda: (b.setText("复制邮箱"), b.setEnabled(True)))

        btn.clicked.connect(_copy)
        return btn


# ------------------------------------------------------------------ quota badge widget
class _QuotaBadge(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._unlimited = False
        self.setStyleSheet(
            "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(5)

        dot = QLabel("●")
        dot.setStyleSheet("color: #22c55e; font-size: 8px; background: transparent; border: none;")
        self._val_lbl = QLabel("—")
        self._val_lbl.setStyleSheet(
            "color: #15803d; font-size: 13px; font-weight: 800; background: transparent; border: none;"
        )
        self._unit_lbl = QLabel("次剩余")
        self._unit_lbl.setStyleSheet(
            "color: #16a34a; font-size: 11px; font-weight: 500; background: transparent; border: none;"
        )
        layout.addWidget(dot)
        layout.addWidget(self._val_lbl)
        layout.addWidget(self._unit_lbl)

    def set_value(self, value: str, unlimited: bool = False):
        self._unlimited = unlimited
        self._val_lbl.setText(value)
        if unlimited:
            self._unit_lbl.setText("无限")
            self.setStyleSheet(
                "QFrame { background: #eff6ff; border: 1.5px solid #bfdbfe; border-radius: 12px; }"
            )
            self._val_lbl.setStyleSheet(
                "color: #1d4ed8; font-size: 13px; font-weight: 800; background: transparent; border: none;"
            )
            self._unit_lbl.setStyleSheet(
                "color: #3b82f6; font-size: 11px; font-weight: 500; background: transparent; border: none;"
            )
        else:
            self._unit_lbl.setText("次剩余")
            val = 0
            try:
                val = int(value)
            except Exception:
                pass
            if val == 0:
                self.setStyleSheet(
                    "QFrame { background: #fff7ed; border: 1.5px solid #fed7aa; border-radius: 12px; }"
                )
                self._val_lbl.setStyleSheet(
                    "color: #c2410c; font-size: 13px; font-weight: 800; background: transparent; border: none;"
                )
                self._unit_lbl.setStyleSheet(
                    "color: #ea580c; font-size: 11px; font-weight: 500; background: transparent; border: none;"
                )
            else:
                self.setStyleSheet(
                    "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; }"
                )
                self._val_lbl.setStyleSheet(
                    "color: #15803d; font-size: 13px; font-weight: 800; background: transparent; border: none;"
                )
                self._unit_lbl.setStyleSheet(
                    "color: #16a34a; font-size: 11px; font-weight: 500; background: transparent; border: none;"
                )
