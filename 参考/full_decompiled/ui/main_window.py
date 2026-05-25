"""主窗口 — 登录门控 + 侧边栏导航 + 内容区域"""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QGraphicsDropShadowEffect, QMessageBox,
    QSystemTrayIcon, QMenu,
)
from PySide6.QtCore import Qt, QUrl, QTimer, Slot, QMetaObject
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QAction, QPixmap, QPainter, QBrush, QPen, QFont, QFontMetrics

from ui.styles import MAIN_STYLESHEET
from ui.pages.login_page import LoginPage
from ui.pages.overview_page import OverviewPage
from ui.pages.cursor_page import CursorPage
from ui.pages.cursor_pro_page import CursorProPage
from ui.pages.kiro_page import KiroPage
from ui.pages.windsurf_page import WindsurfPage
from ui.pages.sub2api_platform_page import Sub2ApiPlatformPage
from ui.dialogs.announcement_dialog import AnnouncementDialog
from ui.dialogs.profile_dialog import ProfileDialog
from ui.platform_icons import platform_pixmap
from api.client import ApiClient


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


_SIDEBAR_TEXT_ICONS: dict[str, tuple[str, str]] = {
    "首页":   ("🏠", "#6366f1"),
    "充值续费": ("💳", "#0ea5e9"),
    "使用教程": ("📖", "#10b981"),
}


def _make_text_icon(char: str, color: str, size: int = 18) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawRoundedRect(0, 0, size, size, 5, 5)
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return pm


class SidebarButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(f"    {text}")
        self.setObjectName("SidebarBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)

        pm = platform_pixmap(text, 18)
        if not pm.isNull():
            self.setIcon(QIcon(pm))
            self.setIconSize(pm.size())
        elif text in _SIDEBAR_TEXT_ICONS:
            char, color = _SIDEBAR_TEXT_ICONS[text]
            self.setIcon(QIcon(_make_text_icon(char, color, 18)))
            self.setIconSize(QPixmap(18, 18).size())

    def set_active(self, active: bool):
        self.setObjectName("SidebarBtnActive" if active else "SidebarBtn")
        self.style().unpolish(self)
        self.style().polish(self)


TUTORIAL_URL_FALLBACK = "https://www.feishu.cn/"

_MENU_KEY_MAP = {
    "Cursor": "cursor",
    "Cursor Pro": "cursor_pro",
    "Kiro": "kiro",
    "Codex": "codex",
    "Claude Code": "claude_code",
    "Gemini": "gemini",
    "OpenClaw": "openclaw",
    "Windsurf": "windsurf",
}

_KEY_LABEL_MAP = {v: k for k, v in _MENU_KEY_MAP.items()}

_PLATFORM_MENUS = ["Cursor", "Cursor Pro", "Kiro", "Codex", "Claude Code", "Gemini", "OpenClaw", "Windsurf"]
_DEFAULT_ALL_MENUS = ["首页", "Cursor", "Cursor Pro", "Kiro", "Codex", "Claude Code", "Gemini", "OpenClaw", "Windsurf", "充值续费", "使用教程"]


def _ordered_menus(order: list) -> list:
    """Build menu list: 首页 first, platforms in custom order, 续费/使用教程 last."""
    if not order:
        return list(_DEFAULT_ALL_MENUS)
    ordered_platforms = []
    for key in order:
        label = _KEY_LABEL_MAP.get(key)
        if label:
            ordered_platforms.append(label)
    seen = set(ordered_platforms)
    for label in _PLATFORM_MENUS:
        if label not in seen:
            ordered_platforms.append(label)
    return ["首页"] + ordered_platforms + ["充值续费", "使用教程"]

APP_VERSION = "2.0.6"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ApiClient(base_url="http://64.90.0.203")
        self._current_index = 0
        self._menu_config: dict = {}
        self._menu_order: list = []
        self._show_renew: bool = True
        self._show_tutorial: bool = True
        self._really_quit = False

        self.setWindowTitle("AI助手")
        self.setMinimumSize(980, 660)
        self.resize(1080, 720)
        self.setStyleSheet(MAIN_STYLESHEET)

        # Top-level stack: login page vs main app
        self._root_stack = QStackedWidget()
        self.setCentralWidget(self._root_stack)

        # Login page
        self._login_page = LoginPage(self.api)
        self._login_page.login_success.connect(self._on_login_success)
        self._root_stack.addWidget(self._login_page)

        # Main app (built lazily on first login)
        self._main_widget: QWidget | None = None

        # Check if already logged in
        if self.api.is_logged_in:
            self._enter_main_app()
        else:
            self._root_stack.setCurrentWidget(self._login_page)

        self._init_tray()
        self._update_dismissed_version: str = ""
        QTimer.singleShot(1000, self._check_update)
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._check_update)
        self._update_timer.start(30 * 60 * 1000)

    def _on_login_success(self):
        self._enter_main_app()

    def _enter_main_app(self):
        if self._main_widget is None:
            self._build_main_app()
        self._root_stack.setCurrentWidget(self._main_widget)
        QTimer.singleShot(500, self._show_announcements)

    def _is_menu_enabled(self, label: str) -> bool:
        if label == "充值续费":
            return self._show_renew
        if label == "使用教程":
            return self._show_tutorial
        key = _MENU_KEY_MAP.get(label)
        if key is None:
            return True
        # If config is empty (not yet set by admin), show all; otherwise respect explicit settings
        if not self._menu_config:
            return True
        val = self._menu_config.get(key, False)
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "")
        return bool(val)

    def _build_main_app(self):
        cache = self.api.load_menu_cache()
        self._menu_config = cache.get("menu_config", {})
        self._menu_order = cache.get("menu_order", [])
        self._show_renew = cache.get("show_renew", True)
        self._show_tutorial = cache.get("show_tutorial", True)
        self._env_config = cache.get("env_config", {})
        self._platform_guides = cache.get("platform_guides", {})

        self._main_widget = QWidget()
        root = QHBoxLayout(self._main_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== Sidebar =====
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        # Logo
        logo_area = QWidget()
        logo_area.setStyleSheet("background: transparent;")
        la = QHBoxLayout(logo_area)
        la.setContentsMargins(22, 26, 18, 22)
        la.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(30, 30)
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        _logo_path = os.path.join(
            sys._MEIPASS if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "ai-icon-neon.png",
        )
        if os.path.exists(_logo_path):
            _pm = QPixmap(_logo_path).scaled(
                30, 30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(_pm)

        name = QLabel("AI助手")
        name.setStyleSheet(
            "color: #ffffff; font-size: 17px; font-weight: 800; "
            "letter-spacing: -0.2px; background: transparent;"
        )
        tag = QLabel("聚合工具")
        tag.setStyleSheet(
            "color: #c7d2fe; font-size: 10px; font-weight: 600; "
            "background: rgba(99,102,241,0.3); border-radius: 8px; "
            "padding: 3px 10px; border: 1px solid rgba(167,139,250,0.3);"
        )
        la.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        la.addWidget(name)
        la.addWidget(tag)
        la.addStretch()
        sb.addWidget(logo_area)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.06); border: none;")
        sb.addWidget(line)
        sb.addSpacing(12)

        # Navigation — always create all buttons & pages, show/hide dynamically
        self._nav_buttons: list[tuple[str, SidebarButton]] = []
        self._nav_index: dict[str, int] = {}

        self._overview_page = OverviewPage(self.api, menu_config=self._menu_config)
        self._overview_page.navigate_to.connect(self._on_page_navigate)
        self._overview_page.auth_expired.connect(self._on_auth_expired)
        self._overview_page.init_data_loaded.connect(self._on_init_data_loaded)
        self._cursor_page = CursorPage(self.api)
        self._cursor_pro_page = CursorProPage(self.api)
        self._kiro_page = KiroPage(self.api)
        self._codex_page = Sub2ApiPlatformPage("Codex", self.api, env_config=self._env_config)
        self._claude_code_page = Sub2ApiPlatformPage("Claude Code", self.api, env_config=self._env_config)
        self._gemini_page = Sub2ApiPlatformPage("Gemini", self.api, env_config=self._env_config)
        self._openclaw_page = Sub2ApiPlatformPage("OpenClaw", self.api, env_config=self._env_config)
        self._windsurf_page = WindsurfPage(self.api)
        self._overview_page.init_data_loaded.connect(self._cursor_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._cursor_pro_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._kiro_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._codex_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._claude_code_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._gemini_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._openclaw_page.load_init_data)
        self._overview_page.init_data_loaded.connect(self._windsurf_page.load_init_data)
        self._cursor_page.navigate_to.connect(self._on_page_navigate)
        self._cursor_pro_page.navigate_to.connect(self._on_page_navigate)
        self._kiro_page.navigate_to.connect(self._on_page_navigate)
        self._codex_page.navigate_to.connect(self._on_page_navigate)
        self._claude_code_page.navigate_to.connect(self._on_page_navigate)
        self._gemini_page.navigate_to.connect(self._on_page_navigate)
        self._openclaw_page.navigate_to.connect(self._on_page_navigate)
        self._windsurf_page.navigate_to.connect(self._on_page_navigate)

        page_map = {
            "首页": self._overview_page,
            "Cursor": self._cursor_page,
            "Cursor Pro": self._cursor_pro_page,
            "Kiro": self._kiro_page,
            "Codex": self._codex_page,
            "Claude Code": self._claude_code_page,
            "Gemini": self._gemini_page,
            "OpenClaw": self._openclaw_page,
            "Windsurf": self._windsurf_page,
        }

        self._page_map = page_map
        self._distribute_guides()
        self._stack = QStackedWidget()
        stack_idx = 0

        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        self._nav_layout = QVBoxLayout(nav_container)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(0)

        for label in _ordered_menus(self._menu_order):
            btn = SidebarButton(label)
            btn.clicked.connect(lambda checked, t=label: self._on_nav_click(t))
            btn.setVisible(self._is_menu_enabled(label))
            self._nav_layout.addWidget(btn)
            self._nav_buttons.append((label, btn))

            if label in page_map:
                self._stack.addWidget(page_map[label])
                self._nav_index[label] = stack_idx
                stack_idx += 1

        sb.addWidget(nav_container)
        sb.addStretch()

        # User info + logout at sidebar bottom
        user_area = QWidget()
        user_area.setStyleSheet("background: transparent;")
        ua = QVBoxLayout(user_area)
        ua.setContentsMargins(14, 10, 14, 16)
        ua.setSpacing(8)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.06); border: none;")
        ua.addWidget(sep)

        info = self.api.user_info
        email_str = info.get("email", "")
        nick_str = info.get("nickname", email_str.split("@")[0] if email_str else "")

        user_card = QPushButton()
        user_card.setFixedHeight(54)
        user_card.setCursor(Qt.CursorShape.PointingHandCursor)
        user_card.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); border-radius: 10px; border: none;"
            "  text-align: left; padding: 0; }"
            "QPushButton:hover { background: rgba(255,255,255,0.10); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.14); }"
        )
        user_card.clicked.connect(self._show_profile_popup)
        ucl = QHBoxLayout(user_card)
        ucl.setContentsMargins(10, 8, 10, 8)
        ucl.setSpacing(10)

        initials = _user_initials(nick_str)
        avatar_color = _avatar_gradient(nick_str)
        avatar = QLabel(initials)
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {avatar_color}; color: #ffffff; font-size: 13px; "
            f"font-weight: 700; border-radius: 17px; border: none; "
            f"letter-spacing: 0.5px;"
        )

        user_col = QVBoxLayout()
        user_col.setSpacing(1)
        self._sidebar_nick_lbl = QLabel(nick_str)
        self._sidebar_nick_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self._sidebar_nick_lbl.setToolTip(email_str)
        email_short = email_str[:22] + "..." if len(email_str) > 22 else email_str
        email_lbl = QLabel(email_short)
        email_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.35); font-size: 10px; "
            "background: transparent; border: none;"
        )
        user_col.addWidget(self._sidebar_nick_lbl)
        user_col.addWidget(email_lbl)

        gear_icon = QLabel("⚙")
        gear_icon.setStyleSheet(
            "color: rgba(255,255,255,0.4); font-size: 20px; background: transparent; border: none;"
        )
        gear_icon.setFixedWidth(24)

        ucl.addWidget(avatar)
        ucl.addLayout(user_col, 1)
        ucl.addWidget(gear_icon)
        ua.addWidget(user_card)
        self._avatar_label = avatar

        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet(
            "color: rgba(255,255,255,0.25); font-size: 10px; background: transparent; "
            "border: none; padding: 0 8px;"
        )
        ua.addWidget(ver)

        sb.addWidget(user_area)
        root.addWidget(sidebar)

        # ===== Content =====
        content = QFrame()
        content.setObjectName("ContentArea")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._stack)
        root.addWidget(content, 1)

        self._root_stack.addWidget(self._main_widget)
        self._set_active_nav("首页")

    def _on_init_data_loaded(self, data: dict):
        """Extract config from init response and update sidebar + overview visibility."""
        import json as _json
        embedded = data.get("_config") or {}
        if not embedded:
            return
        try:
            mc = embedded.get("client_menus", "{}")
            self._pending_menu_config = _json.loads(mc) if isinstance(mc, str) else (mc if isinstance(mc, dict) else {})
            mo = embedded.get("client_menu_order", "[]")
            self._pending_menu_order = _json.loads(mo) if isinstance(mo, str) else (mo if isinstance(mo, list) else [])
            self._pending_show_renew = str(embedded.get("show_renew", "true")).lower() != "false"
            self._pending_show_tutorial = str(embedded.get("show_tutorial", "true")).lower() != "false"
            ec = embedded.get("env_config", "{}")
            self._pending_env_config = _json.loads(ec) if isinstance(ec, str) else (ec if isinstance(ec, dict) else {})
            pg = embedded.get("platform_guides", "{}")
            self._pending_platform_guides = _json.loads(pg) if isinstance(pg, str) else (pg if isinstance(pg, dict) else {})
        except Exception:
            self._pending_menu_config = None
            return
        self._apply_menu_refresh()

    @Slot()
    def _apply_menu_refresh(self):
        new_config = getattr(self, "_pending_menu_config", None)
        new_order = getattr(self, "_pending_menu_order", None)
        if new_config is None:
            return
        self._menu_config = new_config
        if new_order is not None:
            self._menu_order = new_order
        if getattr(self, "_pending_show_renew", None) is not None:
            self._show_renew = self._pending_show_renew
        if getattr(self, "_pending_show_tutorial", None) is not None:
            self._show_tutorial = self._pending_show_tutorial

        desired = _ordered_menus(self._menu_order)
        btn_map = {label: btn for label, btn in self._nav_buttons}
        if self._nav_layout:
            for label in desired:
                btn = btn_map.get(label)
                if btn:
                    self._nav_layout.removeWidget(btn)
                    self._nav_layout.addWidget(btn)

        for label, btn in self._nav_buttons:
            btn.setVisible(self._is_menu_enabled(label))
        self._overview_page.update_menu_config(self._menu_config)

        pending_guides = getattr(self, "_pending_platform_guides", None)
        if isinstance(pending_guides, dict):
            self._platform_guides = pending_guides

        pending_env = getattr(self, "_pending_env_config", None)
        if isinstance(pending_env, dict):
            self._env_config = pending_env
            _env_pages = {
                "codex": getattr(self, "_codex_page", None),
                "claude_code": getattr(self, "_claude_code_page", None),
                "gemini": getattr(self, "_gemini_page", None),
                "openclaw": getattr(self, "_openclaw_page", None),
            }
            for key, page in _env_pages.items():
                if page is not None:
                    val = pending_env.get(key)
                    page.set_env_visible(val is None or bool(val))

        self.api.save_menu_cache(
            self._menu_config, self._menu_order,
            self._show_renew, self._show_tutorial, self._env_config,
            self._platform_guides,
        )
        self._distribute_guides()

    def _distribute_guides(self):
        _GUIDE_PAGE_MAP = {
            "cursor": getattr(self, "_cursor_page", None),
            "cursor_pro": getattr(self, "_cursor_pro_page", None),
            "kiro": getattr(self, "_kiro_page", None),
            "codex": getattr(self, "_codex_page", None),
            "claude_code": getattr(self, "_claude_code_page", None),
            "gemini": getattr(self, "_gemini_page", None),
            "openclaw": getattr(self, "_openclaw_page", None),
        }
        guides = self._platform_guides or {}
        for key, page in _GUIDE_PAGE_MAP.items():
            if page is None or not hasattr(page, "set_guide"):
                continue
            entry = guides.get(key, {})
            if isinstance(entry, dict) and entry.get("enabled"):
                page.set_guide(entry.get("content", ""))
            else:
                page.set_guide(None)

    def _on_auth_expired(self):
        self.api.logout()
        if self._main_widget:
            self._root_stack.removeWidget(self._main_widget)
            self._main_widget.deleteLater()
            self._main_widget = None
        self._root_stack.setCurrentWidget(self._login_page)
        QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录。")

    def _show_profile_popup(self):
        dlg = ProfileDialog(self.api, self)
        dlg.nickname_changed.connect(self._on_nickname_changed)
        dlg.exec()
        if getattr(dlg, "_logout_requested", False):
            self._do_logout_action()

    def _on_nickname_changed(self, new_nick: str):
        if hasattr(self, "_sidebar_nick_lbl"):
            self._sidebar_nick_lbl.setText(new_nick)
        if hasattr(self, "_avatar_label"):
            initials = _user_initials(new_nick)
            self._avatar_label.setText(initials)
            avatar_color = _avatar_gradient(new_nick)
            self._avatar_label.setStyleSheet(
                f"background: {avatar_color}; color: #ffffff; font-size: 13px; "
                f"font-weight: 700; border-radius: 17px; border: none; "
                f"letter-spacing: 0.5px;"
            )

    def _on_logout(self):
        reply = QMessageBox.question(
            self, "退出登录", "确认退出当前账号？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._do_logout_action()

    def _do_logout_action(self):
        self.api.logout()
        if self._main_widget:
            self._root_stack.removeWidget(self._main_widget)
            self._main_widget.deleteLater()
            self._main_widget = None
        self._root_stack.setCurrentWidget(self._login_page)

    def _on_nav_click(self, name: str):
        if name == "使用教程":
            url = self.api.get_tutorial_url() or TUTORIAL_URL_FALLBACK
            QDesktopServices.openUrl(QUrl(url))
            return
        if name == "充值续费":
            url = self.api.get_renew_url()
            if url:
                QDesktopServices.openUrl(QUrl(url))
            else:
                QMessageBox.information(self, "充值续费", "暂未配置充值续费链接，请联系客服。")
            return
        self._set_active_nav(name)

    def _on_page_navigate(self, target: str):
        self._on_nav_click(target)

    def _set_active_nav(self, name: str):
        idx = self._nav_index.get(name, 0)
        self._current_index = idx
        self._stack.setCurrentIndex(idx)
        for label, btn in self._nav_buttons:
            btn.set_active(self._nav_index.get(label, -1) == idx)

    # ------------------------------------------------------------------ Announcements
    def _show_announcements(self):
        import threading

        def _bg():
            try:
                r = self.api.get_type_msg()
                self._ann_data = r.get("data", []) if r.get("success") else []
            except Exception:
                self._ann_data = []
            QMetaObject.invokeMethod(self, "_apply_announcements", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_bg, daemon=True).start()

    @Slot()
    def _apply_announcements(self):
        data = getattr(self, "_ann_data", [])
        if data:
            AnnouncementDialog.show_announcements(data, self)

    # ------------------------------------------------------------------ Tray
    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return

        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        icon_path = os.path.join(base, "assets", "ai-icon-neon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("AI助手 — 后台运行中")

        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._tray_show_window)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._tray_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _tray_show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_quit(self):
        self._really_quit = True
        if self._tray:
            self._tray.hide()
        self.close()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._tray_show_window()

    def closeEvent(self, event):
        if self._tray and self._tray.isVisible() and not self._really_quit:
            self.hide()
            self._tray.showMessage(
                "AI助手",
                "已最小化到系统托盘，无感换号服务持续运行中。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            event.ignore()
            return
        event.accept()

    def _check_update(self):
        """在后台线程检查更新，避免阻塞主线程 UI。"""
        import threading

        def _bg():
            try:
                resp = self.api.check_update(APP_VERSION)
                self._update_resp = resp
            except Exception:
                self._update_resp = {}
            QMetaObject.invokeMethod(self, "_apply_update_check", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_bg, daemon=True).start()

    @Slot()
    def _apply_update_check(self):
        try:
            resp = getattr(self, "_update_resp", {})
            if not resp.get("success"):
                return
            data = resp.get("data") or {}
            if not data.get("needUpdate"):
                self._update_dismissed_version = ""
                return

            latest = data.get("latest", "")
            url = data.get("downloadUrl", "")
            msg = data.get("updateMessage", "")
            force = data.get("forceUpdate", False)

            if not force and latest == self._update_dismissed_version:
                return

            if not self.isVisible() and self._tray and self._tray.isVisible():
                self._tray.showMessage(
                    "发现新版本",
                    f"v{latest} 已发布（当前 v{APP_VERSION}），请打开 AI助手 进行更新。",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                if not force:
                    return

            text = f"发现新版本 v{latest}（当前 v{APP_VERSION}）"
            if msg:
                text += f"\n\n更新内容：\n{msg}"
            if force:
                text += "\n\n⚠ 此版本为必须更新版本，请下载新版本后再使用。"
            elif url:
                text += "\n\n点击「前往下载」跳转到下载页面。"

            box = QMessageBox(self)
            box.setWindowTitle("版本更新")
            box.setText(text)
            box.setIcon(QMessageBox.Icon.Warning if force else QMessageBox.Icon.Information)

            go_btn = None
            if url:
                go_btn = box.addButton("前往下载", QMessageBox.ButtonRole.AcceptRole)
            if force:
                if not url:
                    box.addButton("我知道了（退出）", QMessageBox.ButtonRole.AcceptRole)
                else:
                    box.addButton("退出程序", QMessageBox.ButtonRole.RejectRole)
            else:
                box.addButton("稍后提醒", QMessageBox.ButtonRole.RejectRole)

            box.exec()

            if go_btn and box.clickedButton() == go_btn:
                QDesktopServices.openUrl(QUrl(url))
                if force:
                    self._really_quit = True
                    self.close()
                    return

            if force:
                self._really_quit = True
                self.close()
            else:
                self._update_dismissed_version = latest
        except Exception:
            pass
