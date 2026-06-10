"""Tests: im.tincan.Calls D-Bus contract + CallController._resolve_call.
Bead: tincan-0e6na (contributor: quad341)

Thin contract coverage for the call-control surface added in this PR. The
CallController is mocked at the dbus_service boundary — the deeper oFono
bridge / audio-timer behaviour is left to tincan-z2l9w.

Coverage:
  §1 Calls methods gate on call_setup_ready
     - Dial/Answer/Hangup/SendDtmf -> org.ofono.Error.NotAvailable when
       call_setup_ready is False (the readiness check fires before any
       controller dispatch).
  §2 Calls methods require a wired controller
     - Dial/Answer/Hangup/SendDtmf -> org.freedesktop.DBus.Error.ServiceUnknown
       when call_setup_ready is True but _call_controller is None.
  §3 SendDtmf argument validation
     - multi-char / out-of-set keys -> im.tincan.Error.InvalidArgument, and the
       controller is never dispatched to.
     - a single valid key in [0-9*#] dispatches to controller.send_dtmf.
  §4 CallController._resolve_call("") falls back to the single active call.

All D-Bus registration is mocked — no real bus required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.exceptions
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
    svc.CapabilityChanged = MagicMock()
    return svc


# Each entry: (method_name, args) — every Calls method takes one string arg.
_CALL_METHODS = [
    ("Dial", ("5551234",)),
    ("Answer", ("1",)),
    ("Hangup", ("1",)),
    ("SendDtmf", ("5",)),
]
_METHOD_IDS = [m[0] for m in _CALL_METHODS]


def _dbus_name(exc_info) -> str:
    return exc_info.value.get_dbus_name()


# ---------------------------------------------------------------------------
# §1 call_setup_ready gate
# ---------------------------------------------------------------------------

class TestCallsNotAvailableWhenNotReady:
    """call_setup_ready=False -> org.ofono.Error.NotAvailable for every method."""

    @pytest.mark.parametrize("method,args", _CALL_METHODS, ids=_METHOD_IDS)
    def test_not_available(self, service, method, args):
        # Controller is wired, so NotAvailable must come from the readiness
        # gate and not from the missing-controller branch.
        service.set_call_controller(MagicMock())
        assert service._capabilities.get("call_setup_ready", False) is False
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            getattr(service, method)(*args)
        assert _dbus_name(exc_info) == "org.ofono.Error.NotAvailable"


# ---------------------------------------------------------------------------
# §2 controller-wired gate
# ---------------------------------------------------------------------------

class TestCallsServiceUnknownWhenNoController:
    """call_setup_ready=True but no controller -> ServiceUnknown."""

    @pytest.mark.parametrize("method,args", _CALL_METHODS, ids=_METHOD_IDS)
    def test_service_unknown(self, service, method, args):
        service.set_capability("call_setup_ready", True)
        assert service._call_controller is None
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            getattr(service, method)(*args)
        assert _dbus_name(exc_info) == "org.freedesktop.DBus.Error.ServiceUnknown"


# ---------------------------------------------------------------------------
# §3 SendDtmf validation
# ---------------------------------------------------------------------------

class TestSendDtmfValidation:
    """SendDtmf enforces a single key in [0-9*#] before dispatching."""

    @pytest.fixture
    def ready_service(self, service):
        service.set_capability("call_setup_ready", True)
        service.set_call_controller(MagicMock())
        return service

    @pytest.mark.parametrize("bad_key", ["", "12", "a", "*#", "+", " "])
    def test_invalid_key_raises_and_does_not_dispatch(self, ready_service, bad_key):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            ready_service.SendDtmf(bad_key)
        assert _dbus_name(exc_info) == "im.tincan.Error.InvalidArgument"
        ready_service._call_controller.send_dtmf.assert_not_called()

    @pytest.mark.parametrize("good_key", list("0123456789*#"))
    def test_valid_key_dispatches(self, ready_service, good_key):
        ready_service.SendDtmf(good_key)
        ready_service._call_controller.send_dtmf.assert_called_once_with(good_key)


# ---------------------------------------------------------------------------
# §4 CallController._resolve_call fallback
# ---------------------------------------------------------------------------

class TestResolveCallFallback:
    """_resolve_call('') falls back to the single active call."""

    def _make_controller(self):
        # Drive __init__ down its oFono-absent path: is_call_setup_ready is
        # mocked and dbus.SystemBus raises, so the controller constructs idle
        # without touching a real system bus.
        with patch("tincand.hfp_capability.is_call_setup_ready", return_value=True), \
             patch("dbus.SystemBus", side_effect=RuntimeError("no system bus in test")):
            from tincand.call_controller import CallController
            return CallController(MagicMock(), MagicMock())

    def test_empty_id_returns_single_active_call(self):
        from tincand.call_controller import CallState

        controller = self._make_controller()
        cs = CallState(
            call_id="7",
            ofono_path="/org/ofono/modem0/voicecall07",
            state="active",
            number="5551234",
            direction="inbound",
        )
        controller._calls = {"7": cs}
        assert controller._resolve_call("") is cs

    def test_explicit_id_returns_matching_call(self):
        from tincand.call_controller import CallState

        controller = self._make_controller()
        a = CallState("1", "/p/1", "active", "111", "inbound")
        b = CallState("2", "/p/2", "incoming", "222", "inbound")
        controller._calls = {"1": a, "2": b}
        assert controller._resolve_call("2") is b

    def test_no_calls_raises_keyerror(self):
        controller = self._make_controller()
        controller._calls = {}
        with pytest.raises(KeyError):
            controller._resolve_call("")
