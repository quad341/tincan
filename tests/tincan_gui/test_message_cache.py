"""Unit tests for MessageCache (tincan_gui/message_cache.py)."""
import pytest

from tincan_gui.message_cache import MessageCache, _safe_name


class TestSafeName:
    def test_strips_non_alnum(self):
        assert _safe_name("+1 (815) 791-6347") == "18157916347"

    def test_truncates_at_40(self):
        assert len(_safe_name("a" * 100)) == 40

    def test_empty_falls_back_to_unknown(self):
        assert _safe_name("") == "unknown"

    def test_preserves_lowercase(self):
        assert _safe_name("ABC123") == "abc123"


class TestMessageCache:
    @pytest.fixture
    def cache(self, tmp_path):
        return MessageCache(cache_dir=tmp_path)

    def test_empty_conv_returns_empty_list(self, cache):
        assert cache.get_messages("+18005551234") == []

    def test_add_and_retrieve(self, cache):
        cache.add_message(
            "+18005551234", "inbound", "hello", "Alice", "20260605T143025", "20260605T143025"
        )
        msgs = cache.get_messages("+18005551234")
        assert len(msgs) == 1
        assert msgs[0]["body"] == "hello"
        assert msgs[0]["direction"] == "inbound"
        assert msgs[0]["sender"] == "Alice"

    def test_dedup_same_key(self, cache):
        cache.add_message("+1", "inbound", "hi", "", "20260605T100000", "20260605T100000")
        cache.add_message("+1", "inbound", "hi", "", "20260605T100000", "20260605T100000")
        assert len(cache.get_messages("+1")) == 1

    def test_dedup_different_direction_not_duped(self, cache):
        cache.add_message("+1", "inbound", "hi", "", "20260605T100000", "20260605T100000")
        cache.add_message("+1", "outbound", "hi", "", "20260605T100000", "20260605T100000")
        assert len(cache.get_messages("+1")) == 2

    def test_empty_body_skipped(self, cache):
        cache.add_message("+1", "inbound", "", "", "20260605T100000", "20260605T100000")
        assert cache.get_messages("+1") == []

    def test_persists_to_disk(self, tmp_path):
        c1 = MessageCache(cache_dir=tmp_path)
        c1.add_message("conv1", "outbound", "sent", "", "20260605T120000", "20260605T120000")
        c2 = MessageCache(cache_dir=tmp_path)
        msgs = c2.get_messages("conv1")
        assert len(msgs) == 1
        assert msgs[0]["body"] == "sent"

    def test_trims_to_max_500(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        for i in range(510):
            cache.add_message("c", "inbound", f"msg{i}", "", f"202606{i:06d}", f"202606{i:06d}")
        assert len(cache.get_messages("c")) == 500

    def test_multiple_conversations_isolated(self, cache):
        cache.add_message("alice", "inbound", "hi alice", "", "t1", "t1")
        cache.add_message("bob", "inbound", "hi bob", "", "t2", "t2")
        assert cache.get_messages("alice")[0]["body"] == "hi alice"
        assert cache.get_messages("bob")[0]["body"] == "hi bob"

    def test_corrupted_file_returns_empty(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        (tmp_path / "conv1.json").write_text("not json{{")
        assert cache.get_messages("conv1") == []


class TestOutboundSortKeyGuard:
    """add_message() guard: shorter outbound body at same sort_key is skipped.

    MAP sent-folder echoes use Subject (preview) as body — a truncated form
    of the full message the user typed.  When the full body is already in the
    cache at the same sort_key, the shorter echo must not overwrite or
    duplicate it.
    """

    @pytest.fixture
    def cache(self, tmp_path):
        return MessageCache(cache_dir=tmp_path)

    def test_shorter_body_skipped_when_longer_cached_at_sort_key(self, cache):
        """MAP echo with shorter body at matching sort_key must be silently dropped."""
        cache.add_message("+1", "outbound", "Full message body", "", "T1", "T1")
        cache.add_message("+1", "outbound", "Full message", "", "T1", "T1")
        msgs = cache.get_messages("+1")
        assert len(msgs) == 1
        assert msgs[0]["body"] == "Full message body"

    def test_longer_body_not_blocked_by_guard(self, cache):
        """A longer body arriving at the same sort_key is not blocked."""
        cache.add_message("+1", "outbound", "Short", "", "T1", "T1")
        cache.add_message("+1", "outbound", "Short but extended here", "", "T1", "T1")
        # Guard only fires when existing > incoming; incoming longer → both stored.
        msgs = cache.get_messages("+1")
        assert len(msgs) == 2

    def test_guard_bypassed_when_sort_key_empty(self, cache):
        """Empty sort_key disables the guard — different bodies are both stored."""
        cache.add_message("+1", "outbound", "Full message body", "", "T1", "")
        cache.add_message("+1", "outbound", "Full message", "", "T2", "")
        # sort_key is falsy → guard inactive; different bodies → not exact-deduped.
        msgs = cache.get_messages("+1")
        assert len(msgs) == 2

    def test_guard_is_scoped_to_conversation(self, cache):
        """A longer body in conversation A does not block a shorter body in B."""
        cache.add_message("alice", "outbound", "Full message body", "", "T1", "T1")
        cache.add_message("bob", "outbound", "Full message", "", "T1", "T1")
        assert cache.get_messages("bob")[0]["body"] == "Full message"


class TestMergeInto:
    """merge_into: copy messages from old (miskeyed) cache into canonical cache."""

    def test_copies_missing_messages_to_dest(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        cache.add_message("5551234567", "inbound", "hello", "", "t1", "t1")
        cache.merge_into("+15551234567", "5551234567")
        msgs = cache.get_messages("+15551234567")
        assert len(msgs) == 1
        assert msgs[0]["body"] == "hello"

    def test_dedup_no_double_on_repeated_merge(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        cache.add_message("5551234567", "inbound", "hello", "", "t1", "t1")
        cache.merge_into("+15551234567", "5551234567")
        cache.merge_into("+15551234567", "5551234567")  # idempotent
        assert len(cache.get_messages("+15551234567")) == 1

    def test_noop_when_same_safe_name(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        cache.add_message("conv1", "inbound", "msg", "", "t1", "t1")
        cache.merge_into("conv1", "CONV1")  # same safe_name → noop
        assert len(cache.get_messages("conv1")) == 1

    def test_noop_when_src_empty(self, tmp_path):
        cache = MessageCache(cache_dir=tmp_path)
        cache.merge_into("+15551234567", "empty_src")  # src has no file
        assert cache.get_messages("+15551234567") == []
