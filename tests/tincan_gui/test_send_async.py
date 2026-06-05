"""Tests: async MAP send path — non-blocking UI thread (tincan-k942a).

Coverage:
  - TincandClient.send_message_async() exists and is callable.
  - TincandClient.message_send_accepted and message_send_failed signals exist.
  - send_message_async() emits message_send_failed when bus is disconnected.
  - send_message_async() emits message_send_failed when D-Bus interface is invalid.
  - MainWindow._on_send_accepted handler exists.
  - MainWindow._on_send_failed handler exists.
  - MainWindow._on_send() calls send_message_async, not send_message.
  - message_send_accepted and message_send_failed signals wired to handlers in _wire_dbus.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 TincandClient — send_message_async API surface
# ---------------------------------------------------------------------------

class TestSendMessageAsyncSignals:
    """TincandClient must expose message_send_accepted and message_send_failed signals."""

    def test_message_send_accepted_signal_exists(self):
        client = TincandClient()
        # Connecting to a non-existent signal raises AttributeError; if this
        # line executes without error, the signal is present.
        fired = []
        client.message_send_accepted.connect(lambda to, body, mid: fired.append((to, body, mid)))

    def test_message_send_failed_signal_exists(self):
        client = TincandClient()
        fired = []
        client.message_send_failed.connect(lambda to, body: fired.append((to, body)))

    def test_send_message_async_method_exists(self):
        client = TincandClient()
        assert callable(getattr(client, "send_message_async", None))


class TestSendMessageAsyncFallbackBusDisconnected:
    """send_message_async emits message_send_failed when bus is not connected."""

    def test_emits_send_failed_when_bus_disconnected(self):
        client = TincandClient()
        # _hermetic_dbus conftest already mocks bus as disconnected
        fired = []
        client.message_send_failed.connect(lambda to, body: fired.append((to, body)))

        client.send_message_async("+15550001111", "hello")

        assert len(fired) == 1
        assert fired[0] == ("+15550001111", "hello")

    def test_does_not_emit_send_accepted_when_bus_disconnected(self):
        client = TincandClient()
        accepted = []
        client.message_send_accepted.connect(
            lambda to, body, mid: accepted.append((to, body, mid))
        )

        client.send_message_async("+15550001111", "hello")

        assert accepted == []


class TestSendMessageAsyncFallbackIfaceInvalid:
    """send_message_async emits message_send_failed when D-Bus interface is invalid."""

    @pytest.fixture(autouse=True)
    def _connected_invalid_iface(self, _hermetic_dbus):
        _hermetic_dbus.isConnected.return_value = True
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = False
        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            yield

    def test_emits_send_failed_when_interface_invalid(self):
        client = TincandClient()
        fired = []
        client.message_send_failed.connect(lambda to, body: fired.append((to, body)))

        client.send_message_async("+15550001111", "world")

        assert len(fired) == 1
        assert fired[0] == ("+15550001111", "world")

    def test_does_not_emit_send_accepted_when_interface_invalid(self):
        client = TincandClient()
        accepted = []
        client.message_send_accepted.connect(
            lambda to, body, mid: accepted.append((to, body, mid))
        )

        client.send_message_async("+15550001111", "world")

        assert accepted == []


# ---------------------------------------------------------------------------
# §2 MainWindow — _on_send_accepted / _on_send_failed handlers
# ---------------------------------------------------------------------------

class TestMainWindowSendHandlers:
    """MainWindow must have _on_send_accepted and _on_send_failed handlers."""

    def test_on_send_accepted_handler_exists(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        assert callable(getattr(window, "_on_send_accepted", None))

    def test_on_send_failed_handler_exists(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        assert callable(getattr(window, "_on_send_failed", None))

    def test_on_send_accepted_discards_pending_send(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        phone = "+15550001111"
        text = "test body"
        window._pending_sends.add((phone, text))

        window._on_send_accepted(phone, text, "msg-id-99")

        # After a brief event loop tick (QTimer.singleShot(0, ...)), pending is cleared.
        # Process events to flush the zero-delay timer.
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        assert (phone, text) not in window._pending_sends

    def test_on_send_failed_shows_send_error(self, qtbot, monkeypatch):
        window = MainWindow()
        qtbot.addWidget(window)
        errors = []
        monkeypatch.setattr(window._compose, "show_send_error", lambda msg: errors.append(msg))

        window._on_send_failed("+15550001111", "oops body")

        assert "oops body" in errors

    def test_on_send_failed_marks_last_send_failed(self, qtbot, monkeypatch):
        window = MainWindow()
        qtbot.addWidget(window)
        called = []
        monkeypatch.setattr(
            window._thread_view, "mark_last_send_failed", lambda: called.append(True)
        )

        window._on_send_failed("+15550001111", "failed")

        assert len(called) == 1


# ---------------------------------------------------------------------------
# §3 MainWindow._on_send — uses send_message_async, not send_message
# ---------------------------------------------------------------------------

class TestOnSendUsesAsync:
    """_on_send must call send_message_async instead of the blocking send_message."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_on_send_calls_send_message_async_not_send_message(self, qtbot, monkeypatch):
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "+15550001111"
        window._current_phone_dialable = True

        sync_calls = []
        async_calls = []
        monkeypatch.setattr(
            window._dbus_client, "send_message", lambda *a: sync_calls.append(a) or ""
        )
        monkeypatch.setattr(
            window._dbus_client, "send_message_async", lambda *a: async_calls.append(a)
        )

        window._on_send("hello async")

        assert async_calls, "_on_send must call send_message_async()"
        assert not sync_calls, "_on_send must NOT call blocking send_message()"

    def test_on_send_async_called_with_phone_and_text(self, qtbot, monkeypatch):
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "+15550001111"
        window._current_phone_dialable = True

        async_calls = []
        monkeypatch.setattr(
            window._dbus_client, "send_message_async", lambda *a: async_calls.append(a)
        )

        window._on_send("my message")

        assert len(async_calls) == 1
        to, body = async_calls[0]
        assert to == "+15550001111"
        assert body == "my message"


# ---------------------------------------------------------------------------
# §4 asyncCallWithArgumentList — correct D-Bus send API (regression for n0yel)
# ---------------------------------------------------------------------------

class TestSendUsesAsyncCallWithArgumentList:
    """send_message_async must use asyncCallWithArgumentList, not asyncCall.

    Regression guard: PySide6 QDBusInterface.asyncCall() accepts only the method
    name; passing (method, arg1, arg2) raises TypeError.  The old code swallowed
    that TypeError and showed a false 'sent'.  This fixture enforces the real
    signature so any regression back to asyncCall(method, *args) is caught.
    """

    @pytest.fixture
    def _strict_iface(self, _hermetic_dbus):
        _hermetic_dbus.isConnected.return_value = True
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True

        def _strict_asynccall(method, *extra_args):
            if extra_args:
                raise TypeError(
                    f"asyncCall() takes exactly one argument ({1 + len(extra_args)} given)"
                )
            return MagicMock()

        mock_iface.asyncCall.side_effect = _strict_asynccall
        mock_iface.asyncCallWithArgumentList.return_value = MagicMock()

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface), \
             patch("tincan_gui.dbus_client.QDBusPendingCallWatcher"):
            yield mock_iface

    def test_asyncCallWithArgumentList_called_with_method_and_args(self, _strict_iface):
        client = TincandClient()
        client.send_message_async("+15550001111", "hello")
        _strict_iface.asyncCallWithArgumentList.assert_called_once_with(
            "SendMessage", ["+15550001111", "hello"]
        )

    def test_asyncCall_not_called_with_extra_args(self, _strict_iface):
        """asyncCall(method, to, body) would raise TypeError — must not be called that way."""
        client = TincandClient()
        client.send_message_async("+15550001111", "hello")
        _strict_iface.asyncCall.assert_not_called()

    def test_no_typeerror_propagates(self, _strict_iface):
        """Regression: old asyncCall('SendMessage', to, body) raised TypeError, silently swallowed."""
        client = TincandClient()
        client.send_message_async("+15550001111", "no crash please")


# ---------------------------------------------------------------------------
# §4 Integration — _wire_dbus connects async send signals
# ---------------------------------------------------------------------------

class TestDBusWiringAsyncSend:
    """message_send_accepted and message_send_failed signals must be connected in _wire_dbus."""

    def test_message_send_accepted_signal_wired_to_on_send_accepted(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)

        accepted_calls = []
        monkeypatch.setattr(window, "_on_send_accepted", lambda *a: accepted_calls.append(a))
        # Re-wire with the patched handler
        window._dbus_client.message_send_accepted.connect(window._on_send_accepted)

        window._dbus_client.message_send_accepted.emit("+1", "body", "mid-1")

        assert len(accepted_calls) >= 1

    def test_message_send_failed_signal_wired_to_on_send_failed(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)

        failed_calls = []
        monkeypatch.setattr(window, "_on_send_failed", lambda *a: failed_calls.append(a))
        window._dbus_client.message_send_failed.connect(window._on_send_failed)

        window._dbus_client.message_send_failed.emit("+1", "body")

        assert len(failed_calls) >= 1
