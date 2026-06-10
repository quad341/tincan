"""Tests: TincanService im.tincan.Calls method guards.
Bead: tincan-z2l9w

Coverage:
  §1 call_setup_ready=False → Dial/Answer/Hangup/SendDtmf raise org.ofono.Error.NotAvailable
  §2 _call_controller=None (setup_ready=True) → Dial/Answer/Hangup/SendDtmf raise
       org.freedesktop.DBus.Error.ServiceUnknown
  §3 SendDtmf DTMF key validation — valid single [0-9*#] passes, invalid raises InvalidArgument

No real D-Bus connection required — TincanService instantiated with mocked bus.
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
    # Mock all signal emitters so call-path tests can assert against them.
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    svc.AppNotificationReceived = MagicMock()
    svc.IncomingCall = MagicMock()
    svc.CallConnected = MagicMock()
    svc.CallEnded = MagicMock()
    svc.AudioError = MagicMock()
    svc.AudioRestored = MagicMock()
    return svc


@pytest.fixture
def ready_service(service):
    """Service with call_setup_ready=True but no controller wired."""
    service._capabilities["call_setup_ready"] = True
    return service


@pytest.fixture
def wired_service(ready_service):
    """Service with call_setup_ready=True and a mock CallController attached."""
    ctrl = MagicMock()
    ctrl.dial.return_value = "call0"
    ready_service.set_call_controller(ctrl)
    return ready_service


# ---------------------------------------------------------------------------
# §1 call_setup_ready=False → NotAvailable on all Calls methods
# ---------------------------------------------------------------------------

class TestCallMethodsRequireSetupReady:
    """All im.tincan.Calls methods raise org.ofono.Error.NotAvailable when setup not ready."""

    def _assert_not_available(self, exc_info):
        exc = exc_info.value
        assert isinstance(exc, dbus.exceptions.DBusException)
        assert exc.get_dbus_name() == "org.ofono.Error.NotAvailable"

    def test_dial_raises_not_available(self, service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            service.Dial("+15550001234")
        self._assert_not_available(exc_info)

    def test_answer_raises_not_available(self, service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            service.Answer("call0")
        self._assert_not_available(exc_info)

    def test_hangup_raises_not_available(self, service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            service.Hangup("call0")
        self._assert_not_available(exc_info)

    def test_send_dtmf_raises_not_available(self, service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            service.SendDtmf("5")
        self._assert_not_available(exc_info)


# ---------------------------------------------------------------------------
# §2 _call_controller=None → ServiceUnknown
# ---------------------------------------------------------------------------

class TestCallMethodsRequireController:
    """All Calls methods raise org.freedesktop.DBus.Error.ServiceUnknown when controller absent."""

    def _assert_service_unknown(self, exc_info):
        exc = exc_info.value
        assert isinstance(exc, dbus.exceptions.DBusException)
        assert exc.get_dbus_name() == "org.freedesktop.DBus.Error.ServiceUnknown"

    def test_dial_raises_service_unknown(self, ready_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            ready_service.Dial("+15550001234")
        self._assert_service_unknown(exc_info)

    def test_answer_raises_service_unknown(self, ready_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            ready_service.Answer("call0")
        self._assert_service_unknown(exc_info)

    def test_hangup_raises_service_unknown(self, ready_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            ready_service.Hangup("call0")
        self._assert_service_unknown(exc_info)

    def test_send_dtmf_raises_service_unknown(self, ready_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            ready_service.SendDtmf("5")
        self._assert_service_unknown(exc_info)


# ---------------------------------------------------------------------------
# §3 SendDtmf DTMF key validation
# ---------------------------------------------------------------------------

class TestSendDtmfValidation:
    """SendDtmf validates key is exactly one char in [0-9*#]."""

    def _assert_invalid_argument(self, exc_info):
        exc = exc_info.value
        assert isinstance(exc, dbus.exceptions.DBusException)
        assert exc.get_dbus_name() == "im.tincan.Error.InvalidArgument"

    @pytest.mark.parametrize("key", list("0123456789*#"))
    def test_valid_dtmf_key_dispatches_to_controller(self, wired_service, key):
        wired_service.SendDtmf(key)
        wired_service._call_controller.send_dtmf.assert_called_once_with(key)

    def test_empty_string_raises_invalid_argument(self, wired_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            wired_service.SendDtmf("")
        self._assert_invalid_argument(exc_info)

    def test_multi_char_raises_invalid_argument(self, wired_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            wired_service.SendDtmf("12")
        self._assert_invalid_argument(exc_info)

    def test_letter_raises_invalid_argument(self, wired_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            wired_service.SendDtmf("A")
        self._assert_invalid_argument(exc_info)

    def test_space_raises_invalid_argument(self, wired_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            wired_service.SendDtmf(" ")
        self._assert_invalid_argument(exc_info)


# ---------------------------------------------------------------------------
# §4 on_call_* callbacks fire the correct D-Bus signals
# ---------------------------------------------------------------------------

class TestCallbacksFireSignals:
    """TincanService.on_call_* callbacks emit the correct im.tincan.Calls signals."""

    def test_on_call_incoming_emits_incoming_call_signal(self, service):
        service.on_call_incoming("Alice", "+15550001234")
        service.IncomingCall.assert_called_once_with("Alice", "+15550001234")

    def test_on_call_connected_emits_call_connected_signal(self, service):
        service.on_call_connected()
        service.CallConnected.assert_called_once()

    def test_on_call_ended_emits_call_ended_signal(self, service):
        service.on_call_ended()
        service.CallEnded.assert_called_once()

    def test_on_audio_error_emits_audio_error_signal(self, service):
        service.on_audio_error("sco_timeout")
        service.AudioError.assert_called_once_with("sco_timeout")

    def test_on_audio_restored_emits_audio_restored_signal(self, service):
        service.on_audio_restored()
        service.AudioRestored.assert_called_once()
