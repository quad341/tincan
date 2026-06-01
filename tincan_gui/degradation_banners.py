"""Capability degradation banners: State A (disconnected), B (Show Notifications off), C (ANCS)."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.capability_banner import CapabilityBanner

# ---------------------------------------------------------------------------
# State A: Disconnected
# ---------------------------------------------------------------------------

class StateABanner(CapabilityBanner):
    """Full-width disconnected banner (h=56, red border). Design: tincan-s42 §2 State A."""

    MSG = (
        "⊗ Connection lost — Bluetooth out of range"
        " · Showing cached conversations · reconnecting…"
    )

    def __init__(self, last_seen: str = "", parent: Optional[QWidget] = None) -> None:
        msg = self.MSG if not last_seen else (
            f"⊗ Connection lost — last seen {last_seen} · "
            "Bluetooth out of range · reconnecting…"
        )
        super().__init__(message=msg, parent=parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            "background-color: #fef2f2; border: 1px solid #fca5a5;"
        )


# ---------------------------------------------------------------------------
# State B: Show Notifications off
# ---------------------------------------------------------------------------

class StateBBanner(QWidget):
    """Messaging unavailable banner (h=80, amber). Design: tincan-s42 §2 State B."""

    show_me_how_clicked = Signal()

    MSG_TITLE = "⚠ Messaging unavailable"
    MSG_BODY = (
        "Enable 'Show Notifications' on iPhone:"
        " Settings → Bluetooth → [device] → Show Notifications"
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet(
            "background-color: #fffbeb; border: 1px solid #f59e0b;"
        )
        self.setAccessibleName(f"{self.MSG_TITLE} — {self.MSG_BODY}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel(self.MSG_TITLE)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #92400e;")
        top_row.addWidget(title, stretch=1)

        show_btn = QPushButton("Show me how")
        show_btn.setStyleSheet(
            "QPushButton { color: #92400e; background: transparent; "
            "border: 1px solid #f59e0b; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton:hover { background: #fef3c7; }"
        )
        show_btn.clicked.connect(self.show_me_how_clicked)
        top_row.addWidget(show_btn)
        layout.addLayout(top_row)

        body = QLabel(self.MSG_BODY)
        body_font = QFont()
        body_font.setPointSize(11)
        body.setFont(body_font)
        body.setStyleSheet("color: #92400e;")
        body.setWordWrap(True)
        layout.addWidget(body)


# ---------------------------------------------------------------------------
# State C: ANCS unavailable
# ---------------------------------------------------------------------------

class StateСBanner(QWidget):
    """Thin ANCS-unavailable banner (h=32, lime). Design: tincan-s42 §2 State C."""

    refresh_clicked = Signal()

    MSG = (
        "ℹ Real-time message delivery unavailable (ANCS not connected)"
        " · New messages appear after manual refresh"
        " · Send and conversation list still work."
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "background-color: #f7fee7; border: 1px solid #84cc16;"
        )
        self.setAccessibleName(self.MSG)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)

        label = QLabel(self.MSG)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #365314;")
        layout.addWidget(label, stretch=1)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedWidth(80)
        refresh_btn.setStyleSheet(
            "QPushButton { color: #365314; background: transparent; "
            "border: 1px solid #84cc16; border-radius: 4px; padding: 0 6px; }"
            "QPushButton:hover { background: #ecfccb; }"
        )
        refresh_btn.clicked.connect(self.refresh_clicked)
        layout.addWidget(refresh_btn)
