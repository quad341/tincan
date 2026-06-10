"""HFP call controller — oFono bridge for im.tincan.Calls (tincan-0e6na).

Connects to oFono on the system D-Bus, discovers the iPhone HFP modem,
and translates oFono VoiceCallManager events into im.tincan.Calls signals
on the session bus via TincanService callbacks.

oFono must be running as a system service with the hfp_hf_bluez5 plugin.
If oFono is absent, the controller logs a WARNING and stays idle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from gi.repository import GLib

_log = logging.getLogger(__name__)

_OFONO_BUS = "org.ofono"
_IFACE_MANAGER = "org.ofono.Manager"
_IFACE_VCM = "org.ofono.VoiceCallManager"
_IFACE_CALL = "org.ofono.VoiceCall"

_IPHONE_MAC_FRAGMENT = "d0_6b_78_33_46_20"

_RETRY_STEPS = [1.0, 2.0, 4.0, 8.0, 15.0]
_AUDIO_TIMEOUT_S = 5


@dataclass
class CallState:
    call_id: str
    ofono_path: str
    state: str
    number: str
    direction: str
    audio_error: bool = field(default=False)


class CallController:
    """Bridge between oFono VoiceCallManager and im.tincan.Calls.

    Constructed by __main__ after TincanService; passed to
    TincanService via set_call_controller().
    """

    def __init__(self, service: object, contact_store: object) -> None:
        from tincand.hfp_capability import is_call_setup_ready

        if not is_call_setup_ready():
            _log.warning(
                "CallController: call_setup_ready is False — "
                "im.tincan.Calls methods will return NotAvailable"
            )

        self._service = service
        self._contact_store = contact_store
        self._calls: dict[str, CallState] = {}
        self._modem_path: str | None = None
        self._vcm = None  # org.ofono.VoiceCallManager proxy
        self._audio_timer_id: int | None = None
        self._retry_index: int = 0
        self._system_bus = None
        self._manager = None

        try:
            import dbus

            self._system_bus = dbus.SystemBus()
            manager_obj = self._system_bus.get_object(_OFONO_BUS, "/")
            self._manager = dbus.Interface(manager_obj, _IFACE_MANAGER)
            self._manager.connect_to_signal("ModemAdded", self._on_modem_added)
            self._manager.connect_to_signal("ModemRemoved", self._on_modem_removed)
            self._discover_modem()
        except Exception as exc:  # oFono absent or not running
            _log.warning(
                "CallController: oFono not available (%s) — "
                "install oFono to use call features",
                exc,
            )
            self._system_bus = None
            self._manager = None

    # ------------------------------------------------------------------
    # Modem discovery
    # ------------------------------------------------------------------

    def _is_hfp_iphone_modem(self, path: str, props: dict) -> bool:
        return (
            str(props.get("Type", "")).lower() == "hfp"
            and _IPHONE_MAC_FRAGMENT in str(path).lower()
        )

    def _discover_modem(self) -> None:
        try:
            modems = self._manager.GetModems()
        except Exception as exc:
            _log.debug("CallController: GetModems failed: %s", exc)
            self._schedule_retry()
            return

        for path, props in modems:
            if self._is_hfp_iphone_modem(str(path), dict(props)):
                self._bind_modem(str(path))
                return

        self._schedule_retry()

    def _schedule_retry(self) -> None:
        if self._retry_index >= len(_RETRY_STEPS):
            _log.info("CallController: modem discovery exhausted 30s — idling")
            return
        delay_s = _RETRY_STEPS[self._retry_index]
        self._retry_index += 1
        GLib.timeout_add(int(delay_s * 1000), self._retry_tick)

    def _retry_tick(self) -> bool:
        self._discover_modem()
        return False

    def _bind_modem(self, path: str) -> None:
        import dbus

        _log.info("CallController: bound to HFP modem %s", path)
        self._modem_path = path
        self._retry_index = 0
        vcm_obj = self._system_bus.get_object(_OFONO_BUS, path)
        self._vcm = dbus.Interface(vcm_obj, _IFACE_VCM)
        self._vcm.connect_to_signal("CallAdded", self._on_call_added)
        self._vcm.connect_to_signal("CallRemoved", self._on_call_removed)
        try:
            for call_path, props in self._vcm.GetCalls():
                self._on_call_added(call_path, props)
        except Exception as exc:
            _log.debug("CallController: GetCalls failed: %s", exc)

    def _on_modem_added(self, path: str, props: dict) -> None:
        if self._modem_path is None and self._is_hfp_iphone_modem(str(path), dict(props)):
            self._bind_modem(str(path))

    def _on_modem_removed(self, path: str) -> None:
        if str(path) != self._modem_path:
            return
        _log.info("CallController: HFP modem removed — clearing state")
        had_calls = bool(self._calls)
        self._calls.clear()
        self._vcm = None
        self._modem_path = None
        self._cancel_audio_timer()
        if had_calls:
            self._service.on_call_ended()
        self._retry_index = 0
        self._schedule_retry()

    # ------------------------------------------------------------------
    # Call lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _short_id(path: str) -> str:
        return str(path).rstrip("/").rsplit("/", 1)[-1]

    def _on_call_added(self, path: str, props: dict) -> None:
        import dbus

        call_id = self._short_id(str(path))
        state = str(props.get("State", "incoming"))
        number = str(props.get("LineIdentification", ""))
        direction = "outbound" if state == "dialing" else "inbound"

        call_obj = self._system_bus.get_object(_OFONO_BUS, str(path))
        call_iface = dbus.Interface(call_obj, _IFACE_CALL)
        call_iface.connect_to_signal(
            "PropertyChanged",
            lambda name, val, _cid=call_id: self._on_call_property_changed(_cid, name, val),
        )

        self._calls[call_id] = CallState(
            call_id=call_id,
            ofono_path=str(path),
            state=state,
            number=number,
            direction=direction,
        )

        if state == "incoming":
            caller_name = self._contact_store.get_name(number) or ""
            self._service.on_call_incoming(caller_name, number)

    def _on_call_removed(self, path: str) -> None:
        call_id = self._short_id(str(path))
        self._calls.pop(call_id, None)
        self._cancel_audio_timer()
        self._service.on_call_ended()

    def _on_call_property_changed(self, call_id: str, name: str, value: object) -> None:
        if str(name) != "State":
            return
        cs = self._calls.get(call_id)
        if cs is None:
            return
        new_state = str(value)
        cs.state = new_state
        if new_state == "active":
            self._cancel_audio_timer()
            if cs.audio_error:
                cs.audio_error = False
                self._service.on_audio_restored()
            else:
                self._service.on_call_connected()
        elif new_state == "terminated":
            self._cancel_audio_timer()
            self._service.on_call_ended()

    # ------------------------------------------------------------------
    # Audio timeout
    # ------------------------------------------------------------------

    def _start_audio_timer(self) -> None:
        self._cancel_audio_timer()
        self._audio_timer_id = GLib.timeout_add(_AUDIO_TIMEOUT_S * 1000, self._on_audio_timeout)

    def _cancel_audio_timer(self) -> None:
        if self._audio_timer_id is not None:
            GLib.source_remove(self._audio_timer_id)
            self._audio_timer_id = None

    def _on_audio_timeout(self) -> bool:
        self._audio_timer_id = None
        _log.warning("CallController: audio timeout (%ds) — emitting AudioError", _AUDIO_TIMEOUT_S)
        for cs in self._calls.values():
            cs.audio_error = True
        self._service.on_audio_error("sco_timeout")
        return False

    # ------------------------------------------------------------------
    # Call control (called by TincanService D-Bus methods)
    # ------------------------------------------------------------------

    def answer_call(self, call_id: str) -> None:
        import dbus

        cs = self._resolve_call(call_id)
        call_obj = self._system_bus.get_object(_OFONO_BUS, cs.ofono_path)
        dbus.Interface(call_obj, _IFACE_CALL).Answer()
        self._start_audio_timer()

    def hangup_call(self, call_id: str) -> None:
        import dbus

        if call_id:
            cs = self._resolve_call(call_id)
            call_obj = self._system_bus.get_object(_OFONO_BUS, cs.ofono_path)
            dbus.Interface(call_obj, _IFACE_CALL).Hangup()
        elif self._vcm is not None:
            self._vcm.HangupAll()

    def dial(self, number: str) -> str:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available — HFP modem not found")
        path = self._vcm.Dial(number, "")
        self._start_audio_timer()
        return self._short_id(str(path))

    def send_dtmf(self, key: str) -> None:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available")
        self._vcm.SendTones(key)

    def _resolve_call(self, call_id: str) -> CallState:
        if call_id and call_id in self._calls:
            return self._calls[call_id]
        for cs in self._calls.values():
            return cs
        raise KeyError(f"no active call: {call_id!r}")
