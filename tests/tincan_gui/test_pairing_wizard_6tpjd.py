"""Tests: wizard ANCS_NOT_EXPOSED failure renders adapter alias (tincan-ivihc).
Bead: tincan-6tpjd

Coverage:
  §6  FAILED(ANCS_NOT_EXPOSED) — failure page uses orchestrator.computer_name
      6.1  orchestrator.computer_name='TestAdapter' → failure_page.text() contains 'TestAdapter'
      6.2  orchestrator has no computer_name attr → failure_page.text() contains 'your computer'

Tests intentionally fail until the builder's ivihc commit is merged into main
(_on_orchestrator_state_change reads computer_name from orchestrator and passes
it to FailurePage.configure(); ANCS_NOT_EXPOSED template includes {computer_name}).

No hardware or live D-Bus required.
Run: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincan_gui/test_pairing_wizard_6tpjd.py -v
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


class TestAncsNotExposedRendersAlias:
    """§6: ANCS_NOT_EXPOSED failure page shows the adapter alias as the device name."""

    def test_failure_page_contains_adapter_alias(self, qtbot):
        orch = MagicMock(name="PairingOrchestrator")
        orch.computer_name = "TestAdapter"
        wizard = _wizard_at_ancs_failure(qtbot, orch)
        assert "TestAdapter" in wizard.failure_page.text()

    def test_failure_page_falls_back_to_your_computer_when_no_attr(self, qtbot):
        orch = MagicMock(name="PairingOrchestrator")
        del orch.computer_name
        wizard = _wizard_at_ancs_failure(qtbot, orch)
        assert "your computer" in wizard.failure_page.text()
