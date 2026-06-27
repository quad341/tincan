"""Tests: tincand.__main__ — _select_backend() backend selection logic.
Bead: tincan-spa

Coverage:
  §1 _select_backend() — --backend flag selects correct backend class
  §2 _select_backend() — TINCAN_BACKEND env var selects correct backend class
  §3 _select_backend() — exits when no backend is specified
  §4 _select_backend() — exits when unknown backend name is provided

No hardware or real D-Bus required.
Run with: python -m pytest tests/tincand/test_main.py -v
"""
from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from tincand.__main__ import _select_backend
from tincand.backends.mock import MockBackend


def _args(backend=None, device=None):
    ns = argparse.Namespace()
    ns.backend = backend
    ns.device = device
    return ns


# ---------------------------------------------------------------------------
# §1 --backend flag
# ---------------------------------------------------------------------------

class TestSelectBackendFlag:
    def test_backend_mock_returns_mock_backend(self):
        result = _select_backend(_args(backend="mock"))
        assert isinstance(result, MockBackend)

    def test_backend_ancs_returns_ancs_backend(self):
        from tincand.backends.ancs import ANCSBackend
        result = _select_backend(_args(backend="ancs"))
        assert isinstance(result, ANCSBackend)

    def test_backend_ancs_passes_device_from_flag(self):
        from tincand.backends.ancs import ANCSBackend
        result = _select_backend(_args(backend="ancs"), device_addr="AA:BB:CC:DD:EE:FF")
        assert isinstance(result, ANCSBackend)
        assert result._device_addr == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# §2 TINCAN_BACKEND env var
# ---------------------------------------------------------------------------

class TestSelectBackendEnv:
    def test_env_mock_returns_mock_backend(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "mock")
        result = _select_backend(_args())
        assert isinstance(result, MockBackend)

    def test_env_ancs_returns_ancs_backend(self, monkeypatch):
        from tincand.backends.ancs import ANCSBackend
        monkeypatch.setenv("TINCAN_BACKEND", "ancs")
        result = _select_backend(_args())
        assert isinstance(result, ANCSBackend)

    def test_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "ancs")
        result = _select_backend(_args(backend="mock"))
        assert isinstance(result, MockBackend)


# ---------------------------------------------------------------------------
# §3 No backend → sys.exit
# ---------------------------------------------------------------------------

class TestSelectBackendNoBackend:
    def test_no_backend_calls_sys_exit(self, monkeypatch):
        monkeypatch.delenv("TINCAN_BACKEND", raising=False)
        with pytest.raises(SystemExit):
            _select_backend(_args())

    def test_empty_env_calls_sys_exit(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "")
        with pytest.raises(SystemExit):
            _select_backend(_args())


# ---------------------------------------------------------------------------
# §4 Unknown backend → sys.exit
# ---------------------------------------------------------------------------

class TestSelectBackendUnknown:
    def test_unknown_backend_flag_calls_sys_exit(self):
        with pytest.raises(SystemExit):
            _select_backend(_args(backend="bluez-map"))

    def test_unknown_env_backend_calls_sys_exit(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "unknown_backend")
        with pytest.raises(SystemExit):
            _select_backend(_args())


# ---------------------------------------------------------------------------
# §5 D-Bus mainloop install order (regression: oFono call control)
# ---------------------------------------------------------------------------

class TestMainDbusMainloopOrdering:
    """main() must install the GLib D-Bus mainloop as default BEFORE the first
    SystemBus() is created.

    dbus-python caches the SystemBus singleton; a connection opened before the
    default mainloop is set can never subscribe to signals ("connections must be
    attached to a main loop"). When that happened, CallController's oFono bridge
    silently failed and every im.tincan.Calls method returned NotAvailable —
    calls looked broken with no obvious cause. This locks the ordering in.
    """

    def test_dbus_mainloop_installed_before_first_system_bus(self, monkeypatch):
        import dbus
        import dbus.mainloop.glib

        from tincand import __main__ as m

        order: list[str] = []

        monkeypatch.setattr(
            dbus.mainloop.glib, "DBusGMainLoop",
            lambda set_as_default=False: order.append("mainloop"),
        )
        monkeypatch.setattr(
            dbus, "SystemBus", lambda: (order.append("systembus"), MagicMock())[1],
        )
        monkeypatch.setattr(dbus, "SessionBus", lambda: MagicMock())

        # Neutralise everything else main() touches — no real D-Bus, Qt, or GLib loop.
        monkeypatch.delenv("TINCAN_ADAPTER", raising=False)
        monkeypatch.delenv("TINCAN_BACKEND", raising=False)
        monkeypatch.setattr(
            "tincand.config.DaemonSettings",
            lambda *a, **k: MagicMock(value=lambda *a, **k: None),
        )
        monkeypatch.setattr("tincand.dbus_service.TincanService", MagicMock())
        monkeypatch.setattr("tincand.call_controller.CallController", MagicMock())
        monkeypatch.setattr(m, "_select_backend", lambda *a, **k: MagicMock())
        monkeypatch.setattr(m.GLib, "MainLoop", lambda: MagicMock(run=lambda: None))
        monkeypatch.setattr("signal.signal", lambda *a, **k: None)
        monkeypatch.setattr(
            sys, "argv", ["tincand", "--backend", "mock", "--device", "AA:BB:CC:DD:EE:FF"],
        )

        m.main()

        assert "mainloop" in order, "main() never installed the D-Bus GLib mainloop"
        assert "systembus" in order, "test did not exercise a SystemBus() creation"
        assert order.index("mainloop") < order.index("systembus"), (
            f"SystemBus() created before DBusGMainLoop(set_as_default=True): {order}"
        )
