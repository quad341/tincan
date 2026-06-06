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


# ---------------------------------------------------------------------------
# Known-broken D-Bus contract cases — xfail until the underlying bug lands on
# main. Each entry ties a currently-failing contract assertion to the bead that
# fixes it. strict=True: when the bug is fixed the case xpasses and CI FAILS
# until the entry is removed here, so the contract guard can never silently rot.
# ---------------------------------------------------------------------------
_KNOWN_BROKEN_CONTRACT = {
    "test_handler_has_slot_decorator[_on_contact_photo_received]": (
        "tincan-3vakg: ContactPhotoReceived handler missing @Slot(str, QByteArray) "
        "— avatars do not update live (caught at 2026-06-06 deploy, 7/8 signals)."
    ),
    # RequestReconnect xfail removed: the daemon now exports it (tincan-s7569,
    # landed in this PR) so the contract case passes for real.
}


def pytest_collection_modifyitems(config, items):
    """Mark the known-broken contract cases as strict xfail (tracked by bead)."""
    for item in items:
        for needle, reason in _KNOWN_BROKEN_CONTRACT.items():
            if needle in item.nodeid:
                item.add_marker(pytest.mark.xfail(strict=True, reason=reason))
