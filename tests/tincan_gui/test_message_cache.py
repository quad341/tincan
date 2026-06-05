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
