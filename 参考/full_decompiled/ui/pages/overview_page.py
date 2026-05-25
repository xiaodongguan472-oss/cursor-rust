"""首页 — 平台余额与激活"""

from __future__ import annotations

import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QScrollArea,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor, QShowEvent

from ui.platform_icons import platform_icon_label


def _is_transient_error(msg: str) -> bool:
    """Network / timeout errors that should not trigger auth redirect."""
    if not msg:
        return False
    s = msg.lower()
    if "无法连接" in msg:
        return True
    return any(
        x in s
        for x in (
            "connection",
            "timed out",
            "timeout",
            "refused",
            "network is unreachable",
            "name or service not known",
            "ssl",
            "max retries",
            "errno",
        )
    )


# 激活码展示行与 CDK 输入同一高度（macOS 上 QLineEdit 常不遵守 stylesheet 的 max-height）
_AUTH_CODE_ROW_HEIGHT = 42


def _shadow(w, blur=24, y=6, alpha=14):
    s = QGraphicsDropShadowEffect(w)
    s.setBlurRadius(blur)
    s.setOffset(0, y)
    s.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(s)


def _card(parent=None) -> QFrame:
    c = QFrame(parent)
    c.setStyleSheet(
        "QFrame { background: #ffffff; border: 1px solid #e8ecf1; border-radius: 18px; }"
    )
    _shadow(c)
    return c


class OverviewPage(QWidget):
    navigate_to = Signal(str)
    init_data_loaded = Signal(dict)
    auth_expired = Signal()

    def __init__(self, api_client, menu_config: dict | None = None, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._current_permissions: set = set()
        self._menu_config: dict = menu_config or {}
        self._init_running = False
        self._last_init_data = None
        self._last_init_time = 0.0
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
        vbox.setContentsMargins(32, 24, 32, 36)
        vbox.setSpacing(20)

        # 页面标题
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(0)
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(3)
        title = QLabel("首页")
        title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; "
            "letter-spacing: -0.5px;"
        )
        sub = QLabel("平台余额与激活码管理")
        sub.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addLayout(hdr_col)
        hdr_row.addStretch()
        vbox.addLayout(hdr_row)

        # ========== 平台余额 ==========
        sec_balance_hdr = QHBoxLayout()
        sec_balance_hdr.setSpacing(10)
        bal_bar = QFrame()
        bal_bar.setFixedSize(4, 18)
        bal_bar.setStyleSheet("background: #4f46e5; border-radius: 2px; border: none;")
        bal_tt = QLabel("平台余额")
        bal_tt.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none; padding: 0;"
        )
        sec_balance_hdr.addWidget(bal_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_balance_hdr.addWidget(bal_tt, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_balance_hdr.addStretch()

        self._refresh_balance_btn = QPushButton("刷新余额")
        self._refresh_balance_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_balance_btn.setStyleSheet(
            "QPushButton { background: #ffffff; color: #4f46e5; "
            "  border: 1.5px solid #e0e7ff; border-radius: 10px; "
            "  padding: 5px 16px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #eef2ff; border-color: #c7d2fe; }"
            "QPushButton:pressed { background: #e0e7ff; }"
            "QPushButton:disabled { color: #94a3b8; border-color: #e2e8f0; background: #f8fafc; }"
        )
        self._refresh_balance_btn.clicked.connect(self._refresh_all_balances)
        sec_balance_hdr.addWidget(self._refresh_balance_btn)
        vbox.addLayout(sec_balance_hdr)

        self._MENU_KEY_FOR_PLATFORM = {
            "Cursor": "cursor", "Cursor Pro": "cursor_pro", "Kiro": "kiro",
            "Codex": "codex", "Claude Code": "claude_code",
            "Gemini": "gemini", "OpenClaw": "openclaw",
            "Windsurf": "windsurf",
        }
        platforms = [
            ("Cursor", "#4f46e5", "#eef2ff", "#e0e7ff"),
            ("Cursor Pro",  "#7c3aed", "#f5f3ff", "#ede9fe"),
            ("Kiro",        "#0891b2", "#ecfeff", "#cffafe"),
            ("Codex",       "#059669", "#ecfdf5", "#d1fae5"),
            ("Claude Code", "#7c3aed", "#f5f3ff", "#ede9fe"),
            ("Gemini",      "#d97706", "#fffbeb", "#fef3c7"),
            ("OpenClaw",    "#dc2626", "#fef2f2", "#fecaca"),
            ("Windsurf",    "#0891b2", "#ecfeff", "#cffafe"),
        ]
        self._platform_balance_labels = {}
        self._platform_expire_labels = {}
        self._platform_cards: dict[str, QFrame] = {}

        bal_row = QHBoxLayout()
        bal_row.setSpacing(12)

        for idx, (name, color, bg, border_tint) in enumerate(platforms):
            pbox = QFrame()
            pbox.setStyleSheet(
                f"QFrame {{ background: {bg}; border: 1.5px solid {border_tint}; border-radius: 16px; }}"
                f"QFrame:hover {{ border: 1.5px solid {color}; background: {border_tint}; }}"
            )
            pbox.setCursor(Qt.CursorShape.PointingHandCursor)
            pbox.mousePressEvent = lambda _, n=name: self.navigate_to.emit(n)
            _shadow(pbox, blur=16, y=4, alpha=10)
            pv = QVBoxLayout(pbox)
            pv.setContentsMargins(16, 14, 16, 14)
            pv.setSpacing(6)

            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            icon_lbl = platform_icon_label(name, 22)
            pname = QLabel(name)
            pname.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {color}; "
                "background: transparent; border: none; letter-spacing: 0.3px;"
            )
            top_row.addWidget(icon_lbl)
            top_row.addWidget(pname)
            top_row.addStretch()
            pv.addLayout(top_row)

            pval = QLabel("—")
            pval.setStyleSheet(
                "font-size: 22px; font-weight: 800; color: #0f172a; "
                "background: transparent; border: none; margin-top: 2px;"
            )
            self._platform_balance_labels[name] = pval
            pv.addWidget(pval)

            expire_lbl = QLabel("")
            expire_lbl.setStyleSheet(
                "font-size: 10px; color: #64748b; font-weight: 500; "
                "background: transparent; border: none;"
            )
            self._platform_expire_labels[name] = expire_lbl
            pv.addWidget(expire_lbl)

            menu_key = self._MENU_KEY_FOR_PLATFORM.get(name, "")
            pbox.setVisible(not menu_key or self._is_platform_menu_enabled(menu_key))

            self._platform_cards[name] = pbox
            bal_row.addWidget(pbox)

        vbox.addLayout(bal_row)

        # ========== 激活与兑换 ==========
        sec_redeem_hdr = QHBoxLayout()
        sec_redeem_hdr.setSpacing(10)
        redeem_bar = QFrame()
        redeem_bar.setFixedSize(4, 18)
        redeem_bar.setStyleSheet("background: #059669; border-radius: 2px; border: none;")
        redeem_tt = QLabel("激活码")
        redeem_tt.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none; padding: 0;"
        )
        sec_redeem_hdr.addWidget(redeem_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_redeem_hdr.addWidget(redeem_tt, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_redeem_hdr.addStretch()
        vbox.addLayout(sec_redeem_hdr)

        redeem_card = _card()
        rcl = QVBoxLayout(redeem_card)
        rcl.setContentsMargins(24, 20, 24, 20)
        rcl.setSpacing(14)

        code_row = QHBoxLayout()
        code_row.setSpacing(10)
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("输入激活码")
        self._code_input.setFixedHeight(_AUTH_CODE_ROW_HEIGHT)
        self._code_input.setStyleSheet(
            "QLineEdit { background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 14px; "
            "padding: 0 16px; font-size: 14px; font-weight: 500; color: #0f172a; "
            "font-family: 'SF Mono','Menlo','Consolas',monospace; }"
            "QLineEdit:hover { border-color: #cbd5e1; background: #ffffff; }"
            "QLineEdit:focus { border-color: #6366f1; background: #ffffff; }"
        )
        self._redeem_btn = QPushButton("激  活")
        self._redeem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._redeem_btn.setFixedHeight(_AUTH_CODE_ROW_HEIGHT)
        self._redeem_btn.setStyleSheet(
            "QPushButton { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4f46e5, stop:1 #6366f1);"
            "  color: #fff; border: none; border-radius: 14px; "
            "  padding: 0 28px; font-size: 14px; font-weight: 700; letter-spacing: 0.5px; }"
            "QPushButton:hover { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4338ca, stop:1 #4f46e5); }"
            "QPushButton:pressed { background: #3730a3; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self._redeem_btn.clicked.connect(self._on_unified_redeem)
        self._code_input.returnPressed.connect(self._on_unified_redeem)
        code_row.addWidget(self._code_input, 1)
        code_row.addWidget(self._redeem_btn)
        rcl.addLayout(code_row)

        redeem_hint = QLabel("支持所有类型的激活码，系统自动识别并激活对应平台额度")
        redeem_hint.setStyleSheet(
            "font-size: 11px; color: #94a3b8; background: transparent; border: none;"
        )
        rcl.addWidget(redeem_hint)

        self._redeem_status = QLabel()
        self._redeem_status.setVisible(False)
        self._redeem_status.setWordWrap(True)
        self._redeem_status.setStyleSheet(
            "font-size: 12px; padding: 10px 14px; border-radius: 10px; "
            "background: transparent; border: none;"
        )
        rcl.addWidget(self._redeem_status)

        vbox.addWidget(redeem_card)

        # ========== 快速开始 ==========
        sec_guide_hdr = QHBoxLayout()
        sec_guide_hdr.setSpacing(10)
        guide_bar = QFrame()
        guide_bar.setFixedSize(4, 18)
        guide_bar.setStyleSheet("background: #d97706; border-radius: 2px; border: none;")
        guide_tt = QLabel("快速开始")
        guide_tt.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none; padding: 0;"
        )
        sec_guide_hdr.addWidget(guide_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_guide_hdr.addWidget(guide_tt, 0, Qt.AlignmentFlag.AlignVCenter)
        sec_guide_hdr.addStretch()
        vbox.addLayout(sec_guide_hdr)

        guide = _card()
        gl = QVBoxLayout(guide)
        gl.setContentsMargins(24, 20, 24, 24)
        gl.setSpacing(14)

        steps = [
            ("1", "输入激活码", "在上方输入激活码，系统自动识别并激活对应额度", "#4f46e5", "#eef2ff"),
            ("2", "选择目标软件", "在左侧菜单进入 Cursor、Cursor Pro、Kiro、Codex、Claude Code、Gemini 或 OpenClaw", "#059669", "#ecfdf5"),
            ("3", "开始使用", "Codex / Claude Code / Gemini 一键写入本地配置；Cursor / Kiro 按引导获取账号", "#d97706", "#fffbeb"),
        ]
        for num, title_text, desc_text, color, bg in steps:
            step = self._guide_step(num, title_text, desc_text, color, bg)
            gl.addWidget(step)

        vbox.addWidget(guide)

        vbox.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self._do_init()

    # ------------------------------------------------------------------ helpers
    def _guide_step(self, num, title_text, desc_text, color, bg):
        step = QFrame()
        step.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1.5px solid {color}18; border-radius: 14px; }}"
        )
        h = QHBoxLayout(step)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(14)

        badge = QLabel(num)
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {color}; color: #fff; font-size: 14px; font-weight: 800; "
            f"border-radius: 16px; border: none;"
        )

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title_text)
        t.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {color}; "
            "background: transparent; border: none;"
        )
        d = QLabel(desc_text)
        d.setWordWrap(True)
        d.setStyleSheet(
            "font-size: 12px; color: #64748b; "
            "background: transparent; border: none;"
        )
        col.addWidget(t)
        col.addWidget(d)

        h.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addLayout(col, 1)
        return step

    # ------------------------------------------------------------------ init
    _INIT_CACHE_TTL = 120  # seconds

    def _do_init(self):
        if self._init_running:
            return
        import time
        if (self._last_init_data is not None
                and (time.time() - self._last_init_time) < self._INIT_CACHE_TTL):
            return
        self._init_running = True

        def _safe_bg():
            try:
                self._bg_init()
            except Exception:
                self._init_result = {"success": False, "message": "初始化异常"}
                QMetaObject.invokeMethod(self, "_apply_init", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_safe_bg, daemon=True).start()

    def _bg_init(self):
        try:
            self._init_result = self.api.init_device()
        except Exception:
            self._init_result = {"success": False, "message": "网络请求异常"}
        QMetaObject.invokeMethod(self, "_apply_init", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_init(self):
        self._init_running = False

        r = getattr(self, "_init_result", None)
        if r is None:
            return

        if not r.get("success"):
            if r.get("auth_expired"):
                self.auth_expired.emit()
                return
            msg = r.get("message", "")
            if _is_transient_error(msg):
                self._show_pending_connection("")
            else:
                self._show_unauthorized()
            return

        data = r.get("data") or {}

        # Extract embedded config (redeem_placeholder, etc.)
        embedded_cfg = data.get("_config") or {}
        placeholder = embedded_cfg.get("redeem_placeholder", "")
        if placeholder:
            self._code_input.setPlaceholderText(str(placeholder))

        # Always emit so menu config gets applied regardless of activation
        self.init_data_loaded.emit(data)

        if data.get("banned") or not data.get("activated"):
            self._show_unauthorized()
            return

        import time
        self._last_init_data = data
        self._last_init_time = time.time()
        self._show_authorized(data)

    def _show_unauthorized(self):
        for name in self._platform_balance_labels:
            self._set_balance(name, "未激活", False)
        for lbl in self._platform_expire_labels.values():
            lbl.setText("")

    def _show_pending_connection(self, saved_code: str):
        for name in self._platform_balance_labels:
            self._set_balance(name, "未激活", False)
        for lbl in self._platform_expire_labels.values():
            lbl.setText("")

    def _is_platform_menu_enabled(self, menu_key: str) -> bool:
        """Check if platform is enabled in admin menu config."""
        if not self._menu_config:
            return True
        val = self._menu_config.get(menu_key, False)
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "")
        return bool(val)

    def update_menu_config(self, new_config: dict):
        """Dynamically update menu config and show/hide balance cards."""
        self._menu_config = new_config
        for name, pbox in self._platform_cards.items():
            menu_key = self._MENU_KEY_FOR_PLATFORM.get(name, "")
            pbox.setVisible(not menu_key or self._is_platform_menu_enabled(menu_key))

    _PERM_KEY_MAP = {
        "Cursor": "cursor",
        "Cursor Pro": "cursor_pro",
        "Kiro": "kiro",
        "Codex": "codex",
        "Claude Code": "claude_code",
        "Gemini": "gemini",
        "OpenClaw": "openclaw",
        "Windsurf": "windsurf",
    }

    def _parse_permissions(self, data: dict) -> set:
        """Parse platform_permissions from init data. Empty set = all allowed."""
        import json as _json
        raw = data.get("platform_permissions")
        if not raw:
            return set()
        if isinstance(raw, str):
            try:
                raw = _json.loads(raw)
            except Exception:
                return set()
        if isinstance(raw, list):
            return set(raw)
        return set()

    def _has_permission(self, platform_name: str, perms: set) -> bool:
        if not perms:
            return True
        return self._PERM_KEY_MAP.get(platform_name, "") in perms

    def _format_expire(self, raw: str | None) -> str:
        if not raw:
            return ""
        try:
            dt_str = raw[:16].replace("T", " ")
            return f"到期: {dt_str}"
        except Exception:
            return ""

    _INACTIVE_STYLE = "font-size: 13px; font-weight: 600; color: #94a3b8; background: transparent; border: none;"
    _ACTIVE_STYLE = "font-size: 22px; font-weight: 800; color: #0f172a; background: transparent; border: none; margin-top: 2px;"

    def _set_balance(self, name: str, text: str, active: bool):
        lbl = self._platform_balance_labels.get(name)
        if not lbl:
            return
        lbl.setText(text)
        lbl.setStyleSheet(self._ACTIVE_STYLE if active else self._INACTIVE_STYLE)

    def _show_authorized(self, data: dict):
        perms = self._parse_permissions(data)
        self._current_permissions = perms

        # Cursor
        if self._has_permission("Cursor", perms):
            cursor_val = data.get("over_count", 0) or 0
            if data.get("unlimited"):
                self._set_balance("Cursor", "∞", True)
            elif cursor_val > 0:
                self._set_balance("Cursor", str(cursor_val), True)
            else:
                self._set_balance("Cursor", "未激活", False)
        else:
            self._set_balance("Cursor", "未激活", False)

        # Kiro
        if self._has_permission("Kiro", perms):
            kiro_val = data.get("kiro_over_count", 0) or 0
            if data.get("kiro_unlimited"):
                self._set_balance("Kiro", "∞", True)
            elif kiro_val > 0:
                self._set_balance("Kiro", str(kiro_val), True)
            else:
                self._set_balance("Kiro", "未激活", False)
        else:
            self._set_balance("Kiro", "未激活", False)

        # Windsurf (count-based, like Kiro)
        if self._has_permission("Windsurf", perms):
            ws_val = data.get("windsurf_over_count", 0) or 0
            if data.get("windsurf_unlimited"):
                self._set_balance("Windsurf", "∞", True)
            elif ws_val > 0:
                self._set_balance("Windsurf", str(ws_val), True)
            else:
                self._set_balance("Windsurf", "未激活", False)
        else:
            self._set_balance("Windsurf", "未激活", False)

        # Cursor / Kiro / Windsurf expire
        cursor_exp = self._platform_expire_labels.get("Cursor")
        if cursor_exp:
            cursor_exp.setText(self._format_expire(data.get("end_time")) if self._has_permission("Cursor", perms) and (data.get("unlimited") or (data.get("over_count", 0) or 0) > 0) else "")
        kiro_exp = self._platform_expire_labels.get("Kiro")
        if kiro_exp:
            kiro_exp.setText(self._format_expire(data.get("kiro_end_time")) if self._has_permission("Kiro", perms) and (data.get("kiro_unlimited") or (data.get("kiro_over_count", 0) or 0) > 0) else "")
        ws_exp = self._platform_expire_labels.get("Windsurf")
        if ws_exp:
            ws_exp.setText(self._format_expire(data.get("windsurf_end_time")) if self._has_permission("Windsurf", perms) and (data.get("windsurf_unlimited") or (data.get("windsurf_over_count", 0) or 0) > 0) else "")

        # Sub2API platforms (Codex / Claude Code / Gemini / OpenClaw / Cursor Pro)
        for plat_name, data_key, time_key in (
            ("Codex", "codex_quota", "codex_end_time"),
            ("Claude Code", "claude_code_quota", "claude_code_end_time"),
            ("Gemini", "gemini_quota", "gemini_end_time"),
            ("OpenClaw", "openclaw_quota", "openclaw_end_time"),
            ("Cursor Pro", "cursor_pro_quota", "cursor_pro_end_time"),
        ):
            q = data.get(data_key, 0) or 0
            has_perm = self._has_permission(plat_name, perms)
            if has_perm and q > 0:
                self._set_balance(plat_name, f"${q:.2f}" if isinstance(q, (int, float)) else str(q), True)
            else:
                self._set_balance(plat_name, "未激活", False)
            exp_lbl = self._platform_expire_labels.get(plat_name)
            if exp_lbl:
                exp_lbl.setText(self._format_expire(data.get(time_key)) if has_perm and q > 0 else "")

        threading.Thread(target=self._bg_refresh_sub2api_balances, args=(perms, data), daemon=True).start()

    # ------------------------------------------------------------------ Sub2API real-time balance
    def _bg_refresh_sub2api_balances(self, perms, data):
        try:
            r = self.api.sub2api_get_balance(timeout=10)
            if r.get("success") and isinstance(r.get("data"), dict):
                self._sub2api_balance_result = (r["data"], perms, data)
            else:
                self._sub2api_balance_result = None
        except Exception:
            self._sub2api_balance_result = None
        try:
            QMetaObject.invokeMethod(self, "_apply_sub2api_balances", Qt.ConnectionType.QueuedConnection)
        except RuntimeError:
            pass

    @Slot()
    def _apply_sub2api_balances(self):
        result = getattr(self, "_sub2api_balance_result", None)
        if not result:
            return
        balances, perms, data = result
        for plat_name, balance_key, time_key in (
            ("Codex", "codex_quota", "codex_end_time"),
            ("Claude Code", "claude_code_quota", "claude_code_end_time"),
            ("Gemini", "gemini_quota", "gemini_end_time"),
            ("OpenClaw", "openclaw_quota", "openclaw_end_time"),
            ("Cursor Pro", "cursor_pro_quota", "cursor_pro_end_time"),
        ):
            if balance_key in balances:
                q = balances[balance_key]
                has_perm = self._has_permission(plat_name, perms)
                if has_perm and isinstance(q, (int, float)) and q > 0:
                    self._set_balance(plat_name, f"${q:.2f}", True)
                elif has_perm and isinstance(q, (int, float)) and q == 0:
                    self._set_balance(plat_name, "$0.00", True)

    # ------------------------------------------------------------------ balance refresh
    def _refresh_all_balances(self):
        self._refresh_balance_btn.setEnabled(False)
        self._refresh_balance_btn.setText("刷新中...")
        threading.Thread(target=self._bg_refresh_activation, daemon=True).start()

    def _bg_refresh_activation(self):
        try:
            self._refresh_act_result = self.api.init_device(refresh=True)
        except Exception:
            self._refresh_act_result = {"success": False, "message": "刷新失败，请检查网络连接"}
        try:
            QMetaObject.invokeMethod(self, "_apply_refresh_activation", Qt.ConnectionType.QueuedConnection)
        except RuntimeError:
            pass

    @Slot()
    def _apply_refresh_activation(self):
        self._refresh_balance_btn.setEnabled(True)
        self._refresh_balance_btn.setText("刷新余额")
        r = getattr(self, "_refresh_act_result", None)
        if r is None:
            return
        if not r.get("success"):
            if r.get("auth_expired"):
                self.auth_expired.emit()
                return
            msg = r.get("message", "刷新失败")
            if hasattr(self, "_redeem_status"):
                self._redeem_status.setText(msg)
                self._redeem_status.setStyleSheet(
                    "font-size: 12px; color: #dc2626; background: transparent; border: none;"
                )
                self._redeem_status.setVisible(True)
            return
        data = r.get("data") or {}
        self.init_data_loaded.emit(data)
        if data.get("activated"):
            import time
            self._last_init_data = data
            self._last_init_time = time.time()
            self._show_authorized(data)

    # ------------------------------------------------------------------ unified redeem


    def _on_unified_redeem(self):
        code = self._code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "提示", "请输入激活码")
            return
        self._redeem_btn.setEnabled(False)
        self._redeem_btn.setText("激活中...")
        threading.Thread(target=self._bg_unified_redeem, args=(code,), daemon=True).start()

    def _bg_unified_redeem(self, code):
        self._unified_result = self.api.unified_redeem(code)
        QMetaObject.invokeMethod(self, "_apply_unified_redeem", Qt.ConnectionType.QueuedConnection)

    def _show_redeem_status(self, msg: str, is_error: bool):
        self._redeem_status.setText(msg)
        if is_error:
            self._redeem_status.setStyleSheet(
                "font-size: 12px; padding: 10px 14px; border-radius: 10px; "
                "color: #dc2626; background: #fef2f2; border: 1px solid #fecaca;"
            )
        else:
            self._redeem_status.setStyleSheet(
                "font-size: 12px; padding: 10px 14px; border-radius: 10px; "
                "color: #059669; background: #ecfdf5; border: 1px solid #a7f3d0;"
            )
        self._redeem_status.setVisible(True)

    @Slot()
    def _apply_unified_redeem(self):
        self._redeem_btn.setEnabled(True)
        self._redeem_btn.setText("激  活")
        r = getattr(self, "_unified_result", {})
        if not r.get("success"):
            if r.get("auth_expired"):
                self.auth_expired.emit()
                return
            self._show_redeem_status(r.get("message", "激活失败，请检查激活码"), True)
            return

        data = r.get("data") or {}
        redeem_type = data.get("redeem_type", "")

        if redeem_type == "cdk":
            self._show_redeem_status("激活成功！密钥已自动同步，余额已更新。", False)
            self._code_input.clear()
            self._show_authorized(data)
            self.init_data_loaded.emit(data)
        else:
            self._show_redeem_status("激活成功！余额已更新。", False)
            self._code_input.clear()
            self._do_init()
