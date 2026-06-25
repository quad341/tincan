"""Behavioral tests: multi-call IncomingCallDialog + InCallPanel (tincan-6m2z0).

Coverage:
  §1 IncomingCallDialog — has_active_call=False: baseline regression
  §2 IncomingCallDialog — has_active_call=True: Call Waiting mode (tincan-o7yjg)
  §3 InCallPanel — multi-call controls: add_call/update_call_state/remove_call,
     _MultiCallControls visibility, height transitions (tincan-w59ao)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

import tincan_gui.call_panel as _cp_module
from tincan_gui.call_panel import InCallPanel, IncomingCallDialog

# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture()
def parent_widget(qtbot):
    w = QWidget()
    w.resize(800, 600)
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture(autouse=True)
def _patch_avatar():
    """Stub AvatarWidget so it accepts the size= kwarg call_panel uses.

    The real AvatarWidget.size= is added in tincan-o7yjg / tincan-w59ao.
    This patch lets the dialog/panel tests run independently of that change.
    """
    def _fake_avatar(name, size=None, parent=None):
        lbl = QLabel(name[:2].upper() if name else "?")
        lbl.setFixedSize(size or 44, size or 44)
        return lbl

    with patch.object(_cp_module, "AvatarWidget", side_effect=_fake_avatar):
        yield


# ---------------------------------------------------------------------------
# §1  IncomingCallDialog — has_active_call=False: baseline regression
#
# All tests below create the dialog in its default (single-call incoming) mode.
# They must continue to pass after the has_active_call extension is merged.
# ---------------------------------------------------------------------------


class TestIncomingCallDialogBaseline:
    """§1 has_active_call=False — Answer/Decline/keyboard baseline unchanged (tincan-6m2z0)."""

    @pytest.fixture()
    def dialog(self, qtbot, parent_widget):
        d = IncomingCallDialog(
            caller_name="Alice",
            caller_number="+15551234567",
            avatar_pixmap=None,
            parent=parent_widget,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    def test_answer_emits_answered_and_accepts(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.answered, timeout=1000):
            dialog._answer_btn.click()
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_decline_emits_declined_and_rejects(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.declined, timeout=1000):
            dialog._decline_btn.click()
        assert dialog.result() == dialog.DialogCode.Rejected

    def test_escape_emits_declined(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.declined, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    def test_answer_button_is_default(self, qtbot, dialog):
        assert dialog._answer_btn.isDefault()

    def test_enter_activates_answer(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.answered, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Return)

    def test_h_key_does_not_close_dialog(self, qtbot, dialog):
        """H key is a silent no-op in standard incoming mode (no active call)."""
        qtbot.keyClick(dialog, Qt.Key.Key_H)
        assert dialog.isVisible(), "H key must not close/accept dialog in standard mode"

    def test_r_key_does_not_close_dialog(self, qtbot, dialog):
        """R key is a silent no-op in standard incoming mode (no active call)."""
        qtbot.keyClick(dialog, Qt.Key.Key_R)
        assert dialog.isVisible(), "R key must not close/accept dialog in standard mode"


# ---------------------------------------------------------------------------
# §2  IncomingCallDialog — has_active_call=True: Call Waiting mode
#
# Dialog shows a mini active-call row and replaces Answer with
# Hold & Answer / Release & Answer.  H / R / Esc keyboard shortcuts apply.
# No button is the default button in this mode.
# ---------------------------------------------------------------------------


class TestIncomingCallDialogCallWaiting:
    """§2 has_active_call=True — Call Waiting mode (tincan-6m2z0 / tincan-o7yjg)."""

    @pytest.fixture()
    def dialog(self, qtbot, parent_widget):
        d = IncomingCallDialog(
            caller_name="Carol",
            caller_number="+15559876543",
            avatar_pixmap=None,
            parent=parent_widget,
            has_active_call=True,
            active_call_name="Alice",
            active_call_elapsed=42,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    def test_hold_and_answer_on_h_key(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.hold_and_answer_requested, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_H)

    def test_hold_and_answer_on_button_click(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.hold_and_answer_requested, timeout=1000):
            dialog._hold_btn.click()

    def test_hold_and_answer_accepts_dialog(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.hold_and_answer_requested, timeout=1000):
            dialog._hold_btn.click()
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_release_and_answer_on_r_key(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.release_and_answer_requested, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_R)

    def test_release_and_answer_on_button_click(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.release_and_answer_requested, timeout=1000):
            dialog._release_btn.click()

    def test_release_and_answer_accepts_dialog(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.release_and_answer_requested, timeout=1000):
            dialog._release_btn.click()
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_declined_on_esc(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.declined, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    def test_declined_on_decline_button(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.declined, timeout=1000):
            dialog._decline_btn.click()

    def test_no_default_button_in_call_waiting_mode(self, qtbot, dialog):
        default_btns = [b for b in dialog.findChildren(QPushButton) if b.isDefault()]
        assert default_btns == [], (
            f"Expected no default button, found: {[b.text() for b in default_btns]}"
        )

    def test_enter_does_not_fire_answered_signal(self, qtbot, dialog):
        """Enter must not answer the call in Call Waiting mode (no default button)."""
        received = []
        dialog.answered.connect(received.append)
        qtbot.keyClick(dialog, Qt.Key.Key_Return)
        assert received == []


# ---------------------------------------------------------------------------
# §3  InCallPanel — multi-call controls (tincan-6m2z0 / tincan-w59ao)
#
# add_call: idempotent (duplicate call_id updates state, not inserts duplicate).
# update_call_state / remove_call: no-op for unknown call_id.
# _multi_widget hidden with ≤1 calls; shown at 2+.
# _MultiCallControls shows Swap/EndAll for active+held; Hold&Release for active+waiting.
# Height: 88px with 1 call, 150px with 2+ calls.
# ---------------------------------------------------------------------------


class TestInCallPanelMultiCall:
    """§3 InCallPanel — idempotent add/remove, controls, height (tincan-6m2z0 / tincan-w59ao)."""

    @pytest.fixture()
    def panel(self, qtbot, parent_widget):
        p = InCallPanel(
            caller_name="Alice",
            avatar_pixmap=None,
            parent=parent_widget,
        )
        qtbot.addWidget(p)
        p.show()
        return p

    # --- idempotent add_call ---

    def test_add_call_duplicate_call_id_updates_not_inserts(self, qtbot, panel):
        """add_call with a call_id that already exists updates its state, no new row."""
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call0", "+15551111111", "inbound", "held")
        assert len(panel._calls) == 1
        assert panel._calls["call0"].state == "held"

    def test_add_call_distinct_ids_inserts_two_rows(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        assert len(panel._calls) == 2

    # --- no-op guards ---

    def test_update_call_state_unknown_call_id_noop(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.update_call_state("no-such-call", "held")  # must not raise

    def test_remove_call_unknown_call_id_noop(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.remove_call("no-such-call")  # must not raise
        assert len(panel._calls) == 1

    # --- multi_widget visibility ---

    def test_single_call_multi_widget_not_shown(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        assert not panel._multi_widget.isVisible()

    def test_two_calls_multi_widget_shown(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        assert panel._multi_widget.isVisible()

    def test_remove_returns_to_single_widget(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        panel.remove_call("call1")
        assert not panel._multi_widget.isVisible()

    # --- _MultiCallControls mode: active + held ---

    def test_active_and_held_shows_swap_and_end_all(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        assert panel._multi_ctrl._swap_btn.isVisible()
        assert panel._multi_ctrl._end_all_btn.isVisible()

    def test_active_and_held_hides_hold_and_release(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        assert not panel._multi_ctrl._hold_btn.isVisible()
        assert not panel._multi_ctrl._release_btn.isVisible()

    # --- _MultiCallControls mode: active + waiting ---

    def test_active_and_waiting_shows_hold_and_release(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15553333333", "inbound", "waiting")
        assert panel._multi_ctrl._hold_btn.isVisible()
        assert panel._multi_ctrl._release_btn.isVisible()

    def test_active_and_waiting_hides_swap_and_end_all(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15553333333", "inbound", "waiting")
        assert not panel._multi_ctrl._swap_btn.isVisible()
        assert not panel._multi_ctrl._end_all_btn.isVisible()

    # --- height transitions ---

    def test_height_88_with_single_call(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        assert panel.height() == 88

    def test_height_150_with_two_calls(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        assert panel.height() == 150

    def test_height_returns_to_88_after_remove(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        panel.remove_call("call1")
        assert panel.height() == 88

    # --- update_call_state affects mode ---

    def test_update_to_waiting_switches_to_hold_release_mode(self, qtbot, panel):
        panel.add_call("call0", "+15551111111", "inbound", "active")
        panel.add_call("call1", "+15552222222", "inbound", "held")
        panel.update_call_state("call1", "waiting")
        assert panel._multi_ctrl._hold_btn.isVisible()
        assert panel._multi_ctrl._release_btn.isVisible()
        assert not panel._multi_ctrl._swap_btn.isVisible()
