"""HFP call controller — oFono bridge for im.tincan.Calls (tincan-0e6na).

Connects to oFono on the system D-Bus, discovers the iPhone HFP modem,
and translates oFono VoiceCallManager events into im.tincan.Calls signals
on the session bus via TincanService callbacks.

oFono must be running as a system service with the hfp_hf_bluez5 plugin.
If oFono is absent, the controller logs a WARNING and stays idle.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from gi.repository import GLib

from tincand import call_audio
from tincand.hfp_capability import is_call_setup_ready

_log = logging.getLogger(__name__)

_OFONO_BUS = "org.ofono"
_IFACE_MANAGER = "org.ofono.Manager"
_IFACE_MODEM = "org.ofono.Modem"
_IFACE_VCM = "org.ofono.VoiceCallManager"
_IFACE_CALL = "org.ofono.VoiceCall"

_RETRY_STEPS = [1.0, 2.0, 4.0, 8.0, 15.0]
_AUDIO_TIMEOUT_S = 5

# SCO audio setup: the native bluez SCO nodes are created only when the SCO
# transport comes up, which lags call-active by a beat (observed ~0.5–1 s, but
# can be longer). Poll for them instead of a single deferred shot.
_SCO_SETUP_INTERVAL_MS = 500
_SCO_SETUP_MAX_ATTEMPTS = 10  # ~5 s total

_HCI_RE = re.compile(r"/(hci\d+)/")


def _adapter_hci_from_path(path: str) -> str:
    m = _HCI_RE.search(path)
    return m.group(1) if m else ""


@dataclass
class CallState:
    call_id: str
    ofono_path: str
    state: str
    number: str
    direction: str
    audio_error: bool = field(default=False)
    connected: bool = field(default=False)  # has the call ever reached "active"?


class CallController:
    """Bridge between oFono VoiceCallManager and im.tincan.Calls.

    Constructed by __main__ after TincanService; passed to
    TincanService via set_call_controller().
    """

    def __init__(
        self,
        service: object,
        contact_store: object,
        device_addr: str = "",
        adapter_hci: str = "",
    ) -> None:
        if not is_call_setup_ready():
            _log.warning(
                "CallController: call_setup_ready is False — "
                "im.tincan.Calls methods will return NotAvailable"
            )

        self._service = service
        self._contact_store = contact_store
        self._mac_fragment: str = device_addr.lower().replace(":", "_")
        self._adapter_hci: str = adapter_hci
        self._calls: dict[str, CallState] = {}
        self._modem_path: str | None = None
        self._vcm = None  # org.ofono.VoiceCallManager proxy
        self._audio_timer_id: int | None = None
        self._audio_timer_call_id: str | None = None
        self._audio_setup_timer_id: int | None = None
        self._sco_setup_attempts: int = 0
        self._sco_links: list[tuple[str, str]] = []
        self._call_sigs: dict[str, object] = {}  # SignalMatch per call_id
        self._retry_index: int = 0
        self._pending_online_path: str | None = None
        self._pending_subscription: object | None = None  # dbus SignalMatch
        self._vcm_signal_matches: list = []  # dbus SignalMatch — remove() on rebind
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
        if not self._mac_fragment:
            return False
        return (
            str(props.get("Type", "")) == "hfp"
            and self._mac_fragment in str(path).lower()
        )

    def _discover_modem(self) -> None:
        try:
            modems = self._manager.GetModems()
        except Exception as exc:
            _log.debug("CallController: GetModems failed: %s", exc)
            self._schedule_retry()
            return

        def _rank(path: str, online: bool) -> int:
            is_pref = bool(self._adapter_hci) and f"/{self._adapter_hci}/" in path
            return (not is_pref) * 2 + (not online)

        candidates = [
            (str(path), bool(dict(props).get("Online", False)))
            for path, props in modems
            if self._is_hfp_iphone_modem(str(path), dict(props))
        ]
        if not candidates:
            self._schedule_retry()
            return

        candidates.sort(key=lambda c: _rank(c[0], c[1]))
        top_path, top_online = candidates[0]
        top_rank = _rank(top_path, top_online)

        if top_rank == 1:
            # Preferred adapter modem exists but is Offline — defer bind
            if top_path != self._pending_online_path:
                self._subscribe_modem_online(top_path)
            return

        # Ranks 0, 2, 3: bind immediately
        if top_rank >= 2:
            _log.debug(
                "CallController: preferred adapter %s not available — "
                "binding fallback %s",
                self._adapter_hci or "(none configured)",
                top_path,
            )
        self._cancel_pending_subscription()
        self._bind_modem(top_path)

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

    def _subscribe_modem_online(self, path: str) -> None:
        import dbus

        self._cancel_pending_subscription()
        self._pending_online_path = path
        modem_obj = self._system_bus.get_object(_OFONO_BUS, path)
        modem_iface = dbus.Interface(modem_obj, _IFACE_MODEM)
        self._pending_modem_iface = modem_iface
        _log.info(
            "CallController: sending Powered=true to %s (preferred adapter %s) "
            "to trigger SLC establishment",
            path,
            self._adapter_hci,
        )
        try:
            modem_iface.SetProperty("Powered", dbus.Boolean(True))
        except Exception as exc:
            _log.debug(
                "CallController: SetProperty Powered=true on %s suppressed: %s",
                path,
                exc,
            )
        # A powered modem does NOT go Online on its own — request it, or calls
        # never work (VoiceCallManager stays unbound). If not powered yet this
        # raises NotAvailable (suppressed); the Powered PropertyChanged handler
        # below then re-requests Online once the SLC is up.
        try:
            modem_iface.SetProperty("Online", dbus.Boolean(True))
        except Exception as exc:
            _log.debug(
                "CallController: SetProperty Online=true on %s deferred until Powered: %s",
                path,
                exc,
            )
        self._pending_subscription = modem_iface.connect_to_signal(
            "PropertyChanged",
            lambda name, value: self._on_pending_modem_property_changed(path, name, value),
        )
        _log.info(
            "CallController: preferred adapter %s modem %s is Offline — "
            "deferring bind, watching PropertyChanged",
            self._adapter_hci,
            path,
        )

    def _cancel_pending_subscription(self) -> None:
        if self._pending_subscription is not None:
            try:
                self._pending_subscription.remove()
            except Exception:
                pass
            self._pending_subscription = None
        self._pending_online_path = None
        self._pending_modem_iface = None

    def _cancel_vcm_subscriptions(self) -> None:
        for match in self._vcm_signal_matches:
            try:
                match.remove()
            except Exception:
                pass
        self._vcm_signal_matches = []

    def _on_pending_modem_property_changed(self, path: str, name: str, value: object) -> None:
        if path != self._pending_online_path:
            _log.debug(
                "CallController: ignoring stale PropertyChanged from %s (watching %s)",
                path,
                self._pending_online_path,
            )
            return
        prop = str(name)
        if prop == "Powered" and bool(value):
            # SLC is up now — request Online (rejected before Powered, hence here).
            iface = self._pending_modem_iface
            if iface is not None:
                import dbus

                _log.info("CallController: %s Powered — requesting Online", path)
                try:
                    iface.SetProperty("Online", dbus.Boolean(True))
                except Exception as exc:
                    _log.debug(
                        "CallController: SetProperty Online=true on %s suppressed: %s",
                        path,
                        exc,
                    )
            return
        if prop == "Online" and bool(value):
            _log.info(
                "CallController: %s went Online — binding (preferred adapter %s)",
                path,
                self._adapter_hci,
            )
            self._cancel_pending_subscription()
            self._bind_modem(path)

    def _bind_modem(self, path: str) -> None:
        import dbus

        is_preferred = bool(self._adapter_hci) and f"/{self._adapter_hci}/" in path
        if self._modem_path and self._modem_path != path and not is_preferred:
            _log.info("CallController: re-binding to %s (was bound to %s)", path, self._modem_path)

        if is_preferred and self._modem_path is not None and self._modem_path != path:
            _log.info(
                "CallController: re-binding to preferred adapter %s modem "
                "(was bound to %s)",
                self._adapter_hci,
                self._modem_path,
            )
        elif is_preferred:
            _log.info(
                "CallController: bound to HFP modem %s (preferred adapter %s)",
                path,
                self._adapter_hci,
            )
        else:
            _log.warning(
                "CallController: bound to HFP modem %s "
                "(fallback — preferred adapter %s not available)",
                path,
                self._adapter_hci or "not configured",
            )
        self._cancel_pending_subscription()
        self._cancel_vcm_subscriptions()
        adapter_ok = call_audio.verify_dongle_adapter(path, self._adapter_hci)
        if hasattr(self._service, "set_adapter_warning"):
            if adapter_ok:
                self._service.set_adapter_warning("")
            else:
                actual_hci = _adapter_hci_from_path(path)
                warn = (
                    f"iPhone connected on {actual_hci} (built-in, no SCO). "
                    f"Connect iPhone to the ASUS USB-BT500 ({self._adapter_hci}) for call audio."
                )
                self._service.set_adapter_warning(warn)
        call_audio.verify_usb_autosuspend_off()
        self._modem_path = path
        self._retry_index = 0
        vcm_obj = self._system_bus.get_object(_OFONO_BUS, path)
        self._vcm = dbus.Interface(vcm_obj, _IFACE_VCM)
        self._vcm_signal_matches.append(
            self._vcm.connect_to_signal("CallAdded", self._on_call_added)
        )
        self._vcm_signal_matches.append(
            self._vcm.connect_to_signal("CallRemoved", self._on_call_removed)
        )
        try:
            for call_path, props in self._vcm.GetCalls():
                self._on_call_added(call_path, props)
        except Exception as exc:
            _log.debug("CallController: GetCalls failed: %s", exc)

    def _on_modem_added(self, path: str, props: dict) -> None:
        path = str(path)
        props = dict(props)
        if not self._is_hfp_iphone_modem(path, props):
            return

        is_preferred = bool(self._adapter_hci) and f"/{self._adapter_hci}/" in path
        if is_preferred:
            self._cancel_pending_subscription()
            self._discover_modem()
        elif self._modem_path is None and self._pending_online_path is None:
            self._discover_modem()

    def _on_modem_removed(self, path: str) -> None:
        path = str(path)

        if path == self._pending_online_path:
            self._cancel_pending_subscription()
            self._schedule_retry()

        if path != self._modem_path:
            return
        _log.info("CallController: HFP modem removed — clearing state")
        had_calls = bool(self._calls)
        for call_id, sig in list(self._call_sigs.items()):
            sig.remove()
            self._service.on_call_removed(call_id)
        self._call_sigs.clear()
        self._calls.clear()
        self._cancel_vcm_subscriptions()
        self._vcm = None
        self._modem_path = None
        self._cancel_audio_timer()
        self._cancel_audio_setup_timer()
        self._teardown_call_audio()
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
        sig = call_iface.connect_to_signal(
            "PropertyChanged",
            lambda name, val, _cid=call_id: self._on_call_property_changed(_cid, name, val),
        )
        old_sig = self._call_sigs.get(call_id)
        if old_sig is not None:
            try:
                old_sig.remove()
            except Exception:
                pass
        self._call_sigs[call_id] = sig

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
        elif state == "waiting":
            caller_name = self._contact_store.get_name(number) or ""
            self._service.on_call_waiting(call_id, number, caller_name)

    def _on_call_removed(self, path: str) -> None:
        call_id = self._short_id(str(path))
        sig = self._call_sigs.pop(call_id, None)
        if sig is not None:
            sig.remove()
        self._calls.pop(call_id, None)
        self._service.on_call_removed(call_id)
        if not self._calls:
            self._cancel_audio_timer()
            self._cancel_audio_setup_timer()
            self._teardown_call_audio()
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
            self._service.on_call_active(call_id, cs.number)
            if not cs.connected:
                # First time this call reaches active = it just connected. A
                # timeout that fired while the phone was still ringing is
                # spurious (audio cannot exist before "active"), so clear it and
                # ALWAYS announce CallConnected — downstream (the iris AEC bridge
                # and Call Card capture) engages on CallConnected, not
                # AudioRestored. Firing AudioRestored here on first connect (the
                # old behaviour when a long ring tripped the timer) silently
                # skipped both, causing echo + a card that never noticed the call.
                cs.connected = True
                cs.audio_error = False
                self._service.on_call_connected()
            elif cs.audio_error:
                # Re-active after a genuine mid-call audio drop → audio recovered.
                cs.audio_error = False
                self._service.on_audio_restored()
            # Audio can only establish now that the call is active — start the
            # watchdog here (not on dial), so a long ring never trips it.
            self._start_audio_timer(call_id)
            self._schedule_audio_setup()
        elif new_state == "held":
            self._service.on_call_held(call_id, cs.number)
        elif new_state == "terminated":
            pass  # CallRemoved handles teardown once _calls is empty

    # ------------------------------------------------------------------
    # Audio timeout
    # ------------------------------------------------------------------

    def _start_audio_timer(self, call_id: str = "") -> None:
        self._cancel_audio_timer()
        self._audio_timer_call_id = call_id
        self._audio_timer_id = GLib.timeout_add(_AUDIO_TIMEOUT_S * 1000, self._on_audio_timeout)

    def _cancel_audio_timer(self) -> None:
        if self._audio_timer_id is not None:
            GLib.source_remove(self._audio_timer_id)
            self._audio_timer_id = None
        self._audio_timer_call_id = None

    def _on_audio_timeout(self) -> bool:
        self._audio_timer_id = None
        _log.warning("CallController: audio timeout (%ds) — emitting AudioError", _AUDIO_TIMEOUT_S)
        cs = self._calls.get(self._audio_timer_call_id or "")
        if cs is not None:
            cs.audio_error = True
        self._service.on_audio_error("sco_timeout")
        return False

    # ------------------------------------------------------------------
    # SCO audio setup (polled — the SCO nodes lag call-active)
    # ------------------------------------------------------------------

    def _schedule_audio_setup(self) -> None:
        self._cancel_audio_setup_timer()
        self._sco_setup_attempts = 0
        self._audio_setup_timer_id = GLib.timeout_add(
            _SCO_SETUP_INTERVAL_MS, self._on_audio_setup_tick
        )

    def _cancel_audio_setup_timer(self) -> None:
        if self._audio_setup_timer_id is not None:
            GLib.source_remove(self._audio_setup_timer_id)
            self._audio_setup_timer_id = None

    def _on_audio_setup_tick(self) -> bool:
        """Poll for the bluez SCO nodes and wire routing once they appear.

        Returns True to keep the GLib timer firing (retry), False to stop.
        """
        self._sco_setup_attempts += 1
        if self._modem_path and self._system_bus:
            if self._sco_setup_attempts == 1:
                call_audio.set_ofono_call_volume(self._system_bus, self._modem_path)
            self._sco_links = call_audio.setup_sco_routing(self._mac_fragment)

        if self._sco_links:
            _log.info(
                "CallController: SCO routing established on attempt %d (%d links)",
                self._sco_setup_attempts,
                len(self._sco_links),
            )
            self._cancel_audio_timer()  # audio is up — stand down the watchdog
            self._audio_setup_timer_id = None
            self._report_aec_state()
            return False

        if self._sco_setup_attempts >= _SCO_SETUP_MAX_ATTEMPTS:
            _log.warning(
                "CallController: SCO routing not established after %d attempts "
                "(~%.1fs) — call audio may be relying on the iris AEC bridge",
                self._sco_setup_attempts,
                _SCO_SETUP_MAX_ATTEMPTS * _SCO_SETUP_INTERVAL_MS / 1000.0,
            )
            self._audio_setup_timer_id = None
            # Still verify: WirePlumber or iris's bridge may have routed the
            # call on its own, and the AEC state matters either way.
            self._report_aec_state()
            return False

        return True  # SCO nodes not up yet — retry

    def _report_aec_state(self) -> None:
        """Verify the echo-cancellation invariants and surface the result.

        Echo-free calls are a hard requirement (tincan-97mlk.2): without AEC
        the far party hears themselves and won't stay on the call. The result
        is exposed as the call_audio_aec capability so clients and the doctor
        check can see it.
        """
        ok, detail = call_audio.verify_aec_in_path(self._mac_fragment)
        try:
            self._service.set_capability("call_audio_aec", ok)
        except Exception as exc:  # service surface optional in some tests
            _log.debug("CallController: set_capability(call_audio_aec) failed: %s", exc)
        if ok:
            _log.info("CallController: AEC verified in call path ✓ (%s)", detail)
        else:
            _log.warning(
                "CallController: NO ECHO CANCELLATION in call path — far party "
                "may hear themselves: %s",
                detail,
            )

    def _teardown_call_audio(self) -> None:
        self._cancel_audio_setup_timer()
        call_audio.teardown_sco_routing(self._sco_links)
        self._sco_links = []
        try:
            self._service.set_capability("call_audio_aec", False)
        except Exception as exc:
            _log.debug("CallController: set_capability(call_audio_aec) failed: %s", exc)

    # ------------------------------------------------------------------
    # Call control (called by TincanService D-Bus methods)
    # ------------------------------------------------------------------

    def answer_call(self, call_id: str) -> None:
        import dbus

        cs = self._resolve_call(call_id)
        call_obj = self._system_bus.get_object(_OFONO_BUS, cs.ofono_path)
        dbus.Interface(call_obj, _IFACE_CALL).Answer()
        # The audio watchdog is started when the call reaches "active"
        # (_on_call_property_changed), not here — so a long ring never trips it.

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
        call_id = self._short_id(str(path))
        # No audio watchdog here — it starts when the call reaches "active".
        # Starting it on dial made a ring longer than the timeout fire a spurious
        # AudioError, which then suppressed CallConnected on answer.
        return call_id

    def send_dtmf(self, key: str) -> None:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available")
        self._vcm.SendTones(key)

    def get_calls(self) -> list[CallState]:
        return list(self._calls.values())

    def swap_calls(self) -> None:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available")
        self._vcm.SwapCalls()

    def hold_and_answer(self) -> None:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available")
        self._vcm.HoldAndAnswer()

    def release_and_answer(self) -> None:
        if self._vcm is None:
            raise RuntimeError("oFono VoiceCallManager not available")
        self._vcm.ReleaseAndAnswer()

    def _resolve_call(self, call_id: str) -> CallState:
        if call_id and call_id in self._calls:
            return self._calls[call_id]
        for cs in self._calls.values():
            return cs
        raise KeyError(f"no active call: {call_id!r}")
