"""Sub2API 平台页面 — Codex / Claude Code 共用

功能: API Key 生成与展示、端点展示、一键写入本地配置、使用记录查看
"""

from __future__ import annotations

import json
import os
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QGraphicsDropShadowEffect, QSizePolicy, QLineEdit,
    QApplication, QComboBox,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject

from ui.platform_icons import platform_icon_label, platform_pixmap
from ui.widgets import SectionPanel


def _shadow(w, blur=24, y=6, alpha=14):
    from PySide6.QtGui import QColor
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


def _home_dir() -> str:
    return os.path.expanduser("~")


def _mask_key(key: str) -> str:
    """Mask API key for display: show first 8 and last 4 chars."""
    if not key or len(key) <= 16:
        return key
    return key[:8] + "•" * (len(key) - 12) + key[-4:]


def _find_cmd_in_common_paths(cmd: str) -> str | None:
    """Search common install locations for a command (nvm, homebrew, volta, fnm, etc.)."""
    import sys, glob
    home = _home_dir()
    candidates = []
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        # nvm
        nvm_dir = os.environ.get("NVM_DIR", os.path.join(home, ".nvm"))
        nvm_bins = glob.glob(os.path.join(nvm_dir, "versions", "node", "v*", "bin", cmd))
        if nvm_bins:
            nvm_bins.sort(reverse=True)
            candidates.extend(nvm_bins)
        # fnm
        fnm_bins = glob.glob(os.path.join(home, ".local", "share", "fnm", "node-versions", "v*", "installation", "bin", cmd))
        candidates.extend(sorted(fnm_bins, reverse=True))
        # volta
        volta_bin = os.path.join(home, ".volta", "bin", cmd)
        candidates.append(volta_bin)
        # homebrew
        for brew_prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidates.append(os.path.join(brew_prefix, cmd))
        # system
        candidates.append(os.path.join("/usr", "local", "bin", cmd))
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        # nvm-windows
        nvm_home = os.environ.get("NVM_HOME", os.path.join(appdata, "nvm"))
        nvm_bins = glob.glob(os.path.join(nvm_home, "v*", cmd + ".exe"))
        candidates.extend(sorted(nvm_bins, reverse=True))
        # nvm symlink
        nvm_sym = os.environ.get("NVM_SYMLINK", os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "nodejs"))
        candidates.append(os.path.join(nvm_sym, cmd + ".exe"))
        # volta
        candidates.append(os.path.join(localappdata, "Volta", "bin", cmd + ".exe"))
        # standard
        candidates.append(os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", cmd + ".exe"))
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


_PLATFORM_CONFIG = {
    "Codex": {
        "accent": "#10b981",
        "bg": "#ecfdf5",
        "display_path": os.path.join(_home_dir(), ".codex", "auth.json") + " + config.toml",
        "write_fn": "_write_codex_config",
        "desc": "OpenAI Codex CLI 配置",
        "cli_cmd": "codex",
        "npm_pkg": "@openai/codex",
        "min_node": (16, 0, 0),
        "endpoint_suffix": "/v1",
    },
    "Claude Code": {
        "accent": "#8b5cf6",
        "bg": "#f5f3ff",
        "display_path": os.path.join(_home_dir(), ".claude", "settings.json"),
        "write_fn": "_write_claude_config",
        "desc": "Anthropic Claude Code CLI 配置",
        "cli_cmd": "claude",
        "npm_pkg": "@anthropic-ai/claude-code",
        "min_node": (18, 0, 0),
        "endpoint_suffix": "",
    },
    "Gemini": {
        "accent": "#f59e0b",
        "bg": "#fffbeb",
        "display_path": os.path.join(_home_dir(), ".gemini", ".env"),
        "write_fn": "_write_gemini_config",
        "desc": "Google Gemini CLI 配置",
        "cli_cmd": "gemini",
        "npm_pkg": "@google/gemini-cli",
        "min_node": (20, 0, 0),
        "endpoint_suffix": "/v1",
    },
    "OpenClaw": {
        "accent": "#dc2626",
        "bg": "#fef2f2",
        "display_path": os.path.join(_home_dir(), ".openclaw", "openclaw.json"),
        "write_fn": "_write_openclaw_config",
        "desc": "OpenClaw AI 助手配置",
        "cli_cmd": "openclaw",
        "npm_pkg": "openclaw@latest",
        "min_node": (22, 14, 0),
        "launch_args": ["onboard"],
        "endpoint_suffix": "/v1",
    },
}

_BTN_OUTLINE = (
    "QPushButton { "
    "  background: #ffffff; color: #4f46e5; "
    "  border: 1.5px solid #e0e7ff; border-radius: 10px; "
    "  padding: 0 18px; font-size: 13px; font-weight: 600; min-height: 36px; }"
    "QPushButton:hover { background: #eef2ff; border-color: #c7d2fe; }"
    "QPushButton:pressed { background: #e0e7ff; }"
)

_BTN_SUCCESS = (
    "QPushButton { "
    "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #059669, stop:1 #10b981);"
    "  color: #fff; border: none; border-radius: 12px; "
    "  padding: 0 24px; font-size: 13px; font-weight: 700; min-height: 40px; }"
    "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #047857, stop:1 #059669); }"
    "QPushButton:pressed { background: #065f46; }"
    "QPushButton:disabled { background: #94a3b8; }"
)

_BTN_WARNING = (
    "QPushButton { "
    "  background: #ffffff; color: #d97706; "
    "  border: 1.5px solid #fbbf24; border-radius: 10px; "
    "  padding: 0 18px; font-size: 13px; font-weight: 600; min-height: 36px; }"
    "QPushButton:hover { background: #fffbeb; border-color: #f59e0b; }"
    "QPushButton:pressed { background: #fef3c7; }"
    "QPushButton:disabled { background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }"
)


class Sub2ApiPlatformPage(QWidget):
    """Codex / Claude Code / Gemini 页面"""

    navigate_to = Signal(str)

    _QUOTA_KEY_MAP = {
        "Codex": "codex_quota",
        "Claude Code": "claude_code_quota",
        "Gemini": "gemini_quota",
        "OpenClaw": "openclaw_quota",
    }
    _PERM_KEY_MAP = {
        "Codex": "codex",
        "Claude Code": "claude_code",
        "Gemini": "gemini",
        "OpenClaw": "openclaw",
    }

    _CACHE_TTL = 120  # seconds
    _shared_endpoint: str = ""
    _shared_endpoint_time: float = 0.0

    _ENV_KEY_MAP = {
        "Codex": "codex",
        "Claude Code": "claude_code",
        "Gemini": "gemini",
        "OpenClaw": "openclaw",
    }

    def __init__(self, tool_name: str, api_client, env_config: dict | None = None, parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self.api = api_client
        self._cfg = _PLATFORM_CONFIG.get(tool_name, _PLATFORM_CONFIG["Codex"])
        self._current_key = ""
        self._current_key_id: int | None = None
        self._current_endpoint = ""
        self._endpoint_suffix = self._cfg.get("endpoint_suffix", "")
        self._usage_page = 1
        self._has_quota = False
        self._last_load_time = 0.0
        self._env_card_widget: QFrame | None = None
        env_config = env_config or {}
        env_key = self._ENV_KEY_MAP.get(tool_name, "")
        env_val = env_config.get(env_key)
        self._env_visible = env_val is None or bool(env_val)
        self._build()

    def _display_endpoint(self) -> str:
        """Base endpoint + per-tool suffix for user-facing display/copy."""
        if not self._current_endpoint:
            return ""
        base = self._current_endpoint.rstrip("/")
        return base + self._endpoint_suffix

    def showEvent(self, event):
        super().showEvent(event)
        if self._env_visible and self._env_card_widget and not hasattr(self, "_env_detected"):
            self._env_detected = True
            threading.Thread(target=self._bg_detect_env, daemon=True).start()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        from PySide6.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()

        # Page 0: empty state (no quota)
        self._build_empty_state()
        # Page 1: normal content
        self._build_normal_content()

        outer.addWidget(self._stack)
        self._stack.setCurrentIndex(0)

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
            f"background: {self._cfg['bg']}; border: 2px solid {self._cfg['accent']}20; "
            f"border-radius: 40px;"
        )
        icon_inner = QVBoxLayout(icon_bg)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        icon_lbl = platform_icon_label(self.tool_name, 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_inner.addWidget(icon_lbl)

        icon_wrap = QHBoxLayout()
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_wrap.addWidget(icon_bg)
        center.addLayout(icon_wrap)

        center.addSpacing(20)

        title_lbl = QLabel(f"暂未开通 {self.tool_name}")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1e293b;"
            "background: transparent; border: none;"
        )
        center.addWidget(title_lbl)
        center.addSpacing(8)

        desc_lbl = QLabel(f"激活包含 {self.tool_name} 权限的激活码后，即可使用密钥管理和配置功能")
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
            "QPushButton { background: #ffffff; "
            f"  color: {self._cfg['accent']}; "
            f"  border: 1.5px solid {self._cfg['accent']}40; border-radius: 14px;"
            "  padding: 0 32px; font-size: 14px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {self._cfg['bg']}; }}"
        )
        renew_btn.clicked.connect(self._go_renew)
        btn_row.addWidget(renew_btn)

        center.addLayout(btn_row)
        vbox.addLayout(center)
        vbox.addStretch(3)

        self._stack.addWidget(empty)

    def _go_renew(self):
        url = self.api.get_renew_url()
        if url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "购买", "暂未配置购买链接，请联系客服。")

    def _build_normal_content(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body.setStyleSheet("background: #f4f6f9;")
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(32, 24, 32, 36)
        vbox.setSpacing(20)

        self._build_header(vbox)
        if self._cfg.get("cli_cmd"):
            self._build_env_section(vbox)
        self._build_key_section(vbox)
        self._build_usage_section(vbox)

        # ── 使用说明 ─────────────────────────────────────────────
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
        self._stack.addWidget(scroll)

    def _build_header(self, vbox):
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)
        hdr_icon = platform_icon_label(self.tool_name, 32)
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(3)
        title = QLabel(self.tool_name)
        title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;"
        )
        sub = QLabel(self._cfg["desc"])
        sub.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr_row.addLayout(hdr_col)
        hdr_row.addStretch()
        vbox.addLayout(hdr_row)

    # ---- Environment (CLI install/uninstall) ----
    _ENV_TAG_OK = (
        "font-size: 11px; font-weight: 700; color: #059669; background: #ecfdf5;"
        "border: 1px solid #a7f3d0; border-radius: 10px; padding: 2px 10px;"
    )
    _ENV_TAG_MISS = (
        "font-size: 11px; font-weight: 700; color: #dc2626; background: #fef2f2;"
        "border: 1px solid #fecaca; border-radius: 10px; padding: 2px 10px;"
    )
    _ENV_TAG_WAIT = (
        "font-size: 11px; font-weight: 600; color: #94a3b8; background: #f8fafc;"
        "border: 1px solid #e2e8f0; border-radius: 10px; padding: 2px 10px;"
    )

    def _build_env_section(self, vbox):
        cli_label = f"{self.tool_name} CLI"
        accent = self._cfg["accent"]

        card = _card()
        card.setStyleSheet(
            card.styleSheet()
            + f"QWidget#envCard {{ border-left: 3px solid {accent}; }}"
        )
        card.setObjectName("envCard")
        outer = QHBoxLayout(card)
        outer.setContentsMargins(18, 12, 16, 12)
        outer.setSpacing(0)

        left = QHBoxLayout()
        left.setSpacing(16)
        self._env_tags: dict[str, QLabel] = {}
        for name in ("Node.js", "Git", cli_label):
            pill = QHBoxLayout()
            pill.setSpacing(5)
            lbl = QLabel(name)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #64748b;"
                "background: transparent; border: none;"
            )
            tag = QLabel("…")
            tag.setStyleSheet(self._ENV_TAG_WAIT)
            self._env_tags[name] = tag
            pill.addWidget(lbl)
            pill.addWidget(tag)
            if name == "Node.js":
                self._node_upgrade_btn = QPushButton("⬆ 升级")
                self._node_upgrade_btn.setFixedHeight(24)
                self._node_upgrade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._node_upgrade_btn.setStyleSheet(
                    "QPushButton { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;"
                    "  border-radius: 6px; padding: 0 8px; font-size: 11px; font-weight: 600; }"
                    "QPushButton:hover { background: #fde68a; border-color: #f59e0b; }"
                    "QPushButton:disabled { background: #f8fafc; color: #cbd5e1; border-color: #e2e8f0; }"
                )
                self._node_upgrade_btn.clicked.connect(self._on_node_upgrade)
                self._node_upgrade_btn.setVisible(False)
                pill.addWidget(self._node_upgrade_btn)
            left.addLayout(pill)

        outer.addLayout(left)
        outer.addStretch()

        self._env_launch_btn = QPushButton("▶ 启动")
        self._env_launch_btn.setFixedHeight(30)
        self._env_launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._env_launch_btn.setStyleSheet(
            f"QPushButton {{ background: {accent}; color: #fff; border: none;"
            "  border-radius: 8px; padding: 0 18px; font-size: 12px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {accent}dd; }}"
            "QPushButton:disabled { background: #94a3b8; color: #e2e8f0; }"
        )
        self._env_launch_btn.setEnabled(False)
        self._env_launch_btn.clicked.connect(self._on_env_launch)
        outer.addWidget(self._env_launch_btn)

        outer.addSpacing(6)

        self._env_install_btn = QPushButton("一键安装")
        self._env_install_btn.setFixedHeight(30)
        self._env_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._env_install_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #475569; border: 1.5px solid #cbd5e1;"
            "  border-radius: 8px; padding: 0 14px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #f1f5f9; border-color: #94a3b8; }"
            "QPushButton:disabled { background: #f8fafc; color: #cbd5e1; border-color: #e2e8f0; }"
        )
        self._env_install_btn.clicked.connect(self._on_env_install)
        outer.addWidget(self._env_install_btn)

        outer.addSpacing(6)

        self._env_uninstall_btn = QPushButton("卸载")
        self._env_uninstall_btn.setFixedHeight(30)
        self._env_uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._env_uninstall_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: 1.5px solid #fecaca;"
            "  border-radius: 8px; padding: 0 14px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #fef2f2; border-color: #f87171; }"
            "QPushButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }"
        )
        self._env_uninstall_btn.clicked.connect(self._on_env_uninstall)
        outer.addWidget(self._env_uninstall_btn)

        vbox.addWidget(card)
        self._env_card_widget = card
        if not self._env_visible:
            card.setVisible(False)

        self._env_working = False

    # -- detect --
    @staticmethod
    def _cmd_version(cmd: str) -> str | None:
        import subprocess, shutil, sys
        cmd_path = shutil.which(cmd)
        if not cmd_path:
            cmd_path = _find_cmd_in_common_paths(cmd)
        if not cmd_path:
            return None
        try:
            use_shell = sys.platform == "win32"
            enc = {"encoding": "utf-8", "errors": "replace"} if sys.platform == "win32" else {}
            r = subprocess.run(
                [cmd_path, "--version"], capture_output=True, text=True,
                timeout=10, shell=use_shell, **enc,
            )
            out = ((r.stdout or "").strip() or (r.stderr or "").strip()).split("\n")[0]
            return out or "已安装"
        except Exception:
            return "已安装"

    @staticmethod
    def _parse_node_version(ver_str: str | None) -> tuple[int, ...] | None:
        """Extract (major, minor, patch) from a version string like 'v18.16.0' or 'v20.12.2'."""
        if not ver_str:
            return None
        import re
        m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", ver_str)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    def _bg_detect_env(self):
        cli_cmd = self._cfg.get("cli_cmd", "")
        self._env_node = self._cmd_version("node")
        self._env_git = self._cmd_version("git")
        self._env_cli = self._cmd_version(cli_cmd) if cli_cmd else None
        QMetaObject.invokeMethod(self, "_apply_env_status", Qt.ConnectionType.QueuedConnection)

    _ENV_TAG_WARN = (
        "QLabel { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; "
        "border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600; }"
    )

    @Slot()
    def _apply_env_status(self):
        cli_label = f"{self.tool_name} CLI"
        min_node = self._cfg.get("min_node")
        node_too_old = False
        node_missing = False

        for name, val in [
            ("Node.js", self._env_node),
            ("Git", self._env_git),
            (cli_label, self._env_cli),
        ]:
            tag = self._env_tags.get(name)
            if not tag:
                continue
            if val:
                tag.setText(f"✓ {val}")
                tag.setStyleSheet(self._ENV_TAG_OK)
            else:
                tag.setText("✗ 未安装")
                tag.setStyleSheet(self._ENV_TAG_MISS)

        if min_node:
            if not self._env_node:
                node_missing = True
            else:
                parsed = self._parse_node_version(self._env_node)
                if parsed and parsed < tuple(min_node):
                    node_too_old = True
                    tag = self._env_tags.get("Node.js")
                    if tag:
                        req = ".".join(str(x) for x in min_node)
                        tag.setText(f"⚠ {self._env_node} (需 v{req}+)")
                        tag.setStyleSheet(self._ENV_TAG_WARN)

        show_upgrade = node_too_old or (node_missing and bool(min_node))
        self._node_upgrade_btn.setVisible(show_upgrade)
        if show_upgrade:
            if node_missing:
                self._node_upgrade_btn.setText("⬇ 安装")
            else:
                self._node_upgrade_btn.setText("⬆ 升级")

        if self._env_cli:
            self._env_install_btn.setText("更新")
            self._env_uninstall_btn.setEnabled(True)
            self._env_launch_btn.setEnabled(not node_too_old and not node_missing)
        else:
            self._env_install_btn.setText("一键安装")
            self._env_uninstall_btn.setEnabled(False)
            self._env_launch_btn.setEnabled(False)

    # -- Node.js upgrade --
    def _on_node_upgrade(self):
        if self._env_working:
            return
        min_node = self._cfg.get("min_node")
        req = ".".join(str(x) for x in min_node) if min_node else "20"
        current = self._env_node or "未安装"
        parsed = self._parse_node_version(self._env_node)
        if parsed and not (min_node and parsed < tuple(min_node)):
            QMessageBox.information(self, "Node.js", "当前 Node.js 版本已满足要求。")
            return

        action = "安装" if not self._env_node else "升级"
        ret = QMessageBox.question(
            self, f"{action} Node.js",
            f"{self.tool_name} 需要 Node.js v{req} 或更高版本。\n\n"
            f"当前状态: {current}\n\n"
            f"是否自动{action}到最新 LTS 版本？\n\n"
            "⏱ 预计需要 1~3 分钟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self._env_working = True
        self._node_upgrade_btn.setEnabled(False)
        self._node_upgrade_btn.setText(f"{action}中…")
        self._env_install_btn.setEnabled(False)
        self._env_launch_btn.setEnabled(False)
        threading.Thread(target=self._bg_upgrade_node, daemon=True).start()

    def _bg_upgrade_node(self):
        import shutil, sys
        try:
            darwin = sys.platform == "darwin"
            linux = sys.platform.startswith("linux")
            win32 = sys.platform == "win32"
            ok = False
            detail = ""

            if darwin:
                if shutil.which("brew"):
                    if self._env_node:
                        ok = self._run_cmd(["brew", "upgrade", "node"], 300)
                        if not ok:
                            ok = self._run_cmd(["brew", "install", "node"], 300)
                    else:
                        ok = self._run_cmd(["brew", "install", "node"], 300)
                if not ok:
                    pkg_path = self._mac_download_node_pkg()
                    if pkg_path:
                        self._node_upgrade_ok = False
                        self._node_upgrade_msi_path = pkg_path
                        return
                    if not detail:
                        detail = (
                            "自动安装失败，请手动安装 Node.js:\nhttps://nodejs.org"
                        )

            elif win32:
                # Strategy 1: winget
                if not ok and shutil.which("winget"):
                    ok = self._run_cmd(
                        ["winget", "install", "--id", "OpenJS.NodeJS.LTS",
                         "-e", "--accept-source-agreements", "--accept-package-agreements"],
                        300,
                    )
                # Strategy 2: choco
                if not ok and shutil.which("choco"):
                    ok = self._run_cmd(["choco", "install", "nodejs-lts", "-y"], 300)
                # Strategy 3: silent MSI install
                if not ok:
                    ok = self._win_download_install_node()
                # Strategy 4: download MSI and open for manual install
                if not ok:
                    msi_path = self._win_download_node_msi_to_downloads()
                    if msi_path:
                        self._node_upgrade_ok = False
                        self._node_upgrade_msi_path = msi_path
                        return
                    detail = (
                        "自动升级失败，请手动安装 Node.js LTS:\n\n"
                        "1. 打开 https://nodejs.org\n"
                        "2. 下载 Windows Installer (.msi)\n"
                        "3. 运行安装程序完成安装\n\n"
                        "安装完成后重启本软件"
                    )

            elif linux:
                installed = False
                for upgrade_cmd, install_cmd in [
                    (["apt-get", "install", "-y", "nodejs"], ["apt-get", "install", "-y", "nodejs"]),
                    (["yum", "install", "-y", "nodejs"], ["yum", "install", "-y", "nodejs"]),
                    (["dnf", "install", "-y", "nodejs"], ["dnf", "install", "-y", "nodejs"]),
                ]:
                    if shutil.which(upgrade_cmd[0]):
                        installed = self._run_cmd(upgrade_cmd, 180)
                        break
                ok = installed
                if not ok:
                    detail = (
                        "自动升级失败，建议使用 nvm 安装:\n\n"
                        "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash\n"
                        "nvm install --lts\n\n"
                        "或手动下载: https://nodejs.org"
                    )

            if ok:
                new_ver = self._cmd_version("node") or "最新版"
                self._node_upgrade_ok = True
                self._node_upgrade_msg = f"Node.js 已升级成功！\n\n当前版本: {new_ver}"
            else:
                self._node_upgrade_ok = False
                err = getattr(self, "_last_cmd_err", "") or ""
                self._node_upgrade_msg = detail or (
                    f"升级失败:\n{err}" if err else "升级失败，请手动安装 Node.js:\nhttps://nodejs.org"
                )

        except Exception as e:
            self._node_upgrade_ok = False
            self._node_upgrade_msg = f"升级异常: {e}"
        finally:
            QMetaObject.invokeMethod(self, "_apply_node_upgrade", Qt.ConnectionType.QueuedConnection)

    def _win_download_install_node(self) -> bool:
        """Download Node.js LTS MSI installer and run it silently on Windows."""
        import tempfile, platform as _pf
        try:
            arch = _pf.machine().lower()
            if "arm" in arch or "aarch" in arch:
                msi_suffix = "arm64.msi"
            elif "64" in arch or "amd64" in arch:
                msi_suffix = "x64.msi"
            else:
                msi_suffix = "x86.msi"

            self._env_step_msg = "正在下载 Node.js 安装包…"
            QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)

            version_url = "https://nodejs.org/dist/latest-v22.x/"
            msi_url = None
            try:
                import urllib.request
                req = urllib.request.Request(version_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                import re
                for m in re.finditer(r'href="(node-v[\d.]+-' + re.escape(msi_suffix) + r')"', html):
                    msi_url = version_url + m.group(1)
                    break
            except Exception:
                pass

            if not msi_url:
                msi_url = f"https://nodejs.org/dist/latest-v22.x/node-v22.15.0-{msi_suffix}"

            tmpdir = tempfile.mkdtemp(prefix="node_install_")
            msi_path = os.path.join(tmpdir, f"node-lts-{msi_suffix}")

            try:
                import requests as _req
                resp = _req.get(msi_url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                with open(msi_path, "wb") as f:
                    f.write(resp.content)
            except Exception:
                import urllib.request
                req = urllib.request.Request(msi_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(msi_path, "wb") as f:
                        f.write(resp.read())

            if not os.path.isfile(msi_path) or os.path.getsize(msi_path) < 1_000_000:
                return False

            self._env_step_msg = "正在安装 Node.js…"
            QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)

            import subprocess, sys
            enc = {"encoding": "utf-8", "errors": "replace"} if sys.platform == "win32" else {}
            result = subprocess.run(
                ["msiexec", "/i", msi_path, "/qn", "/norestart"],
                capture_output=True, text=True, timeout=300,
                shell=(sys.platform == "win32"), **enc,
            )

            import shutil as _sh
            _sh.rmtree(tmpdir, ignore_errors=True)

            if result.returncode == 0:
                return True

            result2 = subprocess.run(
                ["msiexec", "/i", msi_path, "/passive", "/norestart"],
                capture_output=True, text=True, timeout=300,
                shell=(sys.platform == "win32"), **enc,
            )
            _sh.rmtree(tmpdir, ignore_errors=True)
            return result2.returncode == 0

        except Exception as e:
            self._last_cmd_err = str(e)
            return False

    def _mac_download_node_pkg(self) -> str:
        """Download Node.js .pkg installer to ~/Downloads on macOS. Returns path or empty."""
        import platform as _pf
        try:
            arch = _pf.machine().lower()
            pkg_suffix = "arm64.pkg" if ("arm" in arch or "aarch" in arch) else "x64.pkg"

            self._env_step_msg = "正在下载 Node.js 安装包…"
            QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)

            version_url = "https://nodejs.org/dist/latest-v22.x/"
            pkg_url = None
            pkg_filename = None
            try:
                import urllib.request, re
                req = urllib.request.Request(version_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                for m in re.finditer(r'href="(node-v[\d.]+-' + re.escape(pkg_suffix) + r')"', html):
                    pkg_filename = m.group(1)
                    pkg_url = version_url + pkg_filename
                    break
            except Exception:
                pass

            if not pkg_url:
                pkg_filename = f"node-v22.15.0-{pkg_suffix}"
                pkg_url = f"https://nodejs.org/dist/latest-v22.x/{pkg_filename}"

            dest = os.path.join(os.path.expanduser("~/Downloads"), pkg_filename)
            try:
                import requests as _req
                resp = _req.get(pkg_url, timeout=300, stream=True,
                                headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            except Exception:
                import urllib.request
                req = urllib.request.Request(pkg_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(dest, "wb") as f:
                        f.write(resp.read())

            if os.path.isfile(dest) and os.path.getsize(dest) > 1_000_000:
                return dest
        except Exception:
            pass
        return ""

    def _win_download_node_msi_to_downloads(self) -> str:
        """Download Node.js MSI to user's Downloads folder. Returns path or empty."""
        import platform as _pf
        try:
            arch = _pf.machine().lower()
            if "arm" in arch or "aarch" in arch:
                msi_suffix = "arm64.msi"
            elif "64" in arch or "amd64" in arch:
                msi_suffix = "x64.msi"
            else:
                msi_suffix = "x86.msi"

            self._env_step_msg = "正在下载 Node.js 安装包…"
            QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)

            version_url = "https://nodejs.org/dist/latest-v22.x/"
            msi_url = None
            msi_filename = None
            try:
                import urllib.request, re
                req = urllib.request.Request(version_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                for m in re.finditer(r'href="(node-v[\d.]+-' + re.escape(msi_suffix) + r')"', html):
                    msi_filename = m.group(1)
                    msi_url = version_url + msi_filename
                    break
            except Exception:
                pass

            if not msi_url:
                msi_filename = f"node-v22.15.0-{msi_suffix}"
                msi_url = f"https://nodejs.org/dist/latest-v22.x/{msi_filename}"

            downloads_dir = os.path.join(os.getenv("USERPROFILE", ""), "Downloads")
            if not os.path.isdir(downloads_dir):
                downloads_dir = os.path.join(os.getenv("USERPROFILE", ""), "下载")
            if not os.path.isdir(downloads_dir):
                downloads_dir = os.getcwd()
            dest = os.path.join(downloads_dir, msi_filename)

            try:
                import requests as _req
                resp = _req.get(msi_url, timeout=300, stream=True,
                                headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            except Exception:
                import urllib.request
                req = urllib.request.Request(msi_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(dest, "wb") as f:
                        f.write(resp.read())

            if os.path.isfile(dest) and os.path.getsize(dest) > 1_000_000:
                return dest
        except Exception:
            pass
        return ""

    @Slot()
    def _apply_node_upgrade(self):
        self._env_working = False
        self._node_upgrade_btn.setEnabled(True)
        self._env_install_btn.setEnabled(True)

        installer_path = getattr(self, "_node_upgrade_msi_path", "")
        if installer_path and os.path.isfile(installer_path):
            self._node_upgrade_msi_path = ""
            ret = QMessageBox.question(
                self, "安装 Node.js",
                f"已下载 Node.js 安装包到:\n{installer_path}\n\n"
                "是否立即打开安装？\n"
                "安装完成后请重启本软件。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret == QMessageBox.StandardButton.Yes:
                import sys, subprocess
                if sys.platform == "win32":
                    os.startfile(installer_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", installer_path])
                else:
                    subprocess.Popen(["xdg-open", installer_path])
            self._node_upgrade_btn.setText("⬆ 升级")
            return

        ok = getattr(self, "_node_upgrade_ok", False)
        msg = getattr(self, "_node_upgrade_msg", "")
        if ok:
            QMessageBox.information(self, "升级成功", msg)
            threading.Thread(target=self._bg_detect_env, daemon=True).start()
        else:
            QMessageBox.warning(self, "升级失败", msg)
            self._node_upgrade_btn.setText("⬆ 升级")

    # -- launch --
    def _on_env_launch(self):
        import shutil, sys, subprocess
        cli_cmd = self._cfg.get("cli_cmd", "")
        cli_path = (shutil.which(cli_cmd) or _find_cmd_in_common_paths(cli_cmd)) if cli_cmd else None
        if not cli_path:
            QMessageBox.warning(
                self, "无法启动",
                f"未找到 {cli_cmd} 命令，请先安装 {self.tool_name}。",
            )
            return

        min_node = self._cfg.get("min_node")
        if min_node:
            node_ver = self._cmd_version("node")
            parsed = self._parse_node_version(node_ver)
            if not parsed:
                ret = QMessageBox.question(
                    self, "Node.js 未安装",
                    f"{self.tool_name} 需要 Node.js v{'.'.join(str(x) for x in min_node)}+。\n\n"
                    "是否自动安装 Node.js？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if ret == QMessageBox.StandardButton.Yes:
                    self._on_node_upgrade()
                return
            if parsed < tuple(min_node):
                req = ".".join(str(x) for x in min_node)
                cur = ".".join(str(x) for x in parsed)
                ret = QMessageBox.question(
                    self, "Node.js 版本过低",
                    f"{self.tool_name} 需要 Node.js v{req} 或更高版本。\n\n"
                    f"当前版本: v{cur}\n\n"
                    "是否自动升级 Node.js？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if ret == QMessageBox.StandardButton.Yes:
                    self._on_node_upgrade()
                return

        if self._current_key and self._current_endpoint:
            write_fn = getattr(self, self._cfg.get("write_fn", ""), None)
            if write_fn:
                try:
                    write_fn(self._current_key, self._current_endpoint)
                except Exception:
                    pass

        extra_args = self._cfg.get("launch_args", [])
        full_cmd = f'"{cli_path}"'
        if extra_args:
            full_cmd += " " + " ".join(extra_args)

        try:
            if sys.platform == "darwin":
                subprocess.Popen([
                    "osascript", "-e",
                    f'tell application "Terminal"\n'
                    f'  do script "{cli_path}{(" " + " ".join(extra_args)) if extra_args else ""}"\n'
                    f'  activate\n'
                    f'end tell',
                ])
            elif sys.platform == "win32":
                subprocess.Popen(
                    f'start "" cmd /k {full_cmd}',
                    shell=True,
                )
            else:
                launch_list = [cli_path] + extra_args
                for term in ("gnome-terminal", "konsole", "xfce4-terminal",
                             "mate-terminal", "lxterminal", "xterm"):
                    if shutil.which(term):
                        if term == "gnome-terminal":
                            subprocess.Popen([term, "--"] + launch_list)
                        else:
                            subprocess.Popen([term, "-e"] + launch_list)
                        break
                else:
                    hint = " ".join([cli_cmd] + extra_args)
                    QMessageBox.information(
                        self, "提示",
                        f"请打开终端手动运行：\n\n{hint}",
                    )
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    # -- install --
    def _on_env_install(self):
        if self._env_working:
            return
        self._env_working = True
        self._env_install_btn.setEnabled(False)
        self._env_uninstall_btn.setEnabled(False)
        self._env_launch_btn.setEnabled(False)
        self._env_install_btn.setText("环境配置中…")
        threading.Thread(target=self._bg_install_all, daemon=True).start()

    def _bg_install_all(self):
        """Install missing prerequisites then the target CLI tool."""
        import shutil, sys
        npm_pkg = self._cfg.get("npm_pkg", "")
        tool_label = self.tool_name
        try:
            steps: list[str] = []
            darwin = sys.platform == "darwin"
            linux = sys.platform.startswith("linux")
            win32 = sys.platform == "win32"

            # Step 1: Node.js / npm
            if not (shutil.which("npm") or _find_cmd_in_common_paths("npm")):
                steps.append("Node.js")
                self._env_step_msg = "正在安装 Node.js…"
                QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)
                installed = False
                if darwin:
                    if shutil.which("brew"):
                        installed = self._run_cmd(["brew", "install", "node"], 180)
                elif linux:
                    for mgr_cmd in [
                        ["apt-get", "install", "-y", "nodejs", "npm"],
                        ["yum", "install", "-y", "nodejs", "npm"],
                        ["dnf", "install", "-y", "nodejs", "npm"],
                    ]:
                        if shutil.which(mgr_cmd[0]):
                            installed = self._run_cmd(mgr_cmd, 180)
                            break
                elif win32:
                    if shutil.which("winget"):
                        installed = self._run_cmd(
                            ["winget", "install", "--id", "OpenJS.NodeJS.LTS",
                             "-e", "--accept-source-agreements", "--accept-package-agreements"],
                            300,
                        )
                    elif shutil.which("choco"):
                        installed = self._run_cmd(["choco", "install", "nodejs-lts", "-y"], 300)

                if not installed and not (shutil.which("npm") or _find_cmd_in_common_paths("npm")):
                    if darwin and not shutil.which("brew"):
                        self._env_result_ok = False
                        self._env_result_msg = (
                            "未检测到 Homebrew，请先安装 Homebrew：\n\n"
                            '/bin/bash -c "$(curl -fsSL '
                            'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n\n'
                            "安装完成后重试。"
                        )
                    elif win32:
                        self._env_result_ok = False
                        self._env_result_msg = (
                            "无法自动安装 Node.js，请手动安装：\n\n"
                            "https://nodejs.org\n\n"
                            "下载 Windows 安装包(.msi)完成安装后重试。"
                        )
                    else:
                        self._env_result_ok = False
                        self._env_result_msg = (
                            "无法自动安装 Node.js，请手动安装：\n\n"
                            "https://nodejs.org\n\n"
                            "安装完成后重试。"
                        )
                    return

            # Step 2: Git
            if not shutil.which("git"):
                steps.append("Git")
                self._env_step_msg = "正在安装 Git…"
                QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)
                if darwin:
                    if shutil.which("brew"):
                        self._run_cmd(["brew", "install", "git"], 120)
                    else:
                        self._run_cmd(["xcode-select", "--install"], 30)
                elif linux:
                    for mgr_cmd in [
                        ["apt-get", "install", "-y", "git"],
                        ["yum", "install", "-y", "git"],
                        ["dnf", "install", "-y", "git"],
                    ]:
                        if shutil.which(mgr_cmd[0]):
                            self._run_cmd(mgr_cmd, 120)
                            break
                elif win32:
                    if shutil.which("winget"):
                        self._run_cmd(
                            ["winget", "install", "--id", "Git.Git",
                             "-e", "--accept-source-agreements", "--accept-package-agreements"],
                            300,
                        )
                    elif shutil.which("choco"):
                        self._run_cmd(["choco", "install", "git", "-y"], 300)

            # Step 3: configure git to use HTTPS instead of SSH for GitHub
            # Many npm packages reference git+ssh://git@github.com/... which
            # fails without SSH keys. This transparently rewrites to HTTPS.
            git_path = shutil.which("git")
            if git_path:
                self._run_cmd(
                    [git_path, "config", "--global",
                     "url.https://github.com/.insteadOf", "ssh://git@github.com/"],
                    10,
                )
                self._run_cmd(
                    [git_path, "config", "--global", "--add",
                     "url.https://github.com/.insteadOf", "git@github.com:"],
                    10,
                )

            # Step 4: install CLI
            self._env_step_msg = f"正在安装 {tool_label}…"
            QMetaObject.invokeMethod(self, "_apply_env_step", Qt.ConnectionType.QueuedConnection)

            npm_path = shutil.which("npm") or _find_cmd_in_common_paths("npm")
            if not npm_path:
                self._env_result_ok = False
                self._env_result_msg = "Node.js 安装后未生效，请重启应用后重试。"
                return

            cli_ok = self._run_cmd([npm_path, "install", "-g", npm_pkg], 300)
            if cli_ok:
                parts = [f"{tool_label} 安装成功！"]
                if steps:
                    parts.insert(0, f"已自动安装: {', '.join(steps)}")
                self._env_result_ok = True
                self._env_result_msg = "\n".join(parts)
            else:
                self._env_result_ok = False
                err = getattr(self, "_last_cmd_err", "")
                self._env_result_msg = f"{tool_label} 安装失败:\n{err}"
        except Exception as e:
            self._env_result_ok = False
            self._env_result_msg = f"安装异常: {e}"
        finally:
            QMetaObject.invokeMethod(self, "_apply_env_result", Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _run_cmd(cmd: list[str], timeout: int = 120) -> bool:
        import subprocess, sys
        try:
            use_shell = sys.platform == "win32"
            enc = {"encoding": "utf-8", "errors": "replace"} if sys.platform == "win32" else {}
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, shell=use_shell, **enc,
            )
            if r.returncode != 0:
                Sub2ApiPlatformPage._last_cmd_err = (r.stderr or "").strip() or (r.stdout or "").strip()
            return r.returncode == 0
        except Exception as e:
            Sub2ApiPlatformPage._last_cmd_err = str(e)
            return False

    @Slot()
    def _apply_env_step(self):
        msg = getattr(self, "_env_step_msg", "")
        if msg:
            self._env_install_btn.setText(msg)

    # -- uninstall --
    def _on_env_uninstall(self):
        if self._env_working:
            return
        cli_cmd = self._cfg.get("cli_cmd", "cli")
        ret = QMessageBox.warning(
            self, f"卸载 {self.tool_name}",
            f"确定要卸载 {self.tool_name} 吗？\n\n"
            f"卸载后将无法在终端使用 {cli_cmd} 命令。\n"
            "Node.js 和 Git 不会被卸载。",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ret != QMessageBox.StandardButton.Ok:
            return
        self._env_working = True
        self._env_install_btn.setEnabled(False)
        self._env_uninstall_btn.setEnabled(False)
        self._env_launch_btn.setEnabled(False)
        self._env_uninstall_btn.setText("卸载中…")
        threading.Thread(target=self._bg_uninstall_cli, daemon=True).start()

    def _bg_uninstall_cli(self):
        import shutil
        npm_pkg = self._cfg.get("npm_pkg", "")
        tool_label = self.tool_name
        try:
            npm_path = shutil.which("npm") or _find_cmd_in_common_paths("npm")
            if not npm_path:
                self._env_result_ok = False
                self._env_result_msg = "未找到 npm，无法卸载。"
            else:
                pkg_name = npm_pkg.replace("@latest", "") if npm_pkg.endswith("@latest") else npm_pkg
                ok = self._run_cmd([npm_path, "uninstall", "-g", pkg_name], 60)
                self._env_result_ok = ok
                self._env_result_msg = (
                    f"{tool_label} 已卸载。" if ok
                    else f"卸载失败:\n{getattr(self, '_last_cmd_err', '')}"
                )
        except Exception as e:
            self._env_result_ok = False
            self._env_result_msg = f"卸载异常: {e}"
        finally:
            QMetaObject.invokeMethod(self, "_apply_env_result", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_env_result(self):
        self._env_working = False
        self._env_install_btn.setEnabled(True)
        self._env_uninstall_btn.setText("卸载")
        ok = getattr(self, "_env_result_ok", False)
        msg = getattr(self, "_env_result_msg", "")
        if ok:
            QMessageBox.information(self, "完成", msg)
        else:
            QMessageBox.warning(self, "操作失败", msg)
        threading.Thread(target=self._bg_detect_env, daemon=True).start()

    def _build_key_section(self, vbox):
        sec_hdr = self._section_header("密钥与端点", self._cfg["accent"])
        vbox.addLayout(sec_hdr)

        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 24)
        cl.setSpacing(16)

        # Provider selector (OpenClaw only)
        self._provider_combo: QComboBox | None = None
        if self.tool_name == "OpenClaw":
            prov_row = QHBoxLayout()
            prov_row.setSpacing(10)
            prov_lbl = QLabel("密钥来源")
            prov_lbl.setFixedWidth(72)
            prov_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 700; color: #475569;"
                "background: transparent; border: none; letter-spacing: 0.3px;"
            )
            self._provider_combo = QComboBox()
            self._provider_combo.addItem("Codex", "codex")
            self._provider_combo.addItem("Claude Code", "claude-code")
            self._provider_combo.setFixedHeight(40)
            self._provider_combo.setStyleSheet(
                "QComboBox { background: #f8fafc; border: 1.5px solid #e2e8f0;"
                "  border-radius: 12px; padding: 0 14px; font-size: 13px;"
                "  font-weight: 600; color: #1e293b; }"
                "QComboBox:hover { border-color: #cbd5e1; background: #fff; }"
                "QComboBox::drop-down { border: none; width: 30px; }"
                "QComboBox::down-arrow { image: none; border-left: 5px solid transparent;"
                "  border-right: 5px solid transparent; border-top: 6px solid #94a3b8; }"
                "QComboBox QAbstractItemView { background: #fff; border: 1px solid #e2e8f0;"
                "  border-radius: 8px; padding: 4px; selection-background-color: #eef2ff;"
                "  selection-color: #1e293b; font-size: 13px; }"
            )
            self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
            prov_hint = QLabel("选择使用哪个工具的密钥")
            prov_hint.setStyleSheet(
                "font-size: 11px; color: #94a3b8; background: transparent; border: none;"
            )
            prov_row.addWidget(prov_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            prov_row.addWidget(self._provider_combo, 1)
            prov_row.addWidget(prov_hint, 0, Qt.AlignmentFlag.AlignVCenter)
            cl.addLayout(prov_row)

        # API Key display
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        key_lbl = QLabel("API Key")
        key_lbl.setFixedWidth(72)
        key_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #475569; background: transparent;"
            "border: none; letter-spacing: 0.3px;"
        )
        self._key_display = QLineEdit()
        self._key_display.setReadOnly(True)
        self._key_display.setPlaceholderText("激活含该工具权限的激活码后自动生成，到期后需重新激活")
        self._key_display.setFixedHeight(40)
        self._key_display.setStyleSheet(
            "QLineEdit { background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; "
            "padding: 0 14px; font-size: 13px; font-family: 'SF Mono','Menlo','Consolas',monospace; color: #1e293b; }"
            "QLineEdit:hover { border-color: #cbd5e1; background: #ffffff; }"
        )
        self._copy_key_btn = QPushButton("复制")
        self._copy_key_btn.setStyleSheet(_BTN_OUTLINE)
        self._copy_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_key_btn.setFixedWidth(64)
        self._copy_key_btn.clicked.connect(self._copy_key)
        key_row.addWidget(key_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        key_row.addWidget(self._key_display, 1)
        key_row.addWidget(self._copy_key_btn)
        cl.addLayout(key_row)

        # Endpoint display
        ep_row = QHBoxLayout()
        ep_row.setSpacing(10)
        ep_lbl = QLabel("端  点")
        ep_lbl.setFixedWidth(72)
        ep_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #475569; background: transparent;"
            "border: none; letter-spacing: 0.3px;"
        )
        self._ep_display = QLineEdit()
        self._ep_display.setReadOnly(True)
        self._ep_display.setPlaceholderText("自动获取")
        self._ep_display.setFixedHeight(40)
        self._ep_display.setStyleSheet(
            "QLineEdit { background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; "
            "padding: 0 14px; font-size: 13px; font-family: 'SF Mono','Menlo','Consolas',monospace; color: #1e293b; }"
            "QLineEdit:hover { border-color: #cbd5e1; background: #ffffff; }"
        )
        self._copy_ep_btn = QPushButton("复制")
        self._copy_ep_btn.setStyleSheet(_BTN_OUTLINE)
        self._copy_ep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_ep_btn.setFixedWidth(64)
        self._copy_ep_btn.clicked.connect(self._copy_endpoint)
        ep_row.addWidget(ep_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        ep_row.addWidget(self._ep_display, 1)
        ep_row.addWidget(self._copy_ep_btn)
        cl.addLayout(ep_row)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #f1f5f9; border: none;")
        cl.addWidget(sep)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._write_btn = QPushButton("⬇ 一键写入本地配置")
        self._write_btn.setStyleSheet(_BTN_SUCCESS)
        self._write_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._write_btn.clicked.connect(self._on_write_local)

        self._refresh_key_btn = QPushButton("↻ 刷新密钥")
        self._refresh_key_btn.setStyleSheet(_BTN_WARNING)
        self._refresh_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_key_btn.clicked.connect(self._on_refresh_key)
        self._refresh_key_btn.setVisible(False)

        btn_row.addWidget(self._write_btn)
        btn_row.addWidget(self._refresh_key_btn)
        btn_row.addStretch()

        cfg_path = self._cfg.get("display_path", "~/.config")
        hint = QLabel(f"📁 {cfg_path}")
        hint.setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent; border: none;")
        btn_row.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)

        cl.addLayout(btn_row)

        vbox.addWidget(card)

    def _build_usage_section(self, vbox):
        sec_hdr = self._section_header("使用记录", "#6366f1")
        vbox.addLayout(sec_hdr)

        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        req_chip = QFrame()
        req_chip.setStyleSheet(
            "QFrame { background: #eef2ff; border: 1.5px solid #e0e7ff; border-radius: 10px; }"
        )
        rch = QHBoxLayout(req_chip)
        rch.setContentsMargins(12, 6, 12, 6)
        rch.setSpacing(6)
        self._stats_requests = QLabel("请求: —")
        self._stats_requests.setStyleSheet(
            "font-size: 13px; color: #4f46e5; background: transparent; font-weight: 700; border: none;"
        )
        rch.addWidget(self._stats_requests)

        cost_chip = QFrame()
        cost_chip.setStyleSheet(
            "QFrame { background: #ecfdf5; border: 1.5px solid #d1fae5; border-radius: 10px; }"
        )
        cch = QHBoxLayout(cost_chip)
        cch.setContentsMargins(12, 6, 12, 6)
        cch.setSpacing(6)
        self._stats_cost = QLabel("花费: —")
        self._stats_cost.setStyleSheet(
            "font-size: 13px; color: #059669; background: transparent; font-weight: 700; border: none;"
        )
        cch.addWidget(self._stats_cost)

        refresh_usage_btn = QPushButton("↻ 刷新")
        refresh_usage_btn.setStyleSheet(_BTN_OUTLINE)
        refresh_usage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_usage_btn.setFixedWidth(88)
        refresh_usage_btn.clicked.connect(self._load_usage)

        stats_row.addWidget(req_chip)
        stats_row.addWidget(cost_chip)
        stats_row.addStretch()
        stats_row.addWidget(refresh_usage_btn)
        cl.addLayout(stats_row)

        # Usage table
        self._usage_table = QTableWidget()
        self._usage_table.setColumnCount(5)
        self._usage_table.setHorizontalHeaderLabels(["时间", "模型", "输入Token", "输出Token", "费用(USD)"])
        header = self._usage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 160)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._usage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._usage_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._usage_table.setAlternatingRowColors(True)
        self._usage_table.verticalHeader().setVisible(False)
        self._usage_table.setMinimumHeight(300)
        self._usage_table.setStyleSheet(
            "QTableWidget { background: #fff; border: 1px solid #e8ecf1; border-radius: 12px; "
            "font-size: 12px; gridline-color: #f1f5f9; }"
            "QTableWidget::item { padding: 8px 12px; }"
            "QHeaderView::section { background: #f8fafc; font-weight: 700; font-size: 11px; "
            "border: none; border-bottom: 2px solid #e2e8f0; padding: 10px 12px; color: #64748b; "
            "letter-spacing: 0.5px; }"
            "QTableWidget::item:alternate { background: #fafbfc; }"
            "QTableWidget::item:selected { background: #eef2ff; }"
        )
        cl.addWidget(self._usage_table)

        # Pager
        pager_row = QHBoxLayout()
        pager_row.setSpacing(10)
        self._prev_btn = QPushButton("‹ 上一页")
        self._prev_btn.setStyleSheet(_BTN_OUTLINE)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(lambda: self._change_page(-1))
        self._page_label = QLabel("第 1 页")
        self._page_label.setStyleSheet(
            "font-size: 12px; color: #64748b; background: transparent; font-weight: 600;"
        )
        self._next_btn = QPushButton("下一页 ›")
        self._next_btn.setStyleSheet(_BTN_OUTLINE)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(lambda: self._change_page(1))
        pager_row.addStretch()
        pager_row.addWidget(self._prev_btn)
        pager_row.addWidget(self._page_label)
        pager_row.addWidget(self._next_btn)
        pager_row.addStretch()
        cl.addLayout(pager_row)

        vbox.addWidget(card)

    def _section_header(self, title, accent):
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0f172a; background: transparent; border: none; padding: 0;"
        )
        hdr.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr.addStretch()
        return hdr

    # ---- Data loading ----
    def showEvent(self, event):
        super().showEvent(event)
        if not self._has_quota:
            return
        import time
        if self._current_key and (time.time() - self._last_load_time) < self._CACHE_TTL:
            return
        self._load_all()

    def _load_all(self):
        threading.Thread(target=self._bg_load_all, daemon=True).start()

    def _resolve_tool_key(self) -> str:
        """Return the tool identifier used for key lookup."""
        if self.tool_name == "OpenClaw" and self._provider_combo is not None:
            return self._provider_combo.currentData() or "codex"
        return self.tool_name.lower().replace(' ', '-')

    def _bg_load_all(self):
        import time as _time
        tool = self._resolve_tool_key()

        cls = Sub2ApiPlatformPage
        if cls._shared_endpoint and (_time.time() - cls._shared_endpoint_time) < self._CACHE_TTL:
            self._bg_endpoint = {"success": True, "data": {"endpoint": cls._shared_endpoint}}
            self._bg_keys = self.api.sub2api_list_keys(tool)
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                ep_future = pool.submit(self.api.sub2api_get_endpoint)
                keys_future = pool.submit(self.api.sub2api_list_keys, tool)
                self._bg_endpoint = ep_future.result()
                self._bg_keys = keys_future.result()
            ep = self._bg_endpoint
            if ep.get("success") and ep.get("data"):
                cls._shared_endpoint = str(ep["data"].get("endpoint", ""))
                cls._shared_endpoint_time = _time.time()

        keys_data = self._bg_keys
        if self.tool_name != "OpenClaw":
            if keys_data.get("success") and isinstance(keys_data.get("data"), list) and not keys_data["data"]:
                gen = self.api.sub2api_generate_key(tool)
                if gen.get("success") and gen.get("data"):
                    self._bg_keys = {"success": True, "data": [gen["data"]]}

        QMetaObject.invokeMethod(self, "_apply_load_all", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_load_all(self):
        import time

        ep = getattr(self, "_bg_endpoint", {})
        if ep.get("success") and ep.get("data"):
            self._current_endpoint = str(ep["data"].get("endpoint", ""))
            self._ep_display.setText(self._display_endpoint())

        keys = getattr(self, "_bg_keys", {})
        if keys.get("success") and isinstance(keys.get("data"), list) and keys["data"]:
            first = keys["data"][0]
            expires = str(first.get("expires_at", "") or "")
            expired = False
            if expires:
                try:
                    from datetime import datetime
                    exp_dt = datetime.fromisoformat(expires[:19])
                    expired = exp_dt < datetime.now()
                except Exception:
                    pass
            if expired:
                self._current_key = ""
                self._current_key_id = None
                self._key_display.clear()
                self._key_display.setPlaceholderText("密钥已到期，请在首页重新激活")
            else:
                self._current_key = first.get("key", "")
                self._current_key_id = first.get("id")
                self._key_display.setText(_mask_key(self._current_key))
                self._last_load_time = time.time()
        else:
            self._current_key = ""
            self._current_key_id = None
            self._key_display.clear()
            if self.tool_name == "OpenClaw":
                provider_name = (self._provider_combo.currentText()
                                 if self._provider_combo else "Codex")
                self._key_display.setPlaceholderText(
                    f"{provider_name} 暂无可用密钥，请先激活该工具的额度"
                )

        self._usage_page = 1
        if self._current_key_id is not None:
            self._load_usage()
            self._reload_stats()
        else:
            self._usage_table.setRowCount(0)
            self._stats_requests.setText("请求: 0")
            self._stats_cost.setText("花费: $0.0000")

    def _render_usage_table(self, data: dict):
        items = data.get("items") or []
        self._usage_table.setRowCount(len(items))
        page_cost = 0.0
        for i, item in enumerate(items):
            ts = str(item.get("created_at", ""))[:19].replace("T", " ")
            model = item.get("model", "—")
            inp = str(item.get("input_tokens", 0))
            out = str(item.get("output_tokens", 0))
            cost = item.get("actual_cost", item.get("total_cost", 0))
            if isinstance(cost, (int, float)):
                page_cost += cost
            cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else str(cost)
            for j, val in enumerate([ts, model, inp, out, cost_str]):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._usage_table.setItem(i, j, cell)

        total = data.get("total", len(items))
        page_size = data.get("page_size", 20)
        total_pages = max(1, (total + page_size - 1) // page_size)
        self._page_label.setText(f"第 {self._usage_page} / {total_pages} 页 (共 {total} 条)")
        self._prev_btn.setEnabled(self._usage_page > 1)
        self._next_btn.setEnabled(self._usage_page < total_pages)

        if self._usage_page == 1:
            self._page_cost_sum = page_cost
            self._page_total = total
        else:
            self._page_cost_sum = getattr(self, "_page_cost_sum", 0) + page_cost

    # ---- Actions ----
    def _on_provider_changed(self):
        """OpenClaw: user switched between Codex / Claude Code key source."""
        self._current_key = ""
        self._current_key_id = None
        self._key_display.clear()
        self._ep_display.clear()
        self._usage_table.setRowCount(0)
        self._stats_requests.setText("请求: —")
        self._stats_cost.setText("花费: —")
        self._last_load_time = 0.0
        self._load_all()

    def _on_write_local(self):
        if not self._current_key:
            QMessageBox.warning(self, "提示", "暂无可用密钥，请先在首页激活包含该工具权限的激活码")
            return
        if not self._current_endpoint:
            QMessageBox.warning(self, "提示", "端点地址为空，请检查 Sub2API 配置")
            return

        write_fn = getattr(self, self._cfg.get("write_fn", ""), None)
        if write_fn is None:
            QMessageBox.warning(self, "错误", "不支持的工具类型")
            return

        try:
            path = write_fn(self._current_key, self._current_endpoint)
            QMessageBox.information(self, "成功", f"配置已写入:\n{path}\n\n请重启 {self.tool_name} 使配置生效。")
        except Exception as e:
            QMessageBox.warning(self, "写入失败", f"无法写入配置文件:\n{e}")

    def _write_codex_config(self, key: str, endpoint: str) -> str:
        import re
        codex_dir = os.path.join(_home_dir(), ".codex")
        os.makedirs(codex_dir, exist_ok=True)
        base_url = endpoint.rstrip("/") + "/v1"
        written = []

        auth_path = os.path.join(codex_dir, "auth.json")
        auth = {}
        if os.path.exists(auth_path):
            try:
                with open(auth_path, "r", encoding="utf-8") as f:
                    auth = json.load(f)
            except (json.JSONDecodeError, OSError):
                auth = {}
        auth["OPENAI_API_KEY"] = key
        with open(auth_path, "w", encoding="utf-8") as f:
            json.dump(auth, f, indent=2, ensure_ascii=False)
        written.append(auth_path)

        toml_path = os.path.join(codex_dir, "config.toml")
        default_provider = "ai"

        if os.path.exists(toml_path):
            try:
                with open(toml_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Detect the current active provider name
                m = re.search(r'^model_provider\s*=\s*"([^"]+)"', content, re.MULTILINE)
                active_provider = m.group(1) if m else None

                if active_provider and f"[model_providers.{active_provider}]" in content:
                    # Update existing active provider's base_url in place
                    content = re.sub(
                        rf'(\[model_providers\.{re.escape(active_provider)}\][^\[]*?base_url\s*=\s*)"[^"]*"',
                        rf'\1"{base_url}"',
                        content,
                        flags=re.DOTALL,
                    )
                elif active_provider:
                    # Active provider set but no block — add the block
                    provider_block = (
                        f'\n[model_providers.{active_provider}]\n'
                        f'name = "{active_provider}"\n'
                        f'base_url = "{base_url}"\n'
                        f'wire_api = "responses"\n'
                        f'requires_openai_auth = true\n'
                    )
                    content = content.rstrip() + "\n" + provider_block
                else:
                    # No active provider — create one
                    provider_block = (
                        f'\n[model_providers.{default_provider}]\n'
                        f'name = "{default_provider}"\n'
                        f'base_url = "{base_url}"\n'
                        f'wire_api = "responses"\n'
                        f'requires_openai_auth = true\n'
                    )
                    content = f'model_provider = "{default_provider}"\n' + content.rstrip() + "\n" + provider_block

                with open(toml_path, "w", encoding="utf-8") as f:
                    f.write(content)
                written.append(toml_path)
            except OSError:
                pass
        else:
            provider_block = (
                f'model_provider = "{default_provider}"\n\n'
                f'[model_providers.{default_provider}]\n'
                f'name = "{default_provider}"\n'
                f'base_url = "{base_url}"\n'
                f'wire_api = "responses"\n'
                f'requires_openai_auth = true\n'
            )
            with open(toml_path, "w", encoding="utf-8") as f:
                f.write(provider_block)
            written.append(toml_path)

        return "\n".join(written)

    def _write_claude_config(self, key: str, endpoint: str) -> str:
        claude_dir = os.path.join(_home_dir(), ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        base_url = endpoint.rstrip("/")

        # 1) ~/.claude/settings.json — env vars for Claude Code CLI
        settings_path = os.path.join(claude_dir, "settings.json")
        settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError):
                settings = {}
        if not isinstance(settings.get("env"), dict):
            settings["env"] = {}
        settings["env"]["ANTHROPIC_API_KEY"] = key
        settings["env"]["ANTHROPIC_BASE_URL"] = base_url
        settings["env"].pop("ANTHROPIC_AUTH_TOKEN", None)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        # Clean up legacy ~/.claude.json and fix key approval
        legacy_path = os.path.join(_home_dir(), ".claude.json")
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
                changed = False
                if isinstance(legacy.get("env"), dict):
                    legacy.pop("env")
                    changed = True
                for k in ("apiKey", "apiUrl"):
                    if k in legacy:
                        legacy.pop(k)
                        changed = True

                # Ensure the key suffix is approved (not rejected) in customApiKeyResponses
                key_suffix = key[-20:] if len(key) > 20 else key
                responses = legacy.get("customApiKeyResponses")
                if isinstance(responses, dict):
                    rejected = responses.get("rejected", [])
                    approved = responses.get("approved", [])
                    if isinstance(rejected, list) and key_suffix in rejected:
                        rejected.remove(key_suffix)
                        changed = True
                    if isinstance(approved, list) and key_suffix not in approved:
                        approved.append(key_suffix)
                        changed = True
                    responses["rejected"] = rejected
                    responses["approved"] = approved

                if changed:
                    with open(legacy_path, "w", encoding="utf-8") as f:
                        json.dump(legacy, f, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, OSError):
                pass

        # 2) ~/.claude/config.json — set primaryApiKey to bypass login
        config_path = os.path.join(claude_dir, "config.json")
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                config = {}
        config["primaryApiKey"] = key
        config["hasCompletedOnboarding"] = True
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return settings_path

    def _write_gemini_config(self, key: str, endpoint: str) -> str:
        gemini_dir = os.path.join(_home_dir(), ".gemini")
        os.makedirs(gemini_dir, exist_ok=True)
        base_url = endpoint.rstrip("/") + "/v1"

        # 1) ~/.gemini/.env — dotenv format (read-merge-write)
        env_path = os.path.join(gemini_dir, ".env")
        env_vars: dict[str, str] = {}
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip()
            except OSError:
                pass
        env_vars["GEMINI_API_KEY"] = key
        env_vars["GOOGLE_GEMINI_BASE_URL"] = base_url
        with open(env_path, "w", encoding="utf-8") as f:
            for k in sorted(env_vars):
                f.write(f"{k}={env_vars[k]}\n")

        # 2) ~/.gemini/settings.json — auth type selection
        settings_path = os.path.join(gemini_dir, "settings.json")
        settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError):
                settings = {}
        if not isinstance(settings.get("security"), dict):
            settings["security"] = {}
        if not isinstance(settings["security"].get("auth"), dict):
            settings["security"]["auth"] = {}
        settings["security"]["auth"]["selectedType"] = "gemini-api-key"
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        return env_path

    def _write_openclaw_config(self, key: str, endpoint: str) -> str:
        oc_dir = os.path.join(_home_dir(), ".openclaw")
        os.makedirs(oc_dir, exist_ok=True)
        base_url = endpoint.rstrip("/") + "/v1"

        json_path = os.path.join(oc_dir, "openclaw.json")
        config: dict = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    import re as _re
                    raw = f.read()
                    raw = _re.sub(r'//.*', '', raw)
                    raw = _re.sub(r',\s*([}\]])', r'\1', raw)
                    config = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                config = {}

        # models.providers — register as an OpenAI-compatible provider
        if not isinstance(config.get("models"), dict):
            config["models"] = {}
        models = config["models"]
        models["mode"] = "merge"
        if not isinstance(models.get("providers"), dict):
            models["providers"] = {}
        models["providers"]["sub2api"] = {
            "baseUrl": base_url,
            "apiKey": key,
            "api": "openai-completions",
            "models": [],
        }

        # env — set ANTHROPIC_API_KEY for native Anthropic model access
        if not isinstance(config.get("env"), dict):
            config["env"] = {}
        config["env"]["ANTHROPIC_API_KEY"] = key
        config["env"]["ANTHROPIC_BASE_URL"] = endpoint.rstrip("/")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return json_path

    def _on_refresh_key(self):
        if not self._current_key:
            QMessageBox.warning(self, "提示", "暂无可用密钥，无法刷新")
            return

        ret = QMessageBox.warning(
            self, "刷新密钥",
            "刷新后请注意：\n\n"
            "1. 当前密钥将立即失效，需重新执行「一键写入本地配置」\n"
            "2. 余额和使用记录保持不变\n\n"
            "确定要刷新吗？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ret != QMessageBox.StandardButton.Ok:
            return

        self._refresh_key_btn.setEnabled(False)
        self._refresh_key_btn.setText("刷新中...")
        threading.Thread(target=self._bg_refresh_key, daemon=True).start()

    def _bg_refresh_key(self):
        tool = self.tool_name.lower().replace(' ', '-')
        self._bg_refresh_result = self.api.sub2api_refresh_key(tool)
        QMetaObject.invokeMethod(self, "_apply_refresh_key", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_refresh_key(self):
        self._refresh_key_btn.setEnabled(True)
        self._refresh_key_btn.setText("↻ 刷新密钥")

        r = getattr(self, "_bg_refresh_result", {})
        if r.get("success") and r.get("data"):
            d = r["data"]
            self._current_key = d.get("key", "")
            self._current_key_id = d.get("id")
            self._key_display.setText(_mask_key(self._current_key))
            if d.get("endpoint"):
                self._current_endpoint = d["endpoint"]
                self._ep_display.setText(self._display_endpoint())
            self._last_load_time = 0
            QMessageBox.information(
                self, "刷新成功",
                "密钥已刷新，请点击「一键写入本地配置」更新本地配置。\n\n旧密钥已失效。"
            )
        else:
            msg = r.get("message", "刷新失败，请稍后重试")
            QMessageBox.warning(self, "刷新失败", msg)

    def _copy_key(self):
        if self._current_key:
            QApplication.clipboard().setText(self._current_key)
            QMessageBox.information(self, "已复制", "API Key 已复制到剪贴板")

    def _copy_endpoint(self):
        display = self._display_endpoint()
        if display:
            QApplication.clipboard().setText(display)
            QMessageBox.information(self, "已复制", "端点地址已复制到剪贴板")

    def _reload_stats(self):
        threading.Thread(target=self._bg_refresh_stats, args=("month",), daemon=True).start()

    def _bg_refresh_stats(self, period):
        self._bg_stats_refresh = self.api.sub2api_get_usage_stats(
            period, api_key_id=self._current_key_id)
        QMetaObject.invokeMethod(self, "_apply_refresh_stats", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_refresh_stats(self):
        r = getattr(self, "_bg_stats_refresh", {})
        if r.get("success") and r.get("data"):
            d = r["data"]
            reqs = d.get("total_requests", 0)
            cost = d.get("total_actual_cost", d.get("total_cost", 0))
            if reqs or cost:
                self._stats_requests.setText(f"请求: {reqs}")
                self._stats_cost.setText(f"花费: ${cost:.4f}" if isinstance(cost, (int, float)) else f"花费: {cost}")
                return
        page_total = getattr(self, "_page_total", None)
        if page_total is not None:
            self._stats_requests.setText(f"请求: {page_total}")
            page_cost = getattr(self, "_page_cost_sum", 0)
            self._stats_cost.setText(f"花费: ${page_cost:.4f}")

    def _load_usage(self):
        threading.Thread(target=self._bg_load_usage, daemon=True).start()

    def _bg_load_usage(self):
        self._bg_usage_refresh = self.api.sub2api_get_usage(
            self._usage_page, 20, api_key_id=self._current_key_id)
        QMetaObject.invokeMethod(self, "_apply_load_usage", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_load_usage(self):
        r = getattr(self, "_bg_usage_refresh", {})
        if r.get("success") and r.get("data"):
            self._render_usage_table(r["data"])
            if self._usage_page == 1:
                self._stats_requests.setText(f"请求: {getattr(self, '_page_total', 0)}")
                self._stats_cost.setText(f"花费: ${getattr(self, '_page_cost_sum', 0):.4f}")

    def _change_page(self, delta):
        self._usage_page = max(1, self._usage_page + delta)
        self._load_usage()

    @staticmethod
    def _normalize_permissions(raw) -> list:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    def set_guide(self, text: str | None):
        """Show or hide the usage guide section."""
        if text:
            self._guide_label.setText(text)
            self._guide_panel.setVisible(True)
        else:
            self._guide_panel.setVisible(False)

    def set_env_visible(self, visible: bool):
        """Dynamically show/hide the environment config section."""
        self._env_visible = visible
        if self._env_card_widget is not None:
            self._env_card_widget.setVisible(visible)
            if visible and not hasattr(self, "_env_detected"):
                self._env_detected = True
                threading.Thread(target=self._bg_detect_env, daemon=True).start()

    def load_init_data(self, data: dict):
        """Called from OverviewPage when activation data is loaded."""
        if self.tool_name == "OpenClaw":
            perms = self._normalize_permissions(data.get("platform_permissions"))
            codex_ok = (not perms or "codex" in perms) and (data.get("codex_quota", 0) or 0) > 0
            claude_ok = (not perms or "claude_code" in perms) and (data.get("claude_code_quota", 0) or 0) > 0
            self._has_quota = codex_ok or claude_ok
            if self._provider_combo is not None:
                self._provider_combo.setEnabled(True)
                if not codex_ok and claude_ok:
                    self._provider_combo.setCurrentIndex(1)
                elif codex_ok:
                    self._provider_combo.setCurrentIndex(0)
        else:
            quota_key = self._QUOTA_KEY_MAP.get(self.tool_name, "")
            perm_key = self._PERM_KEY_MAP.get(self.tool_name, "")
            quota = data.get(quota_key, 0) or 0
            perms = self._normalize_permissions(data.get("platform_permissions"))
            has_perm = not perms or perm_key in perms
            self._has_quota = has_perm and quota > 0

        self._stack.setCurrentIndex(1 if self._has_quota else 0)

        if self._has_quota and self.isVisible():
            self._load_all()
