"""Tests: PBAPContactSync.refresh() + TincanService.RefreshContacts() (tincan-mox38).

Coverage:
  §1 PBAPContactSync.refresh() branching
     - session alive (_pbap_iface + session_path set) → delegates to _retry_pullall
     - session alive → does NOT call _do_connect
     - no session (_pbap_iface None), device_addr set → delegates to _do_connect
     - no session, no device_addr → no-op, no crash
     - refresh() resets _retry_count to zero before branching
  §2 TincanService.RefreshContacts() D-Bus handler
     - _pbap set → calls _pbap.refresh()
     - _pbap is None → returns silently, no crash
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.service


def _make_service():
    from tincand.dbus_service import TincanService
    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    svc.ContactPhotoReceived = MagicMock()
    return svc


def _make_pbap():
    from tincand.backends.pbap import PBAPContactSync
    return PBAPContactSync(_make_service())


# ---------------------------------------------------------------------------
# §1 PBAPContactSync.refresh() branching
# ---------------------------------------------------------------------------

class TestPBAPContactSyncRefresh:
    """PBAPContactSync.refresh() dispatches to _retry_pullall or _do_connect."""

    def test_alive_session_calls_retry_pullall(self):
        pbap = _make_pbap()
        pbap.session_path = "/org/obex/pbap1"
        pbap._pbap_iface = MagicMock()
        pbap._device_addr = "AA:BB:CC:DD:EE:FF"
        pbap._retry_pullall = MagicMock(return_value=False)

        pbap.refresh()

        pbap._retry_pullall.assert_called_once()

    def test_alive_session_does_not_call_do_connect(self):
        pbap = _make_pbap()
        pbap.session_path = "/org/obex/pbap1"
        pbap._pbap_iface = MagicMock()
        pbap._device_addr = "AA:BB:CC:DD:EE:FF"
        pbap._retry_pullall = MagicMock(return_value=False)
        pbap._do_connect = MagicMock()

        pbap.refresh()

        pbap._do_connect.assert_not_called()

    def test_no_session_with_device_addr_calls_do_connect(self):
        pbap = _make_pbap()
        pbap.session_path = None
        pbap._pbap_iface = None
        pbap._device_addr = "AA:BB:CC:DD:EE:FF"
        pbap._do_connect = MagicMock()

        pbap.refresh()

        pbap._do_connect.assert_called_once()

    def test_no_session_no_device_addr_is_noop(self):
        pbap = _make_pbap()
        pbap.session_path = None
        pbap._pbap_iface = None
        pbap._device_addr = None
        pbap._do_connect = MagicMock()
        pbap._retry_pullall = MagicMock()

        pbap.refresh()

        pbap._do_connect.assert_not_called()
        pbap._retry_pullall.assert_not_called()

    def test_refresh_resets_retry_count_to_zero(self):
        pbap = _make_pbap()
        pbap._retry_count = 5
        pbap.session_path = "/org/obex/pbap1"
        pbap._pbap_iface = MagicMock()
        pbap._retry_pullall = MagicMock(return_value=False)

        pbap.refresh()

        assert pbap._retry_count == 0


# ---------------------------------------------------------------------------
# §2 TincanService.RefreshContacts() D-Bus handler
# ---------------------------------------------------------------------------

class TestRefreshContactsDbusHandler:
    """TincanService.RefreshContacts() dispatches to _pbap.refresh() or no-ops."""

    def test_refresh_contacts_calls_pbap_refresh_when_pbap_set(self):
        svc = _make_service()
        mock_pbap = MagicMock()
        svc._pbap = mock_pbap

        svc.RefreshContacts()

        mock_pbap.refresh.assert_called_once()

    def test_refresh_contacts_does_not_raise_when_pbap_none(self):
        svc = _make_service()
        svc._pbap = None

        svc.RefreshContacts()  # must not raise
