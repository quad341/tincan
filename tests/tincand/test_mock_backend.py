"""Tests for MockBackend scripted event dispatch."""
from __future__ import annotations

from gi.repository import GLib

import tincand.backends.mock as mock_mod
from tincand.backends.mock import MockBackend


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.conversations: dict[str, object] = {}

    def upsert_conversation(self, conv) -> None:
        self.calls.append(("upsert", conv.id, conv.unread_count))
        self.conversations[conv.id] = conv

    def Connect(self, device_addr: str) -> None:  # noqa: N802
        self.calls.append(("connect", device_addr))
        for conv in self.conversations.values():
            conv.unread_count = 0

    def Disconnect(self) -> None:  # noqa: N802
        self.calls.append(("disconnect",))

    def on_message_received(self, payload: dict) -> None:
        self.calls.append(("message", payload["body"]))

    def set_capability(self, feature: str, available: bool) -> None:
        self.calls.append(("capability", feature, available))


def test_on_tick_dispatches_full_scripted_sequence() -> None:
    svc = FakeService()
    backend = MockBackend()
    backend.register_service(svc)
    backend._device_addr = "AA:BB:CC:DD:EE:FF"

    results = [backend._on_tick() for _ in range(7)]

    assert results == [GLib.SOURCE_CONTINUE] * 7
    assert svc.calls == [
        ("message", "Still on for dinner?"),
        ("capability", "ancs", False),
        ("capability", "ancs", True),
        ("capability", "messages", False),
        ("capability", "messages", True),
        ("disconnect",),
        ("connect", "AA:BB:CC:DD:EE:FF"),
        ("upsert", "c1", 0),
        ("upsert", "c2", 1),
        ("upsert", "c3", 2),
    ]


def test_on_tick_without_service_removes_source() -> None:
    backend = MockBackend()

    assert backend._on_tick() == GLib.SOURCE_REMOVE


def test_connect_preserves_canned_unread_counts_after_service_reset(
    monkeypatch,
) -> None:
    svc = FakeService()
    backend = MockBackend()
    backend.register_service(svc)
    monkeypatch.setattr(mock_mod.GLib, "timeout_add_seconds", lambda *_args: 42)

    backend.connect("test-device")

    assert svc.calls == [
        ("connect", "test-device"),
        ("upsert", "c1", 0),
        ("upsert", "c2", 1),
        ("upsert", "c3", 2),
    ]
    assert {k: v.unread_count for k, v in svc.conversations.items()} == {
        "c1": 0,
        "c2": 1,
        "c3": 2,
    }
    assert backend._source_id == 42
