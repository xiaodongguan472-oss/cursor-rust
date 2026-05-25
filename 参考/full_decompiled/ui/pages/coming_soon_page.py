"""通用占位页 — 即将上线的功能"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ComingSoonPage(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setStyleSheet("background: #f4f6f9;")
        inner = QVBoxLayout(container)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.setSpacing(16)

        icon_label = QLabel("🔜")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #1e293b; background: transparent;"
        )

        desc_label = QLabel("即将上线，敬请期待")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet(
            "font-size: 14px; color: #94a3b8; background: transparent;"
        )

        badge = QLabel("COMING SOON")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedWidth(170)
        badge.setStyleSheet(
            "font-size: 11px; font-weight: 800; color: #4f46e5; "
            "background: #eef2ff; border-radius: 14px; padding: 8px 18px; "
            "letter-spacing: 2px; border: 1.5px solid #c7d2fe;"
        )

        inner.addStretch(2)
        inner.addWidget(icon_label)
        inner.addWidget(title_label)
        inner.addWidget(desc_label)
        inner.addSpacing(8)
        inner.addWidget(badge, 0, Qt.AlignmentFlag.AlignCenter)
        inner.addStretch(3)

        layout.addWidget(container)
