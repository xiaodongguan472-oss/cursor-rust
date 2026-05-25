"""Cursor 管理页面 — 基于登录助手逻辑"""

import os
import platform
import threading
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QScrollArea, QCheckBox,
    QGraphicsDropShadowEffect, QProgressBar, QStackedWidget,
)
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QColor, QDesktopServices, QShowEvent

from ui.widgets import Card, CardHeader, StatusBadge, SectionPanel
from ui.platform_icons import platform_icon_label


def _shadow(w, blur=20, y=4, alpha=18):
    s = QGraphicsDropShadowEffect(w)
    s.setBlurRadius(blur)
    s.setOffset(0, y)
    s.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(s)


class CursorPage(QWidget):
    _show_msg = Signal(str, str, str)
    _auto_switch_sig = Signal(str)
    _install_progress_sig = Signal(int, str)
    _install_done_sig = Signal(bool, str)
    navigate_to = Signal(str)

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._current_email = ""
        self._current_token = ""
        self._current_pwd = ""
        self._working = False
        self._from_float = False
        self._show_msg.connect(self._do_show_msg)
        self._auto_switch_sig.connect(self._on_auto_switched)
        self._install_progress_sig.connect(self._on_install_progress)
        self._install_done_sig.connect(self._on_install_done)
        self._mini_float = None
        self._last_refresh_ts: float = 0.0
        self._seamless_enabled = True
        self._heartbeat_timer = None
        self._heartbeat_stop = threading.Event()

        from core.seamless_server import set_api_client, set_on_switch_callback
        set_api_client(api_client)
        set_on_switch_callback(lambda email: self._auto_switch_sig.emit(email))

        self._build()
        self._start_heartbeat()

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
            "background: #eef2ff; border: 2px solid rgba(79,70,229,0.12); border-radius: 40px;"
        )
        icon_inner = QVBoxLayout(icon_bg)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        icon_lbl = platform_icon_label("Cursor", 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_inner.addWidget(icon_lbl)

        icon_wrap = QHBoxLayout()
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_wrap.addWidget(icon_bg)
        center.addLayout(icon_wrap)
        center.addSpacing(20)

        title_lbl = QLabel("暂未开通 Cursor")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1e293b;"
            "background: transparent; border: none;"
        )
        center.addWidget(title_lbl)
        center.addSpacing(8)

        desc_lbl = QLabel("激活包含 Cursor 权限的激活码后，即可使用账号管理和一键登录功能")
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
            "  color: #4f46e5;"
            "  border: 1.5px solid rgba(79,70,229,0.25); border-radius: 14px;"
            "  padding: 0 32px; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #eef2ff; }"
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

    def _start_heartbeat(self):
        self._heartbeat_stop.clear()
        def _loop():
            while not self._heartbeat_stop.wait(300):
                try:
                    self.api.cursor_heartbeat()
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        self._heartbeat_timer = t

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
        hdr_icon = platform_icon_label("Cursor", 32)
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(3)
        title = QLabel("Cursor")
        title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;"
        )
        sub = QLabel("一键登录 · 账号管理")
        sub.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr_row.addLayout(hdr_col, 1)
        self._mini_float_btn = QPushButton("⬜ 浮窗模式")
        self._mini_float_btn.setObjectName("SectionToolBtn")
        self._mini_float_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mini_float_btn.setToolTip(
            "进入迷你浮窗：主窗口会隐藏，仅在浮窗点 × 关闭后恢复主界面"
        )
        self._mini_float_btn.clicked.connect(self._on_toggle_mini_float)
        hdr_row.addWidget(self._mini_float_btn, 0, Qt.AlignmentFlag.AlignTop)
        vbox.addLayout(hdr_row)

        # ========== 安装状态条 ==========
        install_strip = QFrame()
        install_strip.setObjectName("cursorInstallStrip")
        install_strip.setStyleSheet(
            "QFrame#cursorInstallStrip { background: #ffffff; border: 1px solid #e8ecf1;"
            "  border-left: 3px solid #4f46e5; border-radius: 12px; }"
        )
        _shadow(install_strip, blur=12, y=2, alpha=8)
        is_outer = QVBoxLayout(install_strip)
        is_outer.setContentsMargins(16, 10, 12, 10)
        is_outer.setSpacing(6)

        # ── 第一行：状态徽章 / 版本号 / 操作按钮 ──
        is_top = QHBoxLayout()
        is_top.setContentsMargins(0, 0, 0, 0)
        is_top.setSpacing(10)

        self._install_status_badge = StatusBadge("检测中", active=False)
        is_top.addWidget(self._install_status_badge)

        self._install_ver_label = QLabel("")
        self._install_ver_label.setStyleSheet(
            "color: #64748b; font-size: 12px; background: transparent; border: none;"
        )
        is_top.addWidget(self._install_ver_label)
        is_top.addStretch()

        self._install_progress = QProgressBar()
        self._install_progress.setFixedSize(120, 4)
        self._install_progress.setRange(0, 100)
        self._install_progress.setValue(0)
        self._install_progress.setTextVisible(False)
        self._install_progress.setVisible(False)
        self._install_progress.setStyleSheet(
            "QProgressBar { background: #e2e8f0; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #4f46e5; border-radius: 2px; }"
        )
        is_top.addWidget(self._install_progress)

        self._install_progress_label = QLabel()
        self._install_progress_label.setStyleSheet(
            "color: #64748b; font-size: 11px; background: transparent; border: none;"
        )
        self._install_progress_label.setVisible(False)
        is_top.addWidget(self._install_progress_label)

        self._launch_cursor_btn = QPushButton("▶ 启动")
        self._launch_cursor_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._launch_cursor_btn.setFixedHeight(30)
        self._launch_cursor_btn.setEnabled(False)
        self._launch_cursor_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: #fff; border: none;"
            "  border-radius: 8px; font-size: 12px; font-weight: 700; padding: 0 18px; }"
            "QPushButton:hover { background: #4338ca; }"
            "QPushButton:disabled { background: #94a3b8; color: #e2e8f0; }"
        )
        self._launch_cursor_btn.clicked.connect(self._on_launch_cursor)
        is_top.addWidget(self._launch_cursor_btn)

        self._install_btn = QPushButton("安装")
        self._install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._install_btn.setFixedHeight(30)
        self._install_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #475569;"
            "  border: 1.5px solid #cbd5e1; border-radius: 8px;"
            "  font-size: 12px; font-weight: 600; padding: 0 14px; }"
            "QPushButton:hover { background: #f1f5f9; border-color: #94a3b8; }"
            "QPushButton:disabled { background: #f8fafc; color: #cbd5e1; border-color: #e2e8f0; }"
        )
        self._install_btn.clicked.connect(self._on_install_cursor)
        is_top.addWidget(self._install_btn)

        self._uninstall_btn = QPushButton("卸载 Cursor")
        self._uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._uninstall_btn.setFixedHeight(30)
        self._uninstall_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444;"
            "  border: 1.5px solid #fecaca; border-radius: 8px;"
            "  font-size: 12px; font-weight: 600; padding: 0 14px; }"
            "QPushButton:hover { background: #fef2f2; border-color: #f87171; }"
            "QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }"
        )
        self._uninstall_btn.clicked.connect(self._on_uninstall_cursor)
        is_top.addWidget(self._uninstall_btn)

        is_outer.addLayout(is_top)

        # ── 第二行：检测到的安装路径（无论是否使用无感换号都需要展示） ──
        is_path_row = QHBoxLayout()
        is_path_row.setContentsMargins(0, 0, 0, 0)
        is_path_row.setSpacing(8)

        self._install_path_label = QLabel("搜索中...")
        self._install_path_label.setStyleSheet(
            "color: #64748b; font-size: 11px; background: transparent;"
            "border: none; padding: 0;"
        )
        self._install_path_label.setWordWrap(True)
        is_path_row.addWidget(self._install_path_label, 1)

        # 仅在自动检测失败时显示：手动重扫 / 选择 Cursor.app 路径
        self._detect_path_btn = QPushButton("检测")
        self._detect_path_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detect_path_btn.setFixedHeight(24)
        self._detect_path_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #4f46e5;"
            "  border: 1.2px solid #c7d2fe; border-radius: 6px;"
            "  font-size: 11px; font-weight: 600; padding: 0 12px; }"
            "QPushButton:hover { background: #eef2ff; border-color: #a5b4fc; }"
            "QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }"
        )
        self._detect_path_btn.clicked.connect(self._on_detect_cursor_path)
        self._detect_path_btn.setVisible(False)
        is_path_row.addWidget(self._detect_path_btn, 0, Qt.AlignmentFlag.AlignRight)

        is_outer.addLayout(is_path_row)

        vbox.addWidget(install_strip)
        threading.Thread(target=self._bg_detect_install, daemon=True).start()

        # ========== 操作面板 ==========
        panel = Card()
        panel.add_widget(CardHeader("操作面板"))

        # 账号 + 登录状态（同行显示）
        acct_row = QWidget()
        acct_l = QHBoxLayout(acct_row)
        acct_l.setContentsMargins(0, 6, 0, 6)
        acct_l.setSpacing(12)
        acct_lb = QLabel("当前账号")
        acct_lb.setObjectName("CardLabel")
        acct_lb.setMinimumWidth(72)
        self._email_label = QLabel("点击「获取账号并登录」获取")
        self._email_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1e293b;"
            "background: transparent; border: none;"
        )
        self._status_badge = StatusBadge("未登录", active=False)
        acct_l.addWidget(acct_lb)
        acct_l.addWidget(self._email_label, 1)
        acct_l.addWidget(self._status_badge)
        panel.add_widget(acct_row)

        # 额度 + 操作按钮（同行）
        action_w = QWidget()
        action_l = QHBoxLayout(action_w)
        action_l.setContentsMargins(0, 6, 0, 4)
        action_l.setSpacing(12)

        self._total_label = self._quota_chip("总额度", "—", "#2563eb")
        self._remain_label = self._quota_chip("剩余", "—", "#059669")
        action_l.addWidget(self._total_label)
        action_l.addWidget(self._remain_label)
        action_l.addStretch()

        self._refresh_btn = self._action_button(
            "获取账号并登录",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f46e5, stop:1 #6366f1)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4338ca, stop:1 #4f46e5)",
            "#3730a3",
            self._on_refresh_cursor,
        )
        self._refresh_btn.setMinimumHeight(38)
        self._refresh_btn.setMaximumHeight(38)
        self._reset_btn = self._action_button(
            "重置机器标识",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #dc2626, stop:1 #ef4444)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b91c1c, stop:1 #dc2626)",
            "#991b1b",
            self._on_reset_machine_code,
        )
        self._reset_btn.setMinimumHeight(38)
        self._reset_btn.setMaximumHeight(38)
        action_l.addWidget(self._refresh_btn)
        action_l.addWidget(self._reset_btn)
        panel.add_widget(action_w)
        vbox.addWidget(panel)

        # ========== 无感换号 ==========
        self._inject_panel = inject_panel = Card()
        inject_panel.add_widget(CardHeader("无感换号"))

        inject_desc = QLabel(
            "注入 Cursor 后，换号无需重启，自动热替换 Token。"
        )
        inject_desc.setStyleSheet(
            "color: #64748b; font-size: 12px; padding: 2px 0 4px 0; "
            "background: transparent; border: none;"
        )
        inject_desc.setWordWrap(True)
        inject_panel.add_widget(inject_desc)

        # 状态 + 目录 + 按钮（紧凑两行）
        inject_row1 = QWidget()
        ir1 = QHBoxLayout(inject_row1)
        ir1.setContentsMargins(0, 2, 0, 2)
        ir1.setSpacing(10)
        inject_lb = QLabel("注入状态")
        inject_lb.setObjectName("CardLabel")
        inject_lb.setMinimumWidth(64)
        self._inject_badge = StatusBadge("检测中", active=False)
        ir1.addWidget(inject_lb)
        ir1.addWidget(self._inject_badge)
        ir1.addStretch()
        self._inject_btn = self._action_button(
            "注入 Cursor",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7c3aed, stop:1 #8b5cf6)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6d28d9, stop:1 #7c3aed)",
            "#5b21b6",
            self._on_inject_or_restore,
        )
        self._inject_btn.setMinimumHeight(36)
        self._inject_btn.setMaximumHeight(36)
        ir1.addWidget(self._inject_btn)

        inject_panel.add_widget(inject_row1)
        vbox.addWidget(inject_panel)

        threading.Thread(target=self._bg_init_inject_status, daemon=True).start()

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

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        now = time.monotonic()
        if now - self._last_refresh_ts > 60:
            self._last_refresh_ts = now
            self._refresh_all()
        self._ensure_mini_float()

    def _refresh_all(self):
        """进入页面时拉取设备完整状态，刷新账号、额度、历史、注入状态。"""
        threading.Thread(target=self._bg_refresh_all, daemon=True).start()

    def _resolve_seamless_key(self) -> str:
        sys_name = platform.system()
        if sys_name == "Windows":
            return "windows"
        elif sys_name == "Darwin":
            arch = platform.machine().lower()
            return "mac_arm" if "arm" in arch else "mac_intel"
        else:
            return "linux"

    def _bg_check_seamless_config(self):
        try:
            cfg = self.api.get_seamless_switch_config()
            key = self._resolve_seamless_key()
            val = cfg.get(key, True)
            if isinstance(val, str):
                self._seamless_enabled = val.lower() not in ("false", "0", "")
            else:
                self._seamless_enabled = bool(val)
        except Exception:
            self._seamless_enabled = True
        from core.seamless_server import set_seamless_disabled
        set_seamless_disabled(not self._seamless_enabled)

    def _bg_load_seamless_and_apply(self):
        try:
            self._bg_check_seamless_config()
            QMetaObject.invokeMethod(self, "_apply_seamless_visibility", Qt.ConnectionType.QueuedConnection)
        except RuntimeError:
            pass

    @Slot()
    def _apply_seamless_visibility(self):
        self._inject_panel.setVisible(self._seamless_enabled)

    def _bg_refresh_all(self):
        try:
            self._bg_check_seamless_config()
            r = self.api.init_device()
            self._refresh_all_result = r
            QMetaObject.invokeMethod(self, "_apply_refresh_all", Qt.ConnectionType.QueuedConnection)
            self._bg_init_inject_status()
            self._bg_detect_install()
        except RuntimeError:
            return
        try:
            from core.cursor_process import disable_cursor_auto_update
            disable_cursor_auto_update()
        except Exception:
            pass

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
            self._refresh_btn.setEnabled(True)
            self._reset_btn.setEnabled(True)
            self._inject_panel.setVisible(self._seamless_enabled)
            # 当前账号以 Cursor 本地数据库为准；本地查不到再回落到后端记忆值
            email = self._read_local_cursor_email() or data.get("email", "")
            if email:
                self._current_email = email
                self._email_label.setText(email)
                self._status_badge.update_status("已登录", True)
            else:
                self._current_email = ""
                self._email_label.setText("点击「获取账号并登录」获取")
                self._status_badge.update_status("未登录", False)
            self._apply_quota_from_data(data)

    @staticmethod
    def _read_local_cursor_email() -> str:
        """从 Cursor 本地 SQLite（state.vscdb）读取真实登录邮箱。"""
        try:
            from core.cursor_auth import CursorAuthManager
            return CursorAuthManager().get_email() or ""
        except Exception:
            return ""

    @Slot(str)
    def _on_auto_switched(self, email: str):
        """无感换号自动切换后更新 UI"""
        self._current_email = email
        self._email_label.setText(email)
        self._status_badge.update_status("已登录", True)

    @Slot()
    def _on_inject_account_applied(self):
        """注入后写完 Cursor 本地 DB，回到主线程刷新当前账号显示"""
        local = self._read_local_cursor_email()
        if local:
            self._current_email = local
        if self._current_email:
            self._email_label.setText(self._current_email)
            self._status_badge.update_status("已登录", True)
        self._refresh_inject_status()
        try:
            self._fetch_quota()
        except Exception:
            pass

    def _show_not_activated(self):
        """设备未激活/封禁/过期时显示空状态页面。"""
        self._current_email = ""
        self._current_token = ""
        self._current_pwd = ""
        self._page_stack.setCurrentIndex(0)

    def _ensure_mini_float(self):
        if self._mini_float is not None:
            return
        from ui.cursor_mini_float import CursorMiniFloatWindow

        parent = self.window()
        self._mini_float = CursorMiniFloatWindow(parent)
        self._mini_float.swap_clicked.connect(lambda: self._on_refresh_cursor(from_float=True))
        self._mini_float.reset_clicked.connect(lambda: self._on_reset_machine_code(from_float=True))
        self._mini_float.closed_by_user.connect(self._on_mini_float_closed)

    def _sync_mini_float_buttons(self):
        if not self._mini_float:
            return
        self._mini_float.set_actions_enabled(
            self._refresh_btn.isEnabled(),
            self._reset_btn.isEnabled(),
        )

    def _restore_main_window(self):
        mw = self.window()
        if mw:
            mw.show()
            mw.raise_()
            mw.activateWindow()

    def _on_mini_float_closed(self):
        """仅浮窗 × 关闭时恢复主界面。"""
        self._restore_main_window()

    def _hide_mini_float_for_modal(self):
        """换号/重置前收起浮窗；需先恢复主窗口以便确认框与流程可操作。"""
        if self._mini_float and self._mini_float.isVisible():
            self._mini_float.hide()
        self._restore_main_window()

    def _on_toggle_mini_float(self):
        self._ensure_mini_float()
        if self._mini_float.isVisible():
            return
        self._sync_mini_float_buttons()
        self._mini_float.show_at_screen_top()
        mw = self.window()
        if mw:
            mw.hide()

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
        """根据 data 中的 unlimited / sum_count / over_count 更新额度显示。"""
        if data.get("unlimited"):
            self._update_quota_chip(self._total_label, "∞")
            self._update_quota_chip(self._remain_label, "∞")
        else:
            total = data.get("sum_count")
            remain = data.get("over_count")
            if total is not None:
                self._update_quota_chip(self._total_label, str(total))
            if remain is not None:
                self._update_quota_chip(self._remain_label, str(remain))

    def set_guide(self, text: str | None):
        """Show or hide the usage guide section."""
        if text:
            self._guide_label.setText(text)
            self._guide_panel.setVisible(True)
        else:
            self._guide_panel.setVisible(False)

    def _do_show_msg(self, kind: str, title: str, msg: str):
        if self._from_float and self._mini_float and self._mini_float.isVisible():
            display = msg if msg and msg != title else title
            self._mini_float.show_result(display, kind == "info")
            return
        if kind == "info":
            QMessageBox.information(self, title, msg)
        else:
            QMessageBox.warning(self, title, msg)

    def _emit_info(self, title: str, msg: str):
        self._show_msg.emit("info", title, msg)

    def _emit_warn(self, title: str, msg: str):
        self._show_msg.emit("warn", title, msg)

    def _thread_exit_cursor_or_warn(self) -> bool:
        from core.cursor_process import exit_cursor

        if not exit_cursor(timeout=8):
            self._emit_warn(
                "关闭 Cursor 失败",
                "Cursor 进程未能正常退出，请手动关闭后重试。",
            )
            return False
        return True

    def _thread_reset_machine_or_warn(self) -> bool:
        from core.machine_reset import MachineIDResetter

        resetter = MachineIDResetter()
        if not resetter.reset():
            # 重置失败不阻断登录流程，仅打印日志（账号凭证写入仍会继续）
            print("[CursorPage] 机器标识重置失败，跳过此步骤继续登录")
        return True

    def _thread_update_auth_or_warn(self, email: str, token: str) -> bool:
        from core.cursor_auth import CursorAuthManager

        auth = CursorAuthManager()
        if not auth.db_exists():
            self._emit_warn(
                "写入失败",
                "未检测到 Cursor 本地数据，请确认已安装并至少启动过一次 Cursor。",
            )
            return False
        if not auth.update_auth(email, token, token):
            self._emit_warn(
                "写入失败",
                "登录凭证写入失败，请确认 Cursor 已完全退出后重试。",
            )
            return False
        return True

    def _thread_clear_cache(self) -> bool:
        from core.cursor_process import clear_cursor_cache

        clear_cursor_cache()
        return True

    def _thread_open_cursor_or_warn(self, after_inject: bool = False) -> bool:
        from core.cursor_process import open_cursor

        return open_cursor(after_inject=after_inject)

    # ------------------------------------------------------------------ 无感换号
    @staticmethod
    def _is_seamless_ready() -> bool:
        try:
            from core.seamless_switch import is_seamless_ready
            return is_seamless_ready()
        except Exception:
            return False

    def _refresh_inject_status(self):
        """刷新注入状态指示"""
        try:
            from core.cursor_injector import CursorInjector
            injector = CursorInjector()
            if not injector.is_available():
                self._inject_badge.update_status("未检测到", False)
                self._inject_btn.setText("注入 Cursor")
                self._inject_btn.setEnabled(True)
            elif injector.is_injected():
                self._inject_badge.update_status("已注入", True)
                self._inject_btn.setText("还原 Cursor")
                self._inject_btn.setEnabled(True)
            else:
                self._inject_badge.update_status("未注入", False)
                self._inject_btn.setText("注入 Cursor")
                self._inject_btn.setEnabled(True)
        except Exception:
            self._inject_badge.update_status("检测失败", False)
            self._inject_btn.setEnabled(True)

    def _bg_init_inject_status(self):
        """后台预检测注入状态，结果传回 UI 线程刷新"""
        import time
        time.sleep(0.5)
        try:
            from core.cursor_injector import CursorInjector
            injector = CursorInjector()
            self._bg_inject_available = injector.is_available()
            self._bg_inject_injected = injector.is_injected() if self._bg_inject_available else False
            self._bg_inject_path = injector.js_path
        except Exception:
            self._bg_inject_available = False
            self._bg_inject_injected = False
            self._bg_inject_path = None
        QMetaObject.invokeMethod(
            self, "_apply_inject_status",
            Qt.ConnectionType.QueuedConnection,
        )

    @Slot()
    def _apply_inject_status(self):
        available = getattr(self, "_bg_inject_available", False)
        injected = getattr(self, "_bg_inject_injected", False)

        if not available:
            self._inject_badge.update_status("未检测到", False)
            self._inject_btn.setText("注入 Cursor")
            self._inject_btn.setEnabled(True)
        elif injected:
            self._inject_badge.update_status("已注入", True)
            self._inject_btn.setText("还原 Cursor")
            self._inject_btn.setEnabled(True)
        else:
            self._inject_badge.update_status("未注入", False)
            self._inject_btn.setText("注入 Cursor")
            self._inject_btn.setEnabled(True)

    def _on_inject_or_restore(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        from core.cursor_injector import CursorInjector
        injector = CursorInjector()

        if not injector.is_available():
            QMessageBox.warning(
                self, "未找到 Cursor",
                "未检测到 Cursor 安装，请确认：\n\n"
                "1. Cursor 已正确安装\n"
                "2. Cursor 至少启动过一次",
            )
            return

        if injector.is_injected():
            reply = QMessageBox.question(
                self, "确认还原",
                "将还原 Cursor 到未注入状态，无感换号功能将不可用。\n\n"
                "需要先关闭 Cursor，还原后重新启动。\n"
                "请确保当前代码已保存！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._working = True
            self._inject_btn.setEnabled(False)
            self._inject_btn.setText("还原中...")
            threading.Thread(target=self._do_restore_inject, daemon=True).start()
        else:
            reply = QMessageBox.question(
                self, "确认注入",
                "将注入 Cursor 以启用无感换号功能。\n\n"
                "需要先关闭 Cursor，注入后重新启动。\n"
                "注入后所有换号操作将不再需要重启 Cursor。\n\n"
                "⚠ 开启后本软件需在后台保持运行，\n"
                "关闭窗口会自动最小化到系统托盘。\n\n"
                "请确保当前代码已保存！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._working = True
            self._inject_btn.setEnabled(False)
            self._inject_btn.setText("注入中...")
            threading.Thread(target=self._do_inject, daemon=True).start()

    def _do_inject(self):
        try:
            if not self._thread_exit_cursor_or_warn():
                return
            from core.cursor_injector import CursorInjector
            injector = CursorInjector()

            # 先还原到干净状态（修复可能的 CRLF 污染等历史问题）
            if injector.is_injected():
                injector.restore()
                print("[Inject] Restored before re-inject for clean state")

            ok, msg = injector.inject()
            if not ok:
                self._emit_warn("注入失败", msg)
                return

            self._thread_clear_cache()

            # 注入完成后强制向服务端取一个新账号，写入 Cursor 本地 DB +
            # 重置机器码 + 写 seamless_state，这样打开 Cursor 立刻就是新账号。
            login_tip = ""
            email = ""
            token = ""
            try:
                r = self.api.get_credentials()
                if r.get("success"):
                    data = r.get("data") or {}
                    email = data.get("email", "") or ""
                    token = data.get("token", "") or ""
                else:
                    login_tip = f"\n\n⚠ 获取账号失败：{r.get('message', '服务器未返回有效数据')}"
            except Exception as e:
                print(f"[Inject] get_credentials error: {e}")
                login_tip = f"\n\n⚠ 获取账号异常：{e}"

            if email and token:
                # 重置机器码 → 写 Cursor SQLite → 写无感换号状态文件
                if not self._thread_reset_machine_or_warn():
                    return
                if not self._thread_update_auth_or_warn(email, token):
                    return
                try:
                    from core.seamless_switch import seamless_switch
                    seamless_switch(email, token)
                except Exception as e:
                    print(f"[Inject] seamless_switch error: {e}")
                self._current_email = email
                login_tip = f"\n\n已自动登录账号: {email}"
                # 回主线程刷新"当前登录账号"显示（从 Cursor 本地 DB 读取）
                QMetaObject.invokeMethod(
                    self, "_on_inject_account_applied",
                    Qt.ConnectionType.QueuedConnection,
                )
            elif not login_tip:
                # 没拿到账号也没异常信息，兜底把 state 清零，让注入 JS 启动后去拉
                from core.seamless_server import write_state
                write_state({
                    "config": {"enabled": True},
                    "accessToken": "",
                    "refreshToken": "",
                    "email": "",
                    "is_new": False,
                    "machineIds": {},
                })

            self._thread_open_cursor_or_warn(after_inject=True)
            self._emit_info(
                "注入成功",
                f"{msg}{login_tip}\n\n"
                "⚠ 无感换号需要本软件在后台保持运行，\n"
                "点击窗口关闭按钮即可最小化到系统托盘。\n"
                "请勿完全退出软件，否则自动换号将失效。",
            )
        except Exception as e:
            self._emit_warn("注入失败", f"操作异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_inject_btn_restore",
                Qt.ConnectionType.QueuedConnection,
            )

    def _do_restore_inject(self):
        try:
            if not self._thread_exit_cursor_or_warn():
                return
            from core.cursor_injector import CursorInjector
            injector = CursorInjector()
            ok, msg = injector.restore()
            if ok:
                self._thread_clear_cache()
                self._thread_open_cursor_or_warn()
                self._emit_info("还原成功", msg)
            else:
                self._emit_warn("还原失败", msg)
        except Exception as e:
            self._emit_warn("还原失败", f"操作异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_inject_btn_restore",
                Qt.ConnectionType.QueuedConnection,
            )

    @Slot()
    def _on_inject_btn_restore(self):
        self._refresh_inject_status()

    # ------------------------------------------------------------------ 额度预检
    def _check_quota_or_warn(self, from_float: bool) -> bool:
        """检查剩余额度，不足时提示并返回 False。无限额度直接放行。"""
        r = self.api.refresh_count()
        if not r.get("success"):
            return True
        data = r.get("data") or {}
        if data.get("unlimited"):
            return True
        remain = data.get("over_count", 0)
        try:
            remain = int(remain)
        except (ValueError, TypeError):
            remain = 0
        if remain <= 0:
            if from_float and self._mini_float and self._mini_float.isVisible():
                self._mini_float.show_result("当前额度已用完", False)
            else:
                QMessageBox.warning(
                    self, "额度不足",
                    "当前额度已用完，无法执行此操作。\n请联系客服充值后再试。",
                )
            return False
        return True

    # ------------------------------------------------------------------ 获取账号并登录
    def _is_injected(self) -> bool:
        try:
            from core.cursor_injector import CursorInjector
            return CursorInjector().is_injected()
        except Exception:
            return False

    def _on_refresh_cursor(self, from_float=False):
        if self._working:
            if not from_float:
                QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        if self._is_injected():
            if from_float and self._mini_float:
                self._mini_float.show_error("请先还原注入")
            else:
                self._hide_mini_float_for_modal()
                QMessageBox.warning(
                    self, "无法手动换号",
                    "当前已开启无感换号，系统会自动切换账号。\n\n"
                    "如需手动换号，请先点击「还原 Cursor」关闭无感换号注入。",
                )
            return

        self._from_float = from_float

        if not from_float:
            self._hide_mini_float_for_modal()
            if not self._check_quota_or_warn(False):
                return
            reply = QMessageBox.question(
                self, "确认换号",
                "将为您获取新账号并自动完成登录，"
                "Cursor 会在过程中重启。\n\n"
                "请确保当前代码已保存！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        else:
            if not self._check_quota_or_warn(True):
                return
            if self._mini_float:
                self._mini_float.show_working("换号中")

        self._working = True
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("正在登录...")
        if not from_float:
            self._sync_mini_float_buttons()
        target = self._do_refresh_cursor
        t = threading.Thread(target=target, daemon=True)
        t.start()

    def _do_refresh_cursor(self):
        try:
            r = self.api.get_credentials()
            if not r.get("success"):
                self._emit_warn("换号失败", r.get("message", "服务器未返回有效数据"))
                return

            data = r.get("data") or {}
            email = data.get("email", "")
            token = data.get("token", "")
            pwd = data.get("pwd", "")

            if not email or not token:
                self._emit_warn("换号失败", data.get("message", "当前暂无可分配账号，请稍后再试"))
                return

            self._current_email = email
            self._current_token = token
            self._current_pwd = pwd

            if not self._thread_exit_cursor_or_warn():
                return
            if not self._thread_reset_machine_or_warn():
                return
            if not self._thread_update_auth_or_warn(email, token):
                return
            self._thread_clear_cache()
            cursor_opened = self._thread_open_cursor_or_warn()
            self._cursor_opened = cursor_opened

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
        # 换号成功，自动认证已写入 Cursor SQLite → 用本地库再校对一次
        local = self._read_local_cursor_email()
        if local:
            self._current_email = local
        self._email_label.setText(self._current_email)
        self._status_badge.update_status("已登录", True)
        self._fetch_quota()
        self._refresh_inject_status()
        opened = getattr(self, "_cursor_opened", True)
        tip = f"新账号已自动登录 Cursor\n\n当前账号: {self._current_email}"
        if not opened:
            tip += "\n\n⚠ 未找到 Cursor 安装路径，请手动打开 Cursor。"
        if self._from_float and self._mini_float:
            self._mini_float.show_result("换号成功" if opened else "换号成功（请手动打开 Cursor）", True)
        else:
            QMessageBox.information(self, "换号成功", tip)

    @Slot()
    def _on_refresh_btn_restore(self):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("获取账号并登录")
        if not self._from_float:
            self._sync_mini_float_buttons()

    # ------------------------------------------------------------------ 重置机器标识
    def _on_reset_machine_code(self, from_float=False):
        if self._working:
            if not from_float:
                QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        if self._is_injected():
            if from_float and self._mini_float:
                self._mini_float.show_error("请先还原注入")
            else:
                self._hide_mini_float_for_modal()
                QMessageBox.warning(
                    self, "无法手动重置",
                    "当前已开启无感换号，换号时会自动重置机器码。\n\n"
                    "如需手动重置，请先点击「还原 Cursor」关闭无感换号注入。",
                )
            return

        self._from_float = from_float

        if not from_float:
            self._hide_mini_float_for_modal()
            if not self._check_quota_or_warn(False):
                return
            reply = QMessageBox.question(
                self, "确认重置",
                "将重置当前设备的机器标识，Cursor 会在过程中重启。\n\n"
                "当前登录状态不受影响，无需重新获取账号。\n\n"
                "请确保当前代码已保存！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        else:
            if not self._check_quota_or_warn(True):
                return
            if self._mini_float:
                self._mini_float.show_working("重置中")

        self._working = True
        self._reset_btn.setEnabled(False)
        self._reset_btn.setText("正在重置...")
        if not from_float:
            self._sync_mini_float_buttons()
        t = threading.Thread(target=self._do_reset_machine, daemon=True)
        t.start()

    def _do_reset_machine(self):
        try:
            if not self._thread_exit_cursor_or_warn():
                return
            if not self._thread_reset_machine_or_warn():
                return
            self._thread_clear_cache()
            cursor_opened = self._thread_open_cursor_or_warn()
            self._cursor_opened = cursor_opened

            QMetaObject.invokeMethod(
                self, "_on_reset_done",
                Qt.ConnectionType.QueuedConnection,
            )
        except Exception as e:
            self._emit_warn("重置失败", f"重置过程异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_reset_btn_restore",
                Qt.ConnectionType.QueuedConnection,
            )

    @Slot()
    def _on_reset_done(self):
        opened = getattr(self, "_cursor_opened", True)
        msg = "机器标识已更新，Cursor 已重新启动。"
        if not opened:
            msg = "机器标识已更新。\n\n⚠ 未找到 Cursor 安装路径，请手动打开 Cursor。"
        if self._from_float and self._mini_float:
            self._mini_float.show_result("重置完成" if opened else "重置完成（请手动打开 Cursor）", True)
        else:
            QMessageBox.information(self, "重置完成", msg)

    @Slot()
    def _on_reset_btn_restore(self):
        self._reset_btn.setEnabled(True)
        self._reset_btn.setText("重置机器标识")
        if not self._from_float:
            self._sync_mini_float_buttons()

    # ------------------------------------------------------------------ 额度（进入页面时自动拉取）
    def _fetch_quota(self):
        r = self.api.refresh_count()
        if not r.get("success"):
            return
        data = r.get("data", {})
        self._apply_quota_from_data(data)

    # ------------------------------------------------------------------ 启动 Cursor
    def _on_launch_cursor(self):
        try:
            from core.cursor_process import open_cursor
            if not open_cursor():
                QMessageBox.warning(
                    self, "启动失败",
                    "未找到 Cursor 安装路径，请确认已正确安装。",
                )
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    # ------------------------------------------------------------------ 安装管理
    def _bg_detect_install(self):
        """Background: detect whether Cursor is installed, its version and install path."""
        time.sleep(0.3)
        try:
            from core.cursor_process import (
                is_cursor_installed, get_cursor_version, _find_cursor_executable,
            )
            self._bg_installed = is_cursor_installed()
            self._bg_version = get_cursor_version() if self._bg_installed else None
            self._bg_install_path = _find_cursor_executable() if self._bg_installed else None
        except Exception:
            self._bg_installed = False
            self._bg_version = None
            self._bg_install_path = None
        QMetaObject.invokeMethod(self, "_apply_install_status", Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _format_cursor_install_dir(exe_path: str) -> str:
        """把 Cursor 可执行文件路径反推为用户可识别的安装目录展示文本"""
        if not exe_path:
            return ""
        norm = exe_path.replace("\\", "/")
        # macOS: /Applications/Cursor.app/Contents/MacOS/Cursor → /Applications/Cursor.app
        idx = norm.lower().find("/cursor.app/")
        if idx != -1:
            return norm[: idx + len("/Cursor.app")]
        # Windows: …/cursor/Cursor.exe（或 app-x.y.z/Cursor.exe）→ 安装根目录
        low = norm.lower()
        for marker in ("/programs/cursor/", "/cursor/"):
            j = low.rfind(marker)
            if j != -1:
                return norm[: j + len(marker) - 1]
        return os.path.dirname(exe_path)

    @Slot()
    def _apply_install_status(self):
        installed = getattr(self, "_bg_installed", False)
        version = getattr(self, "_bg_version", None)
        install_path = getattr(self, "_bg_install_path", None)
        if installed:
            self._install_status_badge.update_status("已安装", True)
            self._install_ver_label.setText(f"v{version}" if version else "")
            self._install_btn.setText("安装 Cursor")
            self._uninstall_btn.setEnabled(True)
            self._launch_cursor_btn.setEnabled(True)
            display = self._format_cursor_install_dir(install_path) if install_path else ""
            if display:
                self._install_path_label.setText(f"✓ 已找到  {display}")
                self._install_path_label.setStyleSheet(
                    "color: #059669; font-size: 11px; background: transparent;"
                    "border: none; padding: 0;"
                )
                self._detect_path_btn.setVisible(False)
            else:
                self._install_path_label.setText("已检测到 Cursor，但未能解析安装路径")
                self._install_path_label.setStyleSheet(
                    "color: #d97706; font-size: 11px; background: transparent;"
                    "border: none; padding: 0;"
                )
                self._detect_path_btn.setVisible(True)
        else:
            self._install_status_badge.update_status("未安装", False)
            self._install_ver_label.setText("")
            self._install_btn.setText("安装 Cursor")
            self._uninstall_btn.setEnabled(False)
            self._launch_cursor_btn.setEnabled(False)
            self._install_path_label.setText("未找到 Cursor 安装目录，请点击右侧「检测」选择 Cursor 路径")
            self._install_path_label.setStyleSheet(
                "color: #dc2626; font-size: 11px; background: transparent;"
                "border: none; padding: 0;"
            )
            self._detect_path_btn.setVisible(True)

    def _on_detect_cursor_path(self):
        """先重扫一次；若仍未检测到，弹出文件选择器让用户手动指定 Cursor 安装目录。"""
        self._detect_path_btn.setEnabled(False)
        self._detect_path_btn.setText("检测中…")

        def _bg_rescan_then_prompt():
            try:
                from core.cursor_process import is_cursor_installed
                installed = is_cursor_installed()
            except Exception:
                installed = False
            QMetaObject.invokeMethod(
                self, "_after_rescan_for_detect",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, installed),
            )

        threading.Thread(target=_bg_rescan_then_prompt, daemon=True).start()

    @Slot(bool)
    def _after_rescan_for_detect(self, installed: bool):
        self._detect_path_btn.setEnabled(True)
        self._detect_path_btn.setText("检测")
        if installed:
            threading.Thread(target=self._bg_detect_install, daemon=True).start()
            return
        self._prompt_pick_cursor_path()

    def _prompt_pick_cursor_path(self):
        """弹出文件选择器：mac 选 Cursor.app，其他平台选安装目录。"""
        from PySide6.QtWidgets import QFileDialog
        system = platform.system()

        if system == "Darwin":
            # 选 .app（Qt 在 mac 上选 .app 用 getOpenFileName 更顺，因为 .app 是 bundle）
            picked, _ = QFileDialog.getOpenFileName(
                self, "选择 Cursor.app",
                "/Applications", "Applications (*.app)"
            )
            if not picked:
                return
            chosen_root = picked
        else:
            picked = QFileDialog.getExistingDirectory(
                self, "选择 Cursor 安装目录（包含 Cursor.exe / cursor 可执行文件）",
                os.path.expanduser("~"),
            )
            if not picked:
                return
            chosen_root = picked

        try:
            from core.cursor_process import (
                validate_user_cursor_path, save_user_cursor_path,
            )
        except Exception as e:
            QMessageBox.warning(self, "检测失败", f"无法加载检测模块: {e}")
            return

        if not validate_user_cursor_path(chosen_root):
            QMessageBox.warning(
                self, "检测失败",
                f"该路径下未找到 Cursor 的 workbench 文件，请确认选对了 Cursor 安装位置。\n\n"
                f"已选择：{chosen_root}",
            )
            return

        if not save_user_cursor_path(chosen_root):
            QMessageBox.warning(self, "保存失败", "写入用户配置失败，请检查磁盘权限。")
            return

        threading.Thread(target=self._bg_detect_install, daemon=True).start()
        threading.Thread(target=self._bg_init_inject_status, daemon=True).start()
        QMessageBox.information(
            self, "检测成功",
            f"已记住该 Cursor 安装位置：\n{chosen_root}",
        )

    def _on_install_cursor(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        installed = getattr(self, "_bg_installed", False)
        if installed:
            reply = QMessageBox.question(
                self, "确认重新安装",
                "检测到 Cursor 已安装，重新安装将覆盖当前版本。\n\n"
                "安装过程中会自动关闭 Cursor，请确保代码已保存！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        else:
            reply = QMessageBox.question(
                self, "确认安装",
                "将从官方源下载并安装最新版 Cursor。\n\n"
                "安装包约 150~200 MB，请确保网络通畅。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._working = True
        self._install_btn.setEnabled(False)
        self._uninstall_btn.setEnabled(False)
        self._launch_cursor_btn.setEnabled(False)
        self._install_btn.setText("安装中…")
        self._install_progress.setVisible(True)
        self._install_progress.setValue(0)
        self._install_progress_label.setVisible(True)
        self._install_progress_label.setText("准备下载...")
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        try:
            from core.cursor_process import install_cursor, exit_cursor, set_cursor_download_urls
            try:
                urls = self.api.get_cursor_download_urls()
                if urls:
                    set_cursor_download_urls(urls)
            except Exception:
                pass
            exit_cursor(timeout=8)

            def progress_cb(pct, text):
                self._install_progress_sig.emit(pct, text)

            ok, msg = install_cursor(progress_cb=progress_cb)
            self._install_done_sig.emit(ok, msg)
        except Exception as e:
            self._install_done_sig.emit(False, f"安装异常: {e}")
        finally:
            self._working = False

    @Slot(int, str)
    def _on_install_progress(self, pct: int, text: str):
        self._install_progress.setValue(pct)
        self._install_progress_label.setText(text)

    @Slot(bool, str)
    def _on_install_done(self, ok: bool, msg: str):
        self._install_progress.setVisible(False)
        self._install_progress_label.setVisible(False)
        self._install_btn.setEnabled(True)
        self._uninstall_btn.setEnabled(True)
        if ok:
            # 安装/重装后，旧的"用户手动指定路径"必然过期，清掉走默认检测
            try:
                from core.cursor_process import clear_user_cursor_path
                clear_user_cursor_path()
            except Exception:
                pass
            QMessageBox.information(self, "安装成功", msg)
        else:
            QMessageBox.warning(self, "安装失败", msg)
        threading.Thread(target=self._bg_detect_install, daemon=True).start()
        threading.Thread(target=self._bg_init_inject_status, daemon=True).start()

    def _on_uninstall_cursor(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        box = QMessageBox(self)
        box.setWindowTitle("确认卸载 Cursor")
        box.setText(
            "确定要彻底卸载 Cursor 吗？\n\n"
            "将执行以下操作：\n"
            "• 运行官方卸载程序\n"
            "• 删除安装目录和缓存\n"
            "• 清理快捷方式和注册表\n\n"
            "卸载前会自动关闭 Cursor，请确保代码已保存！"
        )
        box.setIcon(QMessageBox.Icon.Warning)

        clean_cb = QCheckBox("同时清除所有用户数据和配置（登录、设置、扩展等）")
        clean_cb.setChecked(True)
        clean_cb.setToolTip(
            "勾选后将删除 Cursor 的所有本地数据，实现 100% 彻底卸载"
        )
        box.setCheckBox(clean_cb)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        clean_data = clean_cb.isChecked()
        self._working = True
        self._install_btn.setEnabled(False)
        self._uninstall_btn.setEnabled(False)
        self._launch_cursor_btn.setEnabled(False)
        self._uninstall_btn.setText("卸载中…")
        threading.Thread(target=self._do_uninstall, args=(clean_data,), daemon=True).start()

    def _do_uninstall(self, clean_data: bool):
        try:
            from core.cursor_process import uninstall_cursor
            ok, msg = uninstall_cursor(clean_data=clean_data)
            if ok:
                self._emit_info("卸载成功", msg)
            else:
                self._emit_warn("卸载结果", msg)
        except Exception as e:
            self._emit_warn("卸载失败", f"卸载异常: {e}")
        finally:
            self._working = False
            QMetaObject.invokeMethod(self, "_on_uninstall_done", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _on_uninstall_done(self):
        # 卸载后旧的手动路径必然失效，清掉避免继续指向被删的目录
        try:
            from core.cursor_process import clear_user_cursor_path
            clear_user_cursor_path()
        except Exception:
            pass
        self._install_btn.setEnabled(True)
        self._uninstall_btn.setEnabled(True)
        self._uninstall_btn.setText("卸载 Cursor")
        threading.Thread(target=self._bg_detect_install, daemon=True).start()
        threading.Thread(target=self._bg_init_inject_status, daemon=True).start()

    # ------------------------------------------------------------------ 初始化数据加载
    def load_init_data(self, data: dict):
        if not data:
            return
        if data.get("banned") or not data.get("activated"):
            self._show_not_activated()
            return
        self._page_stack.setCurrentIndex(1)
        email = self._read_local_cursor_email() or data.get("email", "")
        if email:
            self._current_email = email
            self._email_label.setText(email)
            self._status_badge.update_status("已登录", True)
        else:
            self._current_email = ""
            self._email_label.setText("点击「获取账号并登录」获取")
            self._status_badge.update_status("未登录", False)

        self._apply_quota_from_data(data)

        threading.Thread(target=self._bg_load_seamless_and_apply, daemon=True).start()
