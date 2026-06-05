"""Behavior tests: hide/archive conversations from the list (tincan-fbb7l).

Coverage:
  §1 ArchivedConversations store — archive, restore, persistence
  §2 ConversationListWidget — archive hides from active view
  §3 ConversationListWidget — show-archived mode shows hidden items
  §4 ConversationListWidget — restore returns item to active list
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.archived_conversations import ArchivedConversations
from tincan_gui.conversation_list import ConversationData, ConversationListWidget


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_data(name: str, phone: str) -> ConversationData:
    return ConversationData(id=phone, name=name, phone=phone, preview="hi", timestamp="10:00")


def _visible_names(w: ConversationListWidget) -> list[str]:
    return [item._data.name for item in w._items if item.isVisible()]


# ---------------------------------------------------------------------------
# §1  ArchivedConversations store
# ---------------------------------------------------------------------------

class TestArchivedConversationsStore:
    def test_archive_marks_id(self, tmp_path):
        store = ArchivedConversations(tmp_path)
        store.archive("+14155551111")
        assert store.is_archived("+14155551111")

    def test_unarchived_id_not_marked(self, tmp_path):
        store = ArchivedConversations(tmp_path)
        assert not store.is_archived("+14155551111")

    def test_restore_unmarks_id(self, tmp_path):
        store = ArchivedConversations(tmp_path)
        store.archive("+14155551111")
        store.restore("+14155551111")
        assert not store.is_archived("+14155551111")

    def test_all_archived_returns_set(self, tmp_path):
        store = ArchivedConversations(tmp_path)
        store.archive("+14155551111")
        store.archive("+14155552222")
        assert store.all_archived() == {"+14155551111", "+14155552222"}

    def test_persists_across_instances(self, tmp_path):
        s1 = ArchivedConversations(tmp_path)
        s1.archive("+14155551111")
        s2 = ArchivedConversations(tmp_path)
        assert s2.is_archived("+14155551111")

    def test_restore_persists_across_instances(self, tmp_path):
        s1 = ArchivedConversations(tmp_path)
        s1.archive("+14155551111")
        s1.restore("+14155551111")
        s2 = ArchivedConversations(tmp_path)
        assert not s2.is_archived("+14155551111")


# ---------------------------------------------------------------------------
# §2  archive_conversation hides item from active list
# ---------------------------------------------------------------------------

class TestArchiveHidesConversation:
    def test_archive_removes_from_active_view(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001"),
                               _make_data("Bob", "+14155550002")])
        w.archive_conversation("+14155550001")
        assert "Alice" not in _visible_names(w)

    def test_non_archived_remains_visible(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001"),
                               _make_data("Bob", "+14155550002")])
        w.archive_conversation("+14155550001")
        assert "Bob" in _visible_names(w)

    def test_reload_preserves_archive_state(self, qtbot, tmp_path):
        """After load_conversations, previously archived convs stay hidden."""
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001")])
        w.archive_conversation("+14155550001")
        # Simulate a refresh — same conversations reloaded
        w.load_conversations([_make_data("Alice", "+14155550001")])
        assert "Alice" not in _visible_names(w)


# ---------------------------------------------------------------------------
# §3  set_show_archived — archived-only view
# ---------------------------------------------------------------------------

class TestShowArchivedMode:
    def test_archived_visible_in_archived_mode(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001"),
                               _make_data("Bob", "+14155550002")])
        w.archive_conversation("+14155550001")
        w.set_show_archived(True)
        assert "Alice" in _visible_names(w)

    def test_active_hidden_in_archived_mode(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001"),
                               _make_data("Bob", "+14155550002")])
        w.archive_conversation("+14155550001")
        w.set_show_archived(True)
        assert "Bob" not in _visible_names(w)

    def test_returning_to_active_mode_restores_filter(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001"),
                               _make_data("Bob", "+14155550002")])
        w.archive_conversation("+14155550001")
        w.set_show_archived(True)
        w.set_show_archived(False)
        assert "Bob" in _visible_names(w)
        assert "Alice" not in _visible_names(w)


# ---------------------------------------------------------------------------
# §4  restore_conversation returns item to active list
# ---------------------------------------------------------------------------

class TestRestoreConversation:
    def test_restore_makes_item_visible_again(self, qtbot, tmp_path):
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001")])
        w.archive_conversation("+14155550001")
        w.restore_conversation("+14155550001")
        assert "Alice" in _visible_names(w)

    def test_restore_in_archived_mode_hides_item(self, qtbot, tmp_path):
        """After restore, item no longer shows in archived mode."""
        store = ArchivedConversations(tmp_path)
        w = ConversationListWidget(archived=store)
        qtbot.addWidget(w)
        w.load_conversations([_make_data("Alice", "+14155550001")])
        w.archive_conversation("+14155550001")
        w.set_show_archived(True)
        w.restore_conversation("+14155550001")
        assert "Alice" not in _visible_names(w)
