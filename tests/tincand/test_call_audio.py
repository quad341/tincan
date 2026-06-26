"""Tests: tincand/call_audio.py — verify_dongle_adapter, verify_usb_autosuspend_off.
Bead: tincan-3by2j (corrected: tincan-ggh48)

Coverage:
  verify_dongle_adapter:
  - Returns True when adapter_hci matches a path component in modem_path.
  - Returns False when adapter_hci does not match any path component.
  - Returns True (graceful skip) when adapter_hci is empty.
  - No WARNING logged when adapter_hci matches.
  - WARNING logged when adapter_hci is set but path does not contain it.

  verify_usb_autosuspend_off:
  - Returns True when /sys/bus/usb/devices does not exist (sysfs absent — no block).
  - Returns True when matching vendor:product device is not found (dongle absent — no block).
  - Returns True when matching device has power/control='on' (autosuspend disabled).
  - Returns False when matching device has power/control='auto' (autosuspend active).
  - WARNING logged when power/control != 'on'.
  - Returns True when matching device has no power/control file (treated as no block).
  - Non-matching devices do not trigger False even when their control='auto'.
  - Unreadable device directories (OSError) are skipped without crashing.

pathlib.Path is patched at the module level; real sysfs never touched.
"""
from __future__ import annotations

import logging
import pathlib

import pytest

from tincand.call_audio import (
    _DONGLE_USB_PRODUCT,
    _DONGLE_USB_VENDOR,
    verify_dongle_adapter,
    verify_usb_autosuspend_off,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(
    parent: pathlib.Path,
    name: str,
    vendor: str,
    product: str,
    control: str | None = "on",
) -> pathlib.Path:
    """Create a minimal fake sysfs USB device directory under *parent*."""
    dev = parent / name
    dev.mkdir()
    (dev / "idVendor").write_text(vendor + "\n")
    (dev / "idProduct").write_text(product + "\n")
    if control is not None:
        (dev / "power").mkdir()
        (dev / "power" / "control").write_text(control + "\n")
    return dev


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_usb_root(tmp_path, monkeypatch):
    """Redirect pathlib.Path('/sys/bus/usb/devices') to an existing tmp dir."""
    usb_root = tmp_path / "usb_devices"
    usb_root.mkdir()
    _orig = pathlib.Path

    def _factory(*args, **kwargs):
        if args and str(args[0]) == "/sys/bus/usb/devices":
            return usb_root
        return _orig(*args, **kwargs)

    monkeypatch.setattr("tincand.call_audio.pathlib.Path", _factory)
    return usb_root


@pytest.fixture
def missing_usb_root(tmp_path, monkeypatch):
    """Redirect pathlib.Path('/sys/bus/usb/devices') to a non-existent path."""
    missing = tmp_path / "no_usb_devices"
    _orig = pathlib.Path

    def _factory(*args, **kwargs):
        if args and str(args[0]) == "/sys/bus/usb/devices":
            return missing
        return _orig(*args, **kwargs)

    monkeypatch.setattr("tincand.call_audio.pathlib.Path", _factory)
    return missing


# ---------------------------------------------------------------------------
# §1 verify_dongle_adapter
# ---------------------------------------------------------------------------

class TestVerifyDongleAdapter:
    """verify_dongle_adapter — True iff /{adapter_hci}/ appears in modem_path."""

    def test_returns_true_when_adapter_hci_matches_path(self):
        path = "/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20"
        assert verify_dongle_adapter(path, "hci1") is True

    def test_returns_false_when_adapter_hci_not_in_path(self):
        path = "/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20"
        assert verify_dongle_adapter(path, "hci1") is False

    def test_returns_true_when_adapter_hci_empty(self):
        assert verify_dongle_adapter("/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20", "") is True

    def test_no_warning_when_adapter_hci_matches(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_dongle_adapter("/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20", "hci1")
        assert not any(r.levelname == "WARNING" for r in caplog.records)

    def test_warning_logged_when_adapter_hci_not_in_path(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_dongle_adapter("/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20", "hci1")
        assert any(r.levelname == "WARNING" for r in caplog.records)


# ---------------------------------------------------------------------------
# §2 verify_usb_autosuspend_off
# ---------------------------------------------------------------------------

class TestVerifyUsbAutosuspendOff:
    """verify_usb_autosuspend_off — checks RTL8761B USB power/control via sysfs."""

    def test_returns_true_when_usb_devices_absent(self, missing_usb_root):
        assert verify_usb_autosuspend_off() is True

    def test_returns_true_when_dongle_not_found(self, fake_usb_root):
        _make_device(fake_usb_root, "3-1", vendor="1d6b", product="0002", control="auto")
        assert verify_usb_autosuspend_off() is True

    def test_returns_true_when_control_is_on(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="on",
        )
        assert verify_usb_autosuspend_off() is True

    def test_returns_false_when_control_is_auto(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="auto",
        )
        assert verify_usb_autosuspend_off() is False

    def test_warning_logged_when_control_is_auto(self, fake_usb_root, caplog):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="auto",
        )
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_usb_autosuspend_off()
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_returns_true_when_control_file_absent(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control=None,
        )
        assert verify_usb_autosuspend_off() is True

    def test_non_matching_device_auto_does_not_trigger_false(self, fake_usb_root):
        _make_device(fake_usb_root, "3-1", vendor="1d6b", product="0002", control="auto")
        assert verify_usb_autosuspend_off() is True

    def test_skips_unreadable_device_catches_oserror(self, fake_usb_root):
        (fake_usb_root / "3-broken").mkdir()
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="on",
        )
        assert verify_usb_autosuspend_off() is True
