"""Capability degradation banners: State A (disconnected), B (Show Notifications off), C (push notifications), call setup required."""  # noqa: E501
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtGui import QAccessible, QFont
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.capability_banner import CapabilityBanner

# ---------------------------------------------------------------------------
# State A: Disconnected
# ---------------------------------------------------------------------------

class StateABanner(QWidget):
    """Full-width disconnected banner (h=56, red border). Design: tincan-s42 §2 State A."""

    reconnect_clicked = Signal()

    def __init__(self, last_seen: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            "background-color: #fee2e2; border: 2px solid #ef4444; color: #991b1b;"
        )

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

        accessible_name = QCoreApplication.translate(
            "StateABanner",
            "Connection lost. Activate Reconnect to retry immediately.",
        )
        self.setAccessibleName(accessible_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)

        self._label = QLabel(msg)
        label_font = QFont()
        label_font.setPointSize(12)
        label_font.setBold(True)
        self._label.setFont(label_font)
        self._label.setStyleSheet("color: #991b1b;")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, stretch=1)

        reconnect_btn = QPushButton(
            QCoreApplication.translate("StateABanner", "Reconnect")
        )
        reconnect_btn.setMinimumWidth(100)
        reconnect_btn.setAccessibleName(
            QCoreApplication.translate("StateABanner", "Reconnect")
        )
        reconnect_btn.setStyleSheet(
            "QPushButton { color: #991b1b; background: #ffffff; font-size: 12pt;"
            " border: 1px solid #ef4444; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton:hover { background: #fecaca; }"
            "QPushButton:focus { outline: 2px solid #ef4444; outline-offset: 2px; }"
        )
        reconnect_btn.clicked.connect(self.reconnect_clicked)
        layout.addWidget(reconnect_btn)


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
    """Persistent amber banner: ancs_needs_repair=True FALLBACK state. Design: tincan-kzgk7.5."""

    reconnect_clicked = Signal()

    _BTN_IDLE = "Try to Reconnect"
    _BTN_BUSY = "Reconnecting..."

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.setStyleSheet(
            "background-color: #fff3bf; border: 1px solid #e67700;"
        )
        self.setAccessibleName(self.tr("Bluetooth notifications unavailable"))
        self.setAccessibleDescription(
            self.tr(
                "iPhone notifications are paused."
                " They will resume when your iPhone reconnects over Bluetooth."
                " Activate Try to Reconnect to start reconnecting."
            )
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 8, 8, 8)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        headline = QLabel(self.tr("Bluetooth notifications unavailable"))
        headline_font = QFont()
        headline_font.setPointSize(11)
        headline_font.setBold(True)
        headline.setFont(headline_font)
        headline.setStyleSheet("color: #7c3e00;")
        text_col.addWidget(headline)

        body = QLabel(
            self.tr(
                "iPhone notifications are paused."
                " They will resume when your iPhone reconnects over Bluetooth."
            )
        )
        body_font = QFont()
        body_font.setPointSize(10)
        body.setFont(body_font)
        body.setStyleSheet("color: #7c3e00;")
        body.setWordWrap(True)
        text_col.addWidget(body)

        outer.addLayout(text_col, stretch=1)

        self._reconnect_btn = QPushButton(self.tr(self._BTN_IDLE))
        self._reconnect_btn.setMinimumWidth(140)
        self._reconnect_btn.setStyleSheet(
            "QPushButton { color: #7c3e00; background: #ffffff; font-size: 11pt;"
            " border: 1px solid #e67700; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #fff0b3; }"
            "QPushButton:disabled { color: #a8896b; background: #faf0cc;"
            " border-color: #c9a050; }"
            "QPushButton:focus { outline: 2px solid #e67700; outline-offset: 2px; }"
        )
        self._reconnect_btn.clicked.connect(self.reconnect_clicked)
        outer.addWidget(self._reconnect_btn)

    def set_reconnecting(self, reconnecting: bool) -> None:
        """Switch button between idle and busy states."""
        self._reconnect_btn.setText(
            self.tr(self._BTN_BUSY if reconnecting else self._BTN_IDLE)
        )
        self._reconnect_btn.setEnabled(not reconnecting)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._reconnect_btn.setFocus()


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
# Call setup required banner (h=32, amber) — shown when call_setup_ready=False
# ---------------------------------------------------------------------------

class CallSetupRequiredBanner(QWidget):
    """Slim amber banner shown when the SELinux call module is not installed."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "background-color: #fffbeb; border: 1px solid #fbbf24;"
        )

        msg = self.tr(
            "📞 Phone calls: setup required — "
            "run: cd packaging/selinux && sudo ./install.sh"
        )
        self.setAccessibleName(
            self.tr(
                "Phone call setup required."
                " Run: cd packaging/selinux && sudo ./install.sh"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        label = QLabel(msg)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #92400e;")
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)


# ---------------------------------------------------------------------------
# Accessible role factory — StateBBanner + StateCBanner → AlertMessage
# (StateABanner inherits CapabilityBanner and is already covered by its factory)
# ---------------------------------------------------------------------------

def _degradation_banner_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, StateABanner):
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    if isinstance(obj, StateBBanner):
        # State B = urgent: MAP link dropped, messaging broken
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    if isinstance(obj, ANCSRepairBanner):
        # ANCS repair = urgent: authorization lost, reconnect required
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    if isinstance(obj, StateCBanner):
        # State C = informational: ANCS missing, send still works (tincan-5en)
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    if isinstance(obj, CallSetupRequiredBanner):
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    return None


QAccessible.installFactory(_degradation_banner_factory)


# ---------------------------------------------------------------------------
# Adapter unavailable banner (tincan-crfu9)
# ---------------------------------------------------------------------------

class AdapterUnavailableBanner(QFrame):
    """Full-width banner shown when the daemon fell back to a different BT adapter.

    Populated by update_paths(); shown/hidden by MainWindow._refresh_adapter_unavailable_banner().
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "AdapterUnavailableBanner { background: #422006; border-bottom: 1px solid #d97706; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.setSpacing(2)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)

        self._primary_label = QLabel()
        self._primary_label.setTextFormat(Qt.TextFormat.PlainText)
        pf = QFont()
        pf.setPointSize(12)
        self._primary_label.setFont(pf)
        self._primary_label.setStyleSheet("color: #fbbf24;")
        self._primary_label.setWordWrap(True)
        primary_row.addWidget(self._primary_label, stretch=1)

        self._dismiss_btn = QToolButton()
        self._dismiss_btn.setText("✕")
        self._dismiss_btn.setToolTip("Dismiss adapter warning")
        self._dismiss_btn.setAccessibleName("Dismiss adapter warning")
        self._dismiss_btn.setStyleSheet(
            "QToolButton { color: #d97706; border: none; background: transparent; }"
        )
        primary_row.addWidget(self._dismiss_btn, alignment=Qt.AlignmentFlag.AlignTop)

        outer.addLayout(primary_row)

        self._hint_label = QLabel("Change adapter in Settings → Bluetooth")
        hf = QFont()
        hf.setPointSize(11)
        self._hint_label.setFont(hf)
        self._hint_label.setStyleSheet("color: #78716c;")
        outer.addWidget(self._hint_label)

    def update_paths(self, adapter_path_requested: str, adapter_path: str) -> None:
        """Set the banner text to name both the unavailable and actual adapters."""
        self._primary_label.setText(
            f"⚠ Saved adapter {adapter_path_requested} was unavailable"
            f" — using {adapter_path} instead."
        )


# ---------------------------------------------------------------------------
# Adapter mismatch banner (tincan-5y8km.2)
# ---------------------------------------------------------------------------

class AdapterMismatchBanner(QFrame):
    """Persistent amber banner shown when iPhone is on the wrong Bluetooth adapter.

    Not dismissible — the mismatch is a hardware state that clears when the
    operator reconnects the iPhone to the correct adapter.
    Shown/hidden by MainWindow._refresh_adapter_mismatch_banner().
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "AdapterMismatchBanner { background: #fff3bf; border-bottom: 2px solid #f59f00; }"
        )
        self.setAccessibleName("adapter mismatch warning")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        icon = QLabel("⚠")
        icon.setAccessibleName("adapter mismatch warning")
        icon.setStyleSheet("color: #7c4f00; font-size: 16pt;")
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        self._label = QLabel()
        lf = QFont()
        lf.setPointSize(12)
        self._label.setFont(lf)
        self._label.setStyleSheet("color: #7c4f00;")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, stretch=1)

    def update_warning(self, text: str) -> None:
        """Set the warning text verbatim (plain text from adapter_warning field)."""
        self._label.setText(text)
        self.setAccessibleDescription(text)


def _adapter_mismatch_banner_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, AdapterMismatchBanner):
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    return None


QAccessible.installFactory(_adapter_mismatch_banner_factory)
