"""Tests: ANCSBackend — corrected GATT consumer model.
Bead: tincan-2ee

Coverage:
  §1  BackendInterface compliance — list_conversations, register_service
  §2  start() — AgentManager1 + LEAdvertisingManager1 each called once; no GattManager1
  §3  stop() — set_capability('ancs', False); idempotent double-call safe
  §4  Connected=True signal → subscription + set_capability('ancs', True)
  §5  Connected=False signal → clear buffer + set_capability('ancs', False)
  §6  Reconnect: second Connected=True after DISCONNECTED re-runs subscription
  §7  device_addr=None accepts any device; set value filters case-insensitively
  §8  _on_notif_source_changed — cat 4/6 event_id=0 writes ControlPoint; cat 0 ignores
  §9  _on_data_source_changed — on completion calls on_message_received correct shape
  §10 Stale buffer cleared before new ControlPoint write for same UID
  §11 GATT consumer contract — SolicitUUIDs adv, no local GattApplication registered
  §12 LE bond flow — Bonded=True skips Pair(); Bonded=False calls Pair(); failure path
  §13 ANCS service not found — set_capability(False), graceful exit, no crash

No hardware or real D-Bus — all D-Bus objects mocked.
Run with: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincand/test_ancs_backend.py -v
"""
from __future__ import annotations

import inspect
import logging
import struct
from unittest.mock import MagicMock, patch

import pytest

from tincand.ancs_util import (
    ANCS_SERVICE_UUID,
    ATTR_APP_ID,
    ATTR_MESSAGE,
    ATTR_TITLE,
    CONTROL_POINT_UUID,
    DATA_SOURCE_UUID,
    NOTIF_SOURCE_UUID,
)
from tincand.backends.ancs import ANCSBackend

# ---------------------------------------------------------------------------
# D-Bus paths used in managed objects fixture
# ---------------------------------------------------------------------------

_DEV_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
_NOTIF_SRC_PATH = f"{_DEV_PATH}/service01/char01"
_CTRL_PT_PATH = f"{_DEV_PATH}/service01/char02"
_DATA_SRC_PATH = f"{_DEV_PATH}/service01/char03"

_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"


def _make_managed_objects():
    """Fake GetManagedObjects() payload with all three ANCS characteristics."""
    return {
        _NOTIF_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": NOTIF_SOURCE_UUID}},
        _CTRL_PT_PATH: {_GATT_CHAR_IFACE: {"UUID": CONTROL_POINT_UUID}},
        _DATA_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": DATA_SOURCE_UUID}},
    }


def _notif_source_bytes(event_id: int, category_id: int, uid: int) -> bytes:
    """Build an 8-byte Notification Source LE packet."""
    return struct.pack("<BBBBL", event_id, 0, category_id, 1, uid)


def _data_source_tlv(uid: int, title: str = "Alice", message: str = "Hi",
                     app_id: str = "com.apple.MobileSMS") -> bytes:
    """Build a complete Data Source TLV payload in response wire format."""
    def tlv(attr_id: int, val: str) -> bytes:
        b = val.encode("utf-8")
        return bytes([attr_id]) + struct.pack("<H", len(b)) + b

    return (
        bytes([0x00])
        + struct.pack("<L", uid)
        + tlv(ATTR_APP_ID, app_id)
        + tlv(ATTR_TITLE, title)
        + tlv(ATTR_MESSAGE, message)
    )


# ---------------------------------------------------------------------------
# Fixture: mocked D-Bus environment
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
    """Yield (backend, mock_bus, mock_ctrl_pt, mock_service).

    - dbus.service.Object.__init__ is a no-op so scaffold classes can be
      instantiated without a real bus.
    - dbus.SystemBus() returns mock_bus.
    - mock_bus.get_object() returns a tagged MagicMock so dbus.Interface()
      can route by path: ObjectManager → obj_mgr_mock, Device1 →
      mock_device (Bonded=True by default), ControlPoint → mock_ctrl_pt,
      everything else → a fresh MagicMock.
    - backend has a mock service already registered.
    """
    mock_bus = MagicMock(name="SystemBus")
    mock_ctrl_pt = MagicMock(name="ControlPoint")
    mock_service = MagicMock(name="TincanService")
    mock_device = MagicMock(name="Device1")
    mock_device.Get.return_value = True  # Bonded=True; no Pair() by default

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
        if iface == "org.bluez.Device1":
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
    """backend already started (start() called once)."""
    backend, mock_bus, mock_ctrl_pt, mock_service = ctx
    backend.start()
    return backend, mock_bus, mock_ctrl_pt, mock_service


@pytest.fixture
def subscribed(started):
    """backend started and a device has connected (ANCS chars subscribed)."""
    backend, mock_bus, mock_ctrl_pt, mock_service = started
    backend._on_device_connected(_DEV_PATH)
    return backend, mock_bus, mock_ctrl_pt, mock_service


# ---------------------------------------------------------------------------
# §1 BackendInterface compliance
# ---------------------------------------------------------------------------

class TestBackendInterfaceCompliance:
    """ANCSBackend satisfies the BackendInterface contract."""

    def test_list_conversations_returns_empty_list(self, ctx):
        backend, *_ = ctx
        assert backend.list_conversations() == []

    def test_list_conversations_returns_list_type(self, ctx):
        backend, *_ = ctx
        assert isinstance(backend.list_conversations(), list)

    def test_register_service_stores_reference(self, ctx):
        backend, _, _, mock_service = ctx
        assert backend._service is mock_service

    def test_initial_bus_is_none(self, ctx):
        backend, *_ = ctx
        assert backend._bus is None


# ---------------------------------------------------------------------------
# §2 start() — AgentManager1 + LEAdvertisingManager1
# ---------------------------------------------------------------------------

class TestStart:
    """start() connects to the system bus, registers the pairing agent (AgentManager1)
    and the LE advertisement (LEAdvertisingManager1); no local GattApplication is used."""

    def test_registers_pairing_agent_exactly_once(self, ctx):
        backend, mock_bus, _, _ = ctx
        with patch("tincand.backends.ancs.dbus.Interface") as mock_iface:
            mock_iface.return_value = MagicMock()
            backend.start()
        agent_calls = [
            c for c in mock_iface.call_args_list
            if "AgentManager1" in str(c)
        ]
        assert len(agent_calls) >= 1

    def test_registers_advertisement_exactly_once(self, ctx):
        backend, mock_bus, _, _ = ctx
        with patch("tincand.backends.ancs.dbus.Interface") as mock_iface:
            mock_iface.return_value = MagicMock()
            backend.start()
        adv_calls = [
            c for c in mock_iface.call_args_list
            if "LEAdvertisingManager1" in str(c)
        ]
        assert len(adv_calls) >= 1

    def test_start_sets_bus(self, ctx):
        backend, mock_bus, _, _ = ctx
        with patch("tincand.backends.ancs.dbus.Interface"):
            backend.start()
        assert backend._bus is not None

    def test_start_calls_system_bus(self, ctx):
        backend, *_ = ctx
        with patch("tincand.backends.ancs.dbus.SystemBus", return_value=MagicMock()) as sb:
            with patch("tincand.backends.ancs.dbus.Interface"):
                backend.start()
        sb.assert_called_once()

    def test_start_registers_properties_changed_signal_receiver(self, started):
        backend, mock_bus, _, _ = started
        assert mock_bus.add_signal_receiver.called
        signal_names = [
            c.kwargs.get("signal_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_bus.add_signal_receiver.call_args_list
        ]
        assert "PropertiesChanged" in signal_names


# ---------------------------------------------------------------------------
# §3 stop() — idempotent, set_capability
# ---------------------------------------------------------------------------

class TestStop:
    """stop() sets capability to False; double-call is safe."""

    def test_stop_when_started_calls_set_capability_ancs_false(self, started):
        backend, _, _, mock_service = started
        backend.stop()
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_stop_clears_bus_reference(self, started):
        backend, *_ = started
        backend.stop()
        assert backend._bus is None

    def test_stop_is_idempotent_double_call_does_not_raise(self, started):
        backend, *_ = started
        backend.stop()
        backend.stop()  # must not raise

    def test_stop_when_not_started_does_not_raise(self, ctx):
        backend, *_ = ctx
        backend.stop()  # bus is None — should return immediately without error

    def test_stop_when_not_started_does_not_call_set_capability(self, ctx):
        backend, _, _, mock_service = ctx
        backend.stop()
        mock_service.set_capability.assert_not_called()


# ---------------------------------------------------------------------------
# §4 Connected=True → subscription + set_capability('ancs', True)
# ---------------------------------------------------------------------------

class TestDeviceConnected:
    """PropertiesChanged(Connected=True) triggers subscription and capability signal."""

    def test_connected_true_calls_set_capability_ancs_true(self, started):
        backend, _, _, mock_service = started
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_connected_true_via_properties_changed_calls_set_capability(self, started):
        backend, _, _, mock_service = started
        backend._on_properties_changed(
            "org.bluez.Device1",
            {"Connected": True},
            [],
            path=_DEV_PATH,
        )
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_connected_true_stores_control_point_proxy(self, started):
        backend, _, _, _ = started
        backend._on_device_connected(_DEV_PATH)
        assert backend._control_point_proxy is not None

    def test_properties_changed_non_device_interface_ignored(self, started):
        backend, _, _, mock_service = started
        backend._on_properties_changed(
            "org.bluez.GattCharacteristic1",
            {"Connected": True},
            [],
            path=_DEV_PATH,
        )
        mock_service.set_capability.assert_not_called()

    def test_properties_changed_without_connected_key_ignored(self, started):
        backend, _, _, mock_service = started
        backend._on_properties_changed(
            "org.bluez.Device1",
            {"Paired": True},
            [],
            path=_DEV_PATH,
        )
        mock_service.set_capability.assert_not_called()


# ---------------------------------------------------------------------------
# §5 Connected=False → clear buffer + set_capability('ancs', False)
# ---------------------------------------------------------------------------

class TestDeviceDisconnected:
    """PropertiesChanged(Connected=False) clears state and signals capability loss."""

    def test_disconnected_calls_set_capability_ancs_false(self, subscribed):
        backend, _, _, mock_service = subscribed
        mock_service.reset_mock()
        backend._on_device_disconnected()
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_disconnected_clears_control_point_proxy(self, subscribed):
        backend, *_ = subscribed
        backend._on_device_disconnected()
        assert backend._control_point_proxy is None

    def test_disconnected_via_properties_changed(self, subscribed):
        backend, _, _, mock_service = subscribed
        mock_service.reset_mock()
        backend._on_properties_changed(
            "org.bluez.Device1",
            {"Connected": False},
            [],
            path=_DEV_PATH,
        )
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_disconnected_clears_data_buffer(self, subscribed):
        backend, *_ = subscribed
        backend._data_buffer.accumulate(42, bytes(5))  # seed partial data
        backend._on_device_disconnected()
        assert 42 not in backend._data_buffer._buffers


# ---------------------------------------------------------------------------
# §6 Reconnect: second Connected=True after DISCONNECTED re-runs subscription
# ---------------------------------------------------------------------------

class TestReconnect:
    """Second Connected=True after a disconnect re-subscribes to ANCS chars."""

    def test_reconnect_calls_set_capability_ancs_true_again(self, subscribed):
        backend, _, _, mock_service = subscribed
        backend._on_device_disconnected()
        mock_service.reset_mock()
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_reconnect_restores_control_point_proxy(self, subscribed):
        backend, *_ = subscribed
        backend._on_device_disconnected()
        assert backend._control_point_proxy is None
        backend._on_device_connected(_DEV_PATH)
        assert backend._control_point_proxy is not None


# ---------------------------------------------------------------------------
# §7 device_addr filtering
# ---------------------------------------------------------------------------

class TestDeviceAddrFilter:
    """device_addr=None accepts all; explicit value filters case-insensitively.

    The three addr-specific tests will FAIL until the builder adds device_addr
    filtering in _on_device_connected (fetch Address from org.bluez.Device1,
    compare case-insensitively, skip if mismatch).  That is the correct TDD
    state — the tests are the spec.
    """

    @pytest.fixture
    def ctx_filtered(self):
        """ctx variant with device_addr='AA:BB:CC:DD:EE:FF' and Device1 mock."""
        mock_bus = MagicMock(name="SystemBus")
        mock_ctrl_pt = MagicMock(name="ControlPoint")
        mock_service = MagicMock(name="TincanService")
        mock_dev_props = MagicMock(name="Device1Props")

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
            if iface in ("org.bluez.Device1", "org.freedesktop.DBus.Properties"):
                return mock_dev_props
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
            backend = ANCSBackend(device_addr="AA:BB:CC:DD:EE:FF")
            backend.register_service(mock_service)
            backend.start()
            yield backend, mock_bus, mock_ctrl_pt, mock_service, mock_dev_props

    def test_device_addr_none_accepts_any_device(self, started):
        backend, _, _, mock_service = started
        assert backend._device_addr is None
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_matching_device_addr_triggers_subscription(self, ctx_filtered):
        backend, _, _, mock_service, mock_dev_props = ctx_filtered
        mock_dev_props.Get.return_value = "AA:BB:CC:DD:EE:FF"
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_non_matching_device_addr_is_ignored(self, ctx_filtered):
        backend, _, _, mock_service, mock_dev_props = ctx_filtered
        mock_dev_props.Get.return_value = "11:22:33:44:55:66"
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_not_called()

    def test_device_addr_matching_is_case_insensitive(self, ctx_filtered):
        backend, _, _, mock_service, mock_dev_props = ctx_filtered
        mock_dev_props.Get.return_value = "AA:BB:CC:DD:EE:FF"  # uppercase from BlueZ
        backend._device_addr = "aa:bb:cc:dd:ee:ff"             # lowercase filter
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", True)


# ---------------------------------------------------------------------------
# §8 _on_notif_source_changed — dispatch filtering
# ---------------------------------------------------------------------------

class TestNotifSourceChanged:
    """_on_notif_source_changed filters by event_id and category_id."""

    def test_category_4_event_id_0_writes_control_point(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        data = _notif_source_bytes(event_id=0, category_id=4, uid=1)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_called_once()

    def test_category_6_event_id_0_writes_control_point(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        data = _notif_source_bytes(event_id=0, category_id=6, uid=2)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_called_once()

    def test_category_0_other_writes_control_point(self, subscribed):
        # tincan-47mh: category filter removed — ALL EventID=0 notifications routed.
        backend, _, mock_ctrl_pt, _ = subscribed
        data = _notif_source_bytes(event_id=0, category_id=0, uid=3)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_called_once()

    def test_event_id_1_modified_does_not_write_control_point(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        data = _notif_source_bytes(event_id=1, category_id=4, uid=4)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_not_called()

    def test_missing_value_key_does_not_write_control_point(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"RSSI": -70},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_not_called()

    def test_write_value_encodes_uid_as_little_endian(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        uid = 0x00ABCDEF
        data = _notif_source_bytes(event_id=0, category_id=4, uid=uid)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        args, _ = mock_ctrl_pt.WriteValue.call_args
        written_bytes = bytes(args[0])
        # byte 1..4 of the command should be the UID in LE
        assert struct.unpack_from("<L", written_bytes, 1)[0] == uid

    def test_write_value_not_connected_clears_proxy_and_enters_healing(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        timers[1]()   # → ACTIVE (notifying=True by default)
        assert backend._control_point_proxy is not None
        backend._control_point_proxy.WriteValue.side_effect = Exception("Not connected")
        data = _notif_source_bytes(event_id=0, category_id=4, uid=1)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties", {"Value": list(data)}, []
        )
        assert backend._control_point_proxy is None
        assert backend._heal_timer_id is not None

    def test_write_value_not_connected_stops_subsequent_retries(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE
        cp = backend._control_point_proxy
        cp.WriteValue.side_effect = Exception("Not connected")
        data1 = _notif_source_bytes(event_id=0, category_id=4, uid=1)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties", {"Value": list(data1)}, []
        )
        cp.WriteValue.reset_mock()
        data2 = _notif_source_bytes(event_id=0, category_id=4, uid=2)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties", {"Value": list(data2)}, []
        )
        cp.WriteValue.assert_not_called()


# ---------------------------------------------------------------------------
# §9 _on_data_source_changed → on_message_received payload shape
# ---------------------------------------------------------------------------

class TestDataSourceChanged:
    """Complete Data Source payload triggers on_message_received with correct shape."""

    def test_complete_payload_calls_on_message_received(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1, title="Alice", message="Hello",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        mock_service.on_message_received.assert_called_once()

    def test_payload_shape_has_conversation_id(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1, title="Alice", message="Hello",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert "conversation_id" in msg

    def test_payload_conversation_id_is_app_id(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1, title="Alice", message="Hello",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["conversation_id"] == "com.apple.MobileSMS"

    def test_payload_body_is_message_attr(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1, title="Alice", message="Hello world",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["body"] == "Hello world"

    def test_payload_from_is_title_attr(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1, title="Bob", message="Hi",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["from"] == "Bob"

    def test_payload_direction_is_inbound(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1)
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["direction"] == "inbound"

    def test_payload_status_is_unread(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1)
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["status"] == "unread"

    def test_payload_timestamp_is_empty_string(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload = _data_source_tlv(uid=1)
        backend._on_data_source_changed({"Value": list(payload)})
        msg = mock_service.on_message_received.call_args[0][0]
        assert msg["timestamp"] == ""

    def test_missing_value_key_does_not_call_on_message_received(self, subscribed):
        backend, _, _, mock_service = subscribed
        backend._on_data_source_changed({"RSSI": -70})
        mock_service.on_message_received.assert_not_called()

    def test_partial_chunk_does_not_call_on_message_received(self, subscribed):
        backend, _, _, mock_service = subscribed
        # TLV header claims 10 bytes for Title but provides 0 value bytes — truncated
        partial = (
            bytes([0x00])                   # CommandID
            + struct.pack("<L", 99)          # UID LE
            + bytes([ATTR_TITLE])            # AttrID = Title
            + struct.pack("<H", 10)          # Length = 10
            # no value bytes — truncated, ANCSDataBuffer returns None
        )
        backend._on_data_source_changed({"Value": list(partial)})
        mock_service.on_message_received.assert_not_called()

    def test_different_uid_payloads_each_fire_on_message_received(self, subscribed):
        backend, _, _, mock_service = subscribed
        payload_a = _data_source_tlv(uid=10, title="A", message="msg a")
        payload_b = _data_source_tlv(uid=20, title="B", message="msg b")
        backend._on_data_source_changed({"Value": list(payload_a)})
        backend._on_data_source_changed({"Value": list(payload_b)})
        assert mock_service.on_message_received.call_count == 2


# ---------------------------------------------------------------------------
# §10 Stale buffer cleared before new ControlPoint write
# ---------------------------------------------------------------------------

class TestStaleBufferCleared:
    """Stale Data Source buffer for a UID is cleared before each new ControlPoint write."""

    def test_stale_buffer_cleared_on_second_notif_for_same_uid(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        uid = 7

        # Seed stale data in the buffer for uid=7
        backend._data_buffer.accumulate(uid, bytes(5))  # partial header only
        assert uid in backend._data_buffer._buffers

        # Trigger a new notification for the same UID
        data = _notif_source_bytes(event_id=0, category_id=4, uid=uid)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )

        # The stale buffer must be gone so the next data-source fragment starts clean
        assert uid not in backend._data_buffer._buffers

    def test_control_point_written_even_when_stale_buffer_existed(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        uid = 8
        backend._data_buffer.accumulate(uid, bytes(5))
        data = _notif_source_bytes(event_id=0, category_id=4, uid=uid)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_called_once()


# ---------------------------------------------------------------------------
# §11 GATT Consumer Model Contract
# ---------------------------------------------------------------------------

class TestGattConsumerModel:
    """Corrected ANCSBackend acts as a GATT client — no local GATT server registration."""

    def test_no_gatt_manager1_called_during_start(self, ctx):
        """start() must not register a local GattApplication via GattManager1."""
        backend, _, _, _ = ctx
        with patch("tincand.backends.ancs.dbus.Interface") as mock_iface:
            mock_iface.return_value = MagicMock()
            backend.start()
        gatt_calls = [c for c in mock_iface.call_args_list if "GattManager1" in str(c)]
        assert len(gatt_calls) == 0

    def test_advertisement_uses_solicituuids_not_serviceuuids(self, started):
        """Advertisement solicits ANCS from iPhone — SolicitUUIDs, not ServiceUUIDs."""
        backend, *_ = started
        assert backend._adv is not None
        props = backend._adv._props
        assert "SolicitUUIDs" in props
        assert "ServiceUUIDs" not in props

    def test_advertisement_solicituuids_contains_ancs_service_uuid(self, started):
        """SolicitUUIDs contains the ANCS service UUID (7905F431-...)."""
        backend, *_ = started
        assert backend._adv is not None
        uuid_strings = [str(u) for u in backend._adv._props["SolicitUUIDs"]]
        assert any(ANCS_SERVICE_UUID.upper() in u.upper() for u in uuid_strings)

    def test_no_local_gatt_app_on_backend(self, started):
        """Backend does not have _app — GattApplication is gone in the consumer model."""
        backend, *_ = started
        assert not hasattr(backend, "_app")


# ---------------------------------------------------------------------------
# §12 LE Bond Flow
# ---------------------------------------------------------------------------

def _make_bond_ctx_helpers():
    """Shared factory for bond_ctx and no_ancs_ctx fixtures."""
    mock_bus = MagicMock(name="SystemBus")
    mock_ctrl_pt = MagicMock(name="ControlPoint")
    mock_service = MagicMock(name="TincanService")
    mock_device = MagicMock(name="Device1")
    mock_device.Get.return_value = True  # Bonded=True by default

    obj_mgr_mock = MagicMock(name="ObjectManager")
    obj_mgr_mock.GetManagedObjects.return_value = _make_managed_objects()

    def _get_object(service, path):
        obj = MagicMock(name=f"obj({path})")
        obj._dbus_path = str(path)
        return obj

    mock_bus.get_object.side_effect = _get_object
    return mock_bus, mock_ctrl_pt, mock_service, mock_device, obj_mgr_mock


class TestLeBond:
    """LE bond flow: Bonded check, conditional Pair(), graceful failure."""

    @pytest.fixture
    def bond_ctx(self):
        """Started backend with an explicit, configurable Device1 mock."""
        mock_bus, mock_ctrl_pt, mock_service, mock_device, obj_mgr_mock = (
            _make_bond_ctx_helpers()
        )

        def _make_interface(obj, iface):
            path = getattr(obj, "_dbus_path", "")
            if iface == "org.freedesktop.DBus.ObjectManager":
                return obj_mgr_mock
            if iface in ("org.bluez.Device1", "org.freedesktop.DBus.Properties"):
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
            backend.start()
            yield backend, mock_device, mock_service

    def test_already_bonded_device_does_not_call_pair(self, bond_ctx):
        backend, mock_device, _ = bond_ctx
        mock_device.Get.return_value = True  # Bonded=True
        backend._on_device_connected(_DEV_PATH)
        mock_device.Pair.assert_not_called()

    def test_unbonded_device_calls_pair(self, bond_ctx):
        backend, mock_device, _ = bond_ctx
        mock_device.Get.return_value = False  # Bonded=False → must Pair()
        backend._on_device_connected(_DEV_PATH)
        mock_device.Pair.assert_called_once()

    def test_le_bond_failure_calls_set_capability_false(self, bond_ctx):
        backend, mock_device, mock_service = bond_ctx
        mock_device.Get.return_value = False
        mock_device.Pair.side_effect = Exception("org.bluez.Error.AuthenticationFailed")
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_le_bond_failure_does_not_raise(self, bond_ctx):
        backend, mock_device, _ = bond_ctx
        mock_device.Get.return_value = False
        mock_device.Pair.side_effect = Exception("Bond failed")
        backend._on_device_connected(_DEV_PATH)  # must not propagate exception

    def test_le_bond_failure_leaves_control_point_proxy_none(self, bond_ctx):
        backend, mock_device, _ = bond_ctx
        mock_device.Get.return_value = False
        mock_device.Pair.side_effect = Exception("Bond failed")
        backend._on_device_connected(_DEV_PATH)
        assert backend._control_point_proxy is None

    def test_already_exists_proceeds_to_discovery(self, bond_ctx):
        backend, mock_device, mock_service = bond_ctx
        mock_device.Get.return_value = False  # Bonded=False → Pair() attempted
        mock_device.Pair.side_effect = Exception("org.bluez.Error.AlreadyExists")
        backend._on_device_connected(_DEV_PATH)
        mock_device.Pair.assert_called_once()
        # AlreadyExists → proceed to GATT discovery + StartNotify, NOT disable ANCS
        mock_service.set_capability.assert_any_call("ancs", True)


# ---------------------------------------------------------------------------
# §13 ANCS Service Not Found
# ---------------------------------------------------------------------------

class TestAncsServiceNotFound:
    """ANCS GATT chars missing after bond → set_capability(False), graceful exit."""

    @pytest.fixture
    def no_ancs_ctx(self):
        """Started backend where GetManagedObjects returns no ANCS characteristics."""
        mock_bus, _, mock_service, mock_device, _ = _make_bond_ctx_helpers()
        # Override ObjectManager to return no chars
        obj_mgr_mock = MagicMock(name="ObjectManager")
        obj_mgr_mock.GetManagedObjects.return_value = {}

        def _get_object(service, path):
            obj = MagicMock(name=f"obj({path})")
            obj._dbus_path = str(path)
            return obj

        mock_bus.get_object.side_effect = _get_object

        def _make_interface(obj, iface):
            if iface == "org.freedesktop.DBus.ObjectManager":
                return obj_mgr_mock
            if iface == "org.bluez.Device1":
                return mock_device
            return MagicMock(name=f"Interface({iface})")

        with (
            patch("dbus.service.Object.__init__", return_value=None),
            patch("tincand.backends.ancs.dbus.SystemBus", return_value=mock_bus),
            patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_interface),
            patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
        ):
            mock_exc.DBusException = Exception
            backend = ANCSBackend()
            backend.register_service(mock_service)
            backend.start()
            yield backend, mock_service

    def test_ancs_service_not_found_calls_set_capability_false(self, no_ancs_ctx):
        backend, mock_service = no_ancs_ctx
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_ancs_service_not_found_does_not_raise(self, no_ancs_ctx):
        backend, _ = no_ancs_ctx
        backend._on_device_connected(_DEV_PATH)  # must not propagate exception

    def test_ancs_service_not_found_control_point_proxy_remains_none(self, no_ancs_ctx):
        backend, _ = no_ancs_ctx
        backend._on_device_connected(_DEV_PATH)
        assert backend._control_point_proxy is None

    def test_chars_on_other_device_path_not_matched(self):
        """GATT chars from a different device path are ignored — no false ANCS link."""
        other_dev = "/org/bluez/hci0/dev_11_22_33_44_55_66"
        mock_bus = MagicMock(name="SystemBus")
        mock_service = MagicMock(name="TincanService")
        mock_device = MagicMock(name="Device1")
        mock_device.Get.return_value = True  # bonded

        # Chars exist but under a DIFFERENT device path
        obj_mgr_mock = MagicMock(name="ObjectManager")
        obj_mgr_mock.GetManagedObjects.return_value = {
            f"{other_dev}/service01/char01": {_GATT_CHAR_IFACE: {"UUID": NOTIF_SOURCE_UUID}},
            f"{other_dev}/service01/char02": {_GATT_CHAR_IFACE: {"UUID": CONTROL_POINT_UUID}},
            f"{other_dev}/service01/char03": {_GATT_CHAR_IFACE: {"UUID": DATA_SOURCE_UUID}},
        }

        def _get_object(service, path):
            obj = MagicMock(name=f"obj({path})")
            obj._dbus_path = str(path)
            return obj

        mock_bus.get_object.side_effect = _get_object

        def _make_interface(obj, iface):
            if iface == "org.freedesktop.DBus.ObjectManager":
                return obj_mgr_mock
            if iface == "org.bluez.Device1":
                return mock_device
            return MagicMock(name=f"Interface({iface})")

        with (
            patch("dbus.service.Object.__init__", return_value=None),
            patch("tincand.backends.ancs.dbus.SystemBus", return_value=mock_bus),
            patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_interface),
            patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
        ):
            mock_exc.DBusException = Exception
            backend = ANCSBackend()
            backend.register_service(mock_service)
            backend.start()
            backend._on_device_connected(_DEV_PATH)  # _DEV_PATH ≠ other_dev

        mock_service.set_capability.assert_called_with("ancs", False)


# ---------------------------------------------------------------------------
# §14 Signal receiver cleanup on disconnect (regression: tincan-63l3 / e140d31)
# ---------------------------------------------------------------------------

class TestSignalReceiverCleanup:
    """_on_device_disconnected removes both GATT characteristic receivers.

    Before e140d31, disconnect never called remove_signal_receiver — receivers
    accumulated on repeated reconnect cycles.  These tests pin that fix.
    """

    # -- receiver identity -----------------------------------------------

    def test_disconnected_removes_notif_source_receiver(self, subscribed):
        """remove_signal_receiver called with _on_notif_source_changed as handler."""
        backend, mock_bus, _, _ = subscribed
        backend._on_device_disconnected()
        handlers = [c.args[0] for c in mock_bus.remove_signal_receiver.call_args_list]
        assert backend._on_notif_source_changed in handlers

    def test_disconnected_removes_data_source_receiver(self, subscribed):
        """remove_signal_receiver called with _on_data_source_changed_handler as handler."""
        backend, mock_bus, _, _ = subscribed
        backend._on_device_disconnected()
        handlers = [c.args[0] for c in mock_bus.remove_signal_receiver.call_args_list]
        assert backend._on_data_source_changed_handler in handlers

    # -- path correctness ------------------------------------------------

    def test_disconnected_notif_src_receiver_removed_with_correct_path(self, subscribed):
        """NotifSource receiver is removed using _NOTIF_SRC_PATH."""
        backend, mock_bus, _, _ = subscribed
        backend._on_device_disconnected()
        paths = [c.kwargs.get("path") for c in mock_bus.remove_signal_receiver.call_args_list]
        assert _NOTIF_SRC_PATH in paths

    def test_disconnected_data_src_receiver_removed_with_correct_path(self, subscribed):
        """DataSource receiver is removed using _DATA_SRC_PATH."""
        backend, mock_bus, _, _ = subscribed
        backend._on_device_disconnected()
        paths = [c.kwargs.get("path") for c in mock_bus.remove_signal_receiver.call_args_list]
        assert _DATA_SRC_PATH in paths

    # -- state fields cleared --------------------------------------------

    def test_disconnected_clears_notif_src_path_field(self, subscribed):
        backend, *_ = subscribed
        assert backend._notif_src_path is not None  # sanity: was set by connect
        backend._on_device_disconnected()
        assert backend._notif_src_path is None

    def test_disconnected_clears_data_src_path_field(self, subscribed):
        backend, *_ = subscribed
        assert backend._data_src_path is not None
        backend._on_device_disconnected()
        assert backend._data_src_path is None

    # -- no-op paths (not subscribed) ------------------------------------

    def test_started_not_subscribed_disconnect_does_not_call_remove_receiver(self, started):
        """Started but never subscribed: paths are None, remove_signal_receiver must not fire."""
        backend, mock_bus, _, _ = started
        backend._on_device_disconnected()
        mock_bus.remove_signal_receiver.assert_not_called()

    # -- robustness ------------------------------------------------------

    def test_remove_receiver_exception_does_not_propagate(self, subscribed):
        """remove_signal_receiver raising must not bubble up from _on_device_disconnected."""
        backend, mock_bus, _, _ = subscribed
        mock_bus.remove_signal_receiver.side_effect = RuntimeError("bus gone")
        backend._on_device_disconnected()  # must not raise

    # -- reconnect regression (the core defect) --------------------------

    def test_reconnect_cycle_re_registers_both_receivers(self, subscribed):
        """After disconnect+reconnect, add_signal_receiver is called again for ANCS paths."""
        backend, mock_bus, _, _ = subscribed
        add_calls_before = mock_bus.add_signal_receiver.call_count
        backend._on_device_disconnected()
        backend._on_device_connected(_DEV_PATH)
        add_calls_after = mock_bus.add_signal_receiver.call_count
        # Two new add_signal_receiver calls for the new subscription
        assert add_calls_after >= add_calls_before + 2

    def test_reconnect_second_disconnect_removes_receivers_again(self, subscribed):
        """Disconnect → reconnect → disconnect: remove_signal_receiver fires each cycle."""
        backend, mock_bus, _, _ = subscribed
        # First cycle
        backend._on_device_disconnected()
        remove_count_after_first = mock_bus.remove_signal_receiver.call_count
        assert remove_count_after_first == 2  # one per characteristic

        # Reconnect then disconnect again
        backend._on_device_connected(_DEV_PATH)
        backend._on_device_disconnected()
        remove_count_after_second = mock_bus.remove_signal_receiver.call_count
        assert remove_count_after_second == 4  # two more removals on second cycle


# ===========================================================================
# Lifecycle state machine tests (tincan-5mze)
# ===========================================================================
# Fixture: `lc` — GLib mocked; backend started and connected (CONNECTING state).
#
# Timer allocation (deterministic):
#   timers[1] = _check_notifying_after_subscribe  (500 ms poll, created in _on_device_connected)
#   timers[2] = _health_check | _attempt_le_rearm  (created by firing timers[1])
#   timers[3] = _attempt_le_rearm                  (created when health check fails)
#
# _notifying dict: configure _verify_notifying() return values per char path.
# Both paths default to True (healthy ANCS link).

_LC_PROPS_IFACE = "org.freedesktop.DBus.Properties"


@pytest.fixture
def lc():
    """Lifecycle context: GLib mocked, backend started + device connected (CONNECTING).

    Yields (backend, mock_service, mock_bus, mock_glib, timers, notifying).
    """
    _notifying = {_NOTIF_SRC_PATH: True, _DATA_SRC_PATH: True}
    mock_bus = MagicMock(name="SystemBus")
    mock_ctrl_pt = MagicMock(name="ControlPoint")
    mock_service = MagicMock(name="TincanService")
    mock_device = MagicMock(name="Device1")
    mock_device.Get.return_value = True  # Bonded=True by default

    obj_mgr_mock = MagicMock(name="ObjectManager")
    obj_mgr_mock.GetManagedObjects.return_value = _make_managed_objects()

    def _get_object(service, path):
        obj = MagicMock(name=f"obj({path})")
        obj._dbus_path = str(path)
        return obj

    mock_bus.get_object.side_effect = _get_object

    def _make_lc_interface(obj, iface):
        path = getattr(obj, "_dbus_path", "")
        if iface == "org.freedesktop.DBus.ObjectManager":
            return obj_mgr_mock
        if iface == "org.bluez.Device1":
            return mock_device
        if iface == _GATT_CHAR_IFACE and path == _CTRL_PT_PATH:
            return mock_ctrl_pt
        if iface == _LC_PROPS_IFACE:
            props = MagicMock()
            _path = path
            props.Get.side_effect = lambda _i, _p: _notifying.get(_path, True)
            return props
        return MagicMock(name=f"Interface({iface}@{path})")

    mock_glib = MagicMock(name="GLib")
    mock_glib.SOURCE_REMOVE = False
    mock_glib.SOURCE_CONTINUE = True
    _timers: dict = {}
    _next_id = [0]

    def _timeout_add(interval_ms, cb):
        _next_id[0] += 1
        tid = _next_id[0]
        _timers[tid] = cb
        return tid

    mock_glib.timeout_add.side_effect = _timeout_add
    mock_glib.source_remove.side_effect = lambda tid: _timers.pop(tid, None)

    with (
        patch("dbus.service.Object.__init__", return_value=None),
        patch("tincand.backends.ancs.dbus.SystemBus", return_value=mock_bus),
        patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_lc_interface),
        patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
        patch("tincand.backends.ancs.GLib", mock_glib),
    ):
        mock_exc.DBusException = Exception
        backend = ANCSBackend()
        backend.register_service(mock_service)
        backend.start()
        backend._on_device_connected(_DEV_PATH)
        # timers[1] = _check_notifying_after_subscribe (500 ms poll)
        yield backend, mock_service, mock_bus, mock_glib, _timers, _notifying


# ---------------------------------------------------------------------------
# §15 CONNECTING → ACTIVE (500 ms Notifying poll passes)
# ---------------------------------------------------------------------------

class TestConnectingToActive:
    """500 ms poll: both chars Notifying=True → ACTIVE confirmed, health check scheduled."""

    def test_poll_pass_schedules_health_check_at_30s(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        timers[1]()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 30_000 in intervals

    def test_poll_pass_sets_health_check_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        assert backend._health_check_id is not None

    def test_poll_pass_does_not_call_set_capability_ancs_false(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        mock_service.reset_mock()
        timers[1]()
        false_calls = [c for c in mock_service.set_capability.call_args_list
                       if list(c.args) == ["ancs", False]]
        assert not false_calls

    def test_poll_pass_heal_timer_not_scheduled(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        assert backend._heal_timer_id is None

    def test_poll_pass_returns_source_remove(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        result = timers[1]()
        assert result == mock_glib.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# §16 CONNECTING → HEALING (500 ms Notifying poll fails)
# ---------------------------------------------------------------------------

class TestConnectingToHealing:
    """500 ms poll: either char Notifying=False → HEALING entered, capability cleared."""

    def test_poll_fail_notif_src_calls_set_capability_ancs_false(self, lc):
        backend, mock_service, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        mock_service.reset_mock()
        timers[1]()
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_poll_fail_data_src_calls_set_capability_ancs_false(self, lc):
        backend, mock_service, _, _, timers, notifying = lc
        notifying[_DATA_SRC_PATH] = False
        mock_service.reset_mock()
        timers[1]()
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_poll_fail_schedules_heal_timer_at_5s(self, lc):
        backend, _, _, mock_glib, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 5_000 in intervals

    def test_poll_fail_sets_heal_timer_id(self, lc):
        backend, _, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()
        assert backend._heal_timer_id is not None

    def test_poll_fail_health_check_not_scheduled(self, lc):
        backend, _, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()
        assert backend._health_check_id is None


# ---------------------------------------------------------------------------
# §17 ACTIVE → ACTIVE (30 s health check passes)
# ---------------------------------------------------------------------------

class TestActiveHealthCheckPass:
    """30 s health check: both chars Notifying=True → SOURCE_CONTINUE, no HEALING."""

    def test_health_check_pass_returns_source_continue(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        timers[1]()           # → ACTIVE; timers[2] = _health_check
        result = timers[2]()
        assert result == mock_glib.SOURCE_CONTINUE

    def test_health_check_pass_does_not_call_set_capability_ancs_false(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        timers[1]()
        mock_service.reset_mock()
        timers[2]()
        false_calls = [c for c in mock_service.set_capability.call_args_list
                       if list(c.args) == ["ancs", False]]
        assert not false_calls

    def test_health_check_pass_health_check_id_remains_set(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        timers[2]()
        assert backend._health_check_id is not None

    def test_health_check_pass_no_heal_timer_scheduled(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        timers[2]()
        assert backend._heal_timer_id is None


# ---------------------------------------------------------------------------
# §18 ACTIVE → HEALING (30 s health check fails)
# ---------------------------------------------------------------------------

class TestActiveToHealing:
    """30 s health check: either char Notifying=False → HEALING entered."""

    def test_health_check_fail_calls_set_capability_ancs_false(self, lc):
        backend, mock_service, _, _, timers, notifying = lc
        timers[1]()           # → ACTIVE (registers health-check timer)
        notifying[_NOTIF_SRC_PATH] = False
        mock_service.reset_mock()
        backend._health_check()   # tick explicitly — no GLib timer-ID ordering
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_health_check_fail_returns_source_remove(self, lc):
        backend, _, _, mock_glib, timers, notifying = lc
        timers[1]()
        notifying[_NOTIF_SRC_PATH] = False
        result = backend._health_check()   # tick explicitly — no GLib timer-ID ordering
        assert result == mock_glib.SOURCE_REMOVE

    def test_health_check_fail_schedules_heal_timer(self, lc):
        backend, _, _, mock_glib, timers, notifying = lc
        timers[1]()
        notifying[_NOTIF_SRC_PATH] = False
        backend._health_check()   # tick explicitly — no GLib timer-ID ordering
        assert backend._heal_timer_id is not None
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 5_000 in intervals

    def test_health_check_fail_clears_health_check_id(self, lc):
        backend, _, _, _, timers, notifying = lc
        timers[1]()
        notifying[_NOTIF_SRC_PATH] = False
        backend._health_check()   # tick explicitly — no GLib timer-ID ordering
        assert backend._health_check_id is None


# ---------------------------------------------------------------------------
# §19 HEALING → FALLBACK (3rd rearm attempt exhausted)
# ---------------------------------------------------------------------------

class TestHealingToFallback:
    """3rd _attempt_le_rearm call → FALLBACK entered, ancs_needs_repair=True."""

    @pytest.fixture
    def healing(self, lc):
        """lc advanced to HEALING state (500 ms poll failed)."""
        backend, mock_service, mock_bus, mock_glib, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()   # → HEALING; timers[2] = _attempt_le_rearm
        return backend, mock_service, mock_bus, mock_glib, timers, notifying

    def test_first_attempt_returns_source_continue(self, healing):
        backend, _, _, mock_glib, _, _ = healing
        result = backend._attempt_le_rearm()
        assert result == mock_glib.SOURCE_CONTINUE

    def test_second_attempt_returns_source_continue(self, healing):
        backend, _, _, mock_glib, _, _ = healing
        backend._attempt_le_rearm()
        result = backend._attempt_le_rearm()
        assert result == mock_glib.SOURCE_CONTINUE

    def test_third_attempt_enters_fallback_sets_ancs_needs_repair(self, healing):
        backend, mock_service, _, _, _, _ = healing
        backend._attempt_le_rearm()
        backend._attempt_le_rearm()
        mock_service.reset_mock()
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_called_with("ancs_needs_repair", True)

    def test_third_attempt_returns_source_remove(self, healing):
        backend, _, _, mock_glib, _, _ = healing
        backend._attempt_le_rearm()
        backend._attempt_le_rearm()
        result = backend._attempt_le_rearm()
        assert result == mock_glib.SOURCE_REMOVE

    def test_third_attempt_clears_heal_timer_id(self, healing):
        backend, _, _, _, _, _ = healing
        backend._attempt_le_rearm()
        backend._attempt_le_rearm()
        backend._attempt_le_rearm()
        assert backend._heal_timer_id is None

    def test_heal_attempts_counter_increments(self, healing):
        backend, _, _, _, _, _ = healing
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 1
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 2


# ---------------------------------------------------------------------------
# §20 HEALING → ACTIVE (rearm succeeds) [TDD: fails until builder implements]
# ---------------------------------------------------------------------------

class TestHealingToActive:
    """Rearm detects Notifying=True → transitions back to ACTIVE.

    These tests FAIL until the builder implements the rearm success path
    inside _attempt_le_rearm (currently SPIKE-TBD stub).
    """

    @pytest.fixture
    def healing(self, lc):
        backend, mock_service, mock_bus, mock_glib, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()
        return backend, mock_service, mock_bus, mock_glib, timers, notifying

    def test_rearm_success_calls_set_capability_ancs_true(self, healing):
        backend, mock_service, _, _, _, notifying = healing
        notifying[_NOTIF_SRC_PATH] = True  # rearm restored Notifying
        notifying[_DATA_SRC_PATH] = True
        mock_service.reset_mock()
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_rearm_success_clears_heal_timer_id(self, healing):
        backend, _, _, _, _, notifying = healing
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._heal_timer_id is None

    def test_rearm_success_resets_ancs_needs_repair(self, healing):
        backend, mock_service, _, _, _, notifying = healing
        backend._heal_attempts = 3
        backend._service.set_capability("ancs_needs_repair", True)
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        mock_service.reset_mock()
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_any_call("ancs_needs_repair", False)

    def test_rearm_success_restarts_health_check(self, healing):
        backend, _, _, _, _, notifying = healing
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._health_check_id is not None


# ---------------------------------------------------------------------------
# §21 Timer hygiene — stop() and _on_device_disconnected() clear all timers
# ---------------------------------------------------------------------------

class TestTimerHygiene:
    """stop() and _on_device_disconnected() clear both timer IDs; spurious fires no-op."""

    def test_stop_from_active_clears_health_check_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE
        assert backend._health_check_id is not None
        backend.stop()
        assert backend._health_check_id is None

    def test_stop_from_healing_clears_heal_timer_id(self, lc):
        backend, _, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()   # → HEALING
        assert backend._heal_timer_id is not None
        backend.stop()
        assert backend._heal_timer_id is None

    def test_disconnect_from_active_clears_health_check_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE
        assert backend._health_check_id is not None
        backend._on_device_disconnected()
        assert backend._health_check_id is None

    def test_disconnect_from_healing_clears_heal_timer_id(self, lc):
        backend, _, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()   # → HEALING
        assert backend._heal_timer_id is not None
        backend._on_device_disconnected()
        assert backend._heal_timer_id is None

    def test_spurious_health_check_after_stop_returns_source_remove(self, lc):
        backend, mock_service, _, mock_glib, timers, _ = lc
        timers[1]()   # → ACTIVE
        health_check = backend._health_check
        backend.stop()
        mock_service.reset_mock()
        result = health_check()
        assert result == mock_glib.SOURCE_REMOVE

    def test_spurious_health_check_after_stop_no_set_capability(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        timers[1]()
        health_check = backend._health_check
        backend.stop()
        mock_service.reset_mock()
        health_check()
        mock_service.set_capability.assert_not_called()

    def test_spurious_poll_after_disconnect_returns_source_remove(self, lc):
        backend, mock_service, _, mock_glib, timers, _ = lc
        poll = timers[1]
        backend._on_device_disconnected()
        mock_service.reset_mock()
        result = poll()
        assert result == mock_glib.SOURCE_REMOVE

    def test_spurious_poll_after_disconnect_no_set_capability(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        poll = timers[1]
        backend._on_device_disconnected()
        mock_service.reset_mock()
        poll()
        mock_service.set_capability.assert_not_called()

    def test_enter_healing_twice_cancels_first_timer(self, lc):
        backend, _, _, mock_glib, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()   # → HEALING (first heal timer registered)
        first_timer_id = backend._heal_timer_id
        assert first_timer_id is not None
        backend._enter_healing()   # re-enter: cancels first, registers second
        mock_glib.source_remove.assert_any_call(first_timer_id)
        assert backend._heal_timer_id is not None


# ---------------------------------------------------------------------------
# §22 HEALING stub — _attempt_le_rearm contains SPIKE-TBD, makes no D-Bus calls
# ---------------------------------------------------------------------------

class TestHealingStub:
    """_attempt_le_rearm is a documented stub pending spike results."""

    def test_spike_tbd_comment_in_source(self):
        src = inspect.getsource(ANCSBackend._attempt_le_rearm)
        assert "SPIKE-TBD" in src

    def test_stub_makes_no_dbus_bus_calls(self, lc):
        backend, _, mock_bus, _, _, _ = lc
        mock_bus.reset_mock()
        backend._heal_attempts = 0
        backend._attempt_le_rearm()
        mock_bus.get_object.assert_not_called()


# ---------------------------------------------------------------------------
# §23 Double-subscribe guard
# ---------------------------------------------------------------------------

class TestDoubleSubscribeGuard:
    """Second _on_device_connected while _notif_src_path is set → no-op."""

    def test_second_connect_while_subscribed_schedules_no_new_timer(self, lc):
        backend, _, _, mock_glib, _, _ = lc
        assert backend._notif_src_path is not None
        count_before = mock_glib.timeout_add.call_count
        backend._on_device_connected(_DEV_PATH)
        assert mock_glib.timeout_add.call_count == count_before

    def test_second_connect_while_subscribed_no_capability_change(self, lc):
        backend, mock_service, _, _, _, _ = lc
        assert backend._notif_src_path is not None
        mock_service.reset_mock()
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_not_called()


# ---------------------------------------------------------------------------
# §24 Backlog suppression: 2 s grace window after ACTIVE drops replay flood
# ---------------------------------------------------------------------------

class TestBacklogSuppression:
    """iOS replays full Notification Center on connect; suppress during 2 s window."""

    def test_active_transition_sets_backlog_suppress(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE
        assert backend._backlog_suppress is True

    def test_active_transition_schedules_backlog_timer_at_2s(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        timers[1]()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 2_000 in intervals

    def test_active_transition_sets_backlog_timer_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        assert backend._backlog_timer_id is not None

    def test_app_notification_suppressed_during_backlog_window(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE; _backlog_suppress = True
        payload = _data_source_tlv(uid=1, title="Hey", message="Yo",
                                   app_id="com.apple.WhatsApp")
        backend._on_data_source_changed({"Value": list(payload)})
        mock_service.on_app_notification_received.assert_not_called()

    def test_sms_suppressed_during_backlog_window(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        timers[1]()
        payload = _data_source_tlv(uid=2, title="Alice", message="Hi",
                                   app_id="com.apple.MobileSMS")
        backend._on_data_source_changed({"Value": list(payload)})
        mock_service.on_message_received.assert_not_called()

    def test_backlog_timer_fires_clears_suppress(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()   # → ACTIVE; sets backend._backlog_timer_id
        timers[backend._backlog_timer_id]()
        assert backend._backlog_suppress is False

    def test_backlog_timer_fires_clears_timer_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        tid = backend._backlog_timer_id
        timers[tid]()
        assert backend._backlog_timer_id is None

    def test_app_notification_dispatched_after_backlog_window(self, lc):
        backend, mock_service, _, _, timers, _ = lc
        timers[1]()
        timers[backend._backlog_timer_id]()   # backlog window closed
        payload = _data_source_tlv(uid=3, title="Hey", message="New",
                                   app_id="com.apple.WhatsApp")
        backend._on_data_source_changed({"Value": list(payload)})
        mock_service.on_app_notification_received.assert_called_once()

    def test_stop_from_active_clears_backlog_suppress(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        backend.stop()
        assert backend._backlog_suppress is False

    def test_stop_from_active_clears_backlog_timer_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        backend.stop()
        assert backend._backlog_timer_id is None

    def test_disconnect_clears_backlog_suppress(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        backend._on_device_disconnected()
        assert backend._backlog_suppress is False

    def test_disconnect_clears_backlog_timer_id(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        backend._on_device_disconnected()
        assert backend._backlog_timer_id is None

    def test_enter_healing_clears_backlog_suppress(self, lc):
        backend, _, _, _, timers, _ = lc
        timers[1]()
        backend._enter_healing()
        assert backend._backlog_suppress is False

    def test_enter_healing_cancels_backlog_timer(self, lc):
        backend, _, _, mock_glib, timers, _ = lc
        timers[1]()
        backlog_tid = backend._backlog_timer_id
        assert backlog_tid is not None
        backend._enter_healing()
        mock_glib.source_remove.assert_any_call(backlog_tid)
        assert backend._backlog_timer_id is None

    def test_healing_path_does_not_set_backlog_suppress(self, lc):
        backend, _, _, _, timers, notifying = lc
        notifying[_NOTIF_SRC_PATH] = False
        timers[1]()   # → HEALING (not ACTIVE)
        assert backend._backlog_suppress is False


# ---------------------------------------------------------------------------
# §25 StartNotify InProgress race: prior subscribe still pending on reconnect
# ---------------------------------------------------------------------------

def _make_inprogress_ctx(inprogress_on_retry=False):
    """Factory for started backends where StartNotify raises InProgress.

    inprogress_on_retry=False (default): only first call raises InProgress;
    second call succeeds (retry recovers).
    inprogress_on_retry=True: BOTH calls raise InProgress (retry fails too).
    """
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

    call_count = [0]

    def _make_interface(obj, iface):
        path = getattr(obj, "_dbus_path", "")
        if iface == "org.freedesktop.DBus.ObjectManager":
            return obj_mgr_mock
        if iface == "org.bluez.Device1":
            return mock_device
        if iface == _GATT_CHAR_IFACE and path == _CTRL_PT_PATH:
            return mock_ctrl_pt
        if iface == _GATT_CHAR_IFACE:
            char = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 2 or inprogress_on_retry:
                char.StartNotify.side_effect = Exception("org.bluez.Error.InProgress")
            return char
        return MagicMock(name=f"Interface({iface}@{path})")

    mock_glib = MagicMock(name="GLib")
    mock_glib.SOURCE_REMOVE = False
    mock_glib.SOURCE_CONTINUE = True
    _timers: dict = {}
    _next_id = [0]

    def _timeout_add(*args):
        _next_id[0] += 1
        tid = _next_id[0]
        # args[0]=interval, args[1]=callback, args[2:]=callback args
        cb = args[1]
        cb_args = args[2:]
        _timers[tid] = (cb, cb_args)
        return tid

    mock_glib.timeout_add.side_effect = _timeout_add
    mock_glib.source_remove.side_effect = lambda tid: _timers.pop(tid, None)

    return (mock_bus, mock_service, mock_glib, _timers, _make_interface)


class TestStartNotifyInProgress:
    """StartNotify InProgress on reconnect: schedule retry instead of giving up."""

    @pytest.fixture
    def ip_ctx(self):
        """Backend started; first _on_device_connected raises InProgress on both chars."""
        mock_bus, mock_service, mock_glib, _timers, _make_interface = _make_inprogress_ctx()
        with (
            patch("dbus.service.Object.__init__", return_value=None),
            patch("tincand.backends.ancs.dbus.SystemBus", return_value=mock_bus),
            patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_interface),
            patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
            patch("tincand.backends.ancs.GLib", mock_glib),
        ):
            mock_exc.DBusException = Exception
            backend = ANCSBackend()
            backend.register_service(mock_service)
            backend.start()
            backend._on_device_connected(_DEV_PATH)
            # timers[1] = retry _on_device_connected (1500 ms)
            yield backend, mock_service, mock_glib, _timers

    def test_inprogress_does_not_immediately_fail_ancs(self, ip_ctx):
        backend, mock_service, _, _ = ip_ctx
        # Should NOT have set capability False (that would be "ANCS unavailable")
        false_calls = [c for c in mock_service.set_capability.call_args_list
                       if list(c.args) == ["ancs", False]]
        assert not false_calls

    def test_inprogress_sets_subscribe_pending(self, ip_ctx):
        backend, _, _, _ = ip_ctx
        assert backend._subscribe_pending is True

    def test_inprogress_schedules_retry_timer_at_1500ms(self, ip_ctx):
        backend, _, mock_glib, _ = ip_ctx
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 1500 in intervals

    def test_inprogress_does_not_set_notif_src_path(self, ip_ctx):
        backend, _, _, _ = ip_ctx
        assert backend._notif_src_path is None

    def test_retry_after_inprogress_recovers_ancs(self, ip_ctx):
        backend, mock_service, _, _timers = ip_ctx
        # timers[1] is the retry callback (cb, args) tuple
        cb, cb_args = _timers[1]
        cb(*cb_args)   # second call — StartNotify succeeds this time
        assert backend._notif_src_path is not None

    def test_retry_sets_capability_ancs_true(self, ip_ctx):
        backend, mock_service, _, _timers = ip_ctx
        cb, cb_args = _timers[1]
        cb(*cb_args)
        mock_service.set_capability.assert_called_with("ancs", True)

    def test_disconnect_clears_subscribe_pending(self, ip_ctx):
        backend, _, _, _ = ip_ctx
        assert backend._subscribe_pending is True
        backend._on_device_disconnected()
        assert backend._subscribe_pending is False

    def test_stop_clears_subscribe_pending(self, ip_ctx):
        backend, _, _, _ = ip_ctx
        assert backend._subscribe_pending is True
        backend.stop()
        assert backend._subscribe_pending is False


# ---------------------------------------------------------------------------
# §14  _on_adv_error and _probe_le_advertising — actionable diagnostics
# (tincan-1d69e)
# ---------------------------------------------------------------------------


class TestAdvErrorDiagnostics:
    def test_adv_error_sets_capability_false_and_logs_remedy(self, ctx, caplog):
        backend, _, _, mock_service = ctx
        backend._adapter_path = "/org/bluez/hci0"
        exc = Exception("org.bluez.Error.Failed: Failed to register advertisement")
        with caplog.at_level(logging.WARNING, logger="tincand.backends.ancs"):
            backend._on_adv_error(exc)
        mock_service.set_capability.assert_called_with("ancs", False)
        assert "/org/bluez/hci0" in caplog.text
        assert "USB" in caplog.text or "--experimental" in caplog.text

    def test_adv_error_without_service_does_not_raise(self, ctx):
        backend, _, _, _ = ctx
        backend._service = None
        exc = Exception("org.bluez.Error.Failed")
        backend._on_adv_error(exc)  # must not raise

    def test_startup_probe_reports_zero_supported_instances(self, ctx, caplog):
        backend, mock_bus, _, mock_service = ctx
        backend._bus = mock_bus
        backend._adapter_path = "/org/bluez/hci0"
        props_mock = MagicMock()
        props_mock.GetAll.return_value = {"SupportedInstances": 0, "ActiveInstances": 0}
        with patch(
            "tincand.backends.ancs.dbus.Interface", return_value=props_mock
        ):
            with caplog.at_level(logging.WARNING, logger="tincand.backends.ancs"):
                backend._probe_le_advertising()
        mock_service.set_capability.assert_called_with("ancs", False)
        assert "USB" in caplog.text or "--experimental" in caplog.text
