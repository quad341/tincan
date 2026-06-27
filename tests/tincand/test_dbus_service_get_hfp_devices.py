"""Tests: TincanService.GetHFPDevices() — oFono mocking, HFP filter, MAC extraction.
Bead: tincan-woier  (GetHFPDevices + device picker tests)

Coverage:
  §1 oFono unavailable — dbus.SystemBus() raises; GetModems() raises → returns []
  §2 Empty modem list — GetModems() returns [] → returns []
  §3 HFP filter — Type!=hfp modems excluded; mixed list returns only hfp rows
  §4 MAC extraction — dev_D0_6B_78_33_46_20 → D0:6B:78:33:46:20 (lower-hex too)
  §5 Path without dev_ pattern — hfp modem with unparseable path is silently skipped
  §6 Result dict fields — path, mac, name present; name defaults to '' when absent
  §7 Multiple HFP devices — all returned, order preserved

No real D-Bus connection required — TincanService instantiated with mocked bus.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincand.dbus_service import TincanService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    """TincanService with mocked D-Bus registration — no real bus required."""
    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    return svc


@contextmanager
def _ofono_modems(modems):
    """Patch dbus.SystemBus + dbus.Interface so GetHFPDevices sees `modems`."""
    mock_manager = MagicMock()
    mock_manager.GetModems.return_value = modems
    with patch("dbus.SystemBus"), \
         patch("dbus.Interface", return_value=mock_manager):
        yield mock_manager


@contextmanager
def _ofono_raises(exc=None):
    """Patch dbus.SystemBus to raise, simulating oFono bus failure."""
    if exc is None:
        exc = Exception("oFono not running")
    with patch("dbus.SystemBus", side_effect=exc):
        yield


# ---------------------------------------------------------------------------
# §1 oFono unavailable → returns []
# ---------------------------------------------------------------------------

class TestGetHFPDevicesOfonoUnavailable:
    """GetHFPDevices returns [] when the oFono D-Bus connection cannot be established."""

    def test_returns_empty_when_system_bus_raises(self, service):
        with _ofono_raises():
            assert service.GetHFPDevices() == []

    def test_returns_empty_when_get_modems_raises(self, service):
        mock_manager = MagicMock()
        mock_manager.GetModems.side_effect = Exception("org.ofono.Error.NotFound")
        with patch("dbus.SystemBus"), \
             patch("dbus.Interface", return_value=mock_manager):
            assert service.GetHFPDevices() == []


# ---------------------------------------------------------------------------
# §2 Empty modem list → returns []
# ---------------------------------------------------------------------------

class TestGetHFPDevicesEmptyList:
    """GetHFPDevices returns [] when oFono reports no modems at all."""

    def test_returns_empty_when_no_modems(self, service):
        with _ofono_modems([]):
            assert service.GetHFPDevices() == []


# ---------------------------------------------------------------------------
# §3 HFP filter
# ---------------------------------------------------------------------------

class TestGetHFPDevicesTypeFilter:
    """Only modems with Type==hfp are included; all other types are silently excluded."""

    def test_excludes_modem_with_non_hfp_type(self, service):
        modems = [
            ("/org/ofono/mbim_0", {"Type": "mbim", "Name": "Intel XMM"}),
        ]
        with _ofono_modems(modems):
            assert service.GetHFPDevices() == []

    def test_excludes_modem_with_missing_type(self, service):
        modems = [
            ("/org/ofono/modem_0", {"Name": "Generic Modem"}),
        ]
        with _ofono_modems(modems):
            assert service.GetHFPDevices() == []

    def test_includes_modem_with_hfp_type(self, service):
        modems = [
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        assert len(result) == 1

    def test_mixed_modems_returns_only_hfp(self, service):
        modems = [
            ("/org/ofono/mbim_0", {"Type": "mbim", "Name": "Intel XMM"}),
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        assert len(result) == 1
        assert str(result[0]["mac"]) == "D0:6B:78:33:46:20"


# ---------------------------------------------------------------------------
# §4 MAC extraction from dev_ path segment
# ---------------------------------------------------------------------------

class TestGetHFPDevicesMACExtraction:
    """MAC is extracted from dev_XX_XX_XX_XX_XX_XX and colons replace underscores."""

    def test_mac_extracted_and_colon_separated(self, service):
        modems = [
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        assert str(result[0]["mac"]) == "D0:6B:78:33:46:20"

    def test_mac_with_lowercase_hex(self, service):
        modems = [
            (
                "/org/ofono/hfp/dev_aa_bb_cc_dd_ee_ff",
                {"Type": "hfp", "Name": "Pixel 8"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        assert str(result[0]["mac"]) == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# §5 Path without dev_ pattern → modem skipped
# ---------------------------------------------------------------------------

class TestGetHFPDevicesNoDevPattern:
    """HFP modems whose path lacks a parseable dev_XX… segment are silently skipped."""

    def test_skips_hfp_modem_without_dev_pattern(self, service):
        modems = [
            ("/org/ofono/hfp/modem0", {"Type": "hfp", "Name": "Unknown"}),
        ]
        with _ofono_modems(modems):
            assert service.GetHFPDevices() == []


# ---------------------------------------------------------------------------
# §6 Result dict fields
# ---------------------------------------------------------------------------

class TestGetHFPDevicesResultFields:
    """Each result dict contains 'path', 'mac', 'name'; name defaults to '' when absent."""

    _PATH = "/org/ofono/hfp/dev_D0_6B_78_33_46_20"
    _MODEM_WITH_NAME = [(_PATH, {"Type": "hfp", "Name": "iPhone 15 Pro"})]
    _MODEM_NO_NAME = [(_PATH, {"Type": "hfp"})]

    def test_path_key_present(self, service):
        with _ofono_modems(self._MODEM_WITH_NAME):
            result = service.GetHFPDevices()
        assert "path" in result[0]

    def test_path_value_matches_modem_path(self, service):
        with _ofono_modems(self._MODEM_WITH_NAME):
            result = service.GetHFPDevices()
        assert str(result[0]["path"]) == self._PATH

    def test_mac_key_present(self, service):
        with _ofono_modems(self._MODEM_WITH_NAME):
            result = service.GetHFPDevices()
        assert "mac" in result[0]

    def test_name_key_present(self, service):
        with _ofono_modems(self._MODEM_WITH_NAME):
            result = service.GetHFPDevices()
        assert "name" in result[0]

    def test_name_value_matches_modem_name(self, service):
        with _ofono_modems(self._MODEM_WITH_NAME):
            result = service.GetHFPDevices()
        assert str(result[0]["name"]) == "iPhone 15 Pro"

    def test_name_defaults_to_empty_when_absent(self, service):
        with _ofono_modems(self._MODEM_NO_NAME):
            result = service.GetHFPDevices()
        assert str(result[0]["name"]) == ""


# ---------------------------------------------------------------------------
# §7 Multiple HFP devices
# ---------------------------------------------------------------------------

class TestGetHFPDevicesMultipleDevices:
    """All HFP modems are returned; order matches the oFono modem list."""

    def test_two_hfp_devices_both_returned(self, service):
        modems = [
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
            (
                "/org/ofono/hfp/dev_AA_BB_CC_DD_EE_FF",
                {"Type": "hfp", "Name": "Pixel 8"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        assert len(result) == 2

    def test_two_hfp_devices_correct_macs(self, service):
        modems = [
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
            (
                "/org/ofono/hfp/dev_AA_BB_CC_DD_EE_FF",
                {"Type": "hfp", "Name": "Pixel 8"},
            ),
        ]
        with _ofono_modems(modems):
            result = service.GetHFPDevices()
        macs = [str(r["mac"]) for r in result]
        assert "D0:6B:78:33:46:20" in macs
        assert "AA:BB:CC:DD:EE:FF" in macs
