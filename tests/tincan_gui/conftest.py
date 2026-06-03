"""conftest.py — hermetic D-Bus isolation for all tests/tincan_gui tests.

Ensures that no test in this directory touches the real D-Bus session bus or
the live tincand daemon, even when one is running (e.g. during live QA or CI
with a paired device active).

Every test gets:
  - tincan_gui.dbus_client.QDBusConnection patched to return a disconnected mock
  - TincandClient._dbus_call patched to return None (blocks dbus-python path)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tincan_gui.dbus_client import TincandClient


@pytest.fixture(autouse=True)
def _hermetic_dbus(monkeypatch):
    """Prevent all tests/tincan_gui from touching the real session bus."""
    mock_bus = MagicMock(name="mock_session_bus")
    mock_bus.isConnected.return_value = False

    with patch("tincan_gui.dbus_client.QDBusConnection") as mock_conn:
        mock_conn.sessionBus.return_value = mock_bus
        monkeypatch.setattr(TincandClient, "_dbus_call", lambda self, *a: None)
        yield mock_bus
