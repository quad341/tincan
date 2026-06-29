"""Behavioral acceptance tests: BT HFP device picker in Settings.

Mirrors tests/tincan_gui/test_adapter_picker.py for the parallel device-picker
surface (GetHFPDevices → get_hfp_devices() → _DeviceLoader → _populate_device_combo
→ _on_device_changed).

Coverage:
  §1 Populate — normal state (one discovered device)
    - item 0 = 'Auto-discover (recommended)' with UserRole == ''
    - item 1 label == '<mac> (<name>)' with UserRole == mac
  §2 Persist — _on_device_changed writes bluetooth/device_address
    - selecting a device row writes its mac
    - selecting Auto-discover writes ''
  §3 Empty list — oFono returns no HFP modems
    - combo still has the Auto-discover row and is enabled
  §4 Saved-but-undiscovered MAC restore
    - a saved mac not present among discovered devices is appended and selected

All tests mock TincandClient — no real D-Bus required.
Run with: python -m pytest tests/tincan_gui/test_device_picker.py -v
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.settings_dialog import SettingsDialog

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_ONE_DEVICE = [
    {
        "path": "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
        "mac": "D0:6B:78:33:46:20",
        "name": "iPhone 15 Pro",
    },
]

# An adapter is needed so the BT section stays enabled (the device combo's
# effective enabled state depends on its parent section).
_ONE_ADAPTER = [
    {
        "path": "/org/bluez/hci0",
        "alias": "MT7925 (built-in)",
        "address": "00:E1:0D:9A:3F:12",
        "powered": True,
        "hfp_sco_capable": True,
        "le_capable": True,
    },
]


@pytest.fixture(autouse=True)
def _no_tray_show():
    from unittest.mock import patch

    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


def _patch_daemon_settings(monkeypatch, saved_mac="", written=None):
    """Patch tincand.config.DaemonSettings with a fake that captures writes.

    Returns the dict that captures setValue() calls.
    """
    if written is None:
        written = {}

    class _FakeDaemonSettings:
        def value(self, key, default=None, type=None):
            if key == "bluetooth/device_address":
                return saved_mac
            return default

        def setValue(self, key, val):
            written[key] = val

        def sync(self):
            pass

    monkeypatch.setattr("tincand.config.DaemonSettings", _FakeDaemonSettings)
    return written


def _make_dialog(qtbot, monkeypatch, devices, adapters=None):
    """Create SettingsDialog with a mocked client returning `devices`/`adapters`."""
    monkeypatch.setattr(
        TincandClient, "get_adapters", lambda self: adapters or _ONE_ADAPTER
    )
    monkeypatch.setattr(TincandClient, "get_hfp_devices", lambda self: devices)
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})

    client = TincandClient.__new__(TincandClient)
    dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    # Device combo is populated from a background thread; wait for it.
    qtbot.waitUntil(lambda: dlg._device_combo.count() >= 1, timeout=2000)
    return dlg


# ---------------------------------------------------------------------------
# §1 Populate — normal state (one discovered device)
# ---------------------------------------------------------------------------

class TestDevicePopulateNormalState:
    """One discovered device: Auto-discover row first, then a MAC-first device row."""

    def test_autodiscover_row_first_with_empty_userrole(self, qtbot, monkeypatch):
        _patch_daemon_settings(monkeypatch)
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_DEVICE)
        assert dlg._device_combo.itemText(0) == "Auto-discover (recommended)"
        assert dlg._device_combo.itemData(0, Qt.ItemDataRole.UserRole) == ""

    def test_device_row_label_is_mac_first(self, qtbot, monkeypatch):
        _patch_daemon_settings(monkeypatch)
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_DEVICE)
        assert dlg._device_combo.count() == 2
        assert dlg._device_combo.itemText(1) == "D0:6B:78:33:46:20 (iPhone 15 Pro)"
        assert (
            dlg._device_combo.itemData(1, Qt.ItemDataRole.UserRole)
            == "D0:6B:78:33:46:20"
        )


# ---------------------------------------------------------------------------
# §2 Persist — _on_device_changed writes bluetooth/device_address
# ---------------------------------------------------------------------------

class TestDeviceSelectionPersists:
    """Selecting a device writes its mac; selecting Auto-discover writes ''."""

    def test_selecting_device_writes_mac(self, qtbot, monkeypatch):
        written = _patch_daemon_settings(monkeypatch)
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_DEVICE)
        dlg._device_combo.setCurrentIndex(1)
        qtbot.waitUntil(
            lambda: "bluetooth/device_address" in written, timeout=1000
        )
        assert written["bluetooth/device_address"] == "D0:6B:78:33:46:20"

    def test_selecting_autodiscover_writes_empty(self, qtbot, monkeypatch):
        written = _patch_daemon_settings(monkeypatch)
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_DEVICE)
        # Move to the device row, then back to Auto-discover.
        dlg._device_combo.setCurrentIndex(1)
        dlg._device_combo.setCurrentIndex(0)
        qtbot.waitUntil(
            lambda: written.get("bluetooth/device_address") == "", timeout=1000
        )
        assert written["bluetooth/device_address"] == ""


# ---------------------------------------------------------------------------
# §3 Empty list — oFono returns no HFP modems
# ---------------------------------------------------------------------------

class TestDeviceEmptyList:
    """Empty get_hfp_devices(): combo still has the Auto-discover row and is enabled."""

    def test_autodiscover_present_and_enabled_when_no_devices(self, qtbot, monkeypatch):
        _patch_daemon_settings(monkeypatch)
        dlg = _make_dialog(qtbot, monkeypatch, [])
        assert dlg._device_combo.count() == 1
        assert dlg._device_combo.itemText(0) == "Auto-discover (recommended)"
        assert dlg._device_combo.isEnabled()


# ---------------------------------------------------------------------------
# §4 Saved-but-undiscovered MAC restore
# ---------------------------------------------------------------------------

class TestSavedMacRestore:
    """A saved mac not among discovered devices is appended as a synthetic row."""

    def test_undiscovered_saved_mac_appended_and_selected(self, qtbot, monkeypatch):
        saved = "AA:BB:CC:DD:EE:FF"  # not in _ONE_DEVICE
        _patch_daemon_settings(monkeypatch, saved_mac=saved)
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_DEVICE)

        # Auto-discover + discovered device + synthetic saved row = 3 items.
        assert dlg._device_combo.count() == 3
        idx = dlg._device_combo.currentIndex()
        assert dlg._device_combo.itemData(idx, Qt.ItemDataRole.UserRole) == saved
        assert dlg._device_combo.itemText(idx) == saved
