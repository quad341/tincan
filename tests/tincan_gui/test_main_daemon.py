"""Tests: MainWindow daemon signal handlers + ThreadView.append_message.
Bead: tincan-fnf  (tincan-mgc D-Bus signal wiring coverage)

Coverage:
  - _on_daemon_connected: title bar connected, banner_a hidden,
    compose unchanged (enabled only after conversation selected).
  - _on_daemon_disconnected: title bar disconnected, banner_a shown, banner_b/c hidden,
    compose disabled.
  - _on_capability_changed('messages', False/True): banner_b visibility + compose state.
  - _on_capability_changed('ancs', False/True): banner_c visibility.
  - _on_message_received: correct BubbleType dispatch (INBOUND / BODY_UNAVAILABLE / OUTBOUND),
    timestamp truncated to 5 chars.
  - ThreadView.append_message: clears empty-state placeholder, adds bubble, preserves prior
    bubbles on subsequent calls.
  - Integration (_wire_dbus): TincandClient signals trigger correct MainWindow handlers.
  - Regression (tincan-itk9m): MainWindow construction must not spawn real tincand processes.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData, ThreadView


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bubble_count(view: ThreadView) -> int:
    """Count MessageBubble widgets currently in the thread view layout."""
    layout = view._messages_layout
    return sum(
        1 for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), MessageBubble)
    )


def _has_empty_label(view: ThreadView) -> bool:
    return view._messages_layout.indexOf(view._empty_label) >= 0


# ---------------------------------------------------------------------------
# §1 _on_daemon_connected
# ---------------------------------------------------------------------------

class TestDaemonConnected:
    """_on_daemon_connected updates title bar, hides banner_a;
    compose stays disabled until conversation selected."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        # _on_daemon_connected calls get_status(); patch to {} so device_address arg
        # is used as-is and live-daemon state doesn't leak into assertions.
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    def test_title_bar_shows_connected_text(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")

        chip_text = window._title_bar._status_chip.text()
        assert "Connected" in chip_text

    def test_title_bar_shows_device_address(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")

        chip_text = window._title_bar._status_chip.text()
        assert "AA:BB:CC:DD:EE:FF" in chip_text

    def test_banner_a_is_hidden(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        # Force banner_a visible first to ensure the handler hides it
        window._banner_a.show()

        window._on_daemon_connected("device")

        assert not window._banner_a.isVisible()

    def test_compose_stays_disabled_after_daemon_connect_no_conversation(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_connected("device")

        assert not window._compose._send_btn.isEnabled()

    def test_compose_enabled_when_conversation_selected_after_connect(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._on_daemon_connected("device")

        window._on_conversation_selected("conv-1")

        assert window._compose._send_btn.isEnabled()


# ---------------------------------------------------------------------------
# §2 _on_daemon_disconnected
# ---------------------------------------------------------------------------

class TestDaemonDisconnected:
    """_on_daemon_disconnected updates title bar, shows banner_a, hides banner_b/c,
    disables compose."""

    def test_title_bar_shows_disconnected_text(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._on_daemon_connected("some-device")

        window._on_daemon_disconnected()

        chip_text = window._title_bar._status_chip.text()
        assert "Disconnected" in chip_text

    def test_banner_a_is_shown(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_disconnected()

        assert window._banner_a.isVisible()

    def test_banner_b_is_hidden(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_b.show()

        window._on_daemon_disconnected()

        assert not window._banner_b.isVisible()

    def test_banner_c_is_hidden(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._on_daemon_disconnected()

        assert not window._banner_c.isVisible()

    def test_compose_is_disabled(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_disconnected()

        assert not window._compose._send_btn.isEnabled()

    def test_compose_input_is_disabled(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_disconnected()

        assert not window._compose._input.isEnabled()


# ---------------------------------------------------------------------------
# §3 _on_capability_changed
# ---------------------------------------------------------------------------

class TestCapabilityChanged:
    """_on_capability_changed toggles banner_b/c and compose state per feature."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        # _on_capability_changed calls get_status(); patch to {} so the fallback
        # dict (defaults-True + reported feature) is used instead of live state.
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    # --- messages capability ---

    def test_messages_false_shows_banner_b(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_capability_changed("messages", False)

        assert window._banner_b.isVisible()

    def test_messages_true_hides_banner_b(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_b.show()

        window._on_capability_changed("messages", True)

        assert not window._banner_b.isVisible()

    def test_messages_false_disables_compose(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_capability_changed("messages", False)

        assert not window._compose._send_btn.isEnabled()

    def test_messages_capability_does_not_enable_compose_without_conversation(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._compose.set_compose_enabled(False, "messaging unavailable")

        window._on_capability_changed("messages", True)

        assert not window._compose._send_btn.isEnabled()

    # --- ancs capability ---

    def test_ancs_false_shows_banner_c(self, qtbot):
        """CapabilityChanged("ancs", False) alone does not show StateCBanner.
        StateCBanner now requires ancs_status="healing" from ANCSStatusChanged.
        """
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_capability_changed("ancs", False)

        assert not window._banner_c.isVisible()  # healing signal not received yet

    def test_ancs_status_healing_shows_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_ancs_status_changed("healing")

        assert window._banner_c.isVisible()

    def test_ancs_true_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._on_capability_changed("ancs", True)

        assert not window._banner_c.isVisible()

    def test_ancs_capability_does_not_affect_compose(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_capability_changed("ancs", False)

        # ancs has no effect on compose — stays disabled without a conversation selected
        assert not window._compose._send_btn.isEnabled()

    def test_unknown_feature_is_silently_ignored(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Should not raise
        window._on_capability_changed("unknown_feature", False)


# ---------------------------------------------------------------------------
# §4 _on_message_received — BubbleType dispatch
# ---------------------------------------------------------------------------

class TestMessageReceived:
    """_on_message_received dispatches to the correct BubbleType."""

    def _capture_appended(self, window):
        """Monkey-patch ThreadView.append_message to capture the MessageData."""
        appended = []
        window._thread_view.append_message = lambda msg: appended.append(msg)
        return appended

    def test_inbound_direction_produces_inbound_bubble(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        appended = self._capture_appended(window)

        window._on_message_received({
            "direction": "inbound",
            "body": "Hello",
            "sender": "Alice",
            "timestamp": "2024-01-01T10:32:00",
        })

        assert len(appended) == 1
        assert appended[0].bubble_type == BubbleType.INBOUND

    def test_empty_body_produces_body_unavailable(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        appended = self._capture_appended(window)

        window._on_message_received({
            "direction": "inbound",
            "body": "",
            "sender": "Mom",
            "timestamp": "2024-01-01T09:00:00",
        })

        assert appended[0].bubble_type == BubbleType.BODY_UNAVAILABLE

    def test_outbound_direction_produces_outbound_bubble(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        appended = self._capture_appended(window)

        window._on_message_received({
            "direction": "outbound",
            "body": "On my way",
            "sender": "",
            "timestamp": "2024-01-01T10:45:00",
        })

        assert appended[0].bubble_type == BubbleType.OUTBOUND

    def test_timestamp_display_is_hhmm_from_map_format(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        appended = self._capture_appended(window)

        window._on_message_received({
            "direction": "inbound",
            "body": "Hi",
            "sender": "Alice",
            "timestamp": "20240101T103200",  # MAP YYYYMMDDTHHMMSS from daemon
        })

        assert appended[0].timestamp == "10:32"
        assert appended[0].sort_key == "20240101T103200"

    def test_missing_fields_use_safe_defaults(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        appended = self._capture_appended(window)

        window._on_message_received({})

        assert len(appended) == 1
        # Empty body → BODY_UNAVAILABLE
        assert appended[0].bubble_type == BubbleType.BODY_UNAVAILABLE


# ---------------------------------------------------------------------------
# §5 ThreadView.append_message
# ---------------------------------------------------------------------------

class TestThreadViewAppendMessage:
    """append_message clears the empty-state placeholder and adds bubbles."""

    def test_first_append_removes_empty_placeholder(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        assert _has_empty_label(view), "sanity: empty label present before first append"

        view.append_message(MessageData(BubbleType.INBOUND, "Hi", "Alice", "10:32"))

        assert not _has_empty_label(view)

    def test_first_append_adds_one_bubble(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)

        view.append_message(MessageData(BubbleType.INBOUND, "Hi", "Alice", "10:32"))

        assert _bubble_count(view) == 1

    def test_second_append_keeps_first_bubble(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)

        view.append_message(MessageData(BubbleType.INBOUND, "First", "Alice", "10:32"))
        view.append_message(MessageData(BubbleType.OUTBOUND, "Second", "", "10:33"))

        assert _bubble_count(view) == 2

    def test_append_after_load_thread_keeps_loaded_bubbles(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        view.load_thread("Alice", "+1 555-0100", [
            MessageData(BubbleType.INBOUND, "Hey", "Alice", "10:00"),
        ])
        assert _bubble_count(view) == 1

        view.append_message(MessageData(BubbleType.OUTBOUND, "Reply", "", "10:01"))

        assert _bubble_count(view) == 2

    def test_append_placeholder_not_in_layout_after_call(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)

        view.append_message(MessageData(BubbleType.BODY_UNAVAILABLE, "", "Mom", "09:00"))

        assert _has_empty_label(view) is False


# ---------------------------------------------------------------------------
# §6 Integration — TincandClient signals wired via _wire_dbus
# ---------------------------------------------------------------------------

class TestDBusWiring:
    """Emitting TincandClient signals must trigger the corresponding MainWindow handlers."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        # capability_changed signal → _on_capability_changed → get_status(); patch so
        # live-daemon state doesn't override the emitted feature value.
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    def test_connected_signal_triggers_title_bar_update(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.connected.emit("00:11:22:33:44:55")

        assert "Connected" in window._title_bar._status_chip.text()

    def test_disconnected_signal_triggers_banner_a_show(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.disconnected.emit()

        assert window._banner_a.isVisible()

    def test_capability_changed_messages_false_shows_banner_b(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.capability_changed.emit("messages", False)

        assert window._banner_b.isVisible()

    def test_capability_changed_ancs_false_does_not_show_banner_c(self, qtbot):
        """CapabilityChanged alone cannot show StateCBanner; requires
        ANCSStatusChanged("healing")."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.capability_changed.emit("ancs", False)

        assert not window._banner_c.isVisible()

    def test_ancs_status_changed_healing_shows_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.ancs_status_changed.emit("healing")

        assert window._banner_c.isVisible()

    def test_message_received_signal_appends_bubble(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        appended = []
        window._thread_view.append_message = lambda msg: appended.append(msg)

        window._dbus_client.message_received.emit({
            "direction": "inbound",
            "body": "Live message",
            "sender": "Alice",
            "timestamp": "10:32",
        })

        assert len(appended) == 1
        assert appended[0].bubble_type == BubbleType.INBOUND


# ---------------------------------------------------------------------------
# §N _sync_daemon_state — cold-start tray.set_connected path (tincan-wb4c)
# ---------------------------------------------------------------------------

class TestSyncDaemonState:
    """_sync_daemon_state at startup propagates daemon status to tray and _connected_device."""

    @pytest.fixture(autouse=True)
    def _no_list_conversations(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_connected_daemon_sets_tray_connected_true(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"connected": True, "device_name": "TestPhone", "capabilities": {}},
        )
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._tray._connected is True

    def test_connected_daemon_sets_connected_device(self, qtbot, monkeypatch):
        _status = {"connected": True, "device_name": "AA:BB:CC:DD:EE:FF", "capabilities": {}}
        monkeypatch.setattr(TincandClient, "get_status", lambda self: _status)
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._connected_device == "AA:BB:CC:DD:EE:FF"

    def test_disconnected_daemon_tray_connected_stays_false(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"connected": False},
        )
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._tray._connected is False

    def test_no_daemon_response_tray_connected_stays_false(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._tray._connected is False


# ---------------------------------------------------------------------------
# §config-persist  auto-save device on connect (tincan-oxthc)
# ---------------------------------------------------------------------------

class TestDeviceConfigPersist:
    """_on_daemon_connected persists device address to config on first successful connection."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    def test_save_called_when_device_differs_from_config(self, qtbot, monkeypatch):
        import tincan_gui.main as _main_mod
        from tincan_gui.daemon_config import DaemonConfig

        loaded_cfg = DaemonConfig(backend="map", device="")
        saved = []
        monkeypatch.setattr(_main_mod, "load_daemon_config", lambda: loaded_cfg)
        monkeypatch.setattr(_main_mod, "save_daemon_config", lambda c: saved.append(c))

        window = MainWindow()
        qtbot.addWidget(window)
        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")

        assert len(saved) == 1
        assert saved[0].device == "AA:BB:CC:DD:EE:FF"
        assert saved[0].backend == "map"

    def test_save_not_called_when_device_already_matches_config(self, qtbot, monkeypatch):
        import tincan_gui.main as _main_mod
        from tincan_gui.daemon_config import DaemonConfig

        loaded_cfg = DaemonConfig(backend="map", device="AA:BB:CC:DD:EE:FF")
        saved = []
        monkeypatch.setattr(_main_mod, "load_daemon_config", lambda: loaded_cfg)
        monkeypatch.setattr(_main_mod, "save_daemon_config", lambda c: saved.append(c))

        window = MainWindow()
        qtbot.addWidget(window)
        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")

        assert saved == []

    def test_save_not_called_when_device_address_empty(self, qtbot, monkeypatch):
        import tincan_gui.main as _main_mod
        saved = []
        monkeypatch.setattr(_main_mod, "save_daemon_config", lambda c: saved.append(c))

        window = MainWindow()
        qtbot.addWidget(window)
        window._on_daemon_connected("")

        assert saved == []

    def test_saved_config_preserves_existing_backend(self, qtbot, monkeypatch):
        import tincan_gui.main as _main_mod
        from tincan_gui.daemon_config import DaemonConfig

        loaded_cfg = DaemonConfig(backend="fake_map", device="")
        saved = []
        monkeypatch.setattr(_main_mod, "load_daemon_config", lambda: loaded_cfg)
        monkeypatch.setattr(_main_mod, "save_daemon_config", lambda c: saved.append(c))

        window = MainWindow()
        qtbot.addWidget(window)
        window._on_daemon_connected("11:22:33:44:55:66")

        assert saved[0].backend == "fake_map"
        assert saved[0].device == "11:22:33:44:55:66"


# ---------------------------------------------------------------------------
# §N+1 Regression: no subprocess spawned during tests (tincan-itk9m)
# ---------------------------------------------------------------------------

class TestNoSpawnDaemonInTests:
    """Regression: MainWindow construction must not spawn real tincand processes.

    Verifies the _no_daemon_spawn conftest fixture blocks subprocess.Popen calls
    even when daemon config has a device address set.
    """

    def test_mainwindow_with_device_config_spawns_no_process(self, qtbot, monkeypatch):
        import subprocess as _subprocess

        from tincan_gui.daemon_config import DaemonConfig

        monkeypatch.setattr(
            "tincan_gui.main.load_daemon_config",
            lambda: DaemonConfig(backend="map", device="AA:BB:CC:DD:EE:FF"),
        )
        popen_calls = []
        monkeypatch.setattr(_subprocess, "Popen", lambda *a, **kw: popen_calls.append((a, kw)))

        window = MainWindow()
        qtbot.addWidget(window)

        assert popen_calls == [], (
            f"subprocess.Popen called {len(popen_calls)} time(s) — "
            "spawn_daemon mock did not intercept daemon launch"
        )
