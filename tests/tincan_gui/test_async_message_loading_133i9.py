"""Tests: async message loading — _on_messages_loaded, prefetch, stale-reply guard, spinner (tincan-133i9).

Async message-loading paths added in tincan-bmstd had no test coverage.

Coverage:
  §1  cache-key-isolation   — messages_loaded for conv-B seeds conv-B bucket, not conv-A
  §2  stale-reply-guard     — conv-A reply arriving after switch to conv-B: skips render, seeds conv-A cache
  §3  prefetch-no-contam    — prefetch emits for 5 convs; each bucket gets its own messages only
  §4  spinner-transitions   — empty-cache select → set_loading(True); async reply → set_loading(False)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.message_cache import MessageCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_live_daemon(monkeypatch):
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
    monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])
    monkeypatch.setattr(TincandClient, "mark_conversation_read", lambda self, cid: None)
    monkeypatch.setattr(TincandClient, "fetch_contact_photo", lambda self, cid: None)
    # Suppress the async call so tests control exactly when messages_loaded fires.
    monkeypatch.setattr(TincandClient, "get_messages_async", lambda self, cid: None)


def _make_conv(phone: str, name: str | None = None) -> ConversationData:
    return ConversationData(
        id=phone, name=name or phone, phone=phone,
        preview="", timestamp="", preview_direction="inbound",
    )


def _make_msg(body: str, direction: str = "inbound", ts: str = "20260101T120000") -> dict:
    return {
        "body": body,
        "direction": direction,
        "from": "",
        "timestamp": ts,
        "sort_key": ts,
    }


# ---------------------------------------------------------------------------
# §1  cache-key-isolation — messages_loaded for conv-B seeds conv-B, not conv-A
# ---------------------------------------------------------------------------

class TestCacheKeyIsolation:
    """_on_messages_loaded must use the emitted conv_id as the cache key, not _current_phone."""

    def test_messages_land_in_emitted_conv_bucket(self, qtbot, tmp_path):
        """Emit messages_loaded for conv-B while conv-A is active; only conv-B's bucket is written."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phone_a = "+15550001"
        phone_b = "+15550002"
        win._conversations_by_id[phone_a] = _make_conv(phone_a)
        win._conversations_by_id[phone_b] = _make_conv(phone_b)
        win._current_phone = phone_a
        win._pending_load_conv = phone_a

        win._dbus_client.messages_loaded.emit(phone_b, [_make_msg("hello from B")])

        b_cache = win._msg_cache.get_messages(phone_b)
        assert any(m.get("body") == "hello from B" for m in b_cache), (
            "conv-B message must be written to conv-B's cache bucket"
        )

    def test_current_conv_bucket_unaffected_by_background_load(self, qtbot, tmp_path):
        """Conv-A's cache must not receive messages emitted for conv-B."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phone_a = "+15550001"
        phone_b = "+15550002"
        win._conversations_by_id[phone_a] = _make_conv(phone_a)
        win._conversations_by_id[phone_b] = _make_conv(phone_b)
        win._current_phone = phone_a
        win._pending_load_conv = phone_a

        win._dbus_client.messages_loaded.emit(phone_b, [_make_msg("hello from B")])

        a_cache = win._msg_cache.get_messages(phone_a)
        a_bodies = [m.get("body") for m in a_cache]
        assert "hello from B" not in a_bodies, (
            "conv-B message must NOT appear in conv-A's cache bucket"
        )

    def test_cache_key_uses_phone_not_conv_id_when_they_differ(self, qtbot, tmp_path):
        """When conv.phone != conv_id, the cache must be keyed by phone (the canonical key)."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        conv_id = "thread-uuid-001"
        phone = "+15550099"
        win._conversations_by_id[conv_id] = _make_conv(phone, name="Alice")
        win._current_phone = phone
        win._pending_load_conv = conv_id

        win._dbus_client.messages_loaded.emit(conv_id, [_make_msg("key test")])

        phone_cache = win._msg_cache.get_messages(phone)
        assert any(m.get("body") == "key test" for m in phone_cache), (
            "message must be cached under the phone key, not the raw conv_id"
        )


# ---------------------------------------------------------------------------
# §2  stale-reply-guard — conv-A reply arriving after switch to conv-B
# ---------------------------------------------------------------------------

class TestStaleReplyGuard:
    """_on_messages_loaded must skip rendering when _pending_load_conv != emitted conv_id."""

    def test_stale_reply_does_not_update_thread_view(self, qtbot, tmp_path):
        """After switching to conv-B, a delayed conv-A reply must not call load_thread(conv-A)."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phone_a = "+15550001"
        phone_b = "+15550002"
        win._conversations_by_id[phone_a] = _make_conv(phone_a)
        win._conversations_by_id[phone_b] = _make_conv(phone_b)

        # User selected conv-A, then switched to conv-B before async reply arrived.
        win._current_phone = phone_b
        win._pending_load_conv = phone_b

        loaded_convs: list[str] = []
        orig_load = win._thread_view.load_thread
        win._thread_view.load_thread = (
            lambda *a, **kw: (loaded_convs.append(a[1]), orig_load(*a, **kw))
        )

        # Stale conv-A reply arrives.
        win._dbus_client.messages_loaded.emit(phone_a, [_make_msg("stale from A")])

        assert phone_a not in loaded_convs, (
            f"stale conv-A reply must not call load_thread with conv-A; calls: {loaded_convs}"
        )

    def test_stale_reply_seeds_conv_a_cache(self, qtbot, tmp_path):
        """A stale reply must still write to conv-A's cache even when rendering is skipped."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phone_a = "+15550001"
        phone_b = "+15550002"
        win._conversations_by_id[phone_a] = _make_conv(phone_a)
        win._conversations_by_id[phone_b] = _make_conv(phone_b)
        win._current_phone = phone_b
        win._pending_load_conv = phone_b

        win._dbus_client.messages_loaded.emit(phone_a, [_make_msg("stale-but-cached")])

        a_cache = win._msg_cache.get_messages(phone_a)
        assert any(m.get("body") == "stale-but-cached" for m in a_cache), (
            "stale reply must still seed conv-A's cache bucket"
        )

    def test_active_conv_reply_does_render(self, qtbot, tmp_path):
        """A reply whose conv_id matches _pending_load_conv must update the thread view."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phone = "+15550001"
        win._conversations_by_id[phone] = _make_conv(phone)
        win._current_phone = phone
        win._pending_load_conv = phone

        loaded_convs: list[str] = []
        orig_load = win._thread_view.load_thread
        win._thread_view.load_thread = (
            lambda *a, **kw: (loaded_convs.append(a[1]), orig_load(*a, **kw))
        )

        win._dbus_client.messages_loaded.emit(phone, [_make_msg("live reply")])

        assert phone in loaded_convs, (
            "active conv reply must call load_thread to render the thread"
        )


# ---------------------------------------------------------------------------
# §3  prefetch-no-contam — prefetch emits for 5 convs; no cross-contamination
# ---------------------------------------------------------------------------

class TestPrefetchCacheIsolation:
    """Each messages_loaded emit for a prefetch conv must write only to that conv's bucket."""

    def test_five_convs_each_get_own_messages(self, qtbot, tmp_path):
        """Simulated prefetch replies: each bucket contains exactly its own messages."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        phones = [f"+1555000{i}" for i in range(5)]
        for phone in phones:
            win._conversations_by_id[phone] = _make_conv(phone)

        # Set current to something outside the 5 so all replies are non-rendering.
        win._current_phone = "+19999999"
        win._pending_load_conv = "+19999999"

        for i, phone in enumerate(phones):
            win._dbus_client.messages_loaded.emit(
                phone, [_make_msg(f"prefetch body {i}", ts=f"20260101T12000{i}")]
            )

        for i, phone in enumerate(phones):
            bucket = win._msg_cache.get_messages(phone)
            bodies = [m.get("body") for m in bucket]
            assert f"prefetch body {i}" in bodies, (
                f"conv {phone} bucket missing its own prefetch message; got {bodies}"
            )
            for j in range(5):
                if j == i:
                    continue
                assert f"prefetch body {j}" not in bodies, (
                    f"cross-contamination: conv {phone} got message from conv {phones[j]}"
                )

    def test_prefetch_background_replies_do_not_render_to_thread(self, qtbot, tmp_path):
        """Background prefetch replies must not call load_thread for the current conversation."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)

        current = "+15550000"
        win._conversations_by_id[current] = _make_conv(current)
        win._current_phone = current
        win._pending_load_conv = current
        win._thread_view.load_thread(current, current, [], "SMS")

        background_loads: list[str] = []
        orig_load = win._thread_view.load_thread
        win._thread_view.load_thread = (
            lambda *a, **kw: (background_loads.append(a[1]), orig_load(*a, **kw))
        )

        for i in range(1, 5):
            phone = f"+1555000{i}"
            win._conversations_by_id[phone] = _make_conv(phone)
            win._dbus_client.messages_loaded.emit(phone, [_make_msg(f"bg prefetch {i}")])

        # None of the background convs should have triggered a thread render.
        assert all(c != current for c in background_loads), (
            "background prefetch must not render into the current conversation's thread"
        )
        background_others = [c for c in background_loads if c != current]
        assert background_others == [], (
            f"background prefetch convs must not call load_thread; called for: {background_others}"
        )


# ---------------------------------------------------------------------------
# §4  spinner-transitions — set_loading state changes
# ---------------------------------------------------------------------------

class TestSpinnerTransitions:
    """set_loading must activate on empty-cache select and clear after the async reply lands."""

    def test_empty_cache_select_activates_loading_spinner(self, qtbot, tmp_path):
        """`_on_conversation_selected` with empty cache must show the loading label."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)
        win._messages_ok = True

        phone = "+15550001"
        win._conversations_by_id[phone] = _make_conv(phone)

        win._on_conversation_selected(phone)

        label_text = win._thread_view._empty_label.text()
        assert "Loading" in label_text, (
            f"empty-cache select must show loading label; got: {label_text!r}"
        )

    def test_async_reply_clears_loading_spinner(self, qtbot, tmp_path):
        """`_on_messages_loaded` must call set_loading(False) so the loading label clears."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)
        win._messages_ok = True

        phone = "+15550001"
        win._conversations_by_id[phone] = _make_conv(phone)

        win._on_conversation_selected(phone)
        # Confirm loading activated.
        assert "Loading" in win._thread_view._empty_label.text()

        # Async reply arrives.
        win._dbus_client.messages_loaded.emit(phone, [_make_msg("arrived")])

        label_text = win._thread_view._empty_label.text()
        assert "Loading" not in label_text, (
            f"after async reply, loading label must clear; got: {label_text!r}"
        )

    def test_cached_select_does_not_activate_spinner(self, qtbot, tmp_path):
        """If the cache is non-empty, `_on_conversation_selected` must NOT call set_loading(True)."""
        win = MainWindow()
        win._msg_cache = MessageCache(cache_dir=tmp_path)
        qtbot.addWidget(win)
        win._messages_ok = True

        phone = "+15550001"
        win._conversations_by_id[phone] = _make_conv(phone)
        win._msg_cache.add_message(
            phone, "inbound", "cached body", "", "20260101T120000", "20260101T120000"
        )

        loading_calls: list[bool] = []
        orig_set_loading = win._thread_view.set_loading
        win._thread_view.set_loading = (
            lambda v: (loading_calls.append(v), orig_set_loading(v))
        )

        win._on_conversation_selected(phone)

        assert True not in loading_calls, (
            f"cache-hit select must not call set_loading(True); calls: {loading_calls}"
        )
