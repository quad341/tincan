"""Tests: MessageStore filter_new / add_messages / contains.
Bead: tincan-3llzu  (reviewer finding MEDIUM from tincan-7hsh)

Coverage:
  §1 MessageStore.contains
     - new store returns False for unknown handle
     - returns True after add_messages with that handle
     - case-sensitive ('A' != 'a')

  §2 MessageStore.filter_new
     - empty store: all messages pass through unchanged
     - known handle is filtered out; unknown passes through
     - message missing 'path' key (empty default) is excluded from add
       but treated as unknown → passes filter_new
     - filter_new is read-only (does not insert into store)

  §3 MessageStore.add_messages
     - batch-inserts multiple messages in one call
     - duplicate handle: second add_messages is safe (INSERT OR IGNORE)
     - message with no 'path' key is silently skipped
     - after add_messages, filter_new treats those handles as known

  §4 MessageStore persistence
     - close + reopen same db_path: previously-added handle still present
     - parent directory is created when it does not exist

  §5 MessageStore integration — incremental reconciliation
     - poll-1: 3 messages, all new → 3 pass filter_new
     - add poll-1 results, then poll-2: 2 old + 1 new → 1 passes
     - poll-3: all handles from poll-1 + poll-2 → 0 pass filter_new

Uses only sqlite3.connect(':memory:') / tmp_path — no real filesystem I/O
except for §4 (persistence requires a real file).
"""
from __future__ import annotations

from tincand.message_store import MessageStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path):
    """Open a fresh MessageStore backed by a temp file."""
    return MessageStore(tmp_path / "messages.db")


def _msg(path: str, sender: str = "Alice", ts: str = "10:00") -> dict:
    return {"path": path, "sender": sender, "timestamp": ts}


# ---------------------------------------------------------------------------
# §1 MessageStore.contains
# ---------------------------------------------------------------------------

class TestContains:
    """contains() reflects exact handle membership."""

    def test_new_store_returns_false(self, tmp_path):
        store = _store(tmp_path)
        assert store.contains("/telecom/msg/inbox/1") is False
        store.close()

    def test_true_after_add(self, tmp_path):
        store = _store(tmp_path)
        store.add_messages([_msg("/telecom/msg/inbox/1")])
        assert store.contains("/telecom/msg/inbox/1") is True
        store.close()

    def test_case_sensitive(self, tmp_path):
        store = _store(tmp_path)
        store.add_messages([_msg("/telecom/msg/inbox/A")])
        assert store.contains("/telecom/msg/inbox/a") is False
        store.close()


# ---------------------------------------------------------------------------
# §2 MessageStore.filter_new
# ---------------------------------------------------------------------------

class TestFilterNew:
    """filter_new() returns only unseen messages."""

    def test_empty_store_passes_all(self, tmp_path):
        store = _store(tmp_path)
        msgs = [_msg(f"/telecom/msg/inbox/{i}") for i in range(3)]
        assert store.filter_new(msgs) == msgs
        store.close()

    def test_known_handle_filtered(self, tmp_path):
        store = _store(tmp_path)
        m1 = _msg("/telecom/msg/inbox/1")
        m2 = _msg("/telecom/msg/inbox/2")
        store.add_messages([m1])
        result = store.filter_new([m1, m2])
        assert result == [m2]
        store.close()

    def test_no_path_message_passes_filter(self, tmp_path):
        store = _store(tmp_path)
        no_path = {"sender": "Bob"}
        result = store.filter_new([no_path])
        assert result == [no_path]
        store.close()

    def test_filter_new_is_read_only(self, tmp_path):
        store = _store(tmp_path)
        m = _msg("/telecom/msg/inbox/1")
        store.filter_new([m])
        # calling filter_new again should still return the same message
        assert store.filter_new([m]) == [m]
        store.close()


# ---------------------------------------------------------------------------
# §3 MessageStore.add_messages
# ---------------------------------------------------------------------------

class TestAddMessages:
    """add_messages() inserts handles, ignores duplicates, skips no-path."""

    def test_batch_insert_multiple(self, tmp_path):
        store = _store(tmp_path)
        msgs = [_msg(f"/telecom/msg/inbox/{i}") for i in range(5)]
        store.add_messages(msgs)
        for m in msgs:
            assert store.contains(m["path"]) is True
        store.close()

    def test_duplicate_is_safe(self, tmp_path):
        store = _store(tmp_path)
        m = _msg("/telecom/msg/inbox/1")
        store.add_messages([m])
        store.add_messages([m])  # must not raise
        assert store.contains("/telecom/msg/inbox/1") is True
        store.close()

    def test_no_path_key_skipped(self, tmp_path):
        store = _store(tmp_path)
        store.add_messages([{"sender": "Bob"}])
        # empty path is falsy — skipped
        assert store.contains("") is False
        store.close()

    def test_after_add_filter_sees_as_known(self, tmp_path):
        store = _store(tmp_path)
        msgs = [_msg(f"/telecom/msg/inbox/{i}") for i in range(3)]
        store.add_messages(msgs)
        assert store.filter_new(msgs) == []
        store.close()


# ---------------------------------------------------------------------------
# §4 MessageStore persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    """Handles survive close+reopen; parent directory is created."""

    def test_survives_close_reopen(self, tmp_path):
        db = tmp_path / "messages.db"
        store = MessageStore(db)
        store.add_messages([_msg("/telecom/msg/inbox/1")])
        store.close()
        store2 = MessageStore(db)
        assert store2.contains("/telecom/msg/inbox/1") is True
        store2.close()

    def test_creates_parent_directory(self, tmp_path):
        db = tmp_path / "nested" / "dir" / "messages.db"
        store = MessageStore(db)
        store.add_messages([_msg("/telecom/msg/inbox/1")])
        assert db.exists()
        store.close()


# ---------------------------------------------------------------------------
# §5 Integration — incremental reconciliation across polls
# ---------------------------------------------------------------------------

class TestIncrementalReconciliation:
    """Simulate the MAP poll loop: only genuinely new handles surface."""

    def test_three_poll_cycles(self, tmp_path):
        store = _store(tmp_path)

        poll1 = [_msg(f"/telecom/msg/inbox/{i}") for i in range(3)]
        new1 = store.filter_new(poll1)
        assert len(new1) == 3
        store.add_messages(new1)

        poll2 = poll1[:2] + [_msg("/telecom/msg/inbox/new")]
        new2 = store.filter_new(poll2)
        assert len(new2) == 1
        assert new2[0]["path"] == "/telecom/msg/inbox/new"
        store.add_messages(new2)

        poll3 = poll1 + [_msg("/telecom/msg/inbox/new")]
        new3 = store.filter_new(poll3)
        assert new3 == []

        store.close()
