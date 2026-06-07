"""Tests: copy selected text to clipboard fix (tincan-qtri7).

Coverage:
  §1 MessageBubble.contextMenuEvent — copy_act branch
     - copy_act writes only the selected portion to clipboard (not full body)
     - copy_act is a no-op when body label has no selection
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData

_BODY = "hello world"  # plain ASCII, no HTML escaping, known char positions


def _make_bubble(body: str, qtbot) -> MessageBubble:
    data = MessageData(BubbleType.INBOUND, body, "Alice", "10:00")
    with patch("tincan_gui.thread_view.is_dark_theme", return_value=False):
        bubble = MessageBubble(data)
    qtbot.addWidget(bubble)
    bubble.show()
    return bubble


def _make_mock_menu_returning_copy_act():
    """Return (mock_menu, copy_act) where exec() returns copy_act.

    addAction side_effect yields distinct mocks so identity checks
    (chosen is copy_act, chosen is copy_msg_act, …) behave correctly.
    """
    copy_act = MagicMock(name="copy_act")
    copy_msg_act = MagicMock(name="copy_msg_act")
    copy_link_act = MagicMock(name="copy_link_act")
    select_all_act = MagicMock(name="select_all_act")

    menu = MagicMock(name="mock_menu")
    menu.addAction.side_effect = [copy_act, copy_msg_act, copy_link_act, select_all_act]
    menu.exec.return_value = copy_act  # simulate user picking "Copy"
    return menu, copy_act


def _fake_event() -> MagicMock:
    event = MagicMock()
    event.globalPos.return_value = QPoint(0, 0)
    return event


class TestMessageBubbleCopyAct:
    """copy_act handler writes selected text to clipboard (tincan-qtri7)."""

    def test_copy_selected_text_written_to_clipboard(self, qtbot):
        """Selecting a word and invoking copy_act puts only that word on the clipboard."""
        bubble = _make_bubble(_BODY, qtbot)

        # Select "hello" (first 5 chars) — proves selectedText(), not full body, is copied
        bubble._body_label.setSelection(0, 5)
        assert bubble._body_label.hasSelectedText(), "precondition: setSelection must select text"
        assert bubble._body_label.selectedText() == "hello"

        QApplication.clipboard().clear()

        mock_menu, _ = _make_mock_menu_returning_copy_act()
        with patch("tincan_gui.thread_view.QMenu", return_value=mock_menu):
            bubble.contextMenuEvent(_fake_event())

        assert QApplication.clipboard().text() == "hello"

    def test_copy_act_leaves_clipboard_unchanged_with_no_selection(self, qtbot):
        """copy_act must not modify the clipboard when no text is selected."""
        bubble = _make_bubble(_BODY, qtbot)

        assert not bubble._body_label.hasSelectedText(), "precondition: nothing selected"

        QApplication.clipboard().setText("sentinel")

        mock_menu, _ = _make_mock_menu_returning_copy_act()
        with patch("tincan_gui.thread_view.QMenu", return_value=mock_menu):
            bubble.contextMenuEvent(_fake_event())

        # 'if selected:' guard must prevent clipboard write
        assert QApplication.clipboard().text() == "sentinel"
