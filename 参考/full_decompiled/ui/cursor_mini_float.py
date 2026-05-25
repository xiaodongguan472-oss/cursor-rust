"""Cursor 迷你浮窗 — 置顶工具条，换号 / 重置机器码"""

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QEvent, QRect, QPoint, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QMouseEvent


class CursorMiniFloatWindow(QWidget):
    """无边框置顶小窗，可拖动标题栏。"""

    swap_clicked = Signal()
    reset_clicked = Signal()
    closed_by_user = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_anchor = None  # QPoint | None
        self._app_filter_installed = False
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(300)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        self.setObjectName("CursorMiniFloatWindow")
        self.setStyleSheet(
            "#CursorMiniFloatWindow {"
            "  background: transparent;"
            "}"
            "QWidget#MiniFloatRoot {"
            "  background-color: #2b2d3a;"
            "  border-radius: 22px;"
            "  border: none;"
            "}"
        )

        shell = QFrame()
        shell.setObjectName("MiniFloatRoot")
        sl = QVBoxLayout(shell)
        sl.setContentsMargins(14, 12, 14, 14)
        sl.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(34)
        title_bar.setStyleSheet("background: transparent;")
        th = QHBoxLayout(title_bar)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(8)

        dot = QFrame()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            "background: #3b82f6; border-radius: 4px; border: none;"
        )
        ttl = QLabel("Cursor")
        ttl.setStyleSheet(
            "color: #f8fafc; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { color: #94a3b8; background: transparent; "
            "border: none; border-radius: 9px; font-size: 18px; font-weight: 400; }"
            "QPushButton:hover { color: #f1f5f9; background: #3f4252; }"
        )
        close_btn.clicked.connect(self._on_close_clicked)

        self._status_tag = QLabel()
        self._status_tag.setVisible(False)

        th.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        th.addWidget(ttl, 0, Qt.AlignmentFlag.AlignVCenter)
        th.addWidget(self._status_tag, 0, Qt.AlignmentFlag.AlignVCenter)
        th.addStretch()
        th.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #3f4252; border: none;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        swap_btn = QPushButton("换号")
        swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        swap_btn.setMinimumHeight(44)
        swap_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #2563eb, stop:1 #3b82f6);"
            "  color: #fff; border: none; border-radius: 16px;"
            "  font-size: 13px; font-weight: 700; padding: 0 12px;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #1d4ed8, stop:1 #2563eb);"
            "}"
            "QPushButton:pressed { background: #1e40af; }"
            "QPushButton:disabled { background: #475569; color: #cbd5e1; }"
        )
        swap_btn.clicked.connect(self.swap_clicked.emit)

        reset_btn = QPushButton("重置机器码")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setMinimumHeight(44)
        reset_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #e2e8f0;"
            "  border: 1px solid #52556b; border-radius: 16px;"
            "  font-size: 12px; font-weight: 600; padding: 0 10px;"
            "}"
            "QPushButton:hover {"
            "  background: #363945; border-color: #64748b;"
            "}"
            "QPushButton:pressed { background: #2b2d3a; }"
            "QPushButton:disabled { background: #1e293b; color: #64748b; }"
        )
        reset_btn.clicked.connect(self.reset_clicked.emit)

        btn_row.addWidget(swap_btn, 1)
        btn_row.addWidget(reset_btn, 1)

        sl.addWidget(title_bar)
        sl.addSpacing(8)
        sl.addWidget(sep)
        sl.addSpacing(10)
        sl.addLayout(btn_row)

        root.addWidget(shell)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        # 略减轻阴影，避免外圈像多一圈黑色晕边
        shadow.setColor(QColor(0, 0, 0, 55))
        shell.setGraphicsEffect(shadow)

        self._swap_btn = swap_btn
        self._reset_btn = reset_btn

        self._result_timer = QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.timeout.connect(self._clear_status_tag)

    def _on_close_clicked(self):
        self.hide()
        self.closed_by_user.emit()

    def set_actions_enabled(self, swap: bool, reset: bool):
        self._swap_btn.setEnabled(swap)
        self._reset_btn.setEnabled(reset)

    # ---- 内联状态显示 ----

    def show_working(self, action: str):
        self._result_timer.stop()
        self._status_tag.setText(action)
        self._status_tag.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #fbbf24; "
            "background: #422006; border-radius: 8px; padding: 2px 8px; border: none;"
        )
        self._status_tag.setVisible(True)
        if "换号" in action:
            self._swap_btn.setText("换号中…")
        elif "重置" in action:
            self._reset_btn.setText("重置中…")
        self._swap_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)

    def show_result(self, text: str, success: bool):
        color = "#34d399" if success else "#f87171"
        bg = "#064e3b" if success else "#7f1d1d"
        self._status_tag.setText(text)
        self._status_tag.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {color}; "
            f"background: {bg}; border-radius: 8px; padding: 2px 8px; border: none;"
        )
        self._status_tag.setVisible(True)
        self._swap_btn.setText("换号")
        self._reset_btn.setText("重置机器码")
        self._swap_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._result_timer.start(3000)

    def _clear_status_tag(self):
        self._status_tag.setVisible(False)

    @staticmethod
    def _pick_screen_for_show():
        """打开浮窗时优先用鼠标所在显示器，否则主显示器。"""
        s = QGuiApplication.screenAt(QCursor.pos())
        return s if s is not None else QGuiApplication.primaryScreen()

    def _screen_at_global_point(self, global_pt):
        s = QGuiApplication.screenAt(global_pt)
        if s is not None:
            return s
        return QGuiApplication.primaryScreen()

    @staticmethod
    def _widget_is_descendant_of(widget: QWidget, ancestor: QWidget) -> bool:
        w = widget
        while w is not None:
            if w == ancestor:
                return True
            w = w.parentWidget()
        return False

    @staticmethod
    def _widget_or_ancestor_is_push_button(widget: QWidget) -> bool:
        w = widget
        while w is not None:
            if isinstance(w, QPushButton):
                return True
            w = w.parentWidget()
        return False

    def _place_screen_top_center(self, screen):
        """屏幕可用区域顶部水平居中。"""
        self.adjustSize()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.top() + 10
        self.move(x, y)

    def _clamp_to_screen(self, top_left_global: QPoint) -> QPoint:
        """拖动时限制在当前屏工作区内（可随意移动，不锁顶）。"""
        self.adjustSize()
        cand = QRect(top_left_global, self.size())
        screen = self._screen_at_global_point(cand.center())
        if screen is None:
            return top_left_global
        avail = screen.availableGeometry()
        side = 4
        x = top_left_global.x()
        y = top_left_global.y()
        x = max(avail.left() + side, min(x, avail.right() - self.width() - side))
        y = max(avail.top() + side, min(y, avail.bottom() - self.height() - side))
        return QPoint(x, y)

    def show_at_screen_top(self):
        screen = self._pick_screen_for_show()
        self._place_screen_top_center(screen)
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        app = QApplication.instance()
        if app is not None and not self._app_filter_installed:
            app.installEventFilter(self)
            self._app_filter_installed = True

    def hideEvent(self, event):
        app = QApplication.instance()
        if app is not None and self._app_filter_installed:
            app.removeEventFilter(self)
            self._app_filter_installed = False
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self._drag_anchor = None
        super().hideEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            self._drag_anchor is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            top_left = event.globalPosition().toPoint() - self._drag_anchor
            self.move(self._clamp_to_screen(top_left))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
            self._drag_anchor = None
        super().mouseReleaseEvent(event)

    def eventFilter(self, obj, event):
        # 点在浮窗内任意非 QPushButton 区域时开始拖动（子控件事件先发往子控件，用应用级过滤器截获）
        if (
            self.isVisible()
            and isinstance(obj, QWidget)
            and self._widget_is_descendant_of(obj, self)
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            me = event
            if isinstance(me, QMouseEvent) and me.button() == Qt.MouseButton.LeftButton:
                if not self._widget_or_ancestor_is_push_button(obj):
                    self._drag_anchor = me.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    self.grabMouse()
                    return True
        return super().eventFilter(obj, event)
