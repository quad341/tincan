"""Tests: pytest-qt coverage for wizard failure paths, ANCS partial-success, and adapter card states.
Bead: tincan-4ktha

Coverage:
  §1  FailurePage — heading text per FailureReason (7 entries):
        ADAPTER_NOT_CAPABLE, ADVERTISING_FAILED, ANCS_EXT_ADV_BUG,
        ANCS_EXPERIMENTAL_REQUIRED, PAIR_TIMEOUT, ANCS_NOT_EXPOSED, MAP_CONSENT_DENIED
  §2  FailurePage — continue_partial button:
        ANCS_EXT_ADV_BUG and ANCS_EXPERIMENTAL_REQUIRED → button visible
        all other reasons → button hidden
  §3  _AdapterCard — amber/warning state (le_capable=True, hfp_sco_capable=False)
  §4  _AdapterCard — green/capable state (le_capable=True, hfp_sco_capable=True)
  §5  SuccessPage.set_partial(ancs=False) — notifications row shows ⚠ state

These tests are intentionally failing until the builder implements the corresponding
features (tincan-guon4, tincan-j1er1, tincan-06knm, tincan-8ummz).

No hardware or live D-Bus required.
Run with: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincan_gui/test_pairing_wizard_4ktha.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel

from tincan_gui.pairing_wizard import PairingWizard, SuccessPage
from tincand.pairing import FailureReason, PairingState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_orchestrator():
    return MagicMock(name="PairingOrchestrator")


def _drive_wizard(orch, wizard: PairingWizard, states: list[tuple[str, str | None]]) -> None:
    for state, reason in states:
        wizard._on_orchestrator_state_change(state, reason)


def _wizard_at_failure(qtbot, reason: str) -> PairingWizard:
    orch = _make_mock_orchestrator()
    wizard = PairingWizard(orchestrator=orch)
    qtbot.addWidget(wizard)
    wizard.show()
    _drive_wizard(orch, wizard, [(PairingState.FAILED, reason)])
    return wizard


def _card_labels_text(card) -> str:
    return " ".join(lbl.text() for lbl in card.findChildren(QLabel))


# ---------------------------------------------------------------------------
# §1  FailurePage heading text — all 7 FailureReason entries
# ---------------------------------------------------------------------------


class TestFailurePageHeadings:
    """Each failure reason configures FailurePage with the correct heading text."""

    def test_adapter_not_capable_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ADAPTER_NOT_CAPABLE)
        assert wizard.failure_page._heading_label.text() == "No Bluetooth adapter found"

    def test_advertising_failed_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ADVERTISING_FAILED)
        assert wizard.failure_page._heading_label.text() == "Bluetooth advertising failed"

    def test_ancs_ext_adv_bug_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXT_ADV_BUG)
        assert wizard.failure_page._heading_label.text() == "Advertising failed — BlueZ bug"

    def test_ancs_experimental_required_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXPERIMENTAL_REQUIRED)
        assert wizard.failure_page._heading_label.text() == "Experimental features required"

    def test_pair_timeout_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.PAIR_TIMEOUT)
        assert wizard.failure_page._heading_label.text() == "Pairing timed out"

    def test_ancs_not_exposed_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_NOT_EXPOSED)
        assert wizard.failure_page._heading_label.text() == "Notifications not allowed"

    def test_map_consent_denied_heading(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.MAP_CONSENT_DENIED)
        assert wizard.failure_page._heading_label.text() == "Message access denied"


# ---------------------------------------------------------------------------
# §2  FailurePage — continue_partial button visibility
# ---------------------------------------------------------------------------


class TestContinuePartialButton:
    """'Continue without notifications' is shown only for ANCS_* failure reasons."""

    def test_button_visible_for_ancs_ext_adv_bug(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXT_ADV_BUG)
        assert wizard.failure_page.continue_partial is not None
        assert wizard.failure_page.continue_partial.isVisible()

    def test_button_visible_for_ancs_experimental_required(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXPERIMENTAL_REQUIRED)
        assert wizard.failure_page.continue_partial is not None
        assert wizard.failure_page.continue_partial.isVisible()

    def test_button_hidden_for_adapter_not_capable(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ADAPTER_NOT_CAPABLE)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_button_hidden_for_advertising_failed(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ADVERTISING_FAILED)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_button_hidden_for_pair_timeout(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.PAIR_TIMEOUT)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_button_hidden_for_ancs_not_exposed(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_NOT_EXPOSED)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_button_hidden_for_map_consent_denied(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.MAP_CONSENT_DENIED)
        assert not wizard.failure_page.continue_partial.isVisible()


# ---------------------------------------------------------------------------
# §3  _AdapterCard — amber/warning state (le_capable=True, hfp_sco_capable=False)
# ---------------------------------------------------------------------------


class TestAdapterCardAmberState:
    """LE-only adapter (le_capable=True, hfp_sco_capable=False) renders amber/warning state."""

    def _make_amber_card(self, qtbot):
        from tincan_gui.pairing_wizard import _AdapterCard
        card = _AdapterCard()
        qtbot.addWidget(card)
        card.configure(
            "MT7925 (built-in)",
            le_capable=True,
            hfp_sco_capable=False,
            recommended=False,
        )
        return card

    def test_amber_state_shows_warning_icon(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert "⚠" in _card_labels_text(card)

    def test_amber_state_includes_adapter_alias(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert "MT7925 (built-in)" in _card_labels_text(card)

    def test_amber_state_mentions_dongle_recommendation(self, qtbot):
        card = self._make_amber_card(qtbot)
        text = _card_labels_text(card)
        assert "ASUS USB-BT500" in text or "RTL8761B" in text

    def test_amber_state_does_not_show_all_features_available(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert "All tincan features available" not in _card_labels_text(card)


# ---------------------------------------------------------------------------
# §4  _AdapterCard — green/capable state (le_capable=True, hfp_sco_capable=True)
# ---------------------------------------------------------------------------


class TestAdapterCardGreenState:
    """Fully capable adapter (le_capable=True, hfp_sco_capable=True) renders green state."""

    def _make_green_card(self, qtbot):
        from tincan_gui.pairing_wizard import _AdapterCard
        card = _AdapterCard()
        qtbot.addWidget(card)
        card.configure(
            "ASUS USB-BT500",
            le_capable=True,
            hfp_sco_capable=True,
            recommended=True,
        )
        return card

    def test_green_state_shows_all_features_available(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "All tincan features available" in _card_labels_text(card)

    def test_green_state_includes_adapter_alias(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "ASUS USB-BT500" in _card_labels_text(card)

    def test_green_state_shows_checkmark(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "✓" in _card_labels_text(card)

    def test_green_state_does_not_show_warning_icon(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "⚠" not in _card_labels_text(card)


# ---------------------------------------------------------------------------
# §5  SuccessPage.set_partial(ancs=False) — notifications row shows ⚠ state
# ---------------------------------------------------------------------------


class TestSuccessPagePartial:
    """set_partial(ancs=False) replaces '✓ Notifications active' with ⚠ variant."""

    def test_set_partial_removes_notifications_active(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Notifications active" not in page.text()

    def test_set_partial_shows_warning_symbol(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "⚠" in page.text()

    def test_set_partial_shows_notifications_unavailable(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Notifications unavailable" in page.text()

    def test_set_partial_preserves_message_access_row(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "message access" in page.text().lower()

    def test_full_success_still_shows_notifications_active(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        assert "Notifications active" in page.text()

    def test_set_partial_does_not_affect_message_access_granted(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Message access granted" in page.text() or "message access" in page.text().lower()
