"""Capability degradation banners: State A (disconnected), B (Show Notifications off), C (push notifications)."""  # noqa: E501
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtGui import QAccessible, QFont
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.capability_banner import CapabilityBanner

# ---------------------------------------------------------------------------
# State A: Disconnected — inherits CapabilityBanner → AlertMessage role via factory
# ---------------------------------------------------------------------------

class StateABanner(CapabilityBanner):
    """Full-width disconnected banner (h=56, red border). Design: tincan-s42 §2 State A."""

    def __init__(self, last_seen: str = "", parent: Optional[QWidget] = None) -> None:
        if not last_seen:
            msg = QCoreApplication.translate(
                "StateABanner",
                "⊗ Connection lost — Bluetooth out of range"
                " · Showing cached conversations · reconnecting…",
            )
        else:
            msg = QCoreApplication.translate(
                "StateABanner",
                "⊗ Connection lost — last seen {last_seen}"
                " · Bluetooth out of range · reconnecting…",
            ).format(last_seen=last_seen)
        super().__init__(message=msg, parent=parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            "background-color: #fee2e2; border: 2px solid #ef4444; color: #991b1b;"
        )
        _font = QFont()
        _font.setPointSize(12)
        _font.setBold(True)
        self._label.setFont(_font)


# ---------------------------------------------------------------------------
# State B: Show Notifications off
# ---------------------------------------------------------------------------

class StateBBanner(QWidget):
    """Messaging unavailable banner (h=80, amber). Design: tincan-s42 §2 State B."""

    show_me_how_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet(
            "background-color: #fffbeb; border: 1px solid #f59e0b;"
        )

        msg_title = self.tr("⚠ Messaging unavailable")
        msg_body = self.tr(
            "Enable 'Show Notifications' on iPhone:"
            " Settings → Bluetooth → [device] → Show Notifications"
        )
        self.setAccessibleName(f"{msg_title} — {msg_body}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel(msg_title)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #92400e;")
        top_row.addWidget(title, stretch=1)

        show_btn = QPushButton(self.tr("Show me how"))
        show_btn.setStyleSheet(
            "QPushButton { color: #92400e; background: transparent; "
            "border: 1px solid #f59e0b; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton:hover { background: #fef3c7; }"
        )
        show_btn.clicked.connect(self.show_me_how_clicked)
        top_row.addWidget(show_btn)
        layout.addLayout(top_row)

        body = QLabel(msg_body)
        body_font = QFont()
        body_font.setPointSize(11)
        body.setFont(body_font)
        body.setStyleSheet("color: #92400e;")
        body.setWordWrap(True)
        layout.addWidget(body)


# ---------------------------------------------------------------------------
# ANCS Repair: authorization lost — FALLBACK state (tincan-5mze)
# ---------------------------------------------------------------------------

class ANCSRepairBanner(QWidget):
    """Persistent orange banner: ancs_needs_repair=True FALLBACK state (h=56, orange). Design: tincan-5mze.3."""  # noqa: E501

    reconnect_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            "background-color: #fff7ed; border: 1px solid #f97316;"
        )

        msg = self.tr(
            "iPhone notifications unavailable - authorization lost,"
            " tap Reconnect to restore"
        )
        accessible_name = self.tr(
            "iPhone notifications unavailable - authorization lost."
            " Activate Reconnect to restore."
        )
        self.setAccessibleName(accessible_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)

        label = QLabel(msg)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #c2410c;")
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)

        reconnect_btn = QPushButton(self.tr("Reconnect..."))
        reconnect_btn.setMinimumWidth(100)
        reconnect_btn.setAccessibleName(self.tr("Reconnect"))
        reconnect_btn.setStyleSheet(
            "QPushButton { color: #c2410c; background: #ffffff; font-size: 12pt;"
            " border: 1px solid #f97316; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton:hover { background: #ffedd5; }"
            "QPushButton:focus { outline: 2px solid #f97316; outline-offset: 2px; }"
        )
        reconnect_btn.clicked.connect(self.reconnect_clicked)
        layout.addWidget(reconnect_btn)


# ---------------------------------------------------------------------------
# State C: ANCS unavailable
# ---------------------------------------------------------------------------

class StateCBanner(QWidget):
    """Thin ANCS-unavailable banner (h=32, lime). Design: tincan-s42 §2 State C."""

    refresh_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "background-color: #f7fee7; border: 1px solid #84cc16;"
        )

        # tincan-5en: accessible name uses plain-text form per spec §5
        msg = self.tr(
            "ℹ Real-time push notifications unavailable"
            " · New messages appear after manual refresh."
            " · Send and conversation list still work."
        )
        accessible_name = self.tr(
            "Real-time push notifications unavailable."
            " New messages appear after manual refresh."
            " Send and conversation list still work."
        )
        self.setAccessibleName(accessible_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)

        label = QLabel(msg)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #365314;")
        layout.addWidget(label, stretch=1)

        refresh_btn = QPushButton(self.tr("↻ Refresh"))
        refresh_btn.setFixedWidth(80)
        refresh_btn.setStyleSheet(
            "QPushButton { color: #365314; background: transparent; "
            "border: 1px solid #84cc16; border-radius: 4px; padding: 0 6px; }"
            "QPushButton:hover { background: #ecfccb; }"
        )
        refresh_btn.clicked.connect(self.refresh_clicked)
        layout.addWidget(refresh_btn)


# ---------------------------------------------------------------------------
# Contacts-empty hint (tincan-d3xw)
# ---------------------------------------------------------------------------

class ContactsEmptyBanner(QWidget):
    """Slim informational banner shown when PBAP loads 0 contacts (h=32, blue)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #93c5fd;"
        )

        msg = self.tr(
            "ℹ No contacts loaded — on iPhone: Settings › Bluetooth › "
            "[device] › Sync Contacts"
        )
        accessible_name = self.tr(
            "No contacts loaded."
            " To see contact names, enable Sync Contacts in iPhone Settings,"
            " Bluetooth, then tap your device name."
        )
        self.setAccessibleName(accessible_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        label = QLabel(msg)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #1e40af;")
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)


# ---------------------------------------------------------------------------
# Accessible role factory — StateBBanner + StateCBanner → AlertMessage
# (StateABanner inherits CapabilityBanner and is already covered by its factory)
# ---------------------------------------------------------------------------

def _degradation_banner_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, StateBBanner):
        # State B = urgent: MAP link dropped, messaging broken
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    if isinstance(obj, ANCSRepairBanner):
        # ANCS repair = urgent: authorization lost, reconnect required
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    if isinstance(obj, StateCBanner):
        # State C = informational: ANCS missing, send still works (tincan-5en)
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    return None


QAccessible.installFactory(_degradation_banner_factory)
