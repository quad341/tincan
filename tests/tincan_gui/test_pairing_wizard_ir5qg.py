"""Tests: computer_name threading in FailurePage.configure() (tincan-ivihc).
Bead: tincan-ir5qg

Coverage (3 acceptance cases):
  §1  orchestrator.computer_name='My Macs BT' → ANCS_NOT_EXPOSED body shows 'My Macs BT'
  §2  orchestrator has no computer_name attr → body falls back to 'your computer'
  §3  orchestrator.computer_name=42 (not a str) → body falls back to 'your computer'

All cases drive an ANCS_NOT_EXPOSED failure, which uses {computer_name} in its body template.
The two guard branches in _on_orchestrator_state_change (tincan-ivihc fix) are each exercised.

Tests intentionally fail until the builder's ivihc fix is merged into main
(getattr fallback + isinstance guard in pairing_wizard.py; {computer_name} in FAILURE_CONTENT).

No hardware or live D-Bus required.
Run: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincan_gui/test_pairing_wizard_ir5qg.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tincan_gui.pairing_wizard import PairingWizard
from tincand.pairing import FailureReason, PairingState


def _wizard_at_ancs_failure(qtbot, orch) -> PairingWizard:
    wizard = PairingWizard(orchestrator=orch)
    qtbot.addWidget(wizard)
    wizard.show()
    wizard._on_orchestrator_state_change(PairingState.FAILED, FailureReason.ANCS_NOT_EXPOSED)
    return wizard


class TestComputerNameThreading:
    """computer_name is read from the orchestrator and threaded into FailurePage.configure()."""

    def test_failure_page_shows_adapter_name_from_orchestrator(self, qtbot):
        orch = MagicMock(name="PairingOrchestrator")
        orch.computer_name = "My Macs BT"
        wizard = _wizard_at_ancs_failure(qtbot, orch)
        assert "My Macs BT" in wizard.failure_page._body_label.text()

    def test_failure_page_falls_back_to_your_computer_when_attr_missing(self, qtbot):
        orch = MagicMock(name="PairingOrchestrator")
        del orch.computer_name
        wizard = _wizard_at_ancs_failure(qtbot, orch)
        assert "your computer" in wizard.failure_page._body_label.text()

    def test_failure_page_falls_back_when_name_is_not_str(self, qtbot):
        orch = MagicMock(name="PairingOrchestrator")
        orch.computer_name = 42
        wizard = _wizard_at_ancs_failure(qtbot, orch)
        assert "your computer" in wizard.failure_page._body_label.text()
