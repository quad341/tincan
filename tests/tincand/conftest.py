"""conftest.py — safety guard for tincand tests.

Prevents MapBackend.send_message() from reaching a real Bluetooth/OBEX device
during test runs. This is defense-in-depth: even if a test accidentally creates
a MapBackend against a live device, the guard catches it before the SMS is sent.

A test that legitimately needs to exercise send_message() against a mock OBEX
interface is still allowed — the guard only blocks when _msg_access is a real
(non-MagicMock) dbus.Interface object.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _block_real_map_sends(monkeypatch):
    """Fail any test whose MapBackend.send_message reaches a real OBEX interface."""
    try:
        from tincand.backends.bluez_map import MapBackend
    except ImportError:
        yield
        return

    original_send = MapBackend.send_message

    def _guarded(self, to: str, body: str) -> str:
        if self._msg_access is not None and not isinstance(self._msg_access, MagicMock):
            raise RuntimeError(
                f"Real MAP send blocked in test: MapBackend.send_message({to!r}) "
                "called with a non-mock _msg_access. "
                "Use _make_map_backend_with_mock_access() or a mock backend."
            )
        return original_send(self, to, body)

    monkeypatch.setattr(MapBackend, "send_message", _guarded)
    yield
