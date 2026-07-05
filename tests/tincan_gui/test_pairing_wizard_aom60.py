"""Tests: pytest-qt behavioral acceptance for tincan-aom60 wizard UX.
Bead: tincan-aom60.6

Coverage (all 9 required acceptance cases):
  §1  FailurePage heading text — all 7 FailureReason entries
  §2  FailurePage continue_partial button — ANCS_* visible, non-ANCS hidden
  §3  _AdapterCard green (le_capable=True, hfp_sco_capable=True) — no recommendation text
  §4  _AdapterCard amber (le_capable=True, hfp_sco_capable=False) — recommendation copy present
  §5  _AdapterCard red (le_capable=False) — red card, Retry button visible
  §6  SuccessPage.set_partial(ancs=False) — ⚠ Notifications unavailable row
  §7  MapConsentPage body — numbered iOS tap sequence

§1–§4 and §6 are also covered by tincan-4ktha (complementary suites for
builder sub-beads).
§5 (_AdapterCard red / no-adapter) and §7 (MapConsentPage numbered sequence)
are first coverage here.

Tests intentionally fail until builder implements the corresponding features
(tincan-aom60.1–tincan-aom60.5 builder beads).

No hardware or live D-Bus required.
Run: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincan_gui/test_pairing_wizard_aom60.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel

from tincan_gui.pairing_wizard import MapConsentPage, PairingWizard, SuccessPage
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


def _all_labels_text(widget) -> str:
    return " ".join(lbl.text() for lbl in widget.findChildren(QLabel))


# ---------------------------------------------------------------------------
# §1  FailurePage heading text — all 7 FailureReason entries (acceptance case 1)
# ---------------------------------------------------------------------------


class TestFailurePageHeadings:
    """Each failure reason configures FailurePage with the correct user-facing heading."""

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
# §2  FailurePage continue_partial visibility (acceptance cases 2, 3, 4)
# ---------------------------------------------------------------------------


class TestContinuePartialButton:
    """'Continue without notifications' appears only for ANCS_* failure reasons."""

    def test_visible_for_ancs_ext_adv_bug(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXT_ADV_BUG)
        assert wizard.failure_page.continue_partial is not None
        assert wizard.failure_page.continue_partial.isVisible()

    def test_visible_for_ancs_experimental_required(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_EXPERIMENTAL_REQUIRED)
        assert wizard.failure_page.continue_partial is not None
        assert wizard.failure_page.continue_partial.isVisible()

    def test_hidden_for_advertising_failed(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ADVERTISING_FAILED)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_hidden_for_pair_timeout(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.PAIR_TIMEOUT)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_hidden_for_ancs_not_exposed(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.ANCS_NOT_EXPOSED)
        assert not wizard.failure_page.continue_partial.isVisible()

    def test_hidden_for_map_consent_denied(self, qtbot):
        wizard = _wizard_at_failure(qtbot, FailureReason.MAP_CONSENT_DENIED)
        assert not wizard.failure_page.continue_partial.isVisible()


# ---------------------------------------------------------------------------
# §3  _AdapterCard green state (acceptance case 5)
# ---------------------------------------------------------------------------


class TestAdapterCardGreen:
    """le_capable=True, hfp_sco_capable=True → green state, no recommendation text."""

    def _make_green_card(self, qtbot):
        from tincan_gui.pairing_wizard import _AdapterCard
        card = _AdapterCard()
        qtbot.addWidget(card)
        card.configure("ASUS USB-BT500", le_capable=True, hfp_sco_capable=True, recommended=True)
        return card

    def test_shows_all_features_available(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "All tincan features available" in _all_labels_text(card)

    def test_shows_checkmark_icon(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "✓" in _all_labels_text(card)

    def test_no_recommendation_upgrade_text(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "recommend" not in card._status_label.text().lower()

    def test_no_warning_icon(self, qtbot):
        card = self._make_green_card(qtbot)
        assert "⚠" not in _all_labels_text(card)

    def test_retry_button_hidden(self, qtbot):
        card = self._make_green_card(qtbot)
        assert not card.retry_button.isVisible()


# ---------------------------------------------------------------------------
# §4  _AdapterCard amber state (acceptance case 6)
# ---------------------------------------------------------------------------


class TestAdapterCardAmber:
    """le_capable=True, hfp_sco_capable=False → amber state, upgrade recommendation present."""

    def _make_amber_card(self, qtbot):
        from tincan_gui.pairing_wizard import _AdapterCard
        card = _AdapterCard()
        qtbot.addWidget(card)
        card.configure(
            "MT7925 (built-in)", le_capable=True, hfp_sco_capable=False, recommended=False
        )
        return card

    def test_shows_warning_icon(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert "⚠" in _all_labels_text(card)

    def test_shows_dongle_recommendation(self, qtbot):
        card = self._make_amber_card(qtbot)
        status = card._status_label.text()
        assert "ASUS USB-BT500" in status or "RTL8761B" in status

    def test_does_not_show_all_features_available(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert "All tincan features available" not in _all_labels_text(card)

    def test_retry_button_hidden(self, qtbot):
        card = self._make_amber_card(qtbot)
        assert not card.retry_button.isVisible()


# ---------------------------------------------------------------------------
# §5  _AdapterCard red / no-adapter state (acceptance case 7)
# ---------------------------------------------------------------------------


class TestAdapterCardRed:
    """le_capable=False → red state, ✗ icon, Retry button visible (first coverage here)."""

    def _make_red_card(self, qtbot):
        from tincan_gui.pairing_wizard import _AdapterCard
        card = _AdapterCard()
        qtbot.addWidget(card)
        card.configure("", le_capable=False, hfp_sco_capable=False, recommended=False)
        return card

    def test_shows_cross_icon(self, qtbot):
        card = self._make_red_card(qtbot)
        assert "✗" in _all_labels_text(card)

    def test_shows_no_adapter_message(self, qtbot):
        card = self._make_red_card(qtbot)
        text = card._status_label.text().lower()
        assert "bluetooth" in text or "adapter" in text

    def test_retry_button_visible(self, qtbot):
        card = self._make_red_card(qtbot)
        assert card.retry_button.isVisible()

    def test_no_warning_or_check_icon(self, qtbot):
        card = self._make_red_card(qtbot)
        text = _all_labels_text(card)
        assert "⚠" not in text
        assert "✓" not in text

    def test_no_features_available_text(self, qtbot):
        card = self._make_red_card(qtbot)
        assert "All tincan features available" not in _all_labels_text(card)


# ---------------------------------------------------------------------------
# §6  SuccessPage.set_partial(ancs=False) (acceptance case 8)
# ---------------------------------------------------------------------------


class TestSuccessPagePartial:
    """set_partial(ancs=False) shows ⚠ Notifications unavailable; hides active row."""

    def test_removes_notifications_active(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Notifications active" not in page.text()

    def test_shows_warning_symbol(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "⚠" in page.text()

    def test_shows_notifications_unavailable(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Notifications unavailable" in page.text()

    def test_preserves_message_access_granted(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        page.set_partial(ancs=False)
        assert "Message access granted" in page.text()

    def test_full_success_shows_notifications_active(self, qtbot):
        page = SuccessPage()
        qtbot.addWidget(page)
        assert "Notifications active" in page.text()
        assert "⚠" not in page.text()


# ---------------------------------------------------------------------------
# §7  MapConsentPage body — numbered tap sequence (acceptance case 9)
# ---------------------------------------------------------------------------


class TestMapConsentPageBody:
    """MapConsentPage body contains a numbered iOS tap sequence (first coverage here)."""

    def test_body_contains_numbered_step_one(self, qtbot):
        page = MapConsentPage()
        qtbot.addWidget(page)
        assert "1." in page.text()

    def test_body_contains_numbered_step_two(self, qtbot):
        page = MapConsentPage()
        qtbot.addWidget(page)
        assert "2." in page.text()

    def test_body_mentions_allow(self, qtbot):
        page = MapConsentPage()
        qtbot.addWidget(page)
        assert "Allow" in page.text()

    def test_body_includes_ios_settings_path(self, qtbot):
        page = MapConsentPage()
        qtbot.addWidget(page)
        text = page.text()
        assert "Privacy" in text or "Settings" in text

    def test_body_has_no_jargon(self, qtbot):
        page = MapConsentPage()
        qtbot.addWidget(page)
        text = page.text().lower()
        for term in ("ancs", "map", "pbap", "gatt", "ble", "dbus"):
            assert term not in text, f"Technical jargon {term!r} found in MapConsentPage body"
