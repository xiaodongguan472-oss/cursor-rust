"""可复用的自定义组件"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


def _card_shadow(widget, blur=24, y_offset=6, opacity=14):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)
    return shadow


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        _card_shadow(self)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 22, 24, 22)
        self._layout.setSpacing(14)

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_layout(self, layout):
        self._layout.addLayout(layout)


class CardHeader(QWidget):
    def __init__(self, title: str, color: str = "#4f46e5", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(10)

        icon_bg = QFrame()
        icon_bg.setFixedSize(6, 20)
        icon_bg.setStyleSheet(
            f"background: {color}; border-radius: 3px; border: none;"
        )

        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")

        layout.addWidget(icon_bg, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title_label)
        layout.addStretch()


class SectionPanel(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer = QFrame()
        outer.setObjectName("SectionPanel")
        _card_shadow(outer, blur=18, y_offset=4, opacity=12)
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        head = QWidget()
        head.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 16, 18, 10)
        hl.setSpacing(10)

        bar = QFrame()
        bar.setFixedSize(5, 18)
        bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #4f46e5, stop:1 #6366f1); border-radius: 2px; border: none;"
        )
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #1e293b; background: transparent;"
        )

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)

        hl.addWidget(bar, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addStretch(1)
        hl.addLayout(self._actions)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(20, 6, 20, 18)
        self._body.setSpacing(10)

        vl.addWidget(head)
        vl.addLayout(self._body)
        root.addWidget(outer)

    def actions_layout(self) -> QHBoxLayout:
        return self._actions

    def add_body_widget(self, widget):
        self._body.addWidget(widget)

    def add_body_layout(self, layout):
        self._body.addLayout(layout)


class CollapseSection(QWidget):
    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        self._expanded = expanded

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header_container = QFrame()
        header_container.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; }"
        )
        _card_shadow(header_container, blur=12, y_offset=2, opacity=12)
        header_inner = QHBoxLayout(header_container)
        header_inner.setContentsMargins(20, 0, 20, 0)
        header_inner.setSpacing(0)

        self._header_btn = QPushButton(f"    {title}")
        self._header_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; text-align: left; "
            "padding: 15px 0; font-size: 14px; font-weight: 700; color: #1e293b; }"
            "QPushButton:hover { color: #4f46e5; }"
        )
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.clicked.connect(self.toggle)

        self._arrow = QLabel("›")
        self._arrow.setStyleSheet(
            "color: #94a3b8; font-size: 18px; font-weight: bold; background: transparent;"
        )
        self._arrow.setFixedWidth(24)
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_inner.addWidget(self._header_btn, 1)
        header_inner.addWidget(self._arrow)

        main_layout.addWidget(header_container)

        self._content = QFrame()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 18)
        self._content_layout.setSpacing(10)
        self._content.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-top: none; border-radius: 0 0 16px 16px; }"
        )
        main_layout.addWidget(self._content)

        self._header_container = header_container

        if expanded:
            self._content.setVisible(True)
            self._arrow.setText("v")
            self._header_container.setStyleSheet(
                "QFrame { background: #ffffff; border: 1px solid #e2e8f0; "
                "border-radius: 16px 16px 0 0; border-bottom: none; }"
            )
        else:
            self._content.setVisible(False)

    def toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("v" if self._expanded else "›")
        if self._expanded:
            self._header_container.setStyleSheet(
                "QFrame { background: #ffffff; border: 1px solid #e2e8f0; "
                "border-radius: 16px 16px 0 0; border-bottom: none; }"
            )
        else:
            self._header_container.setStyleSheet(
                "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; }"
            )

    def add_content_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_content_layout(self, layout):
        self._content_layout.addLayout(layout)


class StatusBadge(QWidget):
    def __init__(self, text: str, active: bool = False, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._container = QFrame()
        cl = QHBoxLayout(self._container)
        cl.setContentsMargins(12, 6, 16, 6)
        cl.setSpacing(8)

        self._dot = QFrame()
        self._dot.setFixedSize(8, 8)

        self._text = QLabel(text)
        self._text.setStyleSheet("background: transparent; border: none;")

        cl.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        cl.addWidget(self._text)

        self._layout.addWidget(self._container)
        self._layout.addStretch()

        self.update_status(text, active)

    def update_status(self, text: str, active: bool):
        color = "#059669" if active else "#94a3b8"
        bg = "#ecfdf5" if active else "#f1f5f9"
        border = "#d1fae5" if active else "#e2e8f0"
        dot_color = "#10b981" if active else "#cbd5e1"

        self._text.setText(text)
        self._text.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none; letter-spacing: 0.3px;"
        )
        self._dot.setStyleSheet(
            f"background: {dot_color}; border-radius: 4px; border: none;"
        )
        self._container.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1.5px solid {border}; border-radius: 14px; }}"
        )


class InfoRow(QWidget):
    def __init__(
        self,
        label: str,
        value: str = "",
        parent=None,
        field_style: bool = False,
        display_only: bool = False,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self._label = QLabel(label)
        self._label.setObjectName("CardLabel")
        self._label.setMinimumWidth(72)

        self._value = QLabel(value)
        if display_only:
            self._value.setObjectName("DisplayValue")
            self._value.setWordWrap(True)
            layout.addWidget(self._label)
            layout.addWidget(self._value, 1)
        elif field_style:
            self._value.setObjectName("InfoFieldValue")
            strip = QFrame()
            strip.setObjectName("InfoFieldStrip")
            inner = QHBoxLayout(strip)
            inner.setContentsMargins(14, 10, 14, 10)
            inner.addWidget(self._value, 1)
            layout.addWidget(self._label)
            layout.addWidget(strip, 1)
        else:
            self._value.setObjectName("CardValue")
            layout.addWidget(self._label)
            layout.addWidget(self._value, 1)

    def set_value(self, text: str):
        self._value.setText(text)
