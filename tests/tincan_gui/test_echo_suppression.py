"""Tests: _on_message_received echo suppression guards.
Bead: tincan-vgw7l

Three guards in _on_message_received suppress duplicate/echo bubbles.
This file covers each guard's suppress path, pass-through path, and
the guard-cleared-after-use behaviour for _self_echo_guard.

Coverage:
  §1 _pending_sends (optimistic-send outbound echo)
     - matching (conv_id, body) in _pending_sends → no bubble appended
     - different body in _pending_sends → bubble appended
     - different conv_id in _pending_sends → bubble appended
     - _same_conv normalisation: "+15550100" in pending_sends suppresses conv_id "5550100"

  §2 _sent_bodies (MAP-poll sent-folder outbound duplicate)
     - body in _sent_bodies[conv_id] → no bubble appended
     - different body → bubble appended
     - _same_conv normalisation: "+15550100" key suppresses conv_id "5550100"
     - inbound message is never suppressed by _sent_bodies (guard is outbound-only)

  §3 _self_echo_guard (iOS MAP inbound echo of self-sent message)
     - matching (conv_id, body) in _self_echo_guard → no bubble appended
     - entry removed from guard after suppression (consumed once)
     - different body → bubble appended
     - outbound message is never suppressed by _self_echo_guard (guard is inbound-only)

All tests use monkeypatched ThreadView.append_message to count bubble attempts;
no real D-Bus, no QTimer interaction needed.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_window(qtbot, phone: str = "5550001111") -> MainWindow:
    """Return a MainWindow with _current_phone set so guard checks are reached."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_phone = phone
    return window


def _capture(window: MainWindow) -> list:
    """Patch ThreadView.append_message and return the capture list."""
    appended: list = []
    window._thread_view.append_message = lambda msg: appended.append(msg)
    return appended


def _recv(window: MainWindow, direction: str, body: str, conv_id: str = "5550001111") -> None:
    window._on_message_received({
        "direction": direction,
        "body": body,
        "conversation_id": conv_id,
        "sender": "Self",
        "timestamp": "10:00",
    })


# ---------------------------------------------------------------------------
# §1 _pending_sends — outbound optimistic-send echo suppression
# ---------------------------------------------------------------------------

class TestPendingSendsGuard:
    """Outbound echoes matching _pending_sends are swallowed."""

    def test_matching_pending_send_suppresses_bubble(self, qtbot):
        window = _make_window(qtbot)
        appended = _capture(window)
        window._pending_sends.add(("5550001111", "Hello"))

        _recv(window, "outbound", "Hello")

        assert appended == []

    def test_different_body_passes_through(self, qtbot):
        window = _make_window(qtbot)
        appended = _capture(window)
        window._pending_sends.add(("5550001111", "Hello"))

        _recv(window, "outbound", "World")

        assert len(appended) == 1

    def test_different_conv_id_passes_through(self, qtbot):
        window = _make_window(qtbot, phone="5550001111")
        appended = _capture(window)
        window._pending_sends.add(("5550009999", "Hello"))

        _recv(window, "outbound", "Hello", conv_id="5550001111")

        assert len(appended) == 1

    def test_same_conv_normalisation_suppresses(self, qtbot):
        # "+15550001111" and "5550001111" should compare equal via _same_conv.
        window = _make_window(qtbot, phone="+15550001111")
        appended = _capture(window)
        window._pending_sends.add(("+15550001111", "Normalized"))

        _recv(window, "outbound", "Normalized", conv_id="5550001111")

        assert appended == []


# ---------------------------------------------------------------------------
# §2 _sent_bodies — MAP-poll sent-folder outbound duplicate suppression
# ---------------------------------------------------------------------------

class TestSentBodiesGuard:
    """Outbound MAP-poll echoes matching _sent_bodies are swallowed."""

    def test_matching_sent_body_suppresses_bubble(self, qtbot):
        window = _make_window(qtbot)
        appended = _capture(window)
        window._sent_bodies["5550001111"] = {"Sent text"}

        _recv(window, "outbound", "Sent text")

        assert appended == []

    def test_different_body_passes_through(self, qtbot):
        window = _make_window(qtbot)
        appended = _capture(window)
        window._sent_bodies["5550001111"] = {"Sent text"}

        _recv(window, "outbound", "Different text")

        assert len(appended) == 1

    def test_same_conv_normalisation_suppresses(self, qtbot):
        window = _make_window(qtbot, phone="+15550001111")
        appended = _capture(window)
        window._sent_bodies["+15550001111"] = {"Normalized body"}

        _recv(window, "outbound", "Normalized body", conv_id="5550001111")

        assert appended == []

    def test_inbound_not_suppressed_by_sent_bodies(self, qtbot):
        """_sent_bodies guard is outbound-only; inbound must never be swallowed."""
        window = _make_window(qtbot)
        appended = _capture(window)
        window._sent_bodies["5550001111"] = {"Inbound text"}

        _recv(window, "inbound", "Inbound text")

        assert len(appended) == 1


# ---------------------------------------------------------------------------
# §3 _self_echo_guard — iOS MAP inbound echo of self-sent messages
# ---------------------------------------------------------------------------

class TestSelfEchoGuard:
    """Inbound self-echoes mark sent bubble Delivered and render as inbound bubble.

    The echo is NO LONGER suppressed (tincan-wqrq8 / tincan-tqsre): self-conversations
    must show both the sent bubble and the received copy so both sides of the
    conversation are visible.
    """

    def test_matching_self_echo_shows_inbound_bubble(self, qtbot):
        """Self-echo is not suppressed — it renders as its own inbound bubble."""
        window = _make_window(qtbot)
        appended = _capture(window)
        window._self_echo_guard.add(("5550001111", "Echo me"))

        _recv(window, "inbound", "Echo me")

        assert len(appended) == 1

    def test_entry_removed_after_echo(self, qtbot):
        """Guard entry is consumed — a second identical inbound is also shown."""
        window = _make_window(qtbot)
        appended = _capture(window)
        window._self_echo_guard.add(("5550001111", "Echo me"))

        _recv(window, "inbound", "Echo me")  # guard cleared; bubble shown
        _recv(window, "inbound", "Echo me")  # guard gone — also shown

        assert len(appended) == 2

    def test_different_body_passes_through(self, qtbot):
        window = _make_window(qtbot)
        appended = _capture(window)
        window._self_echo_guard.add(("5550001111", "Echo me"))

        _recv(window, "inbound", "Different")

        assert len(appended) == 1

    def test_outbound_not_suppressed_by_self_echo_guard(self, qtbot):
        """_self_echo_guard is inbound-only; outbound must never be swallowed by it."""
        window = _make_window(qtbot)
        appended = _capture(window)
        window._self_echo_guard.add(("5550001111", "Hello"))
        # Clear _pending_sends so _pending_sends guard doesn't fire first.
        window._pending_sends.discard(("5550001111", "Hello"))

        _recv(window, "outbound", "Hello")

        assert len(appended) == 1
