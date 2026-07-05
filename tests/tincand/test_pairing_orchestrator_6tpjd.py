"""Tests: PairingOrchestrator.computer_name populated from adapter Alias (tincan-ivihc).
Bead: tincan-6tpjd

Coverage:
  §1  Properties.Get("org.bluez.Adapter1", "Alias") returns non-empty string →
      computer_name set to that value after start()
  §2  Properties.Get raises DBusException → computer_name stays 'your computer'

Tests intentionally fail until the builder's ivihc commit is merged into main
(start() reads adapter Alias via Props iface and stores as self.computer_name).

No hardware or real D-Bus required.
Run with: python -m pytest tests/tincand/test_pairing_orchestrator_6tpjd.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import pytest

from tincand.pairing import PairingOrchestrator

_ADAPTER_PATH = "/org/bluez/hci0"
_FAST_TIMEOUT = 0.01


def _make_le_adv_mgr_success():
    le_adv_mgr = MagicMock(name="LEAdvertisingManager1")

    def _reg_adv(adv_obj, options, reply_handler, error_handler):
        reply_handler()

    le_adv_mgr.RegisterAdvertisement.side_effect = _reg_adv
    return le_adv_mgr


def _make_bus_with_alias(le_adv_mgr: MagicMock, alias: str) -> MagicMock:
    """Bus mock whose org.freedesktop.DBus.Properties returns *alias* from Get()."""
    bus = MagicMock(name="SystemBus")
    bus.get_object.side_effect = lambda s, p: MagicMock(name=f"obj({p})")

    props_mock = MagicMock(name="Properties")
    props_mock.Get.return_value = alias

    def _iface(obj, iface):
        if iface == "org.bluez.LEAdvertisingManager1":
            return le_adv_mgr
        if iface == "org.freedesktop.DBus.Properties":
            return props_mock
        return MagicMock(name=f"Interface({iface})")

    bus._make_iface = _iface
    return bus


def _make_bus_props_raises(le_adv_mgr: MagicMock) -> MagicMock:
    """Bus mock whose org.freedesktop.DBus.Properties.Get raises DBusException."""
    bus = MagicMock(name="SystemBus")
    bus.get_object.side_effect = lambda s, p: MagicMock(name=f"obj({p})")

    props_mock = MagicMock(name="Properties")
    props_mock.Get.side_effect = dbus.DBusException("simulated adapter query failure")

    def _iface(obj, iface):
        if iface == "org.bluez.LEAdvertisingManager1":
            return le_adv_mgr
        if iface == "org.freedesktop.DBus.Properties":
            return props_mock
        return MagicMock(name=f"Interface({iface})")

    bus._make_iface = _iface
    return bus


@pytest.fixture
def alias_ctx():
    """Orchestrator wired to a Properties mock that returns 'Roglet\\'s Laptop'."""
    le_adv_mgr = _make_le_adv_mgr_success()
    bus = _make_bus_with_alias(le_adv_mgr, "Roglet's Laptop")
    mock_map = MagicMock(name="BluezMap")
    mock_map.create_session.return_value = MagicMock()
    mock_map.list_messages.return_value = []
    cb = MagicMock()

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=True),
        patch("tincand.pairing.BluezMap", return_value=mock_map),
    ):
        orch = PairingOrchestrator(
            on_state_change=cb,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        yield orch


@pytest.fixture
def dbus_exc_ctx():
    """Orchestrator wired to a Properties mock whose Get raises DBusException."""
    le_adv_mgr = _make_le_adv_mgr_success()
    bus = _make_bus_props_raises(le_adv_mgr)
    mock_map = MagicMock(name="BluezMap")
    mock_map.create_session.return_value = MagicMock()
    mock_map.list_messages.return_value = []
    cb = MagicMock()

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=True),
        patch("tincand.pairing.BluezMap", return_value=mock_map),
    ):
        orch = PairingOrchestrator(
            on_state_change=cb,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        yield orch


# ---------------------------------------------------------------------------
# §1 & §2 computer_name from adapter Alias
# ---------------------------------------------------------------------------


class TestComputerNameFromAlias:
    """PairingOrchestrator.start() reads adapter Alias and stores as computer_name."""

    def test_computer_name_set_to_adapter_alias_after_start(self, alias_ctx):
        alias_ctx.start()
        assert alias_ctx.computer_name == "Roglet's Laptop"

    def test_computer_name_is_default_when_dbus_exception(self, dbus_exc_ctx):
        dbus_exc_ctx.start()
        assert dbus_exc_ctx.computer_name == "your computer"
