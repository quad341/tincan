"""Tests: tincand.adapter_check — list_adapters() and HFP capability detection.
Bead: tincan-azcok

Coverage:
  §1 list_adapters() — adapter enumeration
    - 0 adapters: empty ManagedObjects → returns []
    - 1 adapter: single valid path → returns one-element list
    - 2+ adapters: two valid paths → returns two-element list
  §2 list_adapters() — error handling
    - BlueZ DBusException → returns [] without crash
  §3 list_adapters() — single GetManagedObjects() call
    - call_count == 1 with 0 adapters
    - call_count == 1 with 1 adapter
    - call_count == 1 with 2 adapters
  §4 list_adapters() — path validation
    - device path (/org/bluez/hci0/dev_...) skipped
    - path with non-digit hci suffix (hciabc) skipped
  §5 list_adapters() — returned dict structure
    - all dicts contain {path, alias, address, powered, hfp_sco_capable, le_capable}
    - le_capable True when LEAdvertisingManager1 present
    - le_capable False when LEAdvertisingManager1 absent
  §6 detect_adapter_hfp_sco_capability() — USB ID lookup
    - known-good USB ID (0bda:8761, RTL8761B) → True
    - known-bad USB ID (monkeypatched False entry) → False
    - None → None
    - empty string → None
    - non-USB modalias → None

No hardware or D-Bus required — bus arg and dbus.Interface are mocked.
Run with: python -m pytest tests/tincand/test_adapter_check.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import dbus

import tincand.adapter_check as adapter_check_mod
from tincand.adapter_check import (
    detect_adapter_hfp_sco_capability,
    list_adapters,
)

_ADAPTER_IFACE = "org.bluez.Adapter1"
_LE_ADV_MGR_IFACE = "org.bluez.LEAdvertisingManager1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter_objects(*entries: tuple[str, bool]) -> dict:
    """Build a GetManagedObjects return value for the given adapters.

    Each element is (path, has_le) — has_le controls LEAdvertisingManager1 presence.
    """
    objects: dict = {}
    for path, has_le in entries:
        ifaces: dict = {
            _ADAPTER_IFACE: {
                "Alias": f"Adapter at {path}",
                "Address": "AA:BB:CC:DD:EE:FF",
                "Powered": True,
            }
        }
        if has_le:
            ifaces[_LE_ADV_MGR_IFACE] = {}
        objects[path] = ifaces
    return objects


def _setup_bus(monkeypatch, objects: dict) -> tuple[MagicMock, MagicMock]:
    """Patch dbus.Interface so GetManagedObjects() returns `objects`.

    Also suppresses _read_modalias so no sysfs access occurs.
    Returns (mock_bus, mock_interface).
    """
    mock_interface = MagicMock()
    mock_interface.GetManagedObjects.return_value = objects
    monkeypatch.setattr(
        adapter_check_mod.dbus, "Interface", lambda obj, iface: mock_interface
    )
    monkeypatch.setattr(adapter_check_mod, "_read_modalias", lambda hci_name: "")
    return MagicMock(), mock_interface


# ---------------------------------------------------------------------------
# §1 list_adapters() — adapter enumeration
# ---------------------------------------------------------------------------

class TestListAdaptersEnumeration:
    """list_adapters() returns the correct-length list for 0, 1, and 2+ adapters."""

    def test_zero_adapters_returns_empty_list(self, monkeypatch):
        mock_bus, _ = _setup_bus(monkeypatch, {})
        assert list_adapters(bus=mock_bus) == []

    def test_single_adapter_returns_one_element_list(self, monkeypatch):
        objects = _make_adapter_objects(("/org/bluez/hci0", True))
        mock_bus, _ = _setup_bus(monkeypatch, objects)
        assert len(list_adapters(bus=mock_bus)) == 1

    def test_two_adapters_returns_two_element_list(self, monkeypatch):
        objects = _make_adapter_objects(
            ("/org/bluez/hci0", True),
            ("/org/bluez/hci1", False),
        )
        mock_bus, _ = _setup_bus(monkeypatch, objects)
        assert len(list_adapters(bus=mock_bus)) == 2


# ---------------------------------------------------------------------------
# §2 list_adapters() — error handling
# ---------------------------------------------------------------------------

class TestListAdaptersErrorHandling:
    """list_adapters() returns [] on D-Bus failure without raising."""

    def test_dbus_exception_returns_empty_list(self, monkeypatch):
        mock_interface = MagicMock()
        mock_interface.GetManagedObjects.side_effect = dbus.DBusException(
            "org.freedesktop.DBus.Error.ServiceUnknown: BlueZ not running"
        )
        monkeypatch.setattr(
            adapter_check_mod.dbus, "Interface", lambda obj, iface: mock_interface
        )
        monkeypatch.setattr(adapter_check_mod, "_read_modalias", lambda hci_name: "")
        assert list_adapters(bus=MagicMock()) == []


# ---------------------------------------------------------------------------
# §3 list_adapters() — single GetManagedObjects() call
# ---------------------------------------------------------------------------

class TestListAdaptersSingleCall:
    """GetManagedObjects() is called exactly once regardless of adapter count."""

    def _assert_single_call(self, monkeypatch, objects: dict) -> None:
        mock_bus, mock_interface = _setup_bus(monkeypatch, objects)
        list_adapters(bus=mock_bus)
        assert mock_interface.GetManagedObjects.call_count == 1

    def test_call_count_is_one_with_zero_adapters(self, monkeypatch):
        self._assert_single_call(monkeypatch, {})

    def test_call_count_is_one_with_one_adapter(self, monkeypatch):
        self._assert_single_call(
            monkeypatch, _make_adapter_objects(("/org/bluez/hci0", True))
        )

    def test_call_count_is_one_with_two_adapters(self, monkeypatch):
        self._assert_single_call(
            monkeypatch,
            _make_adapter_objects(("/org/bluez/hci0", True), ("/org/bluez/hci1", False)),
        )


# ---------------------------------------------------------------------------
# §4 list_adapters() — path validation
# ---------------------------------------------------------------------------

class TestListAdaptersPathValidation:
    """Paths not matching ^/org/bluez/hci[0-9]+$ are silently skipped."""

    def test_device_path_is_skipped(self, monkeypatch):
        objects: dict = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                _ADAPTER_IFACE: {
                    "Alias": "Device",
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Powered": True,
                }
            }
        }
        mock_bus, _ = _setup_bus(monkeypatch, objects)
        assert list_adapters(bus=mock_bus) == []

    def test_non_digit_hci_suffix_is_skipped(self, monkeypatch):
        objects: dict = {
            "/org/bluez/hciabc": {
                _ADAPTER_IFACE: {
                    "Alias": "Bad",
                    "Address": "00:00:00:00:00:00",
                    "Powered": False,
                }
            }
        }
        mock_bus, _ = _setup_bus(monkeypatch, objects)
        assert list_adapters(bus=mock_bus) == []


# ---------------------------------------------------------------------------
# §5 list_adapters() — returned dict structure
# ---------------------------------------------------------------------------

class TestListAdaptersDictStructure:
    """Each returned dict has all required keys and correct field values."""

    _REQUIRED_KEYS = {"path", "alias", "address", "powered", "hfp_sco_capable", "le_capable"}

    def _single_result(self, monkeypatch, has_le: bool) -> dict:
        objects = _make_adapter_objects(("/org/bluez/hci0", has_le))
        mock_bus, _ = _setup_bus(monkeypatch, objects)
        return list_adapters(bus=mock_bus)[0]

    def test_all_required_keys_present(self, monkeypatch):
        adapter = self._single_result(monkeypatch, has_le=True)
        assert self._REQUIRED_KEYS <= set(adapter)

    def test_le_capable_true_when_le_adv_manager_present(self, monkeypatch):
        adapter = self._single_result(monkeypatch, has_le=True)
        assert adapter["le_capable"] is True

    def test_le_capable_false_when_le_adv_manager_absent(self, monkeypatch):
        adapter = self._single_result(monkeypatch, has_le=False)
        assert adapter["le_capable"] is False


# ---------------------------------------------------------------------------
# §6 detect_adapter_hfp_sco_capability() — USB ID lookup
# ---------------------------------------------------------------------------

class TestDetectAdapterHfpScoCapability:
    """detect_adapter_hfp_sco_capability() returns True/False/None per USB ID table."""

    def test_known_good_usb_id_returns_true(self):
        # RTL8761B (0bda:8761) is in the table as True
        assert detect_adapter_hfp_sco_capability("usb:v0BDAp8761d0100") is True

    def test_known_bad_usb_id_returns_false(self, monkeypatch):
        # Patch the table to include a known-bad entry for test isolation
        monkeypatch.setitem(
            adapter_check_mod._HFP_SCO_USB_CAPABLE, ("dead", "beef"), False
        )
        assert detect_adapter_hfp_sco_capability("usb:vDEADpBEEFd0100") is False

    def test_none_returns_none(self):
        assert detect_adapter_hfp_sco_capability(None) is None

    def test_empty_string_returns_none(self):
        assert detect_adapter_hfp_sco_capability("") is None

    def test_non_usb_modalias_returns_none(self):
        modalias = "pci:v00001234d00005678sv00000000sd00000000bc0Csc03i30"
        assert detect_adapter_hfp_sco_capability(modalias) is None
