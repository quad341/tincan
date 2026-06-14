"""Tests: ANCSBackend HEALING state machine — _attempt_le_rearm() and _enter_healing().
Bead: tincan-kzgk7.6

Coverage:
  §1 HEALING → ACTIVE (natural reconnect on attempt 1)
  §2 HEALING → ACTIVE (natural reconnect on attempt 3)
  §3 Advertisement recycle on attempt 0 only
  §4 HEALING → FALLBACK at attempt 5
  §5 Timer interval is 15 s (not 5 s)
  §6 _enter_healing() resets _heal_attempts to 0
  §7 _recycle_advertisement sequence

Constraints:
  - Mock D-Bus (dbus-python) and GLib — no live BlueZ daemon.
  - do NOT call Device1.Connect() anywhere.
  - GLib.timeout_add is mocked; tests tick timers explicitly.

Run: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincand/test_ancs_healing_kzgk7.py -v
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from tincand.ancs_util import (
    CONTROL_POINT_UUID,
    DATA_SOURCE_UUID,
    NOTIF_SOURCE_UUID,
)
from tincand.backends.ancs import ANCSBackend

# ---------------------------------------------------------------------------
# Test-local D-Bus path constants (must match the lc / healing fixture)
# ---------------------------------------------------------------------------

_DEV_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
_NOTIF_SRC_PATH = f"{_DEV_PATH}/service01/char01"
_CTRL_PT_PATH = f"{_DEV_PATH}/service01/char02"
_DATA_SRC_PATH = f"{_DEV_PATH}/service01/char03"

_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"
_LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_ADV_PATH = "/uk/tincanapp/ancs/advertisement0"


def _make_managed_objects():
    return {
        _NOTIF_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": NOTIF_SOURCE_UUID}},
        _CTRL_PT_PATH: {_GATT_CHAR_IFACE: {"UUID": CONTROL_POINT_UUID}},
        _DATA_SRC_PATH: {_GATT_CHAR_IFACE: {"UUID": DATA_SOURCE_UUID}},
    }


# ---------------------------------------------------------------------------
# Shared fixture: backend started + device connected, enters HEALING state
# ---------------------------------------------------------------------------

@pytest.fixture
def healing_ctx():
    """ANCSBackend in HEALING state with all D-Bus and GLib mocked.

    Returns (backend, mock_service, mock_adv_mgr, mock_glib, timers, notifying).

    - notifying[path] controls what _verify_notifying() returns for each path.
    - timers is a dict {timer_id: callback} — call timers[n]() to fire a timer.
    - After setup, timers[1] = _check_notifying_after_subscribe (just fired,
      triggering HEALING), timers[2] = _attempt_le_rearm (15 s heal timer).
    - _notif_src_path and _data_src_path are pre-set on the backend.
    """
    _notifying: dict[str, bool] = {
        _NOTIF_SRC_PATH: False,  # initially False → 500 ms poll → HEALING
        _DATA_SRC_PATH: True,
    }

    mock_bus = MagicMock(name="SystemBus")
    mock_ctrl_pt = MagicMock(name="ControlPoint")
    mock_service = MagicMock(name="TincanService")
    mock_device = MagicMock(name="Device1")
    mock_device.Get.return_value = True  # Bonded=True — skip Pair()
    mock_adv_mgr = MagicMock(name="LEAdvertisingManager1")

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
        if iface == _GATT_CHAR_IFACE and path == _CTRL_PT_PATH:
            return mock_ctrl_pt
        if iface == _PROPS_IFACE:
            props = MagicMock()
            _path = path
            props.Get.side_effect = lambda _i, _p: _notifying.get(_path, True)
            return props
        if iface == _LE_ADV_MANAGER_IFACE:
            return mock_adv_mgr
        return MagicMock(name=f"Interface({iface}@{path})")

    mock_glib = MagicMock(name="GLib")
    mock_glib.SOURCE_REMOVE = False
    mock_glib.SOURCE_CONTINUE = True
    _timers: dict[int, object] = {}
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
        patch("tincand.backends.ancs.dbus.Interface", side_effect=_make_interface),
        patch("tincand.backends.ancs.dbus.exceptions") as mock_exc,
        patch("tincand.backends.ancs.GLib", mock_glib),
    ):
        mock_exc.DBusException = Exception

        backend = ANCSBackend()
        backend.register_service(mock_service)
        backend.start()
        backend._on_device_connected(_DEV_PATH)
        # timers[1] = _check_notifying_after_subscribe (500 ms)
        # Fire it now with _NOTIF_SRC_PATH Notifying=False → HEALING
        _timers[1]()
        # _enter_healing() ran: _heal_attempts=0, timers[2] = _attempt_le_rearm
        mock_service.reset_mock()
        mock_adv_mgr.reset_mock()
        mock_glib.timeout_add.reset_mock()
        yield backend, mock_service, mock_adv_mgr, mock_glib, _timers, _notifying


# ---------------------------------------------------------------------------
# §1 HEALING → ACTIVE (natural reconnect on attempt 1)
# ---------------------------------------------------------------------------

class TestHealingToActiveAttempt1:
    """_attempt_le_rearm detects Notifying=True on first call → ACTIVE."""

    def test_set_capability_ancs_true(self, healing_ctx):
        backend, mock_service, _, _, timers, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_any_call("ancs", True)

    def test_set_capability_ancs_needs_repair_false(self, healing_ctx):
        backend, mock_service, _, _, timers, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_any_call("ancs_needs_repair", False)

    def test_heal_timer_id_cleared(self, healing_ctx):
        backend, _, _, _, timers, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._heal_timer_id is None

    def test_heal_attempts_reset_to_zero(self, healing_ctx):
        backend, _, _, _, timers, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 0

    def test_health_check_scheduled_at_30s(self, healing_ctx):
        backend, _, _, mock_glib, timers, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 30_000 in intervals

    def test_returns_source_remove(self, healing_ctx):
        backend, _, _, mock_glib, _, notifying = healing_ctx
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        result = backend._attempt_le_rearm()
        assert result == mock_glib.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# §2 HEALING → ACTIVE (natural reconnect on attempt 3)
# ---------------------------------------------------------------------------

class TestHealingToActiveAttempt3:
    """Two failing calls followed by a successful one → ACTIVE on attempt 3."""

    @pytest.fixture
    def after_two_failures(self, healing_ctx):
        backend, mock_service, mock_adv_mgr, mock_glib, timers, notifying = healing_ctx
        # attempts 1 and 2: Notifying=False
        backend._attempt_le_rearm()  # attempt 1: _heal_attempts → 1
        backend._attempt_le_rearm()  # attempt 2: _heal_attempts → 2
        mock_service.reset_mock()
        mock_glib.timeout_add.reset_mock()
        return backend, mock_service, mock_adv_mgr, mock_glib, timers, notifying

    def test_active_transition_on_third_call(self, after_two_failures):
        backend, mock_service, _, _, _, notifying = after_two_failures
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        mock_service.set_capability.assert_any_call("ancs", True)

    def test_heal_attempts_reset_on_third_success(self, after_two_failures):
        backend, _, _, _, _, notifying = after_two_failures
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 0

    def test_heal_timer_id_cleared_on_third_success(self, after_two_failures):
        backend, _, _, _, _, notifying = after_two_failures
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        assert backend._heal_timer_id is None

    def test_health_check_scheduled_on_third_success(self, after_two_failures):
        backend, _, _, mock_glib, _, notifying = after_two_failures
        notifying[_NOTIF_SRC_PATH] = True
        notifying[_DATA_SRC_PATH] = True
        backend._attempt_le_rearm()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 30_000 in intervals


# ---------------------------------------------------------------------------
# §3 Advertisement recycle on attempt 0 only
# ---------------------------------------------------------------------------

class TestAdvertisementRecycle:
    """_recycle_advertisement called on attempt 0; skipped on subsequent attempts."""

    def test_unregister_called_on_first_failing_attempt(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, notifying = healing_ctx
        # Notifying=False: first failing attempt (_heal_attempts starts at 0)
        backend._attempt_le_rearm()
        mock_adv_mgr.UnregisterAdvertisement.assert_called_once_with(_ADV_PATH)

    def test_reregister_timer_scheduled_at_500ms(self, healing_ctx):
        backend, _, _, mock_glib, _, notifying = healing_ctx
        backend._attempt_le_rearm()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 500 in intervals

    def test_unregister_not_called_on_second_failing_attempt(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, notifying = healing_ctx
        backend._attempt_le_rearm()   # attempt 0→1: recycle called
        mock_adv_mgr.reset_mock()
        backend._attempt_le_rearm()   # attempt 1→2: recycle NOT called
        mock_adv_mgr.UnregisterAdvertisement.assert_not_called()

    def test_unregister_not_called_on_third_failing_attempt(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, notifying = healing_ctx
        backend._attempt_le_rearm()   # attempt 0→1
        backend._attempt_le_rearm()   # attempt 1→2
        mock_adv_mgr.reset_mock()
        backend._attempt_le_rearm()   # attempt 2→3: recycle NOT called
        mock_adv_mgr.UnregisterAdvertisement.assert_not_called()


# ---------------------------------------------------------------------------
# §4 HEALING → FALLBACK at attempt 5
# ---------------------------------------------------------------------------

class TestHealingToFallback:
    """5 consecutive failing _attempt_le_rearm calls → FALLBACK."""

    @pytest.fixture
    def after_five_failures(self, healing_ctx):
        backend, mock_service, mock_adv_mgr, mock_glib, timers, notifying = healing_ctx
        for _ in range(5):
            backend._attempt_le_rearm()
        return backend, mock_service, mock_adv_mgr, mock_glib, timers, notifying

    def test_ancs_needs_repair_set_true(self, after_five_failures):
        _, mock_service, *_ = after_five_failures
        mock_service.set_capability.assert_any_call("ancs_needs_repair", True)

    def test_heal_timer_id_none_after_fallback(self, after_five_failures):
        backend, *_ = after_five_failures
        assert backend._heal_timer_id is None

    def test_returns_source_remove_on_fifth_attempt(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        result = None
        for _ in range(5):
            result = backend._attempt_le_rearm()
        assert result == mock_glib.SOURCE_REMOVE

    def test_no_further_timer_scheduled_after_fallback(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        for _ in range(4):
            backend._attempt_le_rearm()
        mock_glib.timeout_add.reset_mock()
        backend._attempt_le_rearm()  # 5th: enters FALLBACK
        # Only heal timer calls — no 15 s reschedule
        heal_reschedule = [
            c for c in mock_glib.timeout_add.call_args_list
            if c.args[0] == 15_000
        ]
        assert heal_reschedule == []

    def test_four_failures_do_not_enter_fallback(self, healing_ctx):
        backend, mock_service, *_ = healing_ctx
        for _ in range(4):
            backend._attempt_le_rearm()
        calls_with_true = [
            c for c in mock_service.set_capability.call_args_list
            if list(c.args) == ["ancs_needs_repair", True]
        ]
        assert calls_with_true == []


# ---------------------------------------------------------------------------
# §5 Timer interval is 15 s (not 5 s)
# ---------------------------------------------------------------------------

class TestHealTimerInterval:
    """Non-terminal _attempt_le_rearm reschedules itself at 15 000 ms."""

    def test_first_failure_reschedules_at_15s(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        backend._attempt_le_rearm()
        reschedule_calls = [
            c for c in mock_glib.timeout_add.call_args_list
            if c.args[0] == 15_000
        ]
        assert len(reschedule_calls) >= 1

    def test_interval_is_not_5s(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        backend._attempt_le_rearm()
        five_second_calls = [
            c for c in mock_glib.timeout_add.call_args_list
            if c.args[0] == 5_000
        ]
        assert five_second_calls == []

    def test_heal_timer_id_updated_after_reschedule(self, healing_ctx):
        backend, _, _, mock_glib, timers, _ = healing_ctx
        old_timer_id = backend._heal_timer_id
        backend._attempt_le_rearm()
        # A new timer was registered; _heal_timer_id should point to it
        assert backend._heal_timer_id is not None
        assert backend._heal_timer_id != old_timer_id


# ---------------------------------------------------------------------------
# §6 _enter_healing() resets _heal_attempts to 0
# ---------------------------------------------------------------------------

class TestEnterHealingReset:
    """_enter_healing() always resets _heal_attempts to 0."""

    def test_resets_attempts_from_zero(self, healing_ctx):
        backend, *_ = healing_ctx
        assert backend._heal_attempts == 0

    def test_resets_attempts_from_nonzero(self, healing_ctx):
        backend, _, _, _, timers, notifying = healing_ctx
        backend._attempt_le_rearm()
        backend._attempt_le_rearm()
        assert backend._heal_attempts == 2
        backend._enter_healing()
        assert backend._heal_attempts == 0

    def test_cancels_existing_heal_timer_on_re_enter(self, healing_ctx):
        backend, _, _, mock_glib, timers, notifying = healing_ctx
        first_timer_id = backend._heal_timer_id
        backend._enter_healing()  # re-enter
        mock_glib.source_remove.assert_any_call(first_timer_id)

    def test_schedules_new_heal_timer_at_15s(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        mock_glib.timeout_add.reset_mock()
        backend._enter_healing()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 15_000 in intervals

    def test_enter_healing_sets_capability_ancs_false(self, healing_ctx):
        backend, mock_service, *_ = healing_ctx
        mock_service.reset_mock()
        backend._enter_healing()
        mock_service.set_capability.assert_any_call("ancs", False)


# ---------------------------------------------------------------------------
# §7 _recycle_advertisement sequence
# ---------------------------------------------------------------------------

class TestRecycleAdvertisementSequence:
    """_recycle_advertisement and _reregister_advertisement sequence."""

    def test_unregister_advertisement_called_with_adv_path(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, _ = healing_ctx
        backend._recycle_advertisement()
        mock_adv_mgr.UnregisterAdvertisement.assert_called_with(_ADV_PATH)

    def test_reregister_timer_scheduled_at_500ms(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        mock_glib.timeout_add.reset_mock()
        backend._recycle_advertisement()
        intervals = [c.args[0] for c in mock_glib.timeout_add.call_args_list]
        assert 500 in intervals

    def test_reregister_timer_callback_is_reregister_method(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        mock_glib.timeout_add.reset_mock()
        backend._recycle_advertisement()
        callbacks = [c.args[1] for c in mock_glib.timeout_add.call_args_list
                     if c.args[0] == 500]
        assert len(callbacks) == 1
        assert callbacks[0] == backend._reregister_advertisement

    def test_reregister_calls_register_advertisement_async(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, _ = healing_ctx
        backend._reregister_advertisement()
        mock_adv_mgr.RegisterAdvertisement.assert_called_once()
        call_kwargs = mock_adv_mgr.RegisterAdvertisement.call_args
        assert call_kwargs.args[0] == _ADV_PATH
        assert "reply_handler" in call_kwargs.kwargs
        assert "error_handler" in call_kwargs.kwargs

    def test_reregister_returns_source_remove(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        result = backend._reregister_advertisement()
        assert result == mock_glib.SOURCE_REMOVE

    def test_dbus_exception_in_unregister_is_swallowed(self, healing_ctx):
        backend, _, mock_adv_mgr, _, _, _ = healing_ctx
        mock_adv_mgr.UnregisterAdvertisement.side_effect = Exception("D-Bus error")
        # Must not raise — DBusException is caught and logged at DEBUG
        backend._recycle_advertisement()  # no exception

    def test_none_bus_in_recycle_returns_early(self, healing_ctx):
        backend, *_ = healing_ctx
        backend._bus = None
        backend._recycle_advertisement()  # no exception, no D-Bus calls

    def test_none_bus_in_reregister_returns_source_remove(self, healing_ctx):
        backend, _, _, mock_glib, _, _ = healing_ctx
        backend._bus = None
        result = backend._reregister_advertisement()
        assert result == mock_glib.SOURCE_REMOVE
