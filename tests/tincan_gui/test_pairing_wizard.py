"""Tests: PairingWizard — GUI for dual-mode ANCS+MAP onboarding.
Bead: tincan-pql5

Coverage:
  §1  Happy path: orchestrator emits all states -> wizard reaches Success screen.
  §2  Adapter not ready: CHECKING_ADAPTER -> FAILED(adapter_not_capable) -> Failure screen.
  §3  Pairing timeout: FAILED(pair_timeout) -> wizard shows retry option.
  §4  MAP consent prompt: MAP_CONSENT_PROMPT -> wizard shows 'Allow message access'
      screen and resumes on user Continue.
  §5  Full failure (MAP consent denied): FAILED(map_consent_denied) -> Failure screen
      with clear message; no jargon (ANCS/MAP/PBAP not shown to user).

No hardware or live D-Bus required; mock orchestrator injected.
Run with: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincan_gui/test_pairing_wizard.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tincan_gui.pairing_wizard import PairingWizard
from tincand.pairing import FailureReason, PairingState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_orchestrator(state_sequence: list[tuple[str, str | None]] | None = None):
    """Return a MagicMock with a controllable on_state_change registration.

    The returned orchestrator records the callback passed to __init__ via
    _capture_callback; tests call _emit(state, reason) to drive the wizard.
    """
    orch = MagicMock(name="PairingOrchestrator")
    orch._callback = None
    orch._state_sequence = state_sequence or []
    return orch


def _drive_wizard(orch_mock, wizard: PairingWizard, states: list[tuple[str, str | None]]) -> None:
    """Emit state changes into the wizard's subscribed handler."""
    for state, reason in states:
        wizard._on_orchestrator_state_change(state, reason)


# ---------------------------------------------------------------------------
# §1 Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """All states emitted in order: wizard reaches the Success screen."""

    _HAPPY_STATES: list[tuple[str, str | None]] = [
        (PairingState.CHECKING_ADAPTER, None),
        (PairingState.ADVERTISING, None),
        (PairingState.WAITING_FOR_PAIR, None),
        (PairingState.VERIFYING_ANCS, None),
        (PairingState.MAP_SESSION, None),
        (PairingState.VERIFYING_MAP, None),
        (PairingState.SUCCESS, None),
    ]

    def test_success_page_shown_on_happy_path(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._HAPPY_STATES)

        assert wizard.currentPage() is wizard.success_page

    def test_success_page_visible_after_happy_path(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._HAPPY_STATES)

        assert wizard.success_page.isVisible()

    def test_success_page_has_no_jargon(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._HAPPY_STATES)

        text = wizard.success_page.text().lower()
        for term in ("ancs", "map", "pbap", "gatt", "ble", "le bond"):
            assert term not in text, f"Technical jargon {term!r} found on success page"

    def test_no_failure_page_on_happy_path(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._HAPPY_STATES)

        assert wizard.currentPage() is not wizard.failure_page


# ---------------------------------------------------------------------------
# §2 Adapter not ready
# ---------------------------------------------------------------------------

class TestAdapterNotReady:
    """CHECKING_ADAPTER → FAILED(adapter_not_capable) → Failure screen shown."""

    _ADAPTER_FAIL_STATES: list[tuple[str, str | None]] = [
        (PairingState.CHECKING_ADAPTER, None),
        (PairingState.FAILED, FailureReason.ADAPTER_NOT_CAPABLE),
    ]

    def test_failure_page_shown_when_adapter_not_capable(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._ADAPTER_FAIL_STATES)

        assert wizard.currentPage() is wizard.failure_page

    def test_failure_page_mentions_adapter_problem(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._ADAPTER_FAIL_STATES)

        text = wizard.failure_page.text().lower()
        assert any(term in text for term in ("bluetooth", "adapter", "capability")), (
            f"Failure page for adapter_not_capable should mention adapter problem; got: {text!r}"
        )

    def test_failure_page_has_no_jargon_for_adapter_fail(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._ADAPTER_FAIL_STATES)

        text = wizard.failure_page.text().lower()
        for term in ("ancs", "map", "pbap", "le advertising"):
            assert term not in text, f"Jargon {term!r} found on adapter failure page"

    def test_retry_or_cancel_button_present_on_adapter_fail(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._ADAPTER_FAIL_STATES)

        # Failure page must offer the user an exit path
        has_exit = (
            wizard.failure_page.cancel_button is not None
            or wizard.failure_page.retry_button is not None
        )
        assert has_exit


# ---------------------------------------------------------------------------
# §3 Pairing timeout
# ---------------------------------------------------------------------------

class TestPairingTimeout:
    """FAILED(pair_timeout): wizard shows retry option so user can try again."""

    _PAIR_TIMEOUT_STATES: list[tuple[str, str | None]] = [
        (PairingState.CHECKING_ADAPTER, None),
        (PairingState.ADVERTISING, None),
        (PairingState.WAITING_FOR_PAIR, None),
        (PairingState.FAILED, FailureReason.PAIR_TIMEOUT),
    ]

    def test_failure_page_shown_on_pair_timeout(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._PAIR_TIMEOUT_STATES)

        assert wizard.currentPage() is wizard.failure_page

    def test_retry_button_visible_on_pair_timeout(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._PAIR_TIMEOUT_STATES)

        assert wizard.failure_page.retry_button is not None
        assert wizard.failure_page.retry_button.isVisible()

    def test_pair_timeout_message_is_user_friendly(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._PAIR_TIMEOUT_STATES)

        text = wizard.failure_page.text().lower()
        # Should mention something about pairing or connection, not timeout codes
        assert any(term in text for term in ("pair", "connect", "phone", "device", "time")), (
            f"Pair timeout message should be user-friendly; got: {text!r}"
        )

    def test_no_jargon_on_pair_timeout_failure(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._PAIR_TIMEOUT_STATES)

        text = wizard.failure_page.text().lower()
        for term in ("ancs", "map", "pbap", "dbus", "ble"):
            assert term not in text


# ---------------------------------------------------------------------------
# §4 MAP consent prompt
# ---------------------------------------------------------------------------

class TestMapConsentPrompt:
    """MAP_CONSENT_PROMPT: wizard shows 'Allow message access' screen; user Continue resumes."""

    _UP_TO_CONSENT_STATES: list[tuple[str, str | None]] = [
        (PairingState.CHECKING_ADAPTER, None),
        (PairingState.ADVERTISING, None),
        (PairingState.WAITING_FOR_PAIR, None),
        (PairingState.VERIFYING_ANCS, None),
        (PairingState.MAP_SESSION, None),
        (PairingState.MAP_CONSENT_PROMPT, None),
    ]

    def test_map_consent_page_shown_on_consent_prompt(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)

        assert wizard.currentPage() is wizard.map_consent_page

    def test_map_consent_page_mentions_message_access(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)

        text = wizard.map_consent_page.text().lower()
        assert any(term in text for term in ("message", "access", "allow")), (
            f"MAP consent page should mention message access; got: {text!r}"
        )

    def test_map_consent_page_has_no_jargon(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)

        text = wizard.map_consent_page.text().lower()
        for term in ("ancs", "map", "pbap", "gatt", "ble"):
            assert term not in text, f"Jargon {term!r} found on MAP consent page"

    def test_continue_button_present_on_consent_page(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)

        assert wizard.map_consent_page.continue_button is not None
        assert wizard.map_consent_page.continue_button.isVisible()

    def test_continue_button_calls_signal_map_consent_on_orchestrator(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)
        qtbot.mouseClick(wizard.map_consent_page.continue_button, None)

        orch.signal_map_consent.assert_called_once()

    def test_after_consent_and_success_wizard_shows_success_page(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._UP_TO_CONSENT_STATES)
        # User clicks Continue → orchestrator eventually emits VERIFYING_MAP then SUCCESS
        _drive_wizard(orch, wizard, [
            (PairingState.VERIFYING_MAP, None),
            (PairingState.SUCCESS, None),
        ])

        assert wizard.currentPage() is wizard.success_page


# ---------------------------------------------------------------------------
# §5 Full failure — MAP consent denied
# ---------------------------------------------------------------------------

class TestMapConsentDenied:
    """FAILED(map_consent_denied): wizard reaches Failure screen with plain message."""

    _CONSENT_DENIED_STATES: list[tuple[str, str | None]] = [
        (PairingState.CHECKING_ADAPTER, None),
        (PairingState.ADVERTISING, None),
        (PairingState.WAITING_FOR_PAIR, None),
        (PairingState.VERIFYING_ANCS, None),
        (PairingState.MAP_SESSION, None),
        (PairingState.MAP_CONSENT_PROMPT, None),
        (PairingState.FAILED, FailureReason.MAP_CONSENT_DENIED),
    ]

    def test_failure_page_shown_when_map_consent_denied(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._CONSENT_DENIED_STATES)

        assert wizard.currentPage() is wizard.failure_page

    def test_failure_message_is_clear_and_plain_language(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._CONSENT_DENIED_STATES)

        text = wizard.failure_page.text().lower()
        # Message should reference the user action (message access / allow)
        assert any(term in text for term in ("message", "access", "allow", "denied")), (
            f"Map consent denied failure should reference message access; got: {text!r}"
        )

    def test_no_jargon_on_map_consent_denied_failure(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._CONSENT_DENIED_STATES)

        text = wizard.failure_page.text().lower()
        for term in ("ancs", "map", "pbap", "gatt", "ble", "dbus", "0x43"):
            assert term not in text, f"Jargon {term!r} found on MAP consent denied failure page"

    def test_failure_page_has_close_or_cancel_button(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._CONSENT_DENIED_STATES)

        assert wizard.failure_page.cancel_button is not None
        assert wizard.failure_page.cancel_button.isVisible()

    def test_failure_page_is_not_success_page(self, qtbot):
        orch = _make_mock_orchestrator()
        wizard = PairingWizard(orchestrator=orch)
        qtbot.addWidget(wizard)
        wizard.show()

        _drive_wizard(orch, wizard, self._CONSENT_DENIED_STATES)

        assert wizard.currentPage() is not wizard.success_page
