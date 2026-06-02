"""Tests: ANCSBackend — corrected GATT consumer model.
Beads: tincan-2ee (§1-§13), tincan-d3ew (§14-§21)

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
  §14 _check_notifying_after_subscribe — Notifying=True → ACTIVE; False → HEALING
  §15 _health_check — Notifying=True → SOURCE_CONTINUE; False → HEALING + SOURCE_REMOVE
  §16 _enter_healing — clears capability, cancels health check, resets counter, arms heal timer
  §17 _attempt_le_rearm — increments counter; enters FALLBACK on 3rd attempt
  §18 _enter_fallback — sets ancs_needs_repair; safe without service
  §19 stop() timer cleanup — GLib.source_remove called for armed timers; IDs cleared to None
  §20 disconnect() timer cleanup — same pattern as stop()
  §21 double-subscribe guard — second _on_device_connected while subscribed is a no-op

No hardware or real D-Bus — all D-Bus objects mocked.
Run with: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincand/test_ancs_backend.py -v
"""
from __future__ import annotations

import struct
from unittest.mock import MagicMock, call, patch

import pytest

from tincand.backends.ancs import ANCSBackend
from tincand.ancs_util import (
    ANCS_SERVICE_UUID,
    ATTR_APP_ID,
    ATTR_MESSAGE,
    ATTR_TITLE,
    CONTROL_POINT_UUID,
    DATA_SOURCE_UUID,
    NOTIF_SOURCE_UUID,
    ANCSDataBuffer,
    build_get_attrs_cmd,
    parse_notification_source,
)

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
# §2 start() — RegisterApplication + RegisterAdvertisement
# ---------------------------------------------------------------------------

class TestStart:
    """start() connects to the system bus and registers both GATT objects."""

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
            mock_adv_mgr = MagicMock()
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
            if iface == "org.bluez.Device1":
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

    def test_category_0_other_does_not_write_control_point(self, subscribed):
        backend, _, mock_ctrl_pt, _ = subscribed
        data = _notif_source_bytes(event_id=0, category_id=0, uid=3)
        backend._on_notif_source_changed(
            "org.freedesktop.DBus.Properties",
            {"Value": list(data)},
            [],
        )
        mock_ctrl_pt.WriteValue.assert_not_called()

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
# §14 _check_notifying_after_subscribe — 500 ms post-subscribe Notifying poll
# ---------------------------------------------------------------------------

class TestCheckNotifyingAfterSubscribe:
    """500 ms post-subscribe poll: both Notifying=True → ACTIVE; either False → HEALING."""

    def test_both_notifying_true_arms_30s_health_check_timer(self, subscribed):
        backend, *_ = subscribed
        with (
            patch("tincand.backends.ancs.GLib.timeout_add", return_value=42) as mock_add,
            patch.object(backend, "_verify_notifying", return_value=True),
        ):
            backend._check_notifying_after_subscribe()
        mock_add.assert_called_once_with(30_000, backend._health_check)

    def test_both_notifying_true_stores_health_check_id(self, subscribed):
        backend, *_ = subscribed
        with (
            patch("tincand.backends.ancs.GLib.timeout_add", return_value=42),
            patch.object(backend, "_verify_notifying", return_value=True),
        ):
            backend._check_notifying_after_subscribe()
        assert backend._health_check_id == 42

    def test_both_notifying_true_returns_source_remove(self, subscribed):
        from gi.repository import GLib as _G
        backend, *_ = subscribed
        with (
            patch("tincand.backends.ancs.GLib.timeout_add"),
            patch.object(backend, "_verify_notifying", return_value=True),
        ):
            result = backend._check_notifying_after_subscribe()
        assert result == _G.SOURCE_REMOVE

    def test_notif_src_notifying_false_calls_enter_healing(self, subscribed):
        backend, *_ = subscribed
        notifying = {backend._notif_src_path: False, backend._data_src_path: True}
        with (
            patch("tincand.backends.ancs.GLib.timeout_add"),
            patch.object(backend, "_verify_notifying", side_effect=lambda p: notifying[p]),
            patch.object(backend, "_enter_healing") as mock_heal,
        ):
            backend._check_notifying_after_subscribe()
        mock_heal.assert_called_once()

    def test_data_src_notifying_false_calls_enter_healing(self, subscribed):
        backend, *_ = subscribed
        notifying = {backend._notif_src_path: True, backend._data_src_path: False}
        with (
            patch("tincand.backends.ancs.GLib.timeout_add"),
            patch.object(backend, "_verify_notifying", side_effect=lambda p: notifying[p]),
            patch.object(backend, "_enter_healing") as mock_heal,
        ):
            backend._check_notifying_after_subscribe()
        mock_heal.assert_called_once()

    def test_healing_path_returns_source_remove(self, subscribed):
        from gi.repository import GLib as _G
        backend, *_ = subscribed
        with (
            patch.object(backend, "_verify_notifying", return_value=False),
            patch.object(backend, "_enter_healing"),
        ):
            result = backend._check_notifying_after_subscribe()
        assert result == _G.SOURCE_REMOVE

    def test_bus_none_returns_source_remove_immediately(self, ctx):
        from gi.repository import GLib as _G
        backend, *_ = ctx
        assert backend._bus is None
        result = backend._check_notifying_after_subscribe()
        assert result == _G.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# §15 _health_check — 30 s ACTIVE health poll
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """_health_check: Notifying=True → SOURCE_CONTINUE; False → HEALING + SOURCE_REMOVE."""

    def test_both_notifying_true_returns_source_continue(self, subscribed):
        from gi.repository import GLib as _G
        backend, *_ = subscribed
        with patch.object(backend, "_verify_notifying", return_value=True):
            result = backend._health_check()
        assert result == _G.SOURCE_CONTINUE

    def test_both_notifying_true_does_not_enter_healing(self, subscribed):
        backend, *_ = subscribed
        with (
            patch.object(backend, "_verify_notifying", return_value=True),
            patch.object(backend, "_enter_healing") as mock_heal,
        ):
            backend._health_check()
        mock_heal.assert_not_called()

    def test_notifying_false_calls_enter_healing(self, subscribed):
        backend, *_ = subscribed
        with (
            patch.object(backend, "_verify_notifying", return_value=False),
            patch.object(backend, "_enter_healing") as mock_heal,
        ):
            backend._health_check()
        mock_heal.assert_called_once()

    def test_notifying_false_returns_source_remove(self, subscribed):
        from gi.repository import GLib as _G
        backend, *_ = subscribed
        with (
            patch.object(backend, "_verify_notifying", return_value=False),
            patch.object(backend, "_enter_healing"),
        ):
            result = backend._health_check()
        assert result == _G.SOURCE_REMOVE

    def test_notifying_false_clears_health_check_id(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = 99
        with (
            patch.object(backend, "_verify_notifying", return_value=False),
            patch.object(backend, "_enter_healing"),
        ):
            backend._health_check()
        assert backend._health_check_id is None

    def test_bus_none_clears_health_check_id_returns_source_remove(self, ctx):
        from gi.repository import GLib as _G
        backend, *_ = ctx
        backend._health_check_id = 77
        result = backend._health_check()
        assert backend._health_check_id is None
        assert result == _G.SOURCE_REMOVE

    def test_notif_src_path_none_clears_id_returns_source_remove(self, subscribed):
        from gi.repository import GLib as _G
        backend, *_ = subscribed
        backend._notif_src_path = None
        backend._health_check_id = 55
        result = backend._health_check()
        assert backend._health_check_id is None
        assert result == _G.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# §16 _enter_healing — HEALING state entry
# ---------------------------------------------------------------------------

class TestEnterHealing:
    """_enter_healing: clears capability, cancels health check, resets counter, arms timer."""

    def test_sets_capability_ancs_false(self, subscribed):
        backend, _, _, mock_service = subscribed
        mock_service.reset_mock()
        with patch("tincand.backends.ancs.GLib.timeout_add"):
            backend._enter_healing()
        mock_service.set_capability.assert_called_with("ancs", False)

    def test_cancels_health_check_timer_when_set(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = 99
        with (
            patch("tincand.backends.ancs.GLib.source_remove") as mock_remove,
            patch("tincand.backends.ancs.GLib.timeout_add"),
        ):
            backend._enter_healing()
        mock_remove.assert_called_with(99)

    def test_health_check_id_none_after_enter_healing(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = 99
        with (
            patch("tincand.backends.ancs.GLib.source_remove"),
            patch("tincand.backends.ancs.GLib.timeout_add"),
        ):
            backend._enter_healing()
        assert backend._health_check_id is None

    def test_no_source_remove_when_health_check_id_is_none(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = None
        with (
            patch("tincand.backends.ancs.GLib.source_remove") as mock_remove,
            patch("tincand.backends.ancs.GLib.timeout_add"),
        ):
            backend._enter_healing()
        mock_remove.assert_not_called()

    def test_resets_heal_attempts_to_zero(self, subscribed):
        backend, *_ = subscribed
        backend._heal_attempts = 2
        with patch("tincand.backends.ancs.GLib.timeout_add"):
            backend._enter_healing()
        assert backend._heal_attempts == 0

    def test_arms_5s_heal_timer(self, subscribed):
        backend, *_ = subscribed
        with patch("tincand.backends.ancs.GLib.timeout_add") as mock_add:
            backend._enter_healing()
        mock_add.assert_called_once_with(5_000, backend._attempt_le_rearm)

    def test_stores_heal_timer_id(self, subscribed):
        backend, *_ = subscribed
        with patch("tincand.backends.ancs.GLib.timeout_add", return_value=55):
            backend._enter_healing()
        assert backend._heal_timer_id == 55


# ---------------------------------------------------------------------------
# §17 _attempt_le_rearm — HEALING body, max 3 attempts
# ---------------------------------------------------------------------------

class TestAttemptLeRearm:
    """_attempt_le_rearm: increments counter; enters FALLBACK on 3rd attempt."""

    @pytest.fixture
    def healing_backend(self, ctx):
        backend, _, _, mock_service = ctx
        backend._heal_attempts = 0
        return backend, mock_service

    def test_increments_heal_attempts(self, healing_backend):
        backend, _ = healing_backend
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 1

    def test_first_attempt_returns_source_continue(self, healing_backend):
        from gi.repository import GLib as _G
        backend, _ = healing_backend
        result = backend._attempt_le_rearm()
        assert result == _G.SOURCE_CONTINUE

    def test_second_attempt_returns_source_continue(self, healing_backend):
        from gi.repository import GLib as _G
        backend, _ = healing_backend
        backend._heal_attempts = 1
        result = backend._attempt_le_rearm()
        assert result == _G.SOURCE_CONTINUE

    def test_third_attempt_calls_enter_fallback(self, healing_backend):
        backend, _ = healing_backend
        backend._heal_attempts = 2
        with patch.object(backend, "_enter_fallback") as mock_fallback:
            backend._attempt_le_rearm()
        mock_fallback.assert_called_once()

    def test_third_attempt_returns_source_remove(self, healing_backend):
        from gi.repository import GLib as _G
        backend, _ = healing_backend
        backend._heal_attempts = 2
        with patch.object(backend, "_enter_fallback"):
            result = backend._attempt_le_rearm()
        assert result == _G.SOURCE_REMOVE

    def test_third_attempt_clears_heal_timer_id(self, healing_backend):
        backend, _ = healing_backend
        backend._heal_attempts = 2
        backend._heal_timer_id = 55
        with patch.object(backend, "_enter_fallback"):
            backend._attempt_le_rearm()
        assert backend._heal_timer_id is None


# ---------------------------------------------------------------------------
# §18 _enter_fallback — FALLBACK state
# ---------------------------------------------------------------------------

class TestEnterFallback:
    """_enter_fallback sets ancs_needs_repair=True; no crash without service."""

    def test_sets_capability_ancs_needs_repair_true(self, subscribed):
        backend, _, _, mock_service = subscribed
        mock_service.reset_mock()
        backend._enter_fallback()
        mock_service.set_capability.assert_called_with("ancs_needs_repair", True)

    def test_no_crash_when_service_is_none(self, ctx):
        backend, *_ = ctx
        backend._service = None
        backend._enter_fallback()  # must not raise


# ---------------------------------------------------------------------------
# §19 stop() clears both timer IDs
# ---------------------------------------------------------------------------

class TestStopClearsTimers:
    """stop() calls GLib.source_remove for armed timers; both IDs are None after."""

    def test_stop_calls_source_remove_for_health_check_id(self, started):
        backend, *_ = started
        backend._health_check_id = 77
        with patch("tincand.backends.ancs.GLib.source_remove") as mock_remove:
            backend.stop()
        mock_remove.assert_any_call(77)

    def test_stop_clears_health_check_id_to_none(self, started):
        backend, *_ = started
        backend._health_check_id = 77
        with patch("tincand.backends.ancs.GLib.source_remove"):
            backend.stop()
        assert backend._health_check_id is None

    def test_stop_calls_source_remove_for_heal_timer_id(self, started):
        backend, *_ = started
        backend._heal_timer_id = 88
        with patch("tincand.backends.ancs.GLib.source_remove") as mock_remove:
            backend.stop()
        mock_remove.assert_any_call(88)

    def test_stop_clears_heal_timer_id_to_none(self, started):
        backend, *_ = started
        backend._heal_timer_id = 88
        with patch("tincand.backends.ancs.GLib.source_remove"):
            backend.stop()
        assert backend._heal_timer_id is None

    def test_stop_skips_source_remove_when_timers_are_none(self, started):
        backend, *_ = started
        assert backend._health_check_id is None
        assert backend._heal_timer_id is None
        with patch("tincand.backends.ancs.GLib.source_remove") as mock_remove:
            backend.stop()
        mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# §20 _on_device_disconnected() clears both timer IDs
# ---------------------------------------------------------------------------

class TestDisconnectClearsTimers:
    """_on_device_disconnected cancels and clears both health check and heal timers."""

    def test_disconnect_calls_source_remove_for_health_check_id(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = 33
        with patch("tincand.backends.ancs.GLib.source_remove") as mock_remove:
            backend._on_device_disconnected()
        mock_remove.assert_any_call(33)

    def test_disconnect_clears_health_check_id_to_none(self, subscribed):
        backend, *_ = subscribed
        backend._health_check_id = 33
        with patch("tincand.backends.ancs.GLib.source_remove"):
            backend._on_device_disconnected()
        assert backend._health_check_id is None

    def test_disconnect_calls_source_remove_for_heal_timer_id(self, subscribed):
        backend, *_ = subscribed
        backend._heal_timer_id = 44
        with patch("tincand.backends.ancs.GLib.source_remove") as mock_remove:
            backend._on_device_disconnected()
        mock_remove.assert_any_call(44)

    def test_disconnect_clears_heal_timer_id_to_none(self, subscribed):
        backend, *_ = subscribed
        backend._heal_timer_id = 44
        with patch("tincand.backends.ancs.GLib.source_remove"):
            backend._on_device_disconnected()
        assert backend._heal_timer_id is None


# ---------------------------------------------------------------------------
# §21 Double-subscribe guard
# ---------------------------------------------------------------------------

class TestDoubleSubscribeGuard:
    """Second _on_device_connected while _notif_src_path is set is a no-op."""

    def test_second_connected_does_not_call_set_capability_again(self, subscribed):
        backend, _, _, mock_service = subscribed
        mock_service.reset_mock()
        backend._on_device_connected(_DEV_PATH)
        mock_service.set_capability.assert_not_called()

    def test_second_connected_does_not_call_get_object_again(self, subscribed):
        backend, mock_bus, *_ = subscribed
        initial_count = mock_bus.get_object.call_count
        backend._on_device_connected(_DEV_PATH)
        assert mock_bus.get_object.call_count == initial_count
