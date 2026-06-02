"""5-step onboarding wizard per tincan-s42 §2 Screen 3."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

# ---------------------------------------------------------------------------
# Base wizard page
# ---------------------------------------------------------------------------

class _TincanPage(QWizardPage):
    """Base page with navy header (title bar color) unless overridden."""

    _HEADER_COLOR = "#1e3a5f"
    _HEADER_TEXT = "#ffffff"

    def __init__(self, step: int, total: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step = step
        self._total = total
        # setTitle() is announced by screen readers as "Step N of 5 — <title>"
        # The wizard page title is set by each subclass via setTitle()/setSubTitle().

    def _make_body_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        font = QFont()
        font.setPointSize(12)
        label.setFont(font)
        return label


# ---------------------------------------------------------------------------
# Step 1: Welcome
# ---------------------------------------------------------------------------

class WelcomePage(_TincanPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(step=1, total=5, parent=parent)
        self.setTitle("Step 1 of 5 — Welcome")
        layout = QVBoxLayout(self)

        heading = QLabel("Welcome to tincan")
        hf = QFont()
        hf.setPointSize(18)
        hf.setBold(True)
        heading.setFont(hf)
        layout.addWidget(heading)

        layout.addWidget(self._make_body_label(
            "tincan lets you send and receive SMS messages, answer calls, "
            "and mirror notifications from your iPhone — all from your desktop, "
            "over standard Bluetooth. No jailbreak required."
        ))
        layout.addWidget(self._make_body_label(
            "Prerequisites: iPhone paired with this computer over Bluetooth."
        ))
        layout.addStretch()


# ---------------------------------------------------------------------------
# Step 2: Detect Bluetooth
# ---------------------------------------------------------------------------

class DetectBluetoothPage(_TincanPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(step=2, total=5, parent=parent)
        self.setTitle("Step 2 of 5 — Detect Bluetooth")
        layout = QVBoxLayout(self)
        layout.addWidget(self._make_body_label("Scanning for Bluetooth adapter…"))

        self._adapter_label = QLabel("Adapter: (scanning)")
        af = QFont()
        af.setPointSize(12)
        self._adapter_label.setFont(af)
        self._adapter_label.setStyleSheet("color: #374151;")
        layout.addWidget(self._adapter_label)

        self._ble_label = QLabel("BLE: unknown  ·  Classic: unknown")
        self._ble_label.setFont(af)
        self._ble_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self._ble_label)

        layout.addWidget(self._make_body_label(
            "Note: simultaneous BLE (ANCS) + Classic (MAP) is verified during "
            "Phase-0 spikes. If your adapter cannot hold both links, "
            "real-time message delivery may not be available."
        ))
        layout.addStretch()

    def update_adapter(self, model: str, ble: bool, classic: bool) -> None:
        self._adapter_label.setText(f"Adapter: {model}")
        self._ble_label.setText(
            f"BLE: {'✓' if ble else '✗'}  ·  Classic: {'✓' if classic else '✗'}"
        )


# ---------------------------------------------------------------------------
# Step 3: Pair iPhone
# ---------------------------------------------------------------------------

class PairIPhonePage(_TincanPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(step=3, total=5, parent=parent)
        self.setTitle("Step 3 of 5 — Pair iPhone")
        layout = QVBoxLayout(self)
        layout.addWidget(self._make_body_label(
            "1. On your iPhone, go to Settings → Bluetooth.\n"
            "2. Your computer should appear in the list. Tap it.\n"
            "3. Confirm the pairing code matches the one shown below."
        ))

        self._pin_label = QLabel("")
        pin_font = QFont()
        pin_font.setPointSize(28)
        pin_font.setBold(True)
        self._pin_label.setFont(pin_font)
        self._pin_label.setAlignment(Qt.AlignCenter)
        self._pin_label.setStyleSheet("letter-spacing: 8px; color: #111827;")
        layout.addWidget(self._pin_label)

        layout.addWidget(self._make_body_label(
            "This page advances automatically when the iPhone confirms pairing."
        ))
        layout.addStretch()

    def show_pin(self, pin: str) -> None:
        """Display pairing PIN; sets accessible name digit-by-digit."""
        self._pin_label.setText(pin)
        spaced = " ".join(list(pin))
        self._pin_label.setAccessibleName(f"Pairing code: {spaced}")


# ---------------------------------------------------------------------------
# Step 4: Show Notifications (amber header — required user action)
# ---------------------------------------------------------------------------

class ShowNotificationsPage(_TincanPage):
    """Step 4 uses dark amber header instead of navy to signal required action."""

    _HEADER_COLOR = "#92400e"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(step=4, total=5, parent=parent)
        self.setTitle("Step 4 of 5 — Show Notifications ⚠")
        layout = QVBoxLayout(self)

        amber_header = QWidget()
        amber_header.setStyleSheet(f"background-color: {self._HEADER_COLOR}; border-radius: 4px;")
        amber_layout = QVBoxLayout(amber_header)
        amber_layout.setContentsMargins(12, 8, 12, 8)
        amber_text = QLabel("⚠ Action required on your iPhone")
        atf = QFont()
        atf.setPointSize(14)
        atf.setBold(True)
        amber_text.setFont(atf)
        amber_text.setStyleSheet("color: #ffffff;")
        amber_layout.addWidget(amber_text)
        layout.addWidget(amber_header)

        layout.addWidget(self._make_body_label(
            "tincan needs 'Show Notifications' enabled to access messages:\n\n"
            "Settings → Bluetooth → [your computer] → Show Notifications → Enable\n\n"
            "This page advances automatically when the setting is detected."
        ))
        layout.addStretch()


# ---------------------------------------------------------------------------
# Step 5: Connected!
# ---------------------------------------------------------------------------

class ConnectedPage(_TincanPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(step=5, total=5, parent=parent)
        self.setTitle("Step 5 of 5 — Connected!")
        layout = QVBoxLayout(self)

        heading = QLabel("You're connected!")
        hf = QFont()
        hf.setPointSize(18)
        hf.setBold(True)
        heading.setFont(hf)
        heading.setStyleSheet("color: #065f46;")
        layout.addWidget(heading)

        layout.addWidget(self._make_body_label("Capability summary:"))
        self._summary_layout = QVBoxLayout()
        layout.addLayout(self._summary_layout)
        layout.addStretch()

    _CAPABILITY_LABELS = {
        "messages": ("Messages", "Messages (unavailable)"),
        "contacts": ("Contacts", "Contacts (unavailable)"),
        "ancs": ("Push notifications", "Push notifications (not yet active)"),
    }

    def set_capabilities(self, capabilities: dict[str, bool]) -> None:
        while self._summary_layout.count():
            item = self._summary_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for feature, ok in capabilities.items():
            ok_label, warn_label = self._CAPABILITY_LABELS.get(
                feature, (feature.capitalize(), f"{feature.capitalize()} (unavailable)")
            )
            icon = "✓" if ok else "⚠"
            text = ok_label if ok else warn_label
            color = "#065f46" if ok else "#92400e"
            label = QLabel(f"{icon}  {text}")
            font = QFont()
            font.setPointSize(12)
            label.setFont(font)
            label.setStyleSheet(f"color: {color};")
            self._summary_layout.addWidget(label)


# ---------------------------------------------------------------------------
# Main Wizard
# ---------------------------------------------------------------------------

class OnboardingWizard(QWizard):
    """5-step onboarding wizard per tincan-s42 §2 Screen 3."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("tincan — Setup")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(600, 420)

        self.welcome_page = WelcomePage()
        self.detect_bt_page = DetectBluetoothPage()
        self.pair_page = PairIPhonePage()
        self.show_notif_page = ShowNotificationsPage()
        self.connected_page = ConnectedPage()

        for page in (
            self.welcome_page,
            self.detect_bt_page,
            self.pair_page,
            self.show_notif_page,
            self.connected_page,
        ):
            self.addPage(page)

        # Step 4: block Next until CapabilityChanged("messages", true) received
        # Wired in tincan-mgc. For now, allow advancing.

    def advance_to_step(self, step: int) -> None:
        """Programmatically advance to a step (1-indexed). Used by D-Bus handlers."""
        while self.currentId() < step - 1:
            self.next()
