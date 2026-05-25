"""Kiro 管理页面 — 一键登录 · 账号管理"""

import json
import threading
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QScrollArea, QStackedWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor, QDesktopServices, QShowEvent

from ui.widgets import Card, CardHeader, InfoRow, StatusBadge, SectionPanel
from ui.platform_icons import platform_icon_label


class KiroPage(QWidget):
    _show_msg = Signal(str, str, str)
    navigate_to = Signal(str)

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._current_email = ""
        self._working = False
        self._hist_items = []
        self._hist_page = 0
        self._hist_loaded = False
        self.HIST_PAGE_SIZE = 5
        self._show_msg.connect(self._do_show_msg)
        self._last_refresh_ts: float = 0.0
        self._build()

    def _build_empty_state(self):
        empty = QWidget()
        empty.setStyleSheet("background: #f4f6f9;")
        vbox = QVBoxLayout(empty)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addStretch(2)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(0)

        icon_bg = QFrame()
        icon_bg.setFixedSize(80, 80)
        icon_bg.setStyleSheet(
            "background: #ecfeff; border: 2px solid rgba(8,145,178,0.12); border-radius: 40px;"
        )
        icon_inner = QVBoxLayout(icon_bg)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        icon_lbl = platform_icon_label("Kiro", 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_inner.addWidget(icon_lbl)
        icon_wrap = QHBoxLayout()
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_wrap.addWidget(icon_bg)
        center.addLayout(icon_wrap)
        center.addSpacing(20)

        title_lbl = QLabel("暂未开通 Kiro")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1e293b;"
            "background: transparent; border: none;"
        )
        center.addWidget(title_lbl)
        center.addSpacing(8)

        desc_lbl = QLabel("激活包含 Kiro 权限的激活码后，即可使用账号管理和登录功能")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            "font-size: 13px; color: #94a3b8; background: transparent;"
            "border: none; padding: 0 60px;"
        )
        center.addWidget(desc_lbl)
        center.addSpacing(24)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(14)

        activate_btn = QPushButton("前往首页激活")
        activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        activate_btn.setFixedHeight(44)
        activate_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #4f46e5, stop:1 #6366f1);"
            "  color: white; border: none; border-radius: 14px;"
            "  padding: 0 32px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #4338ca, stop:1 #4f46e5); }"
        )
        activate_btn.clicked.connect(lambda: self.navigate_to.emit("首页"))
        btn_row.addWidget(activate_btn)

        renew_btn = QPushButton("前往购买")
        renew_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        renew_btn.setFixedHeight(44)
        renew_btn.setStyleSheet(
            "QPushButton { background: #ffffff;"
            "  color: #0891b2;"
            "  border: 1.5px solid rgba(8,145,178,0.25); border-radius: 14px;"
            "  padding: 0 32px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #ecfeff; }"
        )
        renew_btn.clicked.connect(self._go_renew)
        btn_row.addWidget(renew_btn)

        center.addLayout(btn_row)
        vbox.addLayout(center)
        vbox.addStretch(3)
        self._page_stack.addWidget(empty)

    def _go_renew(self):
        url = self.api.get_renew_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "购买", "暂未配置购买链接，请联系客服。")

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._page_stack = QStackedWidget()
        self._build_empty_state()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setStyleSheet("background: #f4f6f9;")
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(32, 24, 32, 36)
        vbox.setSpacing(20)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)
        hdr_icon = platform_icon_label("Kiro", 32)
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(3)
        title = QLabel("Kiro")
        title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;"
        )
        sub = QLabel("一键登录 · 账号管理")
        sub.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr_row.addLayout(hdr_col)
        hdr_row.addStretch()
        vbox.addLayout(hdr_row)

        # ========== 操作面板 ==========
        panel = Card()
        panel.add_widget(CardHeader("操作面板", color="#f59e0b"))

        self._email_row = InfoRow(
            "当前账号",
            "点击「获取账号并登录」获取",
            display_only=True,
        )
        panel.add_widget(self._email_row)

        sw = QWidget()
        sl = QHBoxLayout(sw)
        sl.setContentsMargins(0, 8, 0, 8)
        sl.setSpacing(12)
        lb = QLabel("登录状态")
        lb.setObjectName("CardLabel")
        lb.setMinimumWidth(72)
        self._status_badge = StatusBadge("未登录", active=False)
        sl.addWidget(lb)
        sl.addWidget(self._status_badge, 1)
        panel.add_widget(sw)

        # 额度
        quota_w = QWidget()
        ql = QHBoxLayout(quota_w)
        ql.setContentsMargins(0, 8, 0, 8)
        ql.setSpacing(16)
        self._total_label = self._quota_chip("总额度", "—", "#f59e0b")
        self._remain_label = self._quota_chip("剩余", "—", "#059669")
        ql.addWidget(self._total_label)
        ql.addWidget(self._remain_label)
        ql.addStretch()
        panel.add_widget(quota_w)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #f1f5f9; border: none;")
        panel.add_widget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)
        self._refresh_btn = self._action_button(
            "获取账号并登录",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f59e0b, stop:1 #f97316)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #d97706, stop:1 #f59e0b)",
            "#b45309",
            self._on_refresh_kiro,
        )
        btn_row.addWidget(self._refresh_btn)

        self._register_btn = self._action_button(
            "注册并登录",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6366f1, stop:1 #818cf8)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f46e5, stop:1 #6366f1)",
            "#4338ca",
            self._on_register_kiro,
        )
        btn_row.addWidget(self._register_btn)

        panel.add_layout(btn_row)
        vbox.addWidget(panel)

        # ========== 历史账号 ==========
        hist = SectionPanel("历史账号")
        hist_body = QWidget()
        hbl = QVBoxLayout(hist_body)
        hbl.setContentsMargins(0, 0, 0, 0)
        hbl.setSpacing(10)

        self._hist_cards_wrap = QWidget()
        self._hist_cards_layout = QVBoxLayout(self._hist_cards_wrap)
        self._hist_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._hist_cards_layout.setSpacing(8)

        self._hist_pager = QWidget()
        pl = QHBoxLayout(self._hist_pager)
        pl.setContentsMargins(0, 4, 0, 0)
        pl.setSpacing(10)
        self._hist_prev = QPushButton("上一页")
        self._hist_prev.setObjectName("SectionToolBtn")
        self._hist_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_prev.clicked.connect(self._on_hist_prev)
        self._hist_page_lbl = QLabel("")
        self._hist_page_lbl.setStyleSheet(
            "color: #64748b; font-size: 12px; background: transparent;"
        )
        self._hist_next = QPushButton("下一页")
        self._hist_next.setObjectName("SectionToolBtn")
        self._hist_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_next.clicked.connect(self._on_hist_next)
        pl.addStretch()
        pl.addWidget(self._hist_prev)
        pl.addWidget(self._hist_page_lbl)
        pl.addWidget(self._hist_next)
        pl.addStretch()

        hbl.addWidget(self._hist_cards_wrap)
        hbl.addWidget(self._hist_pager)
        self._hist_pager.setVisible(False)

        hist.add_body_widget(hist_body)
        vbox.addWidget(hist)

        # ========== 使用说明 ==========
        self._guide_panel = SectionPanel("使用说明")
        self._guide_label = QLabel("")
        self._guide_label.setStyleSheet(
            "color: #64748b; font-size: 13px; padding: 4px 0 8px 0; "
            "background: transparent; border: none; line-height: 1.6;"
        )
        self._guide_label.setWordWrap(True)
        self._guide_panel.add_body_widget(self._guide_label)
        self._guide_panel.setVisible(False)
        vbox.addWidget(self._guide_panel)

        vbox.addStretch()
        scroll.setWidget(body)
        self._page_stack.addWidget(scroll)
        self._page_stack.setCurrentIndex(0)
        outer.addWidget(self._page_stack)

        threading.Thread(target=self._bg_fetch_history, daemon=True).start()

    # ------------------------------------------------------------------ lifecycle
    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        now = time.monotonic()
        if now - self._last_refresh_ts > 10:
            self._last_refresh_ts = now
            self._refresh_all()

    def _refresh_all(self):
        threading.Thread(target=self._bg_refresh_all, daemon=True).start()

    def _bg_refresh_all(self):
        r = self.api.init_device()
        self._refresh_all_result = r
        QMetaObject.invokeMethod(self, "_apply_refresh_all", Qt.ConnectionType.QueuedConnection)
        self._bg_fetch_history()

    @Slot()
    def _apply_refresh_all(self):
        r = getattr(self, "_refresh_all_result", None)
        if r is None:
            return
        if r.get("success"):
            data = r.get("data") or {}
            if data.get("banned") or not data.get("activated"):
                self._show_not_activated()
                return
            self._page_stack.setCurrentIndex(1)
            self._apply_quota_from_data(data)

    def _show_not_activated(self):
        self._current_email = ""
        self._page_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _action_button(text, bg, hover, pressed, slot):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(46)
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: #fff; border: none; "
            f"border-radius: 14px; font-size: 14px; font-weight: 700; padding: 0 32px; "
            f"letter-spacing: 0.3px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
            f"QPushButton:disabled {{ background: #94a3b8; }}"
        )
        btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _quota_chip(label: str, value: str, color: str) -> QFrame:
        chip = QFrame()
        chip.setStyleSheet(
            f"QFrame {{ background: {color}0c; border: 1.5px solid {color}1a; "
            f"border-radius: 12px; }}"
        )
        row = QHBoxLayout(chip)
        row.setContentsMargins(14, 8, 16, 8)
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 500; "
            "background: transparent; border: none;"
        )
        val = QLabel(value)
        val.setObjectName("quota_value")
        val.setStyleSheet(
            f"color: {color}; font-size: 15px; font-weight: 800; "
            "background: transparent; border: none;"
        )
        row.addWidget(lbl)
        row.addWidget(val)
        return chip

    def _update_quota_chip(self, chip: QFrame, value: str):
        val_label = chip.findChild(QLabel, "quota_value")
        if val_label:
            val_label.setText(value)

    def _apply_quota_from_data(self, data: dict):
        if data.get("kiro_unlimited") or data.get("unlimited"):
            self._update_quota_chip(self._total_label, "∞")
            self._update_quota_chip(self._remain_label, "∞")
        else:
            total = data.get("kiro_sum_count", data.get("sum_count"))
            remain = data.get("kiro_over_count", data.get("over_count"))
            if total is not None:
                self._update_quota_chip(self._total_label, str(total))
            if remain is not None:
                self._update_quota_chip(self._remain_label, str(remain))

    def _do_show_msg(self, kind: str, title: str, msg: str):
        if kind == "info":
            QMessageBox.information(self, title, msg)
        else:
            QMessageBox.warning(self, title, msg)

    def _emit_info(self, title: str, msg: str):
        self._show_msg.emit("info", title, msg)

    def _emit_warn(self, title: str, msg: str):
        self._show_msg.emit("warn", title, msg)

    # ------------------------------------------------------------------ Kiro 进程操作
    def _thread_exit_kiro_or_warn(self) -> bool:
        from core.kiro_process import exit_kiro
        if not exit_kiro(timeout=8):
            self._emit_warn(
                "关闭 Kiro 失败",
                "Kiro 进程未能正常退出，请手动关闭后重试。",
            )
            return False
        return True

    def _thread_write_auth_or_warn(self, account_info_json: str, access_token: str) -> bool:
        from core.kiro_auth import KiroAuthManager

        try:
            info = json.loads(account_info_json)
        except (json.JSONDecodeError, TypeError):
            self._emit_warn("写入失败", "账号认证信息格式异常")
            return False

        auth = KiroAuthManager()
        return auth.write_auth(
            access_token=access_token,
            refresh_token=info.get("refreshToken", ""),
            client_id=info.get("clientId", ""),
            client_secret=info.get("clientSecret", ""),
            client_id_hash=info.get("clientIdHash", ""),
            region=info.get("region", "us-east-1"),
        )

    def _thread_open_kiro_or_warn(self) -> bool:
        from core.kiro_process import open_kiro
        return open_kiro()

    # ------------------------------------------------------------------ 额度预检
    def _check_quota_or_warn(self) -> bool:
        r = self.api.refresh_kiro_count()
        if not r.get("success"):
            return True
        data = r.get("data") or {}
        if data.get("kiro_unlimited") or data.get("unlimited"):
            return True
        remain = data.get("kiro_over_count", data.get("over_count", 0))
        try:
            remain = int(remain)
        except (ValueError, TypeError):
            remain = 0
        if remain <= 0:
            QMessageBox.warning(
                self, "额度不足",
                "当前额度已用完，无法执行此操作。\n请联系客服充值后再试。",
            )
            return False
        return True

    # ------------------------------------------------------------------ 注册并登录
    def _on_register_kiro(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        if not self._check_quota_or_warn():
            return

        from ui.dialogs.kiro_register_dialog import KiroRegisterDialog
        dlg = KiroRegisterDialog(self.api, parent=self.window())
        dlg.result_ready.connect(self._on_register_result)
        dlg.start()
        dlg.exec()

    def _on_register_result(self, result):
        if result and isinstance(result, dict):
            email = result.get("email", "")
            self._current_email = email
            self._email_row.set_value(email)
            self._status_badge.update_status("已登录", True)
            self._fetch_quota()
            self._fetch_history()

    # ------------------------------------------------------------------ 获取账号并登录
    def _on_refresh_kiro(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        if not self._check_quota_or_warn():
            return

        reply = QMessageBox.question(
            self, "确认换号",
            "将为您获取新 Kiro 账号并自动完成登录，"
            "Kiro 会在过程中重启。\n\n"
            "请确保当前工作已保存！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._working = True
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("正在登录...")
        t = threading.Thread(target=self._do_refresh_kiro, daemon=True)
        t.start()

    def _do_refresh_kiro(self):
        try:
            r = self.api.get_kiro_credentials()
            if not r.get("success"):
                self._emit_warn("换号失败", r.get("message", "服务器未返回有效数据"))
                return

            data = r.get("data") or {}
            email = data.get("email", "")
            token = data.get("token", "")
            account_info = data.get("account_info", "")

            if not email or not token or not account_info:
                self._emit_warn("换号失败", data.get("message", "当前暂无可分配账号，请稍后再试"))
                return

            self._current_email = email
            self._pending_account_info = account_info
            self._pending_token = token

            if not self._thread_exit_kiro_or_warn():
                return
            if not self._thread_write_auth_or_warn(account_info, token):
                self._emit_warn("写入失败", "Kiro 认证文件写入失败，请检查权限。")
                return
            kiro_opened = self._thread_open_kiro_or_warn()
            self._kiro_opened = kiro_opened

            QMetaObject.invokeMethod(
                self, "_on_refresh_done",
                Qt.ConnectionType.QueuedConnection,
            )
        except Exception as e:
            self._emit_warn("换号失败", f"操作异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_refresh_btn_restore",
                Qt.ConnectionType.QueuedConnection,
            )

    @Slot()
    def _on_refresh_done(self):
        self._email_row.set_value(self._current_email)
        self._status_badge.update_status("已登录", True)
        self._fetch_quota()
        self._fetch_history()
        opened = getattr(self, "_kiro_opened", True)
        tip = f"新账号已自动登录 Kiro\n\n当前账号: {self._current_email}"
        if not opened:
            tip += "\n\n⚠ 未找到 Kiro 安装路径，请手动打开 Kiro。"
        QMessageBox.information(self, "换号成功", tip)

    @Slot()
    def _on_refresh_btn_restore(self):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("获取账号并登录")

    # ------------------------------------------------------------------ 额度
    def _fetch_quota(self):
        r = self.api.refresh_kiro_count()
        if not r.get("success"):
            return
        data = r.get("data", {})
        self._apply_quota_from_data(data)

    # ------------------------------------------------------------------ 历史账号
    def _clear_hist_cards(self):
        while self._hist_cards_layout.count():
            item = self._hist_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_hist_page(self):
        self._clear_hist_cards()
        if not self._hist_loaded or not self._hist_items:
            self._hist_pager.setVisible(False)
            return

        total = len(self._hist_items)
        total_pages = max(1, (total + self.HIST_PAGE_SIZE - 1) // self.HIST_PAGE_SIZE)
        if self._hist_page >= total_pages:
            self._hist_page = total_pages - 1
        if self._hist_page < 0:
            self._hist_page = 0

        start = self._hist_page * self.HIST_PAGE_SIZE
        chunk = self._hist_items[start : start + self.HIST_PAGE_SIZE]

        for item in chunk:
            if not isinstance(item, dict):
                continue
            email = item.get("email", "")
            status_val = item.get("status", "")
            use_time = (item.get("useTime", "") or item.get("use_time", "")).replace("T", " ")
            card = self._build_hist_card(email, status_val, use_time)
            self._hist_cards_layout.addWidget(card)

        self._hist_page_lbl.setText(f"第 {self._hist_page + 1} / {total_pages} 页")
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

    def _fetch_history(self):
        threading.Thread(target=self._bg_fetch_history, daemon=True).start()

    def _bg_fetch_history(self):
        r = self.api.get_kiro_history()
        self._hist_result = r
        QMetaObject.invokeMethod(self, "_apply_history", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_history(self):
        r = getattr(self, "_hist_result", None)
        self._hist_loaded = True
        self._hist_items = []
        if r and r.get("success"):
            data = r.get("data")
            if isinstance(data, list):
                self._hist_items = [x for x in data if isinstance(x, dict)]
        self._hist_page = 0
        self._render_hist_page()

    def _build_hist_card(self, email: str, status_val: str, use_time: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1.5px solid #e8ecf1; border-radius: 14px; }"
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 14, 14)
        row.setSpacing(14)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        email_label = QLabel(email or "—")
        email_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1e293b; "
            "background: transparent; border: none;"
        )
        info_col.addWidget(email_label)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        is_available = str(status_val) == "0"
        status_text = "未使用" if is_available else "已使用"
        dot_color = "#10b981" if is_available else "#cbd5e1"
        text_color = "#059669" if is_available else "#94a3b8"

        status_w = QWidget()
        sl = QHBoxLayout(status_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        dot = QFrame()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 3px; border: none;")
        st = QLabel(status_text)
        st.setStyleSheet(
            f"font-size: 11px; color: {text_color}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        sl.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        sl.addWidget(st)
        meta_row.addWidget(status_w)

        if use_time:
            time_label = QLabel(use_time[:19])
            time_label.setStyleSheet(
                "font-size: 11px; color: #94a3b8; background: transparent; border: none;"
            )
            meta_row.addWidget(time_label)

        meta_row.addStretch()
        info_col.addLayout(meta_row)
        row.addLayout(info_col, 1)

        login_btn = QPushButton("一键登录")
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setFixedHeight(34)
        login_btn.setStyleSheet(
            "QPushButton { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #f59e0b, stop:1 #f97316);"
            "  color: #fff; border: none; border-radius: 10px; "
            "  font-size: 12px; font-weight: 700; padding: 0 20px; }"
            "QPushButton:hover { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #d97706, stop:1 #f59e0b); }"
            "QPushButton:pressed { background: #b45309; }"
        )
        login_btn.clicked.connect(lambda _, e=email: self._on_hist_login(e))
        row.addWidget(login_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        return card

    def _on_hist_login(self, email: str):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        reply = QMessageBox.question(
            self, "确认登录",
            f"即将使用历史账号登录 Kiro：\n\n{email}\n\n"
            "Kiro 将自动重启，请确保工作已保存！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._working = True
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("正在登录...")
        t = threading.Thread(
            target=self._do_hist_login, args=(email,), daemon=True
        )
        t.start()

    def _do_hist_login(self, email: str):
        try:
            r = self.api.reuse_kiro_history_account(email)
            if not r.get("success"):
                self._emit_warn("登录失败", r.get("message", "无法获取该账号凭证"))
                return

            data = r.get("data") or {}
            token = data.get("token", "")
            account_info = data.get("account_info", "")
            if not token or not account_info:
                self._emit_warn("登录失败", "该账号凭证已失效，请尝试获取新账号")
                return

            self._current_email = email
            self._pending_account_info = account_info
            self._pending_token = token

            if not self._thread_exit_kiro_or_warn():
                return
            if not self._thread_write_auth_or_warn(account_info, token):
                self._emit_warn("写入失败", "Kiro 认证文件写入失败，请检查权限。")
                return
            kiro_opened = self._thread_open_kiro_or_warn()
            self._kiro_opened = kiro_opened

            QMetaObject.invokeMethod(
                self, "_on_refresh_done",
                Qt.ConnectionType.QueuedConnection,
            )
        except Exception as e:
            self._emit_warn("登录失败", f"操作异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_refresh_btn_restore",
                Qt.ConnectionType.QueuedConnection,
            )

    # ------------------------------------------------------------------ 使用说明
    def set_guide(self, text: str | None):
        """Show or hide the usage guide section."""
        if text:
            self._guide_label.setText(text)
            self._guide_panel.setVisible(True)
        else:
            self._guide_panel.setVisible(False)

    # ------------------------------------------------------------------ 初始化数据加载
    def load_init_data(self, data: dict):
        if not data:
            return
        if data.get("banned") or not data.get("activated"):
            self._show_not_activated()
            return
        self._page_stack.setCurrentIndex(1)
        email = data.get("kiro_email") or data.get("email", "")
        if email:
            self._current_email = email
            self._email_row.set_value(email)
            self._status_badge.update_status("已登录", True)
        self._apply_quota_from_data(data)
        self._fetch_history()
