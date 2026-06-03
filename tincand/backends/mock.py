"""MockBackend — scripted backend for development and integration testing.

Loads canned Alice/Bob/Family conversations and drives a TincanService with a
GLib timer that cycles through MessageReceived, CapabilityChanged, and
Connected/Disconnected events, exercising all three GUI degradation banners.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from gi.repository import GLib

from tincand.backends.base import BackendInterface
from tincand.dbus_service import Conversation

_log = logging.getLogger(__name__)

_CANNED_CONVERSATIONS = [
    Conversation(
        id="c1",
        display_name="Alice",
        participants=["+1 555-0100"],
        last_message_at="2024-01-01T10:15:00",
        last_message_preview="Yeah, free after 6",
        unread_count=0,
    ),
    Conversation(
        id="c2",
        display_name="Bob",
        participants=["+1 555-0101"],
        last_message_at="2024-01-01T09:00:00",
        last_message_preview="Don't forget the meeting",
        unread_count=1,
    ),
    Conversation(
        id="c3",
        display_name="Family",
        participants=["+1 555-0102", "+1 555-0103", "+1 555-0104", "+1 555-0105"],
        last_message_at="2024-01-01T08:00:00",
        last_message_preview="Can everyone make it?",
        unread_count=2,
    ),
]

# Each entry is (event_type, payload).  Cycling through this sequence
# exercises all three GUI degradation banners:
#   banner A — Disconnected / Connected
#   banner B — CapabilityChanged('messages', False/True)
#   banner C — CapabilityChanged('ancs', False/True)
_TICK_SEQUENCE = [
    ("message", {
        "conversation_id": "c1",
        "body": "Still on for dinner?",
        "timestamp": "2024-01-01T10:20:00",
        "direction": "inbound",
        "status": "unread",
        "from": "+1 555-0100",
    }),
    ("capability", ("ancs", False)),      # banner C on
    ("capability", ("ancs", True)),       # banner C off
    ("capability", ("messages", False)),  # banner B on
    ("capability", ("messages", True)),   # banner B off
    ("disconnect", None),                 # banner A on
    ("connect", None),                    # banner A off, reload conversations
]


class MockBackend(BackendInterface):
    """Simulated backend with scripted events.

    Useful for running the GUI without a paired phone and for Layer-2
    integration tests that need a running daemon.
    """

    def __init__(self) -> None:
        self._service: object | None = None
        self._source_id: int | None = None
        self._tick_index: int = 0
        self._device_addr: str | None = None

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def connect(self, device_addr: str) -> None:
        if self._service is None:
            raise RuntimeError("register_service() must be called before connect()")
        self._device_addr = device_addr
        self._service.Connect(device_addr)  # type: ignore[attr-defined]
        self._load_conversations()
        self._source_id = GLib.timeout_add_seconds(3, self._on_tick)
        _log.info("MockBackend connected as %s", device_addr)

    def disconnect(self) -> None:
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
        if self._service is not None and self._device_addr is not None:
            self._service.Disconnect()  # type: ignore[attr-defined]
        _log.info("MockBackend disconnected")

    def poll_inbox(self) -> list:
        return []

    def get_message(self, handle: str) -> object:
        return None

    def send_message(self, to: str, body: str) -> str:
        return f"mock-handle-{to}"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_conversations(self) -> None:
        for conv in _CANNED_CONVERSATIONS:
            self._service.upsert_conversation(replace(conv))  # type: ignore[attr-defined]

    def _on_tick(self) -> bool:
        svc = self._service
        if svc is None:
            return GLib.SOURCE_REMOVE

        event_type, payload = _TICK_SEQUENCE[self._tick_index % len(_TICK_SEQUENCE)]
        self._tick_index += 1

        if event_type == "message":
            svc.on_message_received(payload)
        elif event_type == "capability":
            feature, available = payload
            svc.set_capability(feature, available)
        elif event_type == "disconnect":
            svc.Disconnect()
        elif event_type == "connect":
            svc.Connect(self._device_addr or "AA:BB:CC:DD:EE:FF")
            self._load_conversations()

        return GLib.SOURCE_CONTINUE
