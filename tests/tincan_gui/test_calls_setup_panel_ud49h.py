"""pytest-qt behavioral acceptance tests for CallsSetupPanel (tincan-ud49h).
Bead: tincan-ud49h

Tests should FAIL on the current branch (ImportError — calls_setup_panel.py not yet
merged) and PASS once tincan-lqj89.2 lands on main.

Coverage:
  §1  Initial state — all rows show ⟳ Checking… at construction, success card hidden
  §2  Step B: WirePlumber — checking → ok, checking → fail, fail detail visible
  §3  Step A: oFono — ok, fail without WP warning, fail with WP warning content
  §4  Step C: SELinux — ok, fail (module absent), permissive neutral
  §5  Step D: RTL8761B — ok (autosuspend disabled), fail (autosuspend enabled), N/A
  §6  Success card: hidden when any single step fails (per-step failure coverage)
  §7  Recheck end-to-end: mock fires callback → rows leave checking state with results
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from PySide6.QtCore import Qt

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
    """dbus_client whose preflight_calls captures the callback without firing it."""
    return MagicMock()


@pytest.fixture()
def panel(qtbot, mock_client):
    """CallsSetupPanel in its initial ⟳ Checking… state (callback not yet fired)."""
    p = CallsSetupPanel(mock_client, adapter_vid_pid="")
    qtbot.addWidget(p)
    p.show()
    return p


def _settle(panel: CallsSetupPanel, result: dict) -> None:
    """Drive the panel to a known result state without going through the mock."""
    panel._on_preflight_result(result)


# ---------------------------------------------------------------------------
# §1  Initial state — all rows in ⟳ Checking…, success card hidden
# ---------------------------------------------------------------------------

class TestInitialCheckingState:
    """At construction the panel fires preflight_calls and all rows show ⟳ Checking…."""

    def test_step_b_starts_checking(self, panel):
        assert panel._step_b._status_label.text() == "⟳ Checking…"

    def test_step_a_starts_checking(self, panel):
        assert panel._step_a._status_label.text() == "⟳ Checking…"

    def test_step_c_starts_checking(self, panel):
        assert panel._step_c._status_label.text() == "⟳ Checking…"

    def test_step_d_starts_checking(self, panel):
        assert panel._step_d._status_label.text() == "⟳ Checking…"

    def test_success_card_hidden_initially(self, panel):
        assert not panel._success_card.isVisible()

    def test_preflight_called_on_construction(self, mock_client, panel):
        """__init__ calls _recheck() which calls preflight_calls exactly once."""
        mock_client.preflight_calls.assert_called_once()


# ---------------------------------------------------------------------------
# §2  Step B: WirePlumber — per-state behavioral coverage
# ---------------------------------------------------------------------------

class TestStepBWirePlumber:
    """_on_preflight_result drives Step B to ✓ Done, ✗ Action required, and detail visibility."""

    def test_wp_ok_shows_done(self, panel):
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": True})
        assert panel._step_b._status_label.text() == "✓ Done"

    def test_wp_fail_shows_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": False})
        assert panel._step_b._status_label.text() == "✗ Action required"

    def test_wp_fail_makes_detail_visible(self, panel):
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": False})
        assert panel._step_b._detail.isVisible()

    def test_wp_ok_hides_detail(self, panel):
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": False})
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": True})
        assert not panel._step_b._detail.isVisible()


# ---------------------------------------------------------------------------
# §3  Step A: oFono — ok, fail without warning, fail with WP warning
# ---------------------------------------------------------------------------

class TestStepAOFono:
    """oFono check drives Step A. Cross-step warning injected only when WP also fails."""

    def test_ofono_ok_shows_done(self, panel):
        _settle(panel, {**_ALL_OK, "ofono_available": True, "wireplumber_ofono_backend": True})
        assert panel._step_a._status_label.text() == "✓ Done"

    def test_ofono_fail_with_wp_ok_shows_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "ofono_available": False, "wireplumber_ofono_backend": True})
        assert panel._step_a._status_label.text() == "✗ Action required"

    def test_ofono_fail_wp_ok_no_cross_step_warning(self, panel):
        """When WP is configured, no ordering warning should appear on Step A."""
        _settle(panel, {**_ALL_OK, "ofono_available": False, "wireplumber_ofono_backend": True})
        if panel._step_a._extra_label is not None:
            assert not panel._step_a._extra_label.isVisible()

    def test_ofono_fail_wp_fail_shows_cross_step_warning(self, panel):
        """When BOTH WP and oFono fail, Step A's extra label is visible."""
        _settle(panel, {**_ALL_OK, "ofono_available": False, "wireplumber_ofono_backend": False})
        assert panel._step_a._extra_label is not None
        assert panel._step_a._extra_label.isVisible()

    def test_ofono_fail_wp_fail_warning_text_references_step_b_or_wireplumber(self, panel):
        """Warning text must name the required prerequisite so user knows what to do first."""
        _settle(panel, {**_ALL_OK, "ofono_available": False, "wireplumber_ofono_backend": False})
        text = panel._step_a._extra_label.text()
        assert "WirePlumber" in text or "Step B" in text

    def test_ofono_ok_extra_label_hidden(self, panel):
        """No warning when oFono passes, even if WP is also failing."""
        _settle(panel, {**_ALL_OK, "ofono_available": True})
        if panel._step_a._extra_label is not None:
            assert not panel._step_a._extra_label.isVisible()


# ---------------------------------------------------------------------------
# §4  Step C: SELinux — ok, fail, permissive neutral
# ---------------------------------------------------------------------------

class TestStepCSELinux:
    """selinux_hfp_module drives 3 distinct states: ok (truthy), fail (falsy), permissive."""

    def test_selinux_true_shows_done(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": True})
        assert panel._step_c._status_label.text() == "✓ Done"

    def test_selinux_false_shows_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": False})
        assert panel._step_c._status_label.text() == "✗ Action required"

    def test_selinux_false_makes_detail_visible(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": False})
        assert panel._step_c._detail.isVisible()

    def test_selinux_permissive_is_not_done(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._step_c._status_label.text() != "✓ Done"

    def test_selinux_permissive_is_not_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._step_c._status_label.text() != "✗ Action required"

    def test_selinux_permissive_status_mentions_permissive(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        text = panel._step_c._status_label.text()
        assert "Permissive" in text or "permissive" in text.lower()


# ---------------------------------------------------------------------------
# §5  Step D: RTL8761B — ok (autosuspend disabled), fail, N/A
# ---------------------------------------------------------------------------

class TestStepDRTL8761B:
    """Step D handles three cases: RTL adapter ok, RTL adapter fail, non-RTL N/A."""

    def test_rtl_autosuspend_disabled_shows_done(self, panel):
        _settle(panel, {**_ALL_OK, "adapter_vid_pid": _RTL8761B_VID_PID, "usb_autosuspend_disabled": True})
        assert panel._step_d._status_label.text() == "✓ Done"

    def test_rtl_autosuspend_enabled_shows_action_required(self, panel):
        _settle(panel, {**_ALL_OK, "adapter_vid_pid": _RTL8761B_VID_PID, "usb_autosuspend_disabled": False})
        assert panel._step_d._status_label.text() == "✗ Action required"

    def test_rtl_autosuspend_enabled_makes_detail_visible(self, panel):
        _settle(panel, {**_ALL_OK, "adapter_vid_pid": _RTL8761B_VID_PID, "usb_autosuspend_disabled": False})
        assert panel._step_d._detail.isVisible()

    def test_non_rtl_adapter_step_d_status_not_done_or_fail(self, panel):
        _settle(panel, {**_ALL_OK, "adapter_vid_pid": "0000:0000", "usb_autosuspend_disabled": False})
        text = panel._step_d._status_label.text()
        assert text not in ("✓ Done", "✗ Action required")

    def test_non_rtl_detail_hidden(self, panel):
        _settle(panel, {**_ALL_OK, "adapter_vid_pid": "dead:beef", "usb_autosuspend_disabled": False})
        assert not panel._step_d._detail.isVisible()


# ---------------------------------------------------------------------------
# §6  Success card: hidden when any individual step fails
# ---------------------------------------------------------------------------

class TestSuccessCardSingleStepFailure:
    """Failing any one step suppresses the success card even if the other three pass."""

    def test_success_card_hidden_when_wp_fails(self, panel):
        _settle(panel, {**_ALL_OK, "wireplumber_ofono_backend": False})
        assert not panel._success_card.isVisible()

    def test_success_card_hidden_when_ofono_fails(self, panel):
        _settle(panel, {**_ALL_OK, "ofono_available": False})
        assert not panel._success_card.isVisible()

    def test_success_card_hidden_when_selinux_module_absent(self, panel):
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": False})
        assert not panel._success_card.isVisible()

    def test_success_card_hidden_when_rtl_autosuspend_still_enabled(self, panel):
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": _RTL8761B_VID_PID,
            "usb_autosuspend_disabled": False,
        })
        assert not panel._success_card.isVisible()

    def test_success_card_visible_rtl_all_pass(self, panel):
        """Positive control: RTL adapter with autosuspend disabled → success card shown."""
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": _RTL8761B_VID_PID,
            "usb_autosuspend_disabled": True,
        })
        assert panel._success_card.isVisible()

    def test_success_card_visible_non_rtl_all_pass(self, panel):
        """N/A step D counts as pass: non-RTL adapter + all others ok → success card."""
        _settle(panel, {
            **_ALL_OK,
            "adapter_vid_pid": "1234:abcd",
            "usb_autosuspend_disabled": False,
        })
        assert panel._success_card.isVisible()

    def test_success_card_visible_selinux_permissive_counts_as_pass(self, panel):
        """SELinux permissive mode is treated as a passing state for the success card."""
        _settle(panel, {**_ALL_OK, "selinux_hfp_module": "permissive"})
        assert panel._success_card.isVisible()


# ---------------------------------------------------------------------------
# §7  Recheck end-to-end: mock fires callback → rows leave checking state
# ---------------------------------------------------------------------------

class TestRecheckEndToEnd:
    """Simulate the full recheck → preflight_calls → callback → state update cycle."""

    def test_rows_in_checking_between_recheck_and_callback(self, qtbot, mock_client):
        """After clicking Re-check, rows are in ⟳ Checking… until the callback fires."""
        panel = CallsSetupPanel(mock_client, adapter_vid_pid="")
        qtbot.addWidget(panel)
        panel.show()

        # Settle the panel first so rows are NOT in checking state
        panel._on_preflight_result(_ALL_OK)
        assert panel._step_b._status_label.text() == "✓ Done"

        # Reset the mock; click recheck — callback has NOT fired yet
        mock_client.preflight_calls.reset_mock()
        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)

        for row in (panel._step_b, panel._step_a, panel._step_c, panel._step_d):
            assert row._status_label.text() == "⟳ Checking…", (
                f"row should be checking after recheck button, got '{row._status_label.text()}'"
            )

    def test_callback_from_recheck_updates_rows_correctly(self, qtbot, mock_client):
        """When recheck's callback fires, rows update to reflect the new result."""
        captured = []
        mock_client.preflight_calls.side_effect = lambda cb: captured.append(cb)

        panel = CallsSetupPanel(mock_client, adapter_vid_pid="")
        qtbot.addWidget(panel)
        panel.show()

        # Construction already captured one callback; reset and capture the recheck one
        captured.clear()
        mock_client.preflight_calls.reset_mock()
        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)

        assert len(captured) == 1, "Re-check should have called preflight_calls once"

        # Fire the callback with a result that has WP failing
        fail_result = {**_ALL_OK, "wireplumber_ofono_backend": False, "ofono_available": False}
        captured[0](fail_result)

        assert panel._step_b._status_label.text() == "✗ Action required"
        assert panel._step_a._extra_label is not None
        assert panel._step_a._extra_label.isVisible()
        assert not panel._success_card.isVisible()

    def test_success_card_shown_after_all_ok_callback(self, qtbot, mock_client):
        """Recheck callback with all-ok result shows success card."""
        captured = []
        mock_client.preflight_calls.side_effect = lambda cb: captured.append(cb)

        panel = CallsSetupPanel(mock_client, adapter_vid_pid="")
        qtbot.addWidget(panel)
        panel.show()

        captured.clear()
        mock_client.preflight_calls.reset_mock()
        qtbot.mouseClick(panel._recheck_btn, Qt.MouseButton.LeftButton)

        captured[0](_ALL_OK)

        assert panel._success_card.isVisible()
