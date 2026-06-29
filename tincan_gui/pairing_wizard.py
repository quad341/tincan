"""tincan_gui/pairing_wizard.py — PySide6 pairing wizard for dual-mode ANCS+MAP onboarding."""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from tincand.pairing import FailureReason, PairingState


class _DetectBadge(QLabel):
    """Inline chip showing per-step detection mode (tincan-p7cf2)."""

    _STYLES: dict[str, tuple[str, str, str]] = {
        "AUTO":    ("#14532d", "#f0fdf4", "✓ AUTO"),
        "DONE":    ("#14532d", "#f0fdf4", "✓ AUTO"),
        "PENDING": ("#92400e", "#fffbeb", "⟳ DETECTING…"),
        "IOS":     ("#1e3a5f", "#eff6ff", "📱 iOS STEP"),
    }
    _ACCESSIBLE: dict[str, str] = {
        "AUTO":    "Detection mode: automatic",
        "DONE":    "Detection mode: automatic",
        "PENDING": "Detection mode: detecting…",
        "IOS":     "Detection mode: manual iOS step required",
    }

    def __init__(self, mode: str = "AUTO", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._set_mode(mode)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedHeight(22)

    def _set_mode(self, mode: str) -> None:
        bg, fg, text = self._STYLES.get(mode, self._STYLES["AUTO"])
        self.setText(text)
        self.setAccessibleName(self._ACCESSIBLE.get(mode, "Detection mode: automatic"))
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-size: 11px; "
            f"padding: 2px 8px; border-radius: 3px;"
        )


class _WizardPage(QWizardPage):
    """Base: state-driven wizard page — no automatic next."""

    def nextId(self) -> int:
        return -1

    def _heading(self, text: str, color: str = "#111827") -> QLabel:
        label = QLabel(text)
        font = QFont()
        font.setPointSize(17)
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(f"color: {color};")
        label.setWordWrap(True)
        return label

    def _body(self, text: str) -> QLabel:
        label = QLabel(text)
        font = QFont()
        font.setPointSize(13)
        label.setFont(font)
        label.setStyleSheet("color: #374151;")
        label.setWordWrap(True)
        return label

    def _progress(self, step: int, total: int = 8, color: str = "#0d9488") -> QProgressBar:
        bar = QProgressBar()
        bar.setMaximum(total)
        bar.setValue(step)
        bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
        bar.setAccessibleName(self.tr("Step {step} of {total}").format(step=step, total=total))
        return bar


# ---------------------------------------------------------------------------
# Step pages (auto-advance, no user action required)
# ---------------------------------------------------------------------------


class _WelcomePage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("AUTO"))
        layout.addWidget(self._heading("Connect your iPhone"))
        self._body_label = self._body(
            "This wizard sets up your iPhone to send and receive text messages "
            "from your desktop. Takes about 2 minutes."
        )
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _AdapterCard(QWidget):
    """Inline card showing Bluetooth adapter capability state (tincan-06knm)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self._alias_label = QLabel()
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._retry_button = QPushButton("Retry")
        self._retry_button.setVisible(False)
        self._retry_button.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: white; "
            "font-size: 13pt; min-height: 36px; border-radius: 4px; }"
        )
        layout.addWidget(self._alias_label)
        layout.addWidget(self._status_label)
        layout.addWidget(self._retry_button)

    @property
    def retry_button(self) -> QPushButton:
        return self._retry_button

    def set_scanning(self) -> None:
        self._alias_label.setText("")
        self._status_label.setText("⟳ Looking for a Bluetooth adapter…")
        self._retry_button.setVisible(False)
        self.setStyleSheet("background-color: #f3f4f6; border-radius: 6px;")

    def configure(
        self,
        alias: str,
        *,
        le_capable: bool,
        hfp_sco_capable: bool,
        recommended: bool = False,
    ) -> None:
        self._retry_button.setVisible(False)
        if not le_capable:
            self._alias_label.setText("")
            self._status_label.setText(
                "✗ No Bluetooth adapter found.\n"
                "Plug in a Bluetooth USB adapter and try again."
            )
            self._retry_button.setVisible(True)
            self.setStyleSheet(
                "background-color: #fee2e2; border: 1px solid #dc2626; border-radius: 6px;"
            )
        elif le_capable and hfp_sco_capable:
            self._alias_label.setText(f"✓ {alias}")
            self._status_label.setText(
                "Supports ANCS notifications, messages, and phone calls. "
                "All tincan features available."
            )
            self.setStyleSheet(
                "background-color: #dcfce7; border: 1px solid #14532d; border-radius: 6px;"
            )
        else:
            self._alias_label.setText(f"⚠ {alias}")
            self._status_label.setText(
                "This adapter supports messages (MAP) but may not support "
                "ANCS push notifications or HFP phone calls.\n\n"
                "For full feature support (ANCS notifications + phone calls), we recommend "
                "the ASUS USB-BT500 (RTL8761B). Fully tested with tincan on Fedora 44: "
                "messages, ANCS, HFP call control, and SCO audio all verified."
            )
            self.setStyleSheet(
                "background-color: #fef9c3; border: 1px solid #92400e; border-radius: 6px;"
            )


class _AdapterCapabilityPage(_WizardPage):
    """Step 1: scan for Bluetooth adapter capability (replaces _CheckingAdapterPage)."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 1 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("AUTO"))
        layout.addWidget(self._progress(1))
        layout.addWidget(self._heading("Checking Bluetooth…"))
        self.adapter_card = _AdapterCard()
        self.adapter_card.set_scanning()
        layout.addWidget(self.adapter_card)
        layout.addStretch()

    def text(self) -> str:
        return self.adapter_card._status_label.text()


class _AdvertisingPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 2 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("PENDING"))
        layout.addWidget(self._progress(2))
        layout.addWidget(self._heading("Open Bluetooth on your iPhone"))
        self._body_label = self._body(
            "On your iPhone: Settings → Bluetooth. Turn on Bluetooth.\n\n"
            'Your iPhone will show "tincan" under Other Devices — tap it to continue.'
        )
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _WaitingForPairPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 3 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("AUTO"))
        layout.addWidget(self._progress(3))
        layout.addWidget(self._heading("Tap 'Pair' on your iPhone"))
        self._body_label = self._body(
            "A pairing request will appear on your iPhone. Tap Pair to connect."
        )
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _VerifyingAncsPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 5 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("PENDING"))
        layout.addWidget(self._progress(5))
        layout.addWidget(self._heading("Checking notifications…"))
        self._body_label = self._body("Confirming that notifications are working.")
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _MapSessionPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 6 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("AUTO"))
        layout.addWidget(self._progress(6))
        layout.addWidget(self._heading("Setting up message access…"))
        self._body_label = self._body("Preparing to access your messages.")
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _VerifyingMapPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 7 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("AUTO"))
        layout.addWidget(self._progress(7))
        layout.addWidget(self._heading("Checking message access…"))
        self._body_label = self._body("Confirming that message access is working.")
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


# ---------------------------------------------------------------------------
# User-action pages (exported — referenced from tests)
# ---------------------------------------------------------------------------


class MapConsentPage(_WizardPage):
    """Screen 7: user taps Allow on iPhone then clicks Continue here."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 6 of 8")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("IOS"))
        layout.addWidget(self._progress(6))
        layout.addWidget(self._heading("Allow message access on your iPhone"))
        self._body_label = self._body(
            "Your iPhone will show a prompt asking to allow message access.\n\n"
            "1. On your iPhone, look for a notification or popup titled "
            '"iPhone Wants to Access Your Messages".\n'
            "2. Tap Allow.\n\n"
            "Can't see the prompt? Settings → Privacy & Security → Contacts — "
            "Find tincan in the list and tap Allow."
        )
        layout.addWidget(self._body_label)

        self.continue_button = QPushButton("Continue →")
        self.continue_button.setAccessibleName(
            self.tr("Continue — confirm message access granted")
        )
        self.continue_button.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: white; "
            "font-size: 14pt; min-height: 44px; border-radius: 4px; }"
        )
        layout.addWidget(self.continue_button)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class SuccessPage(_WizardPage):
    """Screen 9: setup complete."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Complete!")
        layout = QVBoxLayout(self)
        layout.addWidget(_DetectBadge("DONE"))
        bar = self._progress(8, color="#16a34a")
        bar.setAccessibleName(self.tr("Setup complete"))
        layout.addWidget(bar)
        layout.addWidget(self._heading("You're all set!", color="#16a34a"))
        self._body_label = self._body(
            "Your iPhone is connected. Text messages will appear in tincan.\n\n"
            "✓ Notifications active\n"
            "✓ Message access granted"
        )
        layout.addWidget(self._body_label)
        start_btn = QPushButton("Start using tincan →")
        start_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; "
            "font-size: 14pt; min-height: 44px; border-radius: 4px; }"
        )
        layout.addWidget(start_btn)
        layout.addStretch()

    def set_partial(self, *, ancs: bool) -> None:
        if not ancs:
            self._body_label.setText(
                "Your iPhone is connected. Text messages will appear in tincan.\n\n"
                "⚠ Notifications unavailable\n"
                "✓ Message access granted"
            )

    def text(self) -> str:
        return f"You're all set! {self._body_label.text()}"


_FAILURE_CONTENT: dict[str, tuple[str, str]] = {
    FailureReason.ADAPTER_NOT_CAPABLE: (
        "No Bluetooth adapter found",
        "tincan couldn't find a Bluetooth adapter on this computer.\n\n"
        "Plug in a Bluetooth USB adapter and try again.",
    ),
    FailureReason.ADVERTISING_FAILED: (
        "Bluetooth advertising failed",
        "tincan couldn't start Bluetooth advertising.\n\n"
        "Try restarting Bluetooth or plug in a USB Bluetooth adapter and try again.",
    ),
    FailureReason.ANCS_EXT_ADV_BUG: (
        "Advertising failed — BlueZ bug",
        "Push notifications are unavailable. Your BlueZ version (≤ 5.86) has a known "
        "extended-advertising bug.\n\n"
        "🔧 Apply the ext-adv patch in docs/ancs-bluez-ext-adv-rootcause.md.\n\n"
        "✓ SMS messages still work without ANCS.",
    ),
    FailureReason.ANCS_EXPERIMENTAL_REQUIRED: (
        "Experimental features required",
        "ANCS notifications need bluetoothd --experimental.\n\n"
        "🔧 Edit /etc/bluetooth/main.conf → add ExperimentalFeatures = true\n"
        "    sudo systemctl restart bluetooth\n\n"
        "✓ SMS messages still work while you fix this.",
    ),
    FailureReason.PAIR_TIMEOUT: (
        "Pairing timed out",
        "Your iPhone didn't respond in time.\n\n"
        "Make sure Bluetooth is on and 'tincan' appears in Other Devices "
        "on your iPhone, then try again.",
    ),
    FailureReason.ANCS_NOT_EXPOSED: (
        "Notifications not allowed",
        "Your iPhone did not grant notification access.\n\n"
        "On your iPhone:\n"
        "  Settings → Bluetooth → tap ⓘ next to {computer_name}\n"
        "  Enable Show Notifications\n\n"
        "Then tap Try again.",
    ),
    FailureReason.MAP_CONSENT_DENIED: (
        "Message access denied",
        "Your iPhone did not grant access to your messages.\n\n"
        "On your iPhone:\n"
        "  Settings → Privacy & Security → Contacts → tincan\n"
        "  Tap Allow\n\n"
        "Then tap Try again.",
    ),
}

_DEFAULT_FAILURE = (
    "Connection failed",
    "Something went wrong connecting your iPhone. Please try again.",
)


class FailurePage(_WizardPage):
    """Screen 10: failure/retry — variant text per FailureReason."""

    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Connection failed")
        layout = QVBoxLayout(self)

        self._heading_label = self._heading("Connection failed", color="#dc2626")
        layout.addWidget(self._heading_label)
        self._body_label = self._body("")
        layout.addWidget(self._body_label)
        layout.addStretch()

        self.retry_button = QPushButton("Try again")
        self.retry_button.setAccessibleName(self.tr("Try again — restart the setup wizard"))
        self.retry_button.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: white; "
            "font-size: 14pt; min-height: 44px; border-radius: 4px; }"
        )
        layout.addWidget(self.retry_button)

        self.cancel_button = QPushButton("Close")
        self.cancel_button.setAccessibleName(self.tr("Close the setup wizard"))
        self.cancel_button.setStyleSheet(
            "QPushButton { background-color: #f9fafb; color: #374151; "
            "font-size: 14pt; min-height: 44px; border-radius: 4px; "
            "border: 1px solid #9ca3af; }"
        )
        layout.addWidget(self.cancel_button)

        self.continue_partial = QPushButton("Continue without notifications")
        self.continue_partial.setAccessibleName(
            self.tr("Continue without notifications — set up messaging only")
        )
        self.continue_partial.setStyleSheet(
            "QPushButton { background-color: #3f3f46; color: #a1a1aa; "
            "font-size: 14pt; min-height: 44px; border-radius: 4px; }"
        )
        self.continue_partial.setVisible(False)
        layout.addWidget(self.continue_partial)

    _ANCS_PARTIAL_REASONS = frozenset({
        FailureReason.ANCS_EXT_ADV_BUG,
        FailureReason.ANCS_EXPERIMENTAL_REQUIRED,
    })

    def configure(self, reason: str | None, *, computer_name: str = "your computer") -> None:
        heading, body = _FAILURE_CONTENT.get(reason or "", _DEFAULT_FAILURE)
        self._heading_label.setText(heading)
        self._body_label.setText(body.format(computer_name=computer_name))
        self.continue_partial.setVisible(reason in self._ANCS_PARTIAL_REASONS)

    def text(self) -> str:
        return f"{self._heading_label.text()} {self._body_label.text()}"


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------


class PairingWizard(QWizard):
    """PySide6 wizard for dual-mode ANCS+MAP iPhone pairing (tincan-f1nu).

    Accepts a PairingOrchestrator and navigates between pages as the
    orchestrator emits state changes. No pairing logic lives here.
    """

    def __init__(self, orchestrator, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator
        self.setWindowTitle("Set up your iPhone")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(600, 480)

        self._welcome_page = _WelcomePage()
        self._adapter_capability_page = _AdapterCapabilityPage()
        self._advertising_page = _AdvertisingPage()
        self._waiting_for_pair_page = _WaitingForPairPage()
        self._verifying_ancs_page = _VerifyingAncsPage()
        self._map_session_page = _MapSessionPage()
        self.map_consent_page = MapConsentPage()
        self._verifying_map_page = _VerifyingMapPage()
        self.success_page = SuccessPage()
        self.failure_page = FailurePage()

        self._page_ids: dict[QWizardPage, int] = {}
        for page in (
            self._welcome_page,
            self._adapter_capability_page,
            self._advertising_page,
            self._waiting_for_pair_page,
            self._verifying_ancs_page,
            self._map_session_page,
            self.map_consent_page,
            self._verifying_map_page,
            self.success_page,
            self.failure_page,
        ):
            self._page_ids[page] = self.addPage(page)

        self._state_page: dict[str, QWizardPage] = {
            PairingState.CHECKING_ADAPTER: self._adapter_capability_page,
            PairingState.ADVERTISING: self._advertising_page,
            PairingState.WAITING_FOR_PAIR: self._waiting_for_pair_page,
            PairingState.VERIFYING_ANCS: self._verifying_ancs_page,
            PairingState.MAP_SESSION: self._map_session_page,
            PairingState.MAP_CONSENT_PROMPT: self.map_consent_page,
            PairingState.VERIFYING_MAP: self._verifying_map_page,
            PairingState.SUCCESS: self.success_page,
        }

        self.map_consent_page.continue_button.clicked.connect(self._on_map_consent_continue)
        self.failure_page.continue_partial.clicked.connect(
            lambda: self.accept_partial(ancs=False)
        )

    def accept_partial(self, *, ancs: bool) -> None:
        """Close the wizard and signal partial success (e.g. messaging-only, no notifications)."""
        self.success_page.set_partial(ancs=ancs)
        self.setCurrentId(self._page_ids[self.success_page])

    def _on_map_consent_continue(self) -> None:
        self._orchestrator.signal_map_consent()

    def _on_orchestrator_state_change(self, state: str, reason: str | None = None) -> None:
        if state == PairingState.FAILED:
            self.failure_page.configure(reason)
            self.setCurrentId(self._page_ids[self.failure_page])
        elif state in self._state_page:
            self.setCurrentId(self._page_ids[self._state_page[state]])
