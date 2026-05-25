"""Cursor Pro 管理页面

功能: 一键配置/取消配置 + 使用记录
"""

from __future__ import annotations

import json
import threading
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QScrollArea, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGraphicsDropShadowEffect, QCheckBox, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject
from PySide6.QtGui import QColor

from ui.widgets import Card, CardHeader, StatusBadge, SectionPanel
from ui.platform_icons import platform_icon_label


# ── Helpers ──────────────────────────────────────────────────────

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


_BTN_OUTLINE = (
    "QPushButton { "
    "  background: #ffffff; color: #4f46e5; "
    "  border: 1.5px solid #e0e7ff; border-radius: 10px; "
    "  padding: 0 18px; font-size: 13px; font-weight: 600; min-height: 36px; }"
    "QPushButton:hover { background: #eef2ff; border-color: #c7d2fe; }"
    "QPushButton:pressed { background: #e0e7ff; }"
)


# ── Page ─────────────────────────────────────────────────────────

class CursorProPage(QWidget):
    _show_msg = Signal(str, str, str)
    navigate_to = Signal(str)
    _install_progress_sig = Signal(int, str)
    _install_done_sig = Signal(bool, str)

    _TOOL = "cursor-pro"
    _CACHE_TTL = 120

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._working = False
        self._has_quota = False
        self._current_key = ""
        self._current_key_id = None
        self._current_endpoint = ""
        self._last_load_time = 0.0
        self._usage_page = 1
        self._is_injected = False
        self._show_msg.connect(self._do_show_msg)
        self._install_progress_sig.connect(self._on_install_progress)
        self._install_done_sig.connect(self._on_install_done)
        self._build()

    # ── Empty state ──────────────────────────────────────────────

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
        icon_lbl = platform_icon_label("Cursor Pro", 42)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_inner.addWidget(icon_lbl)

        icon_wrap = QHBoxLayout()
        icon_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_wrap.addWidget(icon_bg)
        center.addLayout(icon_wrap)
        center.addSpacing(20)

        title_lbl = QLabel("暂未开通 Cursor Pro")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1e293b;"
            "background: transparent; border: none;"
        )
        center.addWidget(title_lbl)
        center.addSpacing(8)

        desc_lbl = QLabel("激活包含 Cursor Pro 权限的激活码后，即可使用一键配置功能")
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
        center.addLayout(btn_row)
        vbox.addLayout(center)
        vbox.addStretch(3)
        self._page_stack.addWidget(empty)

    # ── Main build ───────────────────────────────────────────────

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

        # ── Header ───────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)
        hdr_icon = platform_icon_label("Cursor Pro", 32)
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(3)
        title = QLabel("Cursor Pro")
        title.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;"
        )
        sub = QLabel("Pro 增强 · 一键配置")
        sub.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 400;")
        hdr_col.addWidget(title)
        hdr_col.addWidget(sub)
        hdr_row.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr_row.addLayout(hdr_col, 1)
        vbox.addLayout(hdr_row)

        # ── Install strip (same as Cursor) ────────────────
        self._build_install_strip(vbox)

        # ── Inject card ──────────────────────────────────────────
        self._build_inject_card(vbox)

        # ── Usage ────────────────────────────────────────────────
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
        self._page_stack.addWidget(scroll)
        self._page_stack.setCurrentIndex(0)
        outer.addWidget(self._page_stack)

    # ── Install strip ────────────────────────────────────────────

    def _build_install_strip(self, vbox):
        strip = QFrame()
        strip.setObjectName("cursorProInstallStrip")
        strip.setStyleSheet(
            "QFrame#cursorProInstallStrip { background: #ffffff; border: 1px solid #e8ecf1;"
            "  border-left: 3px solid #7c3aed; border-radius: 12px; }"
        )
        _shadow(strip, blur=12, y=2, alpha=8)
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(16, 10, 12, 10)
        sl.setSpacing(10)

        self._install_badge = StatusBadge("检测中", active=False)
        sl.addWidget(self._install_badge)

        self._install_ver_label = QLabel("")
        self._install_ver_label.setStyleSheet(
            "color: #64748b; font-size: 12px; background: transparent; border: none;"
        )
        sl.addWidget(self._install_ver_label)
        sl.addStretch()

        # 安装进度条（仅在安装/重装过程中显示）
        self._install_progress = QProgressBar()
        self._install_progress.setFixedSize(120, 4)
        self._install_progress.setRange(0, 100)
        self._install_progress.setValue(0)
        self._install_progress.setTextVisible(False)
        self._install_progress.setVisible(False)
        self._install_progress.setStyleSheet(
            "QProgressBar { background: #e2e8f0; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #7c3aed; border-radius: 2px; }"
        )
        sl.addWidget(self._install_progress)

        self._install_progress_label = QLabel()
        self._install_progress_label.setStyleSheet(
            "color: #64748b; font-size: 11px; background: transparent; border: none;"
        )
        self._install_progress_label.setVisible(False)
        sl.addWidget(self._install_progress_label)

        self._launch_btn = QPushButton("▶ 启动")
        self._launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._launch_btn.setFixedHeight(30)
        self._launch_btn.setEnabled(False)
        self._launch_btn.setStyleSheet(
            "QPushButton { background: #7c3aed; color: #fff; border: none;"
            "  border-radius: 8px; font-size: 12px; font-weight: 700; padding: 0 18px; }"
            "QPushButton:hover { background: #6d28d9; }"
            "QPushButton:disabled { background: #94a3b8; color: #e2e8f0; }"
        )
        self._launch_btn.clicked.connect(self._on_launch_cursor)
        sl.addWidget(self._launch_btn)

        self._install_btn = QPushButton("安装 Cursor")
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
        sl.addWidget(self._install_btn)

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
        sl.addWidget(self._uninstall_btn)

        vbox.addWidget(strip)
        threading.Thread(target=self._bg_detect_install, daemon=True).start()

    def _bg_detect_install(self):
        time.sleep(0.3)
        try:
            from core.cursor_process import is_cursor_installed, get_cursor_version
            self._bg_installed = is_cursor_installed()
            self._bg_version = get_cursor_version() if self._bg_installed else None
        except Exception:
            self._bg_installed = False
            self._bg_version = None
        QMetaObject.invokeMethod(self, "_apply_install_status", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_install_status(self):
        installed = getattr(self, "_bg_installed", False)
        version = getattr(self, "_bg_version", None)
        if installed:
            self._install_badge.update_status("已安装", True)
            self._install_ver_label.setText(f"v{version}" if version else "")
            self._uninstall_btn.setEnabled(True)
            self._launch_btn.setEnabled(True)
            self._install_btn.setText("重新安装")
        else:
            self._install_badge.update_status("未安装", False)
            self._install_ver_label.setText("")
            self._uninstall_btn.setEnabled(False)
            self._launch_btn.setEnabled(False)
            self._install_btn.setText("安装 Cursor")

    def _on_launch_cursor(self):
        try:
            from core.cursor_process import open_cursor
            if not open_cursor():
                QMessageBox.warning(self, "启动失败", "未找到 Cursor 安装路径，请确认已正确安装。")
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    # ── 安装 / 重装 ──────────────────────────────────────────────

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
        self._launch_btn.setEnabled(False)
        if hasattr(self, "_inject_btn"):
            self._inject_btn.setEnabled(False)
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
        if hasattr(self, "_inject_btn"):
            self._inject_btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "安装成功", msg)
        else:
            QMessageBox.warning(self, "安装失败", msg)
        threading.Thread(target=self._bg_detect_install, daemon=True).start()
        # 安装后注入态可能变化，刷新一次
        self._refresh_inject_status_async()

    # ── 卸载 ─────────────────────────────────────────────────────

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
        self._launch_btn.setEnabled(False)
        if hasattr(self, "_inject_btn"):
            self._inject_btn.setEnabled(False)
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
        self._install_btn.setEnabled(True)
        self._uninstall_btn.setEnabled(True)
        self._uninstall_btn.setText("卸载 Cursor")
        if hasattr(self, "_inject_btn"):
            self._inject_btn.setEnabled(True)
        threading.Thread(target=self._bg_detect_install, daemon=True).start()
        # 卸载（含清理数据）后注入态肯定失效，刷新一次
        self._refresh_inject_status_async()

    def _refresh_inject_status_async(self):
        """安装/卸载完成后异步刷新一次注入状态展示（best-effort）。"""
        def _run():
            cfg: dict = {}
            try:
                from core.cursor_pro_setup import read_current_config
                cfg = read_current_config() or {}
            except Exception:
                cfg = {}
            self._pending_inject_cfg = cfg
            QMetaObject.invokeMethod(
                self, "_apply_status_safe", Qt.ConnectionType.QueuedConnection
            )
        threading.Thread(target=_run, daemon=True).start()

    @Slot()
    def _apply_status_safe(self):
        try:
            cfg = getattr(self, "_pending_inject_cfg", None) or {}
            self._apply_status(cfg)
        except Exception:
            pass

    # ── Inject card (Pro 账号配置) ────────────────────────────────

    def _build_inject_card(self, vbox):
        panel = Card()
        panel.add_widget(CardHeader("Pro 账号配置", color="#7c3aed"))

        # Status row: label + badge ... button
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 4, 0, 4)
        rl.setSpacing(12)

        status_lb = QLabel("配置状态")
        status_lb.setObjectName("CardLabel")
        status_lb.setMinimumWidth(72)
        rl.addWidget(status_lb)

        self._inject_badge = StatusBadge("检测中", active=False)
        rl.addWidget(self._inject_badge)
        rl.addStretch()

        self._inject_btn = QPushButton("一键配置")
        self._inject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._inject_btn.setMinimumHeight(38)
        self._inject_btn.setMaximumHeight(38)
        self._inject_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #7c3aed, stop:1 #8b5cf6);"
            "  color: #fff; border: none; border-radius: 14px;"
            "  font-size: 14px; font-weight: 700; padding: 0 32px;"
            "  letter-spacing: 0.3px; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "  stop:0 #6d28d9, stop:1 #7c3aed); }"
            "QPushButton:pressed { background: #5b21b6; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self._inject_btn.clicked.connect(self._on_inject_or_cancel)
        rl.addWidget(self._inject_btn)

        panel.add_widget(row)
        vbox.addWidget(panel)

    # ── Usage section ────────────────────────────────────────────

    def _build_usage_section(self, vbox):
        sec_hdr = self._section_header("使用记录")
        vbox.addLayout(sec_hdr)

        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)

        req_chip = QFrame()
        req_chip.setStyleSheet(
            "QFrame { background: #f5f3ff; border: 1.5px solid #ede9fe; border-radius: 10px; }"
        )
        rch = QHBoxLayout(req_chip)
        rch.setContentsMargins(12, 6, 12, 6)
        rch.setSpacing(6)
        self._stats_requests = QLabel("请求: —")
        self._stats_requests.setStyleSheet(
            "font-size: 13px; color: #7c3aed; background: transparent; font-weight: 700; border: none;"
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
        refresh_usage_btn.clicked.connect(self._on_refresh_usage)

        stats_row.addWidget(req_chip)
        stats_row.addWidget(cost_chip)
        stats_row.addStretch()
        stats_row.addWidget(refresh_usage_btn)
        cl.addLayout(stats_row)

        self._usage_table = QTableWidget()
        self._usage_table.setColumnCount(5)
        self._usage_table.setHorizontalHeaderLabels(
            ["时间", "模型", "输入Token", "输出Token", "费用(USD)"]
        )
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
            "QTableWidget::item:selected { background: #f5f3ff; }"
        )
        cl.addWidget(self._usage_table)

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

    # ── Section header helper ────────────────────────────────────

    @staticmethod
    def _section_header(title_text: str):
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        lbl = QLabel(title_text)
        lbl.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #0f172a; "
            "background: transparent; border: none; padding: 0;"
        )
        hdr.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr.addStretch()
        return hdr

    # ── Message helpers ──────────────────────────────────────────

    def _do_show_msg(self, kind: str, title: str, msg: str):
        if kind == "info":
            QMessageBox.information(self, title, msg)
        else:
            QMessageBox.warning(self, title, msg)

    def set_guide(self, text: str | None):
        """Show or hide the usage guide section."""
        if text:
            self._guide_label.setText(text)
            self._guide_panel.setVisible(True)
        else:
            self._guide_panel.setVisible(False)

    def _emit_info(self, title: str, msg: str):
        self._show_msg.emit("info", title, msg)

    def _emit_warn(self, title: str, msg: str):
        self._show_msg.emit("warn", title, msg)

    def _display_endpoint(self) -> str:
        if not self._current_endpoint:
            return ""
        base = self._current_endpoint.rstrip("/")
        return base + "/v1"

    # ── Data loading (Sub2Api pattern) ───────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._has_quota:
            return
        if self._current_key and (time.time() - self._last_load_time) < self._CACHE_TTL:
            return
        self._load_all()

    def _load_all(self):
        threading.Thread(target=self._bg_load_all, daemon=True).start()

    def _bg_load_all(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:
            ep_future = pool.submit(self.api.sub2api_get_endpoint)
            keys_future = pool.submit(self.api.sub2api_list_keys, self._TOOL)
            status_future = pool.submit(self._read_local_config)
            self._bg_endpoint = ep_future.result()
            self._bg_keys = keys_future.result()
            self._bg_local_config = status_future.result()

        keys_data = self._bg_keys
        if keys_data.get("success") and isinstance(keys_data.get("data"), list) and not keys_data["data"]:
            gen = self.api.sub2api_generate_key(self._TOOL)
            if gen.get("success") and gen.get("data"):
                self._bg_keys = {"success": True, "data": [gen["data"]]}

        QMetaObject.invokeMethod(self, "_apply_load_all", Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _read_local_config() -> dict:
        try:
            from core.cursor_pro_setup import read_current_config
            return read_current_config()
        except Exception:
            return {}

    @Slot()
    def _apply_load_all(self):
        ep = getattr(self, "_bg_endpoint", {})
        if ep.get("success") and ep.get("data"):
            self._current_endpoint = str(ep["data"].get("endpoint", ""))

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
            if not expired:
                self._current_key = first.get("key", "")
                self._current_key_id = first.get("id")
                self._last_load_time = time.time()
            else:
                self._current_key = ""
                self._current_key_id = None
        else:
            self._current_key = ""
            self._current_key_id = None

        cfg = getattr(self, "_bg_local_config", {})
        self._apply_status(cfg)

        self._usage_page = 1
        if self._current_key_id is not None:
            self._load_usage()
            self._reload_stats()
        else:
            self._usage_table.setRowCount(0)
            self._stats_requests.setText("请求: 0")
            self._stats_cost.setText("花费: $0.0000")

    # ── Status display ───────────────────────────────────────────

    def _apply_status(self, cfg: dict):
        api_ok = bool(cfg.get("openai_base_url")) and bool(cfg.get("has_openai_key"))
        injected = api_ok
        self._is_injected = injected

        if injected:
            email = cfg.get("email", "")
            label = "已配置"
            if email:
                label += f"  ·  {email}"
            self._inject_badge.update_status(label, True)
            self._inject_btn.setText("取消配置")
            self._inject_btn.setStyleSheet(
                "QPushButton { background: #f1f5f9; color: #475569; "
                "  border: 1px solid #e2e8f0; border-radius: 14px;"
                "  font-size: 14px; font-weight: 700; padding: 0 32px; }"
                "QPushButton:hover { background: #e2e8f0; }"
                "QPushButton:disabled { background: #f8fafc; color: #cbd5e1; }"
            )
        else:
            self._inject_badge.update_status("未配置", False)
            self._inject_btn.setText("一键配置")
            self._inject_btn.setStyleSheet(
                "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "  stop:0 #7c3aed, stop:1 #8b5cf6);"
                "  color: #fff; border: none; border-radius: 14px;"
                "  font-size: 14px; font-weight: 700; padding: 0 32px;"
                "  letter-spacing: 0.3px; }"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "  stop:0 #6d28d9, stop:1 #7c3aed); }"
                "QPushButton:pressed { background: #5b21b6; }"
                "QPushButton:disabled { background: #94a3b8; }"
            )

    # ── Usage data ───────────────────────────────────────────────

    def _on_refresh_usage(self):
        if self._current_key_id is not None:
            self._load_usage()
            self._reload_stats()

    def _reload_stats(self):
        threading.Thread(target=self._bg_refresh_stats, daemon=True).start()

    def _bg_refresh_stats(self):
        self._bg_stats_data = self.api.sub2api_get_usage_stats(
            "month", api_key_id=self._current_key_id
        )
        QMetaObject.invokeMethod(self, "_apply_stats", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_stats(self):
        r = getattr(self, "_bg_stats_data", {})
        if r.get("success") and r.get("data"):
            d = r["data"]
            reqs = d.get("total_requests", 0)
            cost = d.get("total_actual_cost", d.get("total_cost", 0))
            if reqs or cost:
                self._stats_requests.setText(f"请求: {reqs}")
                if isinstance(cost, (int, float)):
                    self._stats_cost.setText(f"花费: ${cost:.4f}")
                else:
                    self._stats_cost.setText(f"花费: {cost}")
                return
        page_total = getattr(self, "_page_total", None)
        if page_total is not None:
            self._stats_requests.setText(f"请求: {page_total}")
            page_cost = getattr(self, "_page_cost_sum", 0)
            self._stats_cost.setText(f"花费: ${page_cost:.4f}")

    def _load_usage(self):
        threading.Thread(target=self._bg_load_usage, daemon=True).start()

    def _bg_load_usage(self):
        self._bg_usage_data = self.api.sub2api_get_usage(
            self._usage_page, 20, api_key_id=self._current_key_id
        )
        QMetaObject.invokeMethod(self, "_apply_usage", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _apply_usage(self):
        r = getattr(self, "_bg_usage_data", {})
        if r.get("success") and r.get("data"):
            self._render_usage_table(r["data"])
            if self._usage_page == 1:
                self._stats_requests.setText(f"请求: {getattr(self, '_page_total', 0)}")
                self._stats_cost.setText(f"花费: ${getattr(self, '_page_cost_sum', 0):.4f}")

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

    def _change_page(self, delta):
        self._usage_page = max(1, self._usage_page + delta)
        self._load_usage()

    # ── Inject / Cancel inject ───────────────────────────────────

    def _on_inject_or_cancel(self):
        if self._working:
            QMessageBox.information(self, "提示", "操作进行中，请耐心等待...")
            return

        if self._is_injected:
            reply = QMessageBox.question(
                self, "确认取消配置",
                "取消配置后 Cursor 将恢复默认设置并自动重启，确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._working = True
            self._inject_btn.setEnabled(False)
            self._inject_btn.setText("正在取消...")
            threading.Thread(target=self._do_teardown, daemon=True).start()
        else:
            if not self._current_key or not self._current_endpoint:
                QMessageBox.warning(self, "提示", "服务初始化中，请稍后重试")
                return
            reply = QMessageBox.question(
                self, "确认配置",
                "配置后将使用服务端分配的共享 Pro 账号登录 Cursor"
                "（会替换当前 Cursor 的登录态），并自动重启 Cursor，确认继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._working = True
            self._inject_btn.setEnabled(False)
            self._inject_btn.setText("正在配置...")
            threading.Thread(target=self._do_setup, daemon=True).start()

    def _do_setup(self):
        try:
            relay_url = self._display_endpoint()
            relay_key = self._current_key

            # 始终向服务端申请 Cursor Pro 账号并自动登录到本机 Cursor。
            # 服务端按"用户绑定"模式调度：同一用户每次拿到的都是同一账号；
            # 账号池耗尽时直接终止配置并提示用户。
            try:
                resp = self.api.get_cursor_pro_config(with_account=True) or {}
            except Exception:
                resp = {}

            if not resp.get("success"):
                msg = (resp.get("message") or "").strip() \
                    or "无法从服务端获取 Pro 账号，请稍后重试"
                self._emit_warn("配置失败", msg)
                return

            data = resp.get("data") or {}
            cursor_account = data.get("cursorAccount")
            if not isinstance(cursor_account, dict) \
                    or not cursor_account.get("accessToken"):
                self._emit_warn(
                    "配置失败",
                    "服务端未下发 Cursor Pro 账号，请联系管理员补充账号",
                )
                return

            allowed_models = data.get("allowedModels") or []
            disabled_models = data.get("disabledModels") or []
            if not isinstance(allowed_models, list):
                allowed_models = []
            if not isinstance(disabled_models, list):
                disabled_models = []

            from core.cursor_pro_setup import full_setup
            results = full_setup(
                cursor_account=cursor_account,
                relay_url=relay_url,
                relay_api_key=relay_key,
                allowed_models=[str(m) for m in allowed_models],
                disabled_models=[str(m) for m in disabled_models],
                keep_login=False,
            )

            failed = [r for r in results if not r[1]]
            if failed:
                self._emit_warn("配置失败", "部分配置未成功，请稍后重试")
            else:
                logged_email = cursor_account.get("email", "")
                tail = f"\n已自动登录账号: {logged_email}" if logged_email else ""
                self._emit_info(
                    "配置完成",
                    f"Cursor Pro API 已配置，Cursor 正在重启。{tail}",
                )
        except Exception:
            self._emit_warn("配置失败", "操作异常，请稍后重试")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_action_done", Qt.ConnectionType.QueuedConnection,
            )

    def _fetch_pro_config(
        self, with_account: bool = False,
    ) -> tuple[list[str], list[str], dict | None]:
        """拉取服务端下发的 Cursor Pro 一键配置。

        Args:
            with_account: 是否同时让服务端分配一个 Pro 账号（用于自动登录）。
                False 时不消耗账号池配额。

        Returns:
            ``(allowed_models, disabled_models, cursor_account)``。任一字段缺失
            或请求失败时对应值降级为 ``[]`` / ``None``，让一键配置仍可继续。
        """
        try:
            resp = self.api.get_cursor_pro_config(with_account=with_account) or {}
            if resp.get("success"):
                data = resp.get("data") or {}
                allowed = data.get("allowedModels") or []
                disabled = data.get("disabledModels") or []
                if not isinstance(allowed, list):
                    allowed = []
                if not isinstance(disabled, list):
                    disabled = []
                acc = data.get("cursorAccount") if with_account else None
                if not isinstance(acc, dict):
                    acc = None
                return (
                    [str(m) for m in allowed],
                    [str(m) for m in disabled],
                    acc,
                )
        except Exception:
            pass
        return [], [], None

    # 兼容旧调用点
    def _fetch_model_overrides(self) -> tuple[list[str], list[str]]:
        a, d, _ = self._fetch_pro_config(with_account=False)
        return a, d

    def _do_teardown(self):
        try:
            from core.cursor_pro_setup import full_teardown
            results = full_teardown()

            failed = [r for r in results if not r[1]]
            if failed:
                self._emit_warn("取消失败", "部分操作未成功，请稍后重试")
            else:
                self._emit_info("已取消", "Cursor Pro 配置已取消，Cursor 正在重启。")
        except Exception:
            self._emit_warn("取消失败", "操作异常，请稍后重试")
        finally:
            self._working = False
            QMetaObject.invokeMethod(
                self, "_on_action_done", Qt.ConnectionType.QueuedConnection,
            )

    @Slot()
    def _on_action_done(self):
        self._inject_btn.setEnabled(True)
        self._load_all()

    # ── Permission / activation gate ─────────────────────────────

    @staticmethod
    def _parse_permissions(data: dict) -> set:
        raw = data.get("platform_permissions")
        if not raw:
            return set()
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return set()
        if isinstance(raw, list):
            return set(raw)
        return set()

    def load_init_data(self, data: dict):
        if not data:
            return
        if data.get("banned") or not data.get("activated"):
            self._page_stack.setCurrentIndex(0)
            return
        perms = self._parse_permissions(data)
        if perms and "cursor_pro" not in perms:
            self._page_stack.setCurrentIndex(0)
            return

        quota = data.get("cursor_pro_quota", 0) or 0
        if quota <= 0:
            self._page_stack.setCurrentIndex(0)
            return

        self._has_quota = True
        self._page_stack.setCurrentIndex(1)

        if self.isVisible():
            self._load_all()
