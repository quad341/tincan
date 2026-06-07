"""Behavioral acceptance tests for call_panel.py (tincan-fx79v.4).

Coverage:
  §1 IncomingCallDialog — Answer/Decline buttons and keyboard shortcuts
  §2 InCallPanel — timer, Hold toggle, Hang Up, Keypad toggle
  §3 DTMFKeypad — key press emits signal and updates display
  §4 AudioErrorPanel — Retry and Hang Up emit correct signals
  §5 Known API regression — AvatarWidget must accept a size kwarg (call_panel.py uses it)

NOTE: §5 documents a bug in call_panel.py: it calls AvatarWidget(name, size=N) but
AvatarWidget.__init__ only accepts (name, parent=None). The §1-§4 suites patch
AvatarWidget to bypass this bug and test the dialog/panel behavior in isolation.
Once the builder fixes call_panel.py (or AvatarWidget) to accept size=N, the
patch can be removed and the §5 test will start passing.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

import tincan_gui.call_panel as _cp_module
from tincan_gui.call_panel import (
    AudioErrorPanel,
    DTMFKeypad,
    InCallPanel,
    IncomingCallDialog,
)


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
    """Replace AvatarWidget with a plain QLabel so call_panel.py instantiates cleanly.

    call_panel.py calls AvatarWidget(name, size=N) but the real AvatarWidget only
    accepts (name, parent=None).  Patch it here so the behavioral tests can run
    independently of that implementation bug.  See §5 for the explicit regression test.
    """
    def _fake_avatar(name, size=None, parent=None):
        lbl = QLabel(name[:2].upper() if name else "?")
        lbl.setFixedSize(size or 44, size or 44)
        return lbl

    with patch.object(_cp_module, "AvatarWidget", side_effect=_fake_avatar):
        yield


# ---------------------------------------------------------------------------
# §1 IncomingCallDialog
# ---------------------------------------------------------------------------

class TestIncomingCallDialog:
    """IncomingCallDialog emits the correct signals on user actions (tincan-fx79v)."""

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
        """Clicking Answer emits answered and closes dialog as accepted."""
        received = []
        dialog.answered.connect(lambda: received.append("answered"))

        with qtbot.waitSignal(dialog.answered, timeout=1000):
            dialog._answer_btn.click()

        assert received == ["answered"]
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_decline_emits_declined_and_rejects(self, qtbot, dialog):
        """Clicking Decline emits declined and closes dialog as rejected."""
        received = []
        dialog.declined.connect(lambda: received.append("declined"))

        with qtbot.waitSignal(dialog.declined, timeout=1000):
            dialog._decline_btn.click()

        assert received == ["declined"]
        assert dialog.result() == dialog.DialogCode.Rejected

    def test_escape_emits_declined(self, qtbot, dialog):
        """Pressing Esc triggers decline (emits declined signal)."""
        received = []
        dialog.declined.connect(lambda: received.append("declined"))

        with qtbot.waitSignal(dialog.declined, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Escape)

        assert received == ["declined"]

    def test_enter_activates_answer_default_button(self, qtbot, dialog):
        """Pressing Enter activates the Answer button (it is the default button)."""
        assert dialog._answer_btn.isDefault(), "Answer button must be the default button"

        received = []
        dialog.answered.connect(lambda: received.append("answered"))

        with qtbot.waitSignal(dialog.answered, timeout=1000):
            qtbot.keyClick(dialog, Qt.Key.Key_Return)

        assert received == ["answered"]


# ---------------------------------------------------------------------------
# §2 InCallPanel
# ---------------------------------------------------------------------------

class TestInCallPanel:
    """InCallPanel timer, Hold, Hang Up, and Keypad controls (tincan-fx79v)."""

    @pytest.fixture()
    def panel(self, qtbot, parent_widget):
        p = InCallPanel(
            caller_name="Bob",
            avatar_pixmap=None,
            parent=parent_widget,
        )
        qtbot.addWidget(p)
        p.show()
        return p

    def test_timer_ticks_to_one_second(self, qtbot, panel):
        """Timer label advances from 0:00:00 to 0:00:01 after one tick."""
        assert panel._timer_lbl.text() == "0:00:00"
        qtbot.wait(1200)
        assert panel._timer_lbl.text() == "0:00:01"

    def test_hold_toggle_changes_text_and_emits_signal(self, qtbot, panel):
        """Toggling Hold changes button label to 'Resume' and emits hold_toggled(True)."""
        received = []
        panel.hold_toggled.connect(received.append)

        panel._hold_btn.click()

        assert received == [True]
        assert "Resume" in panel._hold_btn.text()

    def test_hang_up_emits_signal(self, qtbot, panel):
        """Clicking Hang Up emits hang_up_requested."""
        from PySide6.QtWidgets import QPushButton
        hang_btn = next(b for b in panel.findChildren(QPushButton) if "Hang" in b.text())

        with qtbot.waitSignal(panel.hang_up_requested, timeout=1000):
            hang_btn.click()

    def test_keypad_toggle_emits_signal(self, qtbot, panel):
        """Toggling Keypad button emits keypad_toggled(True)."""
        received = []
        panel.keypad_toggled.connect(received.append)

        panel._keypad_btn.click()

        assert received == [True]


# ---------------------------------------------------------------------------
# §3 DTMFKeypad
# ---------------------------------------------------------------------------

class TestDTMFKeypad:
    """DTMFKeypad emits tone_pressed and updates display (tincan-fx79v)."""

    @pytest.fixture()
    def keypad(self, qtbot, parent_widget):
        k = DTMFKeypad(parent=parent_widget)
        qtbot.addWidget(k)
        k.show()
        return k

    def test_key_5_emits_tone_pressed_and_updates_display(self, qtbot, keypad):
        """Pressing the '5' button emits tone_pressed('5') and appends '5' to display."""
        received = []
        keypad.tone_pressed.connect(received.append)

        from PySide6.QtWidgets import QPushButton
        btn_5 = next(b for b in keypad.findChildren(QPushButton) if b.text() == "5")
        btn_5.click()

        assert received == ["5"]
        assert keypad._display.text() == "5"


# ---------------------------------------------------------------------------
# §4 AudioErrorPanel
# ---------------------------------------------------------------------------

class TestAudioErrorPanel:
    """AudioErrorPanel Retry and Hang Up buttons emit the correct signals (tincan-fx79v)."""

    @pytest.fixture()
    def panel(self, qtbot, parent_widget):
        p = AudioErrorPanel(parent=parent_widget)
        qtbot.addWidget(p)
        p.show()
        return p

    def test_retry_button_emits_retry_requested(self, qtbot, panel):
        """Clicking Retry emits retry_requested."""
        from PySide6.QtWidgets import QPushButton
        retry_btn = next(b for b in panel.findChildren(QPushButton) if "Retry" in b.text())

        with qtbot.waitSignal(panel.retry_requested, timeout=1000):
            retry_btn.click()

    def test_hang_up_button_emits_hang_up_requested(self, qtbot, panel):
        """Clicking Hang Up emits hang_up_requested."""
        from PySide6.QtWidgets import QPushButton
        hang_btn = next(b for b in panel.findChildren(QPushButton) if "Hang" in b.text())

        with qtbot.waitSignal(panel.hang_up_requested, timeout=1000):
            hang_btn.click()


# ---------------------------------------------------------------------------
# §5 AvatarWidget API regression
# ---------------------------------------------------------------------------

class TestAvatarWidgetSizeKwarg:
    """call_panel.py requires AvatarWidget to accept a size= keyword argument.

    This test will fail until either call_panel.py is updated to use the
    current AvatarWidget(name, parent=None) signature, or AvatarWidget itself
    is extended to accept a size= parameter.
    """

    def test_avatar_widget_accepts_size_kwarg(self):
        """AvatarWidget(name, size=N) must not raise TypeError."""
        from tincan_gui.avatar import AvatarWidget

        # Ensure it doesn't raise — we don't need to show it
        try:
            _widget = AvatarWidget("Alice", size=68)
        except TypeError as exc:
            pytest.fail(
                f"AvatarWidget does not accept size= kwarg but call_panel.py uses it: {exc}"
            )
