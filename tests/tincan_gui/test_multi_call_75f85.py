"""Behavioral tests for CallWaitingDialog and MultiCallPanel (tincan-75f85).

Coverage:
  §1 CallWaitingDialog — buttons, keyboard shortcuts, caller info display
  §2 MultiCallPanel — state layout, signal dispatch, state badges
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

import tincan_gui.call_panel as _cp_module
from tincan_gui.call_panel import CallEntry, CallWaitingDialog, MultiCallPanel


# ---------------------------------------------------------------------------
# Shared fixtures
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
    """Replace AvatarWidget with a plain QLabel to decouple from the size= kwarg issue."""
    def _fake_avatar(name, size=None, parent=None):
        lbl = QLabel(name[:2].upper() if name else "?")
        if size:
            lbl.setFixedSize(size, size)
        return lbl

    with patch.object(_cp_module, "AvatarWidget", side_effect=_fake_avatar):
        yield


# ---------------------------------------------------------------------------
# §1 CallWaitingDialog
# ---------------------------------------------------------------------------

class TestCallWaitingDialog:
    """CallWaitingDialog buttons, keyboard shortcuts, and caller info display."""

    @pytest.fixture()
    def dialog(self, qtbot, parent_widget):
        d = CallWaitingDialog(
            waiting_name="Carol",
            waiting_number="+15559876543",
            active_name="Bob",
            active_elapsed=42,
            parent=parent_widget,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    def test_hold_and_answer_emits_signal_and_accepts(self, qtbot, dialog):
        """Hold & Answer emits hold_and_answer_requested and closes as Accepted."""
        received = []
        dialog.hold_and_answer_requested.connect(lambda: received.append("hold_and_answer"))

        with qtbot.waitSignal(dialog.hold_and_answer_requested, timeout=1000):
            dialog._hold_btn.click()

        assert received == ["hold_and_answer"]
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_release_and_answer_emits_signal_and_accepts(self, qtbot, dialog):
        """Release & Answer emits release_and_answer_requested and closes as Accepted."""
        received = []
        dialog.release_and_answer_requested.connect(lambda: received.append("release_and_answer"))

        with qtbot.waitSignal(dialog.release_and_answer_requested, timeout=1000):
            dialog._release_btn.click()

        assert received == ["release_and_answer"]
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_decline_emits_signal_and_rejects(self, qtbot, dialog):
        """Clicking Decline emits declined and closes as Rejected."""
        received = []
        dialog.declined.connect(lambda: received.append("declined"))

        with qtbot.waitSignal(dialog.declined, timeout=1000):
            dialog._decline_btn.click()

        assert received == ["declined"]
        assert dialog.result() == dialog.DialogCode.Rejected

    def test_escape_emits_declined_and_rejects(self, qtbot, dialog):
        """Pressing Escape emits declined and closes as Rejected."""
        received = []
        dialog.declined.connect(lambda: received.append("declined"))

        with qtbot.waitSignal(dialog.declined, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Escape)

        assert received == ["declined"]
        assert dialog.result() == dialog.DialogCode.Rejected

    def test_key_h_emits_hold_and_answer_and_accepts(self, qtbot, dialog):
        """Pressing H emits hold_and_answer_requested and closes as Accepted."""
        received = []
        dialog.hold_and_answer_requested.connect(lambda: received.append("hold_and_answer"))

        with qtbot.waitSignal(dialog.hold_and_answer_requested, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_H)

        assert received == ["hold_and_answer"]
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_key_r_emits_release_and_answer_and_accepts(self, qtbot, dialog):
        """Pressing R emits release_and_answer_requested and closes as Accepted."""
        received = []
        dialog.release_and_answer_requested.connect(lambda: received.append("release_and_answer"))

        with qtbot.waitSignal(dialog.release_and_answer_requested, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_R)

        assert received == ["release_and_answer"]
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_waiting_caller_name_displayed(self, qtbot, parent_widget):
        """Dialog shows the waiting caller's name."""
        dialog = CallWaitingDialog(
            waiting_name="Carol",
            waiting_number="+15559876543",
            active_name="Bob",
            active_elapsed=0,
            parent=parent_widget,
        )
        qtbot.addWidget(dialog)

        labels = [lbl for lbl in dialog.findChildren(QLabel) if lbl.text() == "Carol"]
        assert labels, "No QLabel showing waiting caller name 'Carol'"

    def test_waiting_number_shown_when_no_name(self, qtbot, parent_widget):
        """When waiting_name is empty the phone number is shown instead."""
        dialog = CallWaitingDialog(
            waiting_name="",
            waiting_number="+15559876543",
            active_name="Bob",
            active_elapsed=0,
            parent=parent_widget,
        )
        qtbot.addWidget(dialog)

        labels = [lbl for lbl in dialog.findChildren(QLabel) if lbl.text() == "+15559876543"]
        assert labels, "No QLabel showing waiting number '+15559876543'"

    def test_active_caller_name_displayed_in_mini_row(self, qtbot, parent_widget):
        """The active-call mini-row shows the active caller's name."""
        dialog = CallWaitingDialog(
            waiting_name="Carol",
            waiting_number="+15559876543",
            active_name="Bob",
            active_elapsed=0,
            parent=parent_widget,
        )
        qtbot.addWidget(dialog)

        labels = [lbl for lbl in dialog.findChildren(QLabel) if lbl.text() == "Bob"]
        assert labels, "No QLabel showing active caller name 'Bob' in the mini-row"


# ---------------------------------------------------------------------------
# §2 MultiCallPanel
# ---------------------------------------------------------------------------

class TestMultiCallPanel:
    """MultiCallPanel state layout, signal dispatch, and state badge content."""

    @pytest.fixture()
    def panel(self, qtbot, parent_widget):
        p = MultiCallPanel(parent=parent_widget)
        qtbot.addWidget(p)
        p.show()
        return p

    def _entry(self, call_id="cid-1", name="Alice", state="active", elapsed=0):
        return CallEntry(
            call_id=call_id,
            name=name,
            avatar_pixmap=None,
            state=state,
            elapsed=elapsed,
        )

    # ------------------------------------------------------------------
    # Layout: single active call
    # ------------------------------------------------------------------

    def test_single_active_height_is_88(self, panel):
        """Single active call: panel height is 88px."""
        panel.update_calls([self._entry(state="active")])

        assert panel.height() == 88

    def test_single_active_no_swap_visible(self, panel):
        """Single active call: Swap Calls is not visible."""
        panel.update_calls([self._entry(state="active")])

        assert not panel._swap_btn.isVisible()

    def test_single_active_no_end_all_visible(self, panel):
        """Single active call: End All Calls is not visible."""
        panel.update_calls([self._entry(state="active")])

        assert not panel._end_all_btn.isVisible()

    def test_single_active_hang_up_present(self, panel):
        """Single active call: a Hang Up button is present in the row."""
        panel.update_calls([self._entry(state="active")])

        hang_btns = [b for b in panel.findChildren(QPushButton) if "Hang" in b.text()]
        assert hang_btns, "No Hang Up button found for single active call"

    # ------------------------------------------------------------------
    # Layout: active + held
    # ------------------------------------------------------------------

    def test_active_held_height_is_132(self, panel):
        """Active + held: panel height is 132px."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="b", name="Bob", state="held"),
        ])

        assert panel.height() == 132

    def test_active_held_swap_visible(self, panel):
        """Active + held: Swap Calls is visible."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="b", name="Bob", state="held"),
        ])

        assert panel._swap_btn.isVisible()

    def test_active_held_end_all_visible(self, panel):
        """Active + held: End All Calls is visible."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="b", name="Bob", state="held"),
        ])

        assert panel._end_all_btn.isVisible()

    def test_active_held_two_hang_up_buttons(self, panel):
        """Active + held: two Hang Up buttons — one per row."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="b", name="Bob", state="held"),
        ])

        hang_btns = [b for b in panel.findChildren(QPushButton) if "Hang" in b.text()]
        assert len(hang_btns) == 2

    # ------------------------------------------------------------------
    # Layout: active + waiting
    # ------------------------------------------------------------------

    def test_active_waiting_end_all_visible(self, panel):
        """Active + waiting: End All Calls is visible."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        assert panel._end_all_btn.isVisible()

    def test_active_waiting_swap_not_visible(self, panel):
        """Active + waiting: Swap Calls is NOT visible (no held call in the pair)."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        assert not panel._swap_btn.isVisible()

    def test_active_waiting_active_row_has_hang_up(self, panel):
        """Active + waiting: the active row shows a Hang Up button."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        hang_btns = [b for b in panel.findChildren(QPushButton) if "Hang" in b.text()]
        assert hang_btns, "Active row must have a Hang Up button"

    def test_active_waiting_waiting_row_has_hold_and_answer(self, panel):
        """Active + waiting: waiting row shows Hold & Answer."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        hold_btns = [b for b in panel.findChildren(QPushButton) if "Hold" in b.text()]
        assert hold_btns, "Waiting row must have a Hold & Answer button"

    def test_active_waiting_waiting_row_has_release_and_answer(self, panel):
        """Active + waiting: waiting row shows Release & Answer."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        release_btns = [b for b in panel.findChildren(QPushButton) if "Release" in b.text()]
        assert release_btns, "Waiting row must have a Release & Answer button"

    def test_active_waiting_waiting_row_has_decline(self, panel):
        """Active + waiting: waiting row shows Decline."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        decline_btns = [b for b in panel.findChildren(QPushButton) if b.text() == "Decline"]
        assert decline_btns, "Waiting row must have a Decline button"

    def test_solo_waiting_row_has_no_hang_up(self, panel):
        """Waiting-only row has no Hang Up button."""
        panel.update_calls([self._entry(call_id="c", name="Carol", state="waiting")])

        hang_btns = [b for b in panel.findChildren(QPushButton) if "Hang" in b.text()]
        assert not hang_btns, "Waiting row must NOT have a Hang Up button"

    # ------------------------------------------------------------------
    # Signal dispatch
    # ------------------------------------------------------------------

    def test_hang_up_emits_active_call_id(self, panel):
        """Hang Up on an active call emits hang_up_requested with the correct call_id."""
        panel.update_calls([self._entry(call_id="call-active-1", state="active")])

        received = []
        panel.hang_up_requested.connect(received.append)

        hang_btn = next(b for b in panel.findChildren(QPushButton) if "Hang" in b.text())
        hang_btn.click()

        assert received == ["call-active-1"]

    def test_hang_up_emits_held_call_id(self, panel):
        """Hang Up on a held call emits hang_up_requested with the correct call_id."""
        panel.update_calls([self._entry(call_id="call-held-7", state="held")])

        received = []
        panel.hang_up_requested.connect(received.append)

        hang_btn = next(b for b in panel.findChildren(QPushButton) if "Hang" in b.text())
        hang_btn.click()

        assert received == ["call-held-7"]

    def test_swap_calls_emits_swap_requested(self, qtbot, panel):
        """Clicking Swap Calls emits swap_requested."""
        panel.update_calls([
            self._entry(call_id="a", state="active"),
            self._entry(call_id="b", state="held"),
        ])

        with qtbot.waitSignal(panel.swap_requested, timeout=1000):
            panel._swap_btn.click()

    def test_end_all_calls_emits_end_all_requested(self, qtbot, panel):
        """Clicking End All Calls emits end_all_requested."""
        panel.update_calls([
            self._entry(call_id="a", state="active"),
            self._entry(call_id="b", state="held"),
        ])

        with qtbot.waitSignal(panel.end_all_requested, timeout=1000):
            panel._end_all_btn.click()

    def test_hold_and_answer_inline_emits_signal(self, qtbot, panel):
        """Clicking Hold & Answer in the waiting row emits hold_and_answer_requested."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        hold_btn = next(b for b in panel.findChildren(QPushButton) if "Hold" in b.text())

        with qtbot.waitSignal(panel.hold_and_answer_requested, timeout=1000):
            hold_btn.click()

    def test_release_and_answer_inline_emits_signal(self, qtbot, panel):
        """Clicking Release & Answer in the waiting row emits release_and_answer_requested."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        release_btn = next(b for b in panel.findChildren(QPushButton) if "Release" in b.text())

        with qtbot.waitSignal(panel.release_and_answer_requested, timeout=1000):
            release_btn.click()

    def test_decline_waiting_inline_emits_signal(self, qtbot, panel):
        """Clicking Decline in the waiting row emits decline_waiting_requested."""
        panel.update_calls([
            self._entry(call_id="a", name="Alice", state="active"),
            self._entry(call_id="c", name="Carol", state="waiting"),
        ])

        decline_btn = next(b for b in panel.findChildren(QPushButton) if b.text() == "Decline")

        with qtbot.waitSignal(panel.decline_waiting_requested, timeout=1000):
            decline_btn.click()

    # ------------------------------------------------------------------
    # State badges
    # ------------------------------------------------------------------

    def test_active_state_badge_text(self, panel):
        """Active call row shows the '● ACTIVE' state badge."""
        panel.update_calls([self._entry(state="active")])

        badges = [lbl for lbl in panel.findChildren(QLabel)
                  if lbl.accessibleName().startswith("Call state:")]
        active_badge = next((b for b in badges if "ACTIVE" in b.accessibleName()), None)
        assert active_badge is not None, "No 'Call state: ACTIVE' badge found"
        assert "ACTIVE" in active_badge.text()

    def test_held_state_badge_text(self, panel):
        """Held call row shows the '⏸ HELD' state badge."""
        panel.update_calls([self._entry(state="held")])

        badges = [lbl for lbl in panel.findChildren(QLabel)
                  if lbl.accessibleName().startswith("Call state:")]
        held_badge = next((b for b in badges if "HELD" in b.accessibleName()), None)
        assert held_badge is not None, "No 'Call state: HELD' badge found"
        assert "HELD" in held_badge.text()

    def test_waiting_state_badge_text(self, panel):
        """Waiting call row shows the '⏳ WAITING' state badge."""
        panel.update_calls([self._entry(state="waiting")])

        badges = [lbl for lbl in panel.findChildren(QLabel)
                  if lbl.accessibleName().startswith("Call state:")]
        waiting_badge = next((b for b in badges if "WAITING" in b.accessibleName()), None)
        assert waiting_badge is not None, "No 'Call state: WAITING' badge found"
        assert "WAITING" in waiting_badge.text()
