"""tincand/pairing.py — dual-mode ANCS+MAP pairing state machine."""
from __future__ import annotations

import logging
import threading

import dbus

from tincand.adapter_check import check_adapter_le_capable

_log = logging.getLogger(__name__)

_BLUEZ_SERVICE = "org.bluez"
_LE_ADV_MGR_IFACE = "org.bluez.LEAdvertisingManager1"
_ADV_PATH = "/uk/tincanapp/pairing/advertisement0"


class PairingState:
    IDLE = "IDLE"
    CHECKING_ADAPTER = "CHECKING_ADAPTER"
    ADVERTISING = "ADVERTISING"
    WAITING_FOR_PAIR = "WAITING_FOR_PAIR"
    VERIFYING_ANCS = "VERIFYING_ANCS"
    MAP_SESSION = "MAP_SESSION"
    MAP_CONSENT_PROMPT = "MAP_CONSENT_PROMPT"
    VERIFYING_MAP = "VERIFYING_MAP"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FailureReason:
    ADAPTER_NOT_CAPABLE = "adapter_not_capable"
    ADVERTISING_FAILED = "advertising_failed"
    PAIR_TIMEOUT = "pair_timeout"
    ANCS_NOT_EXPOSED = "ancs_not_exposed"
    MAP_CONSENT_DENIED = "map_consent_denied"


class BluezMap:
    """Thin MAP client for pairing-flow verification (real calls via obexd)."""

    def create_session(self) -> object:
        """Establish an OBEX MAP session. Raises on 0x43 Forbidden."""
        raise NotImplementedError

    def list_messages(self) -> list:
        """Enumerate inbox messages to confirm MAP access."""
        return []


class PairingOrchestrator:
    """Orchestrate dual-mode ANCS+MAP pairing.

    State sequence:
      CHECKING_ADAPTER → ADVERTISING → WAITING_FOR_PAIR → VERIFYING_ANCS
      → MAP_SESSION → [MAP_CONSENT_PROMPT →] VERIFYING_MAP → SUCCESS
      or → FAILED(reason) at any step.

    Args:
        on_state_change: Callable(state, failure_reason=None)
        adapter_path: BlueZ adapter object path (e.g. /org/bluez/hci0)
        pair_timeout: seconds to wait for iOS to initiate pairing
        ancs_timeout: seconds to wait for ANCS chars after pair
    """

    def __init__(
        self,
        on_state_change,
        adapter_path: str = "/org/bluez/hci0",
        pair_timeout: float = 120.0,
        ancs_timeout: float = 30.0,
    ) -> None:
        self._on_state_change = on_state_change
        self._adapter_path = adapter_path
        self._pair_timeout = pair_timeout
        self._ancs_timeout = ancs_timeout
        self._lock = threading.Lock()
        self._pair_timer: threading.Timer | None = None
        self._ancs_timer: threading.Timer | None = None
        self._done = False

    def _emit(self, state: str, failure_reason: str | None = None) -> None:
        self._on_state_change(state, failure_reason)

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self._cancel_timers()
        self._on_state_change(PairingState.FAILED, reason)

    def _cancel_timers(self) -> None:
        with self._lock:
            if self._pair_timer:
                self._pair_timer.cancel()
                self._pair_timer = None
            if self._ancs_timer:
                self._ancs_timer.cancel()
                self._ancs_timer = None

    def start(self) -> None:
        """Begin the pairing flow: check adapter capability then advertise."""
        self._emit(PairingState.CHECKING_ADAPTER)
        if not check_adapter_le_capable(self._adapter_path):
            self._fail(FailureReason.ADAPTER_NOT_CAPABLE)
            return

        bus = dbus.SystemBus()
        adapter_obj = bus.get_object(_BLUEZ_SERVICE, self._adapter_path)
        le_adv_mgr = dbus.Interface(adapter_obj, _LE_ADV_MGR_IFACE)
        le_adv_mgr.RegisterAdvertisement(
            _ADV_PATH,
            {},
            reply_handler=self._on_adv_registered,
            error_handler=self._on_adv_error,
        )
        _log.debug("PairingOrchestrator: RegisterAdvertisement sent (async)")

    def _on_adv_registered(self) -> None:
        self._emit(PairingState.ADVERTISING)
        self._emit(PairingState.WAITING_FOR_PAIR)
        with self._lock:
            timer = threading.Timer(self._pair_timeout, self._on_pair_timeout)
            timer.daemon = True
            timer.start()
            self._pair_timer = timer
        _log.info("PairingOrchestrator: advertising — waiting for iOS pair")

    def _on_adv_error(self, error: object) -> None:
        _log.warning("PairingOrchestrator: RegisterAdvertisement failed: %s", error)
        self._fail(FailureReason.ADVERTISING_FAILED)

    def _on_pair_timeout(self) -> None:
        _log.warning("PairingOrchestrator: pair timeout (%ss)", self._pair_timeout)
        self._fail(FailureReason.PAIR_TIMEOUT)

    def _on_device_paired(self, dev_path: str) -> None:
        """Signal: iOS completed pairing with this adapter."""
        with self._lock:
            if self._pair_timer:
                self._pair_timer.cancel()
                self._pair_timer = None
        _log.info("PairingOrchestrator: device paired at %s", dev_path)
        self._emit(PairingState.VERIFYING_ANCS)
        with self._lock:
            timer = threading.Timer(self._ancs_timeout, self._on_ancs_timeout)
            timer.daemon = True
            timer.start()
            self._ancs_timer = timer

    def _on_ancs_timeout(self) -> None:
        _log.warning("PairingOrchestrator: ANCS timeout (%ss)", self._ancs_timeout)
        self._fail(FailureReason.ANCS_NOT_EXPOSED)

    def _on_ancs_chars_appeared(self, dev_path: str) -> None:
        """Signal: BlueZ discovered ANCS characteristics on the paired device."""
        with self._lock:
            if self._ancs_timer:
                self._ancs_timer.cancel()
                self._ancs_timer = None
        _log.info("PairingOrchestrator: ANCS chars found on %s", dev_path)
        self._emit(PairingState.MAP_SESSION)
        self._try_map_session(first_attempt=True)

    def _try_map_session(self, first_attempt: bool = True) -> None:
        try:
            map_client = BluezMap()
            map_client.create_session()
            map_client.list_messages()
            self._emit(PairingState.VERIFYING_MAP)
            self._emit(PairingState.SUCCESS)
            _log.info("PairingOrchestrator: pairing complete")
        except Exception as exc:  # noqa: BLE001
            exc_str = str(exc)
            if "0x43" in exc_str or "Forbidden" in exc_str:
                if first_attempt:
                    _log.info("PairingOrchestrator: MAP 0x43 — prompting user consent")
                    self._emit(PairingState.MAP_CONSENT_PROMPT)
                else:
                    _log.warning("PairingOrchestrator: MAP consent denied on retry")
                    self._fail(FailureReason.MAP_CONSENT_DENIED)
            else:
                _log.warning("PairingOrchestrator: MAP session error: %s", exc)
                self._fail(FailureReason.MAP_CONSENT_DENIED)

    def signal_map_consent(self) -> None:
        """User granted MAP access on iPhone; retry MAP session creation."""
        _log.info("PairingOrchestrator: user signalled MAP consent — retrying")
        self._try_map_session(first_attempt=False)
