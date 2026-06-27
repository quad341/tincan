"""Tests: tincand.__main__ — _select_backend(), _mac_from_ofono_path(), _resolve_device_address().
Bead: tincan-spa (§1–4), tincan-17bsu (§5–6)

Coverage:
  §1 _select_backend() — --backend flag selects correct backend class
  §2 _select_backend() — TINCAN_BACKEND env var selects correct backend class
  §3 _select_backend() — exits when no backend is specified
  §4 _select_backend() — exits when unknown backend name is provided
  §5 _mac_from_ofono_path() — extracts MAC from oFono modem path (3 cases)
  §6 _resolve_device_address() — 5-branch priority chain (CLI, env, DaemonSettings, oFono, empty)
  §7 main() D-Bus mainloop install order (regression: oFono call control)

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
# §5 _mac_from_ofono_path — MAC extraction from oFono modem path (tincan-17bsu)
# ---------------------------------------------------------------------------

class TestMacFromOfonoPath:
    """_mac_from_ofono_path() extracts a Bluetooth MAC from an oFono modem path."""

    def test_valid_path_returns_mac(self):
        from tincand.__main__ import _mac_from_ofono_path
        result = _mac_from_ofono_path("/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20")
        assert result == "D0:6B:78:33:46:20"

    def test_path_too_short_returns_empty(self):
        from tincand.__main__ import _mac_from_ofono_path
        assert _mac_from_ofono_path("/hfp/org/bluez/hci1/dev_D0_6B") == ""

    def test_no_dev_segment_returns_empty(self):
        from tincand.__main__ import _mac_from_ofono_path
        assert _mac_from_ofono_path("/hfp/org/bluez/hci1") == ""


# ---------------------------------------------------------------------------
# §6 _resolve_device_address — 5-branch priority chain (tincan-17bsu)
# ---------------------------------------------------------------------------

def _ns(device=None):
    ns = argparse.Namespace()
    ns.device = device
    return ns


class TestResolveDeviceAddressCLI:
    """Branch 1: --device CLI flag takes highest priority."""

    def test_cli_flag_returns_address(self):
        from tincand.__main__ import _resolve_device_address
        addr, discovered = _resolve_device_address(_ns(device="AA:BB:CC:DD:EE:FF"))
        assert addr == "AA:BB:CC:DD:EE:FF"

    def test_cli_flag_device_discovered_is_false(self):
        from tincand.__main__ import _resolve_device_address
        _, discovered = _resolve_device_address(_ns(device="D0:6B:78:33:46:20"))
        assert discovered is False


class TestResolveDeviceAddressEnv:
    """Branch 2: TINCAN_DEVICE env var (below CLI flag, above config)."""

    def test_env_var_returns_address(self, monkeypatch):
        monkeypatch.setenv("TINCAN_DEVICE", "11:22:33:44:55:66")
        from tincand.__main__ import _resolve_device_address
        addr, discovered = _resolve_device_address(_ns())
        assert addr == "11:22:33:44:55:66"
        assert discovered is False

    def test_cli_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TINCAN_DEVICE", "11:22:33:44:55:66")
        from tincand.__main__ import _resolve_device_address
        addr, _ = _resolve_device_address(_ns(device="AA:BB:CC:DD:EE:FF"))
        assert addr == "AA:BB:CC:DD:EE:FF"


class TestResolveDeviceAddressDaemonSettings:
    """Branch 3: DaemonSettings bluetooth/device_address from tincan.ini."""

    def test_daemon_settings_returns_address(self, monkeypatch):
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)
        mock_ds = MagicMock()
        mock_ds.return_value.value.return_value = "D0:6B:78:33:46:20"
        with patch("tincand.config.DaemonSettings", mock_ds):
            from tincand.__main__ import _resolve_device_address
            addr, discovered = _resolve_device_address(_ns())
        assert addr == "D0:6B:78:33:46:20"
        assert discovered is False

    def test_env_overrides_daemon_settings(self, monkeypatch):
        monkeypatch.setenv("TINCAN_DEVICE", "AA:BB:CC:DD:EE:FF")
        mock_ds = MagicMock()
        mock_ds.return_value.value.return_value = "D0:6B:78:33:46:20"
        with patch("tincand.config.DaemonSettings", mock_ds):
            from tincand.__main__ import _resolve_device_address
            addr, _ = _resolve_device_address(_ns())
        assert addr == "AA:BB:CC:DD:EE:FF"


class TestResolveDeviceAddressOFono:
    """Branch 4: oFono auto-discovery — device_discovered=True."""

    def _mock_dbus_with_modems(self, modems):
        mock_manager = MagicMock()
        mock_manager.GetModems.return_value = modems
        mock_dbus = MagicMock()
        mock_dbus.Interface.return_value = mock_manager
        return mock_dbus

    def test_ofono_discovery_returns_mac_and_discovered_true(self, monkeypatch):
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)
        mock_ds = MagicMock()
        mock_ds.return_value.value.return_value = ""
        mock_dbus = self._mock_dbus_with_modems([
            ("/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20", {"Type": "hfp", "Online": True}),
        ])
        with patch.dict(sys.modules, {"dbus": mock_dbus}):
            with patch("tincand.config.DaemonSettings", mock_ds):
                from tincand.__main__ import _resolve_device_address
                addr, discovered = _resolve_device_address(_ns())
        assert addr == "D0:6B:78:33:46:20"
        assert discovered is True

    def test_ofono_unavailable_falls_through_to_empty(self, monkeypatch):
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)
        mock_ds = MagicMock()
        mock_ds.return_value.value.return_value = ""
        mock_dbus = MagicMock()
        mock_dbus.SystemBus.side_effect = Exception("no system bus")
        with patch.dict(sys.modules, {"dbus": mock_dbus}):
            with patch("tincand.config.DaemonSettings", mock_ds):
                from tincand.__main__ import _resolve_device_address
                addr, discovered = _resolve_device_address(_ns())
        assert addr == ""
        assert discovered is False


class TestResolveDeviceAddressEmpty:
    """Branch 5: no source provides an address — waiting/retry mode."""

    def test_all_sources_empty_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("TINCAN_DEVICE", raising=False)
        mock_ds = MagicMock()
        mock_ds.return_value.value.return_value = ""
        mock_dbus = MagicMock()
        mock_dbus.SystemBus.side_effect = ImportError("dbus not available")
        with patch.dict(sys.modules, {"dbus": mock_dbus}):
            with patch("tincand.config.DaemonSettings", mock_ds):
                from tincand.__main__ import _resolve_device_address
                addr, discovered = _resolve_device_address(_ns())
        assert addr == ""
        assert discovered is False


# ---------------------------------------------------------------------------
# §7 D-Bus mainloop install order (regression: oFono call control)
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
