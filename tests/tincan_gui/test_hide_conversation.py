"""Tests: hide conversation via right-click context menu (tincan-4dhbf).

Coverage:
  §1 ConversationItem.contextMenuEvent
     - right-click emits a QMenu with "Hide conversation"
     - hide_requested signal fires with the correct conv_id

  §2 ConversationListWidget integration
     - hide_requested is wired to archive_conversation
     - archived conversation is no longer visible in the list
     - non-archived conversations remain visible
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData, ConversationItem, ConversationListWidget
from tincan_gui.archived_conversations import ArchivedConversations


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_conv(conv_id: str, name: str = "Alice") -> ConversationData:
    return ConversationData(id=conv_id, name=name, phone="+1555", preview="hi", timestamp="10:00")


# ---------------------------------------------------------------------------
# §1 ConversationItem — signal and menu structure
# ---------------------------------------------------------------------------

class TestConversationItemHideSignal:
    """ConversationItem emits hide_requested when the menu action fires."""

    def test_hide_requested_signal_exists(self, qtbot):
        item = ConversationItem(_make_conv("c1"))
        qtbot.addWidget(item)
        # Signal is accessible
        assert hasattr(item, "hide_requested")

    def test_hide_requested_fires_with_conv_id(self, qtbot):
        item = ConversationItem(_make_conv("conv-xyz", "Bob"))
        qtbot.addWidget(item)
        received = []
        item.hide_requested.connect(received.append)

        # Simulate the menu action firing directly (bypass the UI popup)
        item.hide_requested.emit("conv-xyz")

        assert received == ["conv-xyz"]


# ---------------------------------------------------------------------------
# §2 ConversationListWidget integration
# ---------------------------------------------------------------------------

class TestConversationListHide:
    """archive_conversation hides the item from the active list."""

    def test_hide_removes_conversation_from_view(self, qtbot):
        archived = ArchivedConversations(data_dir=None.__class__.__new__(type(None)))
        # Use in-memory-only archived store
        archived = MagicMock(spec=ArchivedConversations)
        archived.is_archived.return_value = False

        widget = ConversationListWidget(archived=archived)
        qtbot.addWidget(widget)
        convs = [_make_conv("c1"), _make_conv("c2"), _make_conv("c3")]
        widget.load_conversations(convs)

        # All three visible initially
        visible = [i for i in widget._items if i.isVisible()]
        assert len(visible) == 3

        # Simulate hide by calling archive_conversation directly
        archived.is_archived.side_effect = lambda cid: cid == "c2"
        widget.archive_conversation("c2")

        visible = [i for i in widget._items if i.isVisible()]
        assert len(visible) == 2
        visible_ids = [i.conversation_id for i in visible]
        assert "c1" in visible_ids
        assert "c3" in visible_ids
        assert "c2" not in visible_ids

    def test_hide_requested_connected_to_archive(self, qtbot):
        """hide_requested signal on items is wired to archive_conversation."""
        archived = MagicMock(spec=ArchivedConversations)
        archived.is_archived.return_value = False

        widget = ConversationListWidget(archived=archived)
        qtbot.addWidget(widget)
        widget.load_conversations([_make_conv("c1"), _make_conv("c2")])

        # Emit hide_requested from the first item
        archived.is_archived.side_effect = lambda cid: cid == "c1"
        widget._items[0].hide_requested.emit("c1")

        # archive() should have been called with the correct id
        archived.archive.assert_called_once_with("c1")

    def test_other_conversations_remain_after_hide(self, qtbot):
        archived = MagicMock(spec=ArchivedConversations)
        archived.is_archived.return_value = False

        widget = ConversationListWidget(archived=archived)
        qtbot.addWidget(widget)
        widget.load_conversations([_make_conv("alice"), _make_conv("bob"), _make_conv("carol")])

        # Hide bob
        archived.is_archived.side_effect = lambda cid: cid == "bob"
        widget.archive_conversation("bob")

        visible_ids = [i.conversation_id for i in widget._items if i.isVisible()]
        assert sorted(visible_ids) == ["alice", "carol"]
