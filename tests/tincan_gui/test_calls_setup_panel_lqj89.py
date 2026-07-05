"""pytest-qt behavioral acceptance tests for CallsSetupPanel (tincan-lqj89.4).
Bead: tincan-lqj89.4

Tests should FAIL on the current branch (ImportError — calls_setup_panel.py not yet merged)
and PASS once tincan-lqj89.2 + .3 land on main.

Coverage:
  §1  All 4 preflight checks True → success card visible, all step rows show ✓
  §2  wireplumber_ofono_backend=False → Step A row shows WirePlumber ordering warning
  §3  wireplumber_ofono_backend=True → Step A row does NOT show ordering warning
  §4  adapter_vid_pid != RTL8761B → Step D shows N/A neutral text
  §5  adapter_vid_pid == RTL8761B + usb_autosuspend_disabled=False → Step D shows failure
  §6  selinux_hfp_module == 'permissive' → Step C shows neutral ℹ text
  §7  Re-check button → all rows reset to ⟳ Checking… before results arrive
  §8  Close button → dialog.accept() fires (dialog closes with Accepted result)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton

from tincan_gui.calls_setup_panel import CallsSetupPanel

_RTL8761B_VID_PID = "0b05:1bf6"

_ALL_OK = {
    "wireplumber_ofono_backend": True,
    "ofono_available": True,
    "selinux_hfp_module": True,
    "usb_autosuspend_disabled": True,
    "adapter_vid_pid": _RTL8761B_VID_PID,
}


@pytest.fixture()
def mock_client():
    """dbus_client whose preflight_calls does not fire the callback automatically."""
    return MagicMock()


@pytest.fixture()
def panel(qtbot, mock_client):
    """CallsSetupPanel in its initial ⟳ Checking… state (callback not yet fired)."""
    p = CallsSetupPanel(mock_client, adapter_vid_pid="")
    qtbot.addWidget(p)
    p.show()
    return p


def _settle(panel: CallsSetupPanel, result: dict) -> None:
    """Drive the panel to a known state by injecting a preflight result directly."""
    panel._on_preflight_result(result)


def _find_close_button(panel: CallsSetupPanel) -> QPushButton:
    for btn in panel.findChildren(QPushButton):
        if btn.text() == "Close":
            return btn
    raise AssertionError("Close button not found in CallsSetupPanel")


# ---------------------------------------------------------------------------
# §1  All 4 checks True → success card visible, all rows ✓
# ---------------------------------------------------------------------------

class TestAllChecksPass:
    """When every preflight check passes, all rows show ✓ Done and the success card appears."""

    def test_success_card_visible(self, panel):
        _settle(panel, _ALL_OK)
        assert panel._success_card.isVisible()

    def test_step_b_shows_done(self, panel):
        _settle(panel, _ALL_OK)
        assert panel._step_b._status_label.text() == "✓ Done"

    def test_step_a_shows_done(self, panel):
        _settle(panel, _ALL_OK)
        assert panel._step_a._status_label.text() == "✓ Done"

    def test_step_c_shows_done(self, panel):
        _settle(panel, _ALL_OK)
        assert panel._step_c._status_label.text() == "✓ Done"

    def test_step_d_shows_done(self, panel):
        _settle(panel, _ALL_OK)
        assert panel._step_d._status_label.text() == "✓ Done"


# ---------------------------------------------------------------------------
# §2  wireplumber_ofono_backend=False → Step A shows WirePlumber ordering warning
# ---------------------------------------------------------------------------

class TestWirePlumberOrderingWarning:
    """Step A's extra label carries a cross-step warning when WirePlumber is not configured."""

    def test_step_a_extra_label_visible(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "wireplumber_ofono_backend": False,
            "ofono_available": False,
        })
        assert panel._step_a._extra_label is not None
        assert panel._step_a._extra_label.isVisible()

    def test_step_a_extra_label_references_wireplumber(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "wireplumber_ofono_backend": False,
            "ofono_available": False,
        })
        text = panel._step_a._extra_label.text()
        assert "WirePlumber" in text or "Step B" in text


# ---------------------------------------------------------------------------
# §3  wireplumber_ofono_backend=True → Step A does NOT show ordering warning
# ---------------------------------------------------------------------------

class TestNoWirePlumberWarningWhenWPOK:
    """When WirePlumber is done, Step A's ordering warning is suppressed even if oFono fails."""

    def test_step_a_extra_label_hidden(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "wireplumber_ofono_backend": True,
            "ofono_available": False,
        })
        if panel._step_a._extra_label is not None:
            assert not panel._step_a._extra_label.isVisible()


# ---------------------------------------------------------------------------
# §4  adapter_vid_pid != RTL8761B → Step D shows N/A neutral text
# ---------------------------------------------------------------------------

class TestStepDNonRTLAdapter:
    """A non-RTL8761B adapter causes Step D to show an N/A status, not a failure."""

    def test_step_d_status_contains_na(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": "1234:5678",
            "usb_autosuspend_disabled": False,
        })
        text = panel._step_d._status_label.text()
        assert "N/A" in text or "not applicable" in text.lower()

    def test_step_d_detail_hidden(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": "0000:0000",
        })
        assert not panel._step_d._detail.isVisible()

    def test_success_card_visible_when_non_rtl_and_all_other_pass(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": "1234:5678",
            "usb_autosuspend_disabled": False,
        })
        assert panel._success_card.isVisible()


# ---------------------------------------------------------------------------
# §5  adapter_vid_pid == RTL8761B + usb_autosuspend_disabled=False → Step D failure
# ---------------------------------------------------------------------------

class TestStepDRTLAutosuspendFailure:
    """RTL8761B adapter with USB autosuspend still enabled → Step D shows ✗ Action required."""

    def test_step_d_shows_action_required(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": _RTL8761B_VID_PID,
            "usb_autosuspend_disabled": False,
        })
        assert panel._step_d._status_label.text() == "✗ Action required"

    def test_step_d_detail_visible(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": _RTL8761B_VID_PID,
            "usb_autosuspend_disabled": False,
        })
        assert panel._step_d._detail.isVisible()

    def test_success_card_hidden_when_step_d_fails(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": _RTL8761B_VID_PID,
            "usb_autosuspend_disabled": False,
        })
        assert not panel._success_card.isVisible()


# ---------------------------------------------------------------------------
# §6  selinux_hfp_module == 'permissive' → Step C shows neutral ℹ text
# ---------------------------------------------------------------------------

class TestStepCSELinuxPermissive:
    """selinux_hfp_module='permissive' → Step C shows an ℹ neutral note, not ✓ or ✗."""

    def test_step_c_status_contains_info_marker_or_permissive(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        text = panel._step_c._status_label.text()
        assert "ℹ" in text or "Permissive" in text

    def test_step_c_status_is_not_done(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._step_c._status_label.text() != "✓ Done"

    def test_step_c_status_is_not_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._step_c._status_label.text() != "✗ Action required"

    def test_success_card_visible_when_selinux_permissive_and_others_pass(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._success_card.isVisible()


# ---------------------------------------------------------------------------
# §7  Re-check button → all rows reset to ⟳ Checking… before results arrive
# ---------------------------------------------------------------------------

class TestRecheckButton:
    """Clicking ↺ Re-check all resets every row to ⟳ Checking… and fires preflight_calls."""

    def test_rows_reset_to_checking_after_recheck(self, qtbot, panel, mock_client):
        _settle(panel, _ALL_OK)
        mock_client.preflight_calls.reset_mock()

        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)

        for row in (panel._step_b, panel._step_a, panel._step_c, panel._step_d):
            assert row._status_label.text() == "⟳ Checking…", (
                f"expected ⟳ Checking…, got '{row._status_label.text()}'"
            )

    def test_success_card_hidden_after_recheck(self, qtbot, panel, mock_client):
        _settle(panel, _ALL_OK)
        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)
        assert not panel._success_card.isVisible()

    def test_recheck_fires_preflight_calls(self, qtbot, panel, mock_client):
        mock_client.preflight_calls.reset_mock()
        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)
        mock_client.preflight_calls.assert_called_once()


# ---------------------------------------------------------------------------
# §8  Close button → dialog.accept() (Accepted result)
# ---------------------------------------------------------------------------

class TestCloseButton:
    """Close button fires self.accept() — dialog closes with Accepted result."""

    def test_close_button_emits_finished_signal(self, qtbot, panel):
        close_btn = _find_close_button(panel)
        with qtbot.waitSignal(panel.finished, timeout=1000):
            qtbot.mouseClick(close_btn, Qt.MouseButton.LeftButton)

    def test_close_button_sets_accepted_result(self, qtbot, panel):
        close_btn = _find_close_button(panel)
        with qtbot.waitSignal(panel.finished, timeout=1000):
            qtbot.mouseClick(close_btn, Qt.MouseButton.LeftButton)
        assert panel.result() == QDialog.DialogCode.Accepted
