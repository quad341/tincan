"""Tests: BackendManager lifecycle + CLI BackendManager wiring.
Bead: tincan-voor  (commit ce9f2b2)

Coverage:
  §1 BackendManager.register_service
     - calls primary.register_service
     - calls each secondary.register_service

  §2 BackendManager.connect
     - calls primary.connect then each secondary.connect in order
     - secondary exception logged as WARNING, does not abort remaining secondaries

  §3 BackendManager.disconnect
     - calls secondaries in reverse order, then primary

  §4 BackendManager delegation
     - poll_inbox delegates to primary.poll_inbox
     - get_message delegates to primary.get_message
     - send_message delegates to primary.send_message

  §5 CLI __main__.py
     - --with-ancs + --backend map: creates BackendManager(MapBackend, [ANCSBackend])
     - --with-ancs + --backend ancs: logs WARNING, no BackendManager created
"""
from __future__ import annotations

import logging
import sys
from argparse import Namespace
from unittest.mock import MagicMock, call, patch

import pytest

from tincand.backend_manager import BackendManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend(name: str = "b") -> MagicMock:
    b = MagicMock(name=name)
    b.poll_inbox.return_value = []
    b.get_message.return_value = None
    b.send_message.return_value = ""
    return b


def _make_manager(primary=None, secondaries=None):
    p = primary or _make_backend("primary")
    secs = secondaries if secondaries is not None else [_make_backend("s1")]
    return BackendManager(primary=p, secondaries=secs), p, secs


# ---------------------------------------------------------------------------
# §1 register_service
# ---------------------------------------------------------------------------

class TestBackendManagerRegisterService:
    """register_service fans out to primary and all secondaries."""

    def test_register_service_calls_primary(self):
        mgr, primary, _ = _make_manager()
        svc = MagicMock(name="svc")

        mgr.register_service(svc)

        primary.register_service.assert_called_once_with(svc)

    def test_register_service_calls_secondary(self):
        secondary = _make_backend("s1")
        mgr, _, _ = _make_manager(secondaries=[secondary])
        svc = MagicMock(name="svc")

        mgr.register_service(svc)

        secondary.register_service.assert_called_once_with(svc)

    def test_register_service_calls_all_secondaries(self):
        s1, s2 = _make_backend("s1"), _make_backend("s2")
        mgr, _, _ = _make_manager(secondaries=[s1, s2])
        svc = MagicMock()

        mgr.register_service(svc)

        s1.register_service.assert_called_once_with(svc)
        s2.register_service.assert_called_once_with(svc)

    def test_register_service_no_secondaries_still_calls_primary(self):
        mgr, primary, _ = _make_manager(secondaries=[])
        svc = MagicMock()

        mgr.register_service(svc)

        primary.register_service.assert_called_once_with(svc)


# ---------------------------------------------------------------------------
# §2 connect
# ---------------------------------------------------------------------------

class TestBackendManagerConnect:
    """connect calls primary first, then secondaries in order."""

    def test_connect_calls_primary(self):
        mgr, primary, _ = _make_manager(secondaries=[])

        mgr.connect("AA:BB")

        primary.connect.assert_called_once_with("AA:BB")

    def test_connect_calls_secondary_after_primary(self):
        call_order = []
        primary = _make_backend("primary")
        secondary = _make_backend("s1")
        primary.connect.side_effect = lambda addr: call_order.append("primary")
        secondary.connect.side_effect = lambda addr: call_order.append("secondary")
        mgr = BackendManager(primary=primary, secondaries=[secondary])

        mgr.connect("AA:BB")

        assert call_order == ["primary", "secondary"]

    def test_connect_calls_secondaries_in_order(self):
        call_order = []
        primary = _make_backend()
        s1, s2 = _make_backend("s1"), _make_backend("s2")
        s1.connect.side_effect = lambda addr: call_order.append("s1")
        s2.connect.side_effect = lambda addr: call_order.append("s2")
        mgr = BackendManager(primary=primary, secondaries=[s1, s2])

        mgr.connect("AA:BB")

        assert call_order == ["s1", "s2"]

    def test_secondary_exception_does_not_abort(self):
        primary = _make_backend()
        s1 = _make_backend("s1")
        s2 = _make_backend("s2")
        s1.connect.side_effect = RuntimeError("s1 failed")
        mgr = BackendManager(primary=primary, secondaries=[s1, s2])

        mgr.connect("AA:BB")  # must not raise

        s2.connect.assert_called_once_with("AA:BB")

    def test_secondary_exception_logged_as_warning(self, caplog):
        primary = _make_backend()
        s1 = _make_backend("s1")
        s1.connect.side_effect = RuntimeError("boom")
        mgr = BackendManager(primary=primary, secondaries=[s1])

        with caplog.at_level(logging.WARNING, logger="tincand.backend_manager"):
            mgr.connect("AA:BB")

        assert any("connect failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# §3 disconnect
# ---------------------------------------------------------------------------

class TestBackendManagerDisconnect:
    """disconnect calls secondaries in reverse order, then primary last."""

    def test_disconnect_calls_primary(self):
        mgr, primary, _ = _make_manager(secondaries=[])

        mgr.disconnect()

        primary.disconnect.assert_called_once()

    def test_disconnect_calls_secondaries_before_primary(self):
        call_order = []
        primary = _make_backend()
        secondary = _make_backend("s1")
        secondary.disconnect.side_effect = lambda: call_order.append("secondary")
        primary.disconnect.side_effect = lambda: call_order.append("primary")
        mgr = BackendManager(primary=primary, secondaries=[secondary])

        mgr.disconnect()

        assert call_order.index("secondary") < call_order.index("primary")

    def test_disconnect_calls_secondaries_in_reverse_order(self):
        call_order = []
        primary = _make_backend()
        s1, s2 = _make_backend("s1"), _make_backend("s2")
        s1.disconnect.side_effect = lambda: call_order.append("s1")
        s2.disconnect.side_effect = lambda: call_order.append("s2")
        mgr = BackendManager(primary=primary, secondaries=[s1, s2])

        mgr.disconnect()

        assert call_order[:2] == ["s2", "s1"]

    def test_disconnect_secondary_exception_does_not_abort(self):
        primary = _make_backend()
        s1 = _make_backend("s1")
        s1.disconnect.side_effect = RuntimeError("s1 disconnect failed")
        mgr = BackendManager(primary=primary, secondaries=[s1])

        mgr.disconnect()  # must not raise

        primary.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# §4 Delegation
# ---------------------------------------------------------------------------

class TestBackendManagerDelegation:
    """poll_inbox / get_message / send_message delegate to primary only."""

    def test_poll_inbox_delegates_to_primary(self):
        mgr, primary, _ = _make_manager()
        primary.poll_inbox.return_value = [{"msg": 1}]

        result = mgr.poll_inbox()

        assert result == [{"msg": 1}]
        primary.poll_inbox.assert_called_once()

    def test_poll_inbox_does_not_call_secondary(self):
        secondary = _make_backend("s1")
        mgr, _, _ = _make_manager(secondaries=[secondary])

        mgr.poll_inbox()

        secondary.poll_inbox.assert_not_called()

    def test_get_message_delegates_to_primary(self):
        mgr, primary, _ = _make_manager()
        primary.get_message.return_value = {"body": "hello"}

        result = mgr.get_message("/handle/1")

        assert result == {"body": "hello"}
        primary.get_message.assert_called_once_with("/handle/1")

    def test_send_message_delegates_to_primary(self):
        mgr, primary, _ = _make_manager()
        primary.send_message.return_value = "msg-id-1"

        result = mgr.send_message("+15550001111", "Hi")

        assert result == "msg-id-1"
        primary.send_message.assert_called_once_with("+15550001111", "Hi")


# ---------------------------------------------------------------------------
# §5 CLI __main__.py
# ---------------------------------------------------------------------------

class TestCLIBackendManagerWiring:
    """--with-ancs + --backend map wraps in BackendManager; ancs backend logs warning."""

    def test_with_ancs_map_creates_backend_manager(self, monkeypatch, caplog):
        from tincand import __main__ as daemon_main
        from tincand.backends.bluez_map import MapBackend

        monkeypatch.setattr(sys, "argv", ["tincand", "--backend", "map", "--with-ancs"])
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)

        created_backends = []

        real_init = BackendManager.__init__

        def capture_init(self_mgr, primary, secondaries=None):
            created_backends.append((type(primary).__name__,
                                     [type(s).__name__ for s in (secondaries or [])]))
            real_init(self_mgr, primary, secondaries)

        # TincanService is imported locally inside main(); patch it at its definition site.
        with patch("dbus.SessionBus"), \
             patch("dbus.mainloop.glib.DBusGMainLoop"), \
             patch("tincand.dbus_service.TincanService") as mock_svc_cls, \
             patch("tincand.backend_manager.BackendManager.__init__", capture_init), \
             patch("tincand.backend_manager.BackendManager.register_service"), \
             patch("tincand.backends.bluez_map.MapBackend.register_service"), \
             patch("tincand.backends.ancs.ANCSBackend.__init__", return_value=None), \
             patch("tincand.backends.ancs.ANCSBackend.register_service"), \
             patch("gi.repository.GLib.MainLoop") as mock_loop_cls, \
             patch("signal.signal"):
            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_loop = MagicMock()
            mock_loop.run.return_value = None
            mock_loop_cls.return_value = mock_loop

            daemon_main.main()

        assert len(created_backends) == 1
        primary_name, sec_names = created_backends[0]
        assert primary_name == "MapBackend"
        assert "ANCSBackend" in sec_names

    def test_with_ancs_ancs_backend_logs_warning(self, monkeypatch, caplog):
        from tincand import __main__ as daemon_main

        monkeypatch.setattr(sys, "argv", ["tincand", "--backend", "ancs", "--with-ancs"])
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)
        monkeypatch.setenv("TINCAN_DEVICE", "AA:BB:CC:DD:EE:FF")

        backend_manager_created = []

        with patch("dbus.SessionBus"), \
             patch("dbus.mainloop.glib.DBusGMainLoop"), \
             patch("tincand.dbus_service.TincanService") as mock_svc_cls, \
             patch("tincand.backends.ancs.ANCSBackend.__init__", return_value=None), \
             patch("tincand.backends.ancs.ANCSBackend.register_service"), \
             patch("tincand.backends.ancs.ANCSBackend.connect"), \
             patch("tincand.backends.ancs.ANCSBackend.disconnect"), \
             patch("tincand.backend_manager.BackendManager.__init__",
                   side_effect=lambda *a, **kw: backend_manager_created.append(True)), \
             patch("gi.repository.GLib.MainLoop") as mock_loop_cls, \
             patch("signal.signal"):
            mock_svc = MagicMock()
            mock_svc_cls.return_value = mock_svc
            mock_loop = MagicMock()
            mock_loop.run.return_value = None
            mock_loop_cls.return_value = mock_loop

            with caplog.at_level(logging.WARNING, logger="tincand.__main__"):
                daemon_main.main()

        assert backend_manager_created == []
        assert any("with-ancs" in r.message.lower() or "ignoring" in r.message.lower()
                   for r in caplog.records)
