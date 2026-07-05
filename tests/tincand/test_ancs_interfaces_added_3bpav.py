"""Tests: ANCSBackend._on_interfaces_added() — InterfacesAdded receiver (tincan-3bpav).

Coverage:
  §1  InterfacesAdded + Device1/Connected=True → _on_device_connected queued via idle_add
  §2  Double-fire (InterfacesAdded + PropertiesChanged same device) → exactly 1 subscribe
  §3  InterfacesAdded without Device1 interface → no idle_add, ignored
  §4  InterfacesAdded with Connected=False → no idle_add, ignored
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from tincand.ancs_util import (
    CONTROL_POINT_UUID,
    DATA_SOURCE_UUID,
    NOTIF_SOURCE_UUID,
)
from tincand.backends.ancs import ANCSBackend

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_DEV_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
_NOTIF_SRC_PATH = f"{_DEV_PATH}/service01/char01"
_CTRL_PT_PATH = f"{_DEV_PATH}/service01/char02"
_DATA_SRC_PATH = f"{_DEV_PATH}/service01/char03"

_DEVICE_IFACE = "org.bluez.Device1"
_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"


def _make_managed_objects():
    return {
        _NOTIF_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": NOTIF_SOURCE_UUID}},
        _CTRL_PT_PATH: {_GATT_CHAR_IFACE: {"UUID": CONTROL_POINT_UUID}},
        _DATA_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": DATA_SOURCE_UUID}},
    }


# ---------------------------------------------------------------------------
# Fixtures — matches the style of test_ancs_backend.py
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
    """Mocked D-Bus environment; backend registered with mock service."""
    mock_bus = MagicMock(name="SystemBus")
    mock_ctrl_pt = MagicMock(name="ControlPoint")
    mock_service = MagicMock(name="TincanService")
    mock_device = MagicMock(name="Device1")
    mock_device.Get.return_value = True  # Bonded=True

    obj_mgr_mock = MagicMock(name="ObjectManager")
    obj_mgr_mock.GetManagedObjects.return_value = _make_managed_objects()

    def _get_object(service, path):
        obj = MagicMock(name=f"obj({path})")
        obj._dbus_path = str(path)
        return obj

    mock_bus.get_object.side_effect = _get_object

    def _make_interface(obj, iface):
        path = getattr(obj, "_dbus_path", "")
        if iface == "org.freedesktop.DBus.ObjectManager":
            return obj_mgr_mock
        if iface == _DEVICE_IFACE:
            return mock_device
        if iface == "org.bluez.GattCharacteristic1" and path == _CTRL_PT_PATH:
            return mock_ctrl_pt
        return MagicMock(name=f"Interface({iface}@{path})")

    with (
        patch("dbus.service.Object.__init__", return_value=None),
        patch("tincand.backends.ancs.dbus.SystemBus", return_value=mock_bus),
        patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_interface),
        patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
    ):
        mock_exc.DBusException = Exception
        backend = ANCSBackend()
        backend.register_service(mock_service)
        yield backend, mock_bus, mock_ctrl_pt, mock_service


@pytest.fixture
def started(ctx):
    """backend.start() called; device not yet connected."""
    backend, mock_bus, mock_ctrl_pt, mock_service = ctx
    backend.start()
    return backend, mock_bus, mock_ctrl_pt, mock_service


# ---------------------------------------------------------------------------
# §1 InterfacesAdded + Connected=True → idle_add queues _on_device_connected
# ---------------------------------------------------------------------------

class TestInterfacesAddedConnectedTrue:
    """Connected=True in Device1 interface → _on_device_connected queued via idle_add."""

    def test_connected_true_queues_on_device_connected(self, started):
        backend, *_ = started
        interfaces = {_DEVICE_IFACE: {"Connected": True}}
        with patch("tincand.backends.ancs.GLib.idle_add") as mock_idle:
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_idle.assert_called_once_with(backend._on_device_connected, _DEV_PATH)

    def test_connected_true_eventually_sets_ancs_capability(self, started):
        """When idle_add fires, the backend sets ancs=True (end-to-end smoke)."""
        backend, _, _, mock_service = started
        interfaces = {_DEVICE_IFACE: {"Connected": True}}
        with patch("tincand.backends.ancs.GLib.idle_add", side_effect=lambda fn, *a: fn(*a)):
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_connected_true_object_path_passed_as_string(self, started):
        """object_path is coerced to str before being passed to idle_add."""
        backend, *_ = started
        # Use a non-string type (dbus.ObjectPath is a str subclass, but test the coercion intent)
        interfaces = {_DEVICE_IFACE: {"Connected": True}}
        captured = []
        def _capture(fn, *args):
            captured.append(args)
        with patch("tincand.backends.ancs.GLib.idle_add", side_effect=_capture):
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        assert len(captured) == 1
        assert isinstance(captured[0][0], str)


# ---------------------------------------------------------------------------
# §2 Double-fire: InterfacesAdded + PropertiesChanged → exactly 1 subscribe
# ---------------------------------------------------------------------------

class TestDoubleFire:
    """Both InterfacesAdded and PropertiesChanged(Connected=True) fire for the same device.

    The double-subscribe guard in _on_device_connected (_notif_src_path is not None → return)
    ensures the second trigger does nothing even if idle_add fires after the direct call.
    """

    def test_double_fire_only_one_ancs_capability_set(self, started):
        """set_capability('ancs', True) is called exactly once despite two triggers."""
        backend, _, _, mock_service = started
        interfaces = {_DEVICE_IFACE: {"Connected": True}}

        idle_queue = []
        with patch(
            "tincand.backends.ancs.GLib.idle_add",
            side_effect=lambda fn, *a: idle_queue.append((fn, a)),
        ):
            backend._on_interfaces_added(_DEV_PATH, interfaces)  # queues idle_add
            backend._on_device_connected(_DEV_PATH)              # PropertiesChanged: direct call

        # Fire the queued idle_add — guard should block a second subscription
        for fn, args in idle_queue:
            fn(*args)

        calls = [c for c in mock_service.set_capability.call_args_list if c == call("ancs", True)]
        assert len(calls) == 1, (
            f"Expected 1 subscribe, got {len(calls)}: {mock_service.set_capability.call_args_list}"
        )

    def test_double_fire_notif_src_path_set_once(self, started):
        """_notif_src_path is set after the first trigger; guard prevents reset."""
        backend, *_ = started
        interfaces = {_DEVICE_IFACE: {"Connected": True}}

        idle_queue = []
        with patch(
            "tincand.backends.ancs.GLib.idle_add",
            side_effect=lambda fn, *a: idle_queue.append((fn, a)),
        ):
            backend._on_device_connected(_DEV_PATH)              # first subscriber
            backend._on_interfaces_added(_DEV_PATH, interfaces)  # queues idle_add

        path_after_first = backend._notif_src_path

        for fn, args in idle_queue:
            fn(*args)

        assert backend._notif_src_path == path_after_first  # unchanged — guard worked


# ---------------------------------------------------------------------------
# §3 InterfacesAdded without Device1 interface → ignored
# ---------------------------------------------------------------------------

class TestInterfacesAddedNoDevice1:
    """If Device1 is absent from the added interfaces, the event is ignored."""

    def test_no_device1_interface_no_idle_add(self, started):
        backend, *_ = started
        interfaces = {"org.bluez.GattService1": {"UUID": "some-uuid"}}
        with patch("tincand.backends.ancs.GLib.idle_add") as mock_idle:
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_idle.assert_not_called()

    def test_empty_interfaces_dict_no_idle_add(self, started):
        backend, *_ = started
        with patch("tincand.backends.ancs.GLib.idle_add") as mock_idle:
            backend._on_interfaces_added(_DEV_PATH, {})
        mock_idle.assert_not_called()

    def test_no_device1_no_capability_set(self, started):
        backend, _, _, mock_service = started
        interfaces = {"org.bluez.LEAdvertisement1": {}}
        backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_service.set_capability.assert_not_called()


# ---------------------------------------------------------------------------
# §4 InterfacesAdded with Connected=False → ignored
# ---------------------------------------------------------------------------

class TestInterfacesAddedConnectedFalse:
    """Device1 present but Connected=False → event is ignored."""

    def test_connected_false_no_idle_add(self, started):
        backend, *_ = started
        interfaces = {_DEVICE_IFACE: {"Connected": False}}
        with patch("tincand.backends.ancs.GLib.idle_add") as mock_idle:
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_idle.assert_not_called()

    def test_connected_key_absent_no_idle_add(self, started):
        """Device1 interface present but Connected key is missing → ignored."""
        backend, *_ = started
        interfaces = {_DEVICE_IFACE: {"Paired": True}}
        with patch("tincand.backends.ancs.GLib.idle_add") as mock_idle:
            backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_idle.assert_not_called()

    def test_connected_false_no_capability_set(self, started):
        backend, _, _, mock_service = started
        interfaces = {_DEVICE_IFACE: {"Connected": False}}
        backend._on_interfaces_added(_DEV_PATH, interfaces)
        mock_service.set_capability.assert_not_called()
