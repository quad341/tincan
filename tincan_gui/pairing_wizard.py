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


# ---------------------------------------------------------------------------
# _DetectBadge — per-page detection mode chip
# ---------------------------------------------------------------------------

class _DetectBadge(QLabel):
    """Inline chip showing the current detection mode for a wizard step.

    Modes:
      AUTO    — automatic detection active (green)
      PENDING — detection in progress (amber)
      IOS     — manual iOS step required (navy)
      DONE    — detection complete (same as AUTO)
    """

    _STYLES: dict[str, tuple[str, str, str | None]] = {
        # mode: (text, stylesheet, accessibleName or None)
        "AUTO": (
            "✓ AUTO",
            "background-color: #14532d; color: #f0fdf4; "
            "font-size: 11px; padding: 2px 8px; border-radius: 3px;",
            "Detection mode: automatic",
        ),
        "PENDING": (
            "⟳ DETECTING…",
            "background-color: #92400e; color: #fffbeb; "
            "font-size: 11px; padding: 2px 8px; border-radius: 3px;",
            None,
        ),
        "IOS": (
            "📱 iOS STEP",
            "background-color: #1e3a5f; color: #eff6ff; "
            "font-size: 11px; padding: 2px 8px; border-radius: 3px;",
            "Detection mode: manual iOS step required",
        ),
        "DONE": (
            "✓ AUTO",
            "background-color: #14532d; color: #f0fdf4; "
            "font-size: 11px; padding: 2px 8px; border-radius: 3px;",
            None,
        ),
    }

    def __init__(self, mode: str = "AUTO", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        text, style, accessible = self._STYLES.get(mode, self._STYLES["AUTO"])
        self.setText(text)
        self.setStyleSheet(style)
        if accessible:
            self.setAccessibleName(accessible)


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
        layout.addWidget(self._heading("Connect your iPhone"))
        self._body_label = self._body(
            "This wizard sets up your iPhone to send and receive text messages "
            "from your desktop. Takes about 2 minutes."
        )
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _CheckingAdapterPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 1 of 8")
        layout = QVBoxLayout(self)
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
        layout.addWidget(self._progress(1))
        layout.addWidget(self._heading("Checking Bluetooth…"))
        self._body_label = self._body(
            "Making sure a Bluetooth adapter is available on this computer."
        )
        layout.addWidget(self._body_label)
        layout.addStretch()

    def text(self) -> str:
        return self._body_label.text()


class _AdvertisingPage(_WizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Set up your iPhone  ·  Step 2 of 8")
        layout = QVBoxLayout(self)
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
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
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
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
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
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
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
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
        self.detect_badge = _DetectBadge("AUTO")
        layout.addWidget(self.detect_badge)
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
        self.detect_badge = _DetectBadge("IOS")
        layout.addWidget(self.detect_badge)
        layout.addWidget(self._progress(6))
        layout.addWidget(self._heading("Allow message access on your iPhone"))
        self._body_label = self._body(
            "Your iPhone is asking to share your messages. On your iPhone, tap Allow to continue."
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

    def text(self) -> str:
        return f"You're all set! {self._body_label.text()}"


_FAILURE_CONTENT: dict[str, tuple[str, str]] = {
    FailureReason.ADAPTER_NOT_CAPABLE: (
        "No Bluetooth adapter found",
        "tincan couldn't find a Bluetooth adapter on this computer.\n\n"
        "Plug in a Bluetooth USB adapter and try again.",
    ),
    FailureReason.ADVERTISING_FAILED: (
        "No Bluetooth adapter found",
        "tincan couldn't find a Bluetooth adapter on this computer.\n\n"
        "Plug in a Bluetooth USB adapter and try again.",
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
        "To fix this on your iPhone: Settings → Bluetooth → tincan\n\n"
        "Then try again.",
    ),
    FailureReason.MAP_CONSENT_DENIED: (
        "Message access denied",
        "Your iPhone did not grant access to your messages.\n\n"
        "To fix this on your iPhone: Settings → Privacy → Contacts\n\n"
        "Then try again.",
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

    def configure(self, reason: str | None) -> None:
        heading, body = _FAILURE_CONTENT.get(reason or "", _DEFAULT_FAILURE)
        self._heading_label.setText(heading)
        self._body_label.setText(body)

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
        self._checking_adapter_page = _CheckingAdapterPage()
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
            self._checking_adapter_page,
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
            PairingState.CHECKING_ADAPTER: self._checking_adapter_page,
            PairingState.ADVERTISING: self._advertising_page,
            PairingState.WAITING_FOR_PAIR: self._waiting_for_pair_page,
            PairingState.VERIFYING_ANCS: self._verifying_ancs_page,
            PairingState.MAP_SESSION: self._map_session_page,
            PairingState.MAP_CONSENT_PROMPT: self.map_consent_page,
            PairingState.VERIFYING_MAP: self._verifying_map_page,
            PairingState.SUCCESS: self.success_page,
        }

        self.map_consent_page.continue_button.clicked.connect(self._on_map_consent_continue)

    def _on_map_consent_continue(self) -> None:
        self._orchestrator.signal_map_consent()

    def _on_orchestrator_state_change(self, state: str, reason: str | None = None) -> None:
        if state == PairingState.FAILED:
            self.failure_page.configure(reason)
            self.setCurrentId(self._page_ids[self.failure_page])
        elif state in self._state_page:
            self.setCurrentId(self._page_ids[self._state_page[state]])
