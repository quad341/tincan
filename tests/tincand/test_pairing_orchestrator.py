"""Tests: PairingOrchestrator — dual-mode ANCS+MAP pairing state machine.
Bead: tincan-inb6

Coverage:
  §1  Happy path: CAPABLE adapter -> advertising -> pair -> ANCS chars -> MAP -> SUCCESS
  §2  Adapter NOT_CAPABLE: FAILED(adapter_not_capable) immediately, no advertising
  §3  Pairing timeout: iOS never initiates pair within timeout -> FAILED(pair_timeout)
  §4  ANCS chars absent after pair: FAILED(ancs_not_exposed)
  §5  MAP 0x43 Forbidden first call: MAP_CONSENT_PROMPT emitted; user retry -> SUCCESS
  §6  MAP 0x43 Forbidden on retry too: FAILED(map_consent_denied)
  §7  RegisterAdvertisement async error (NoReply/D-Bus): FAILED(advertising_failed)
  §8  State sequence emitted in correct order on happy path

No hardware or real D-Bus — all D-Bus interactions mocked.
Run with: python -m pytest tests/tincand/test_pairing_orchestrator.py -v
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from tincand.pairing import FailureReason, PairingOrchestrator, PairingState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADAPTER_PATH = "/org/bluez/hci0"
_DEV_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"

# Short timeouts so timeout tests don't block for real durations.
_FAST_TIMEOUT = 0.01


# ---------------------------------------------------------------------------
# State capture helper
# ---------------------------------------------------------------------------

class _StateCapture:
    """Collects on_state_change callbacks; sets a threading.Event on terminal state."""

    def __init__(self):
        self.states: list[str] = []
        self.failure_reasons: list[str | None] = []
        self._lock = threading.Lock()
        self.terminal = threading.Event()

    def __call__(self, state: str, failure_reason: str | None = None) -> None:
        with self._lock:
            self.states.append(state)
            self.failure_reasons.append(failure_reason)
        if state in (PairingState.SUCCESS, PairingState.FAILED):
            self.terminal.set()

    def wait_terminal(self, timeout: float = 2.0) -> bool:
        return self.terminal.wait(timeout)

    @property
    def last_state(self) -> str | None:
        with self._lock:
            return self.states[-1] if self.states else None

    @property
    def last_failure(self) -> str | None:
        with self._lock:
            return self.failure_reasons[-1] if self.failure_reasons else None


# ---------------------------------------------------------------------------
# D-Bus mock helpers
# ---------------------------------------------------------------------------

def _make_le_adv_mgr_success():
    """LEAdvertisingManager1 mock whose RegisterAdvertisement immediately succeeds."""
    le_adv_mgr = MagicMock(name="LEAdvertisingManager1")

    def _reg_adv(adv_obj, options, reply_handler, error_handler):
        reply_handler()

    le_adv_mgr.RegisterAdvertisement.side_effect = _reg_adv
    return le_adv_mgr


def _make_le_adv_mgr_fail():
    """LEAdvertisingManager1 mock whose RegisterAdvertisement immediately errors."""
    le_adv_mgr = MagicMock(name="LEAdvertisingManager1")

    def _reg_adv(adv_obj, options, reply_handler, error_handler):
        error_handler(Exception("org.bluez.Error.NoReply: timeout"))

    le_adv_mgr.RegisterAdvertisement.side_effect = _reg_adv
    return le_adv_mgr


def _make_bus(le_adv_mgr: MagicMock) -> MagicMock:
    """Minimal SystemBus mock; routes LEAdvertisingManager1 to the provided mock."""
    bus = MagicMock(name="SystemBus")
    bus.get_object.side_effect = lambda s, p: MagicMock(name=f"obj({p})", _dbus_path=str(p))

    def _iface(obj, iface):
        if iface == "org.bluez.LEAdvertisingManager1":
            return le_adv_mgr
        return MagicMock(name=f"Interface({iface})")

    bus._make_iface = _iface
    return bus


def _make_map_always_success():
    mock_map = MagicMock(name="BluezMap")
    mock_map.create_session.return_value = MagicMock(name="MAPSession")
    mock_map.list_messages.return_value = []
    return mock_map


def _make_map_403_then_success():
    """MAP that raises Forbidden on first create_session, succeeds on second."""
    mock_map = MagicMock(name="BluezMap")
    call_count = {"n": 0}

    def _create(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("Forbidden: 0x43")
        return MagicMock(name="MAPSession")

    mock_map.create_session.side_effect = _create
    mock_map.list_messages.return_value = []
    return mock_map


def _make_map_always_403():
    mock_map = MagicMock(name="BluezMap")
    mock_map.create_session.side_effect = Exception("Forbidden: 0x43")
    return mock_map


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def capable_ctx():
    """Orchestrator with CAPABLE adapter; RegisterAdvertisement and MAP succeed."""
    capture = _StateCapture()
    le_adv_mgr = _make_le_adv_mgr_success()
    bus = _make_bus(le_adv_mgr)
    mock_map = _make_map_always_success()

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=True),
        patch("tincand.pairing.BluezMap", return_value=mock_map),
    ):
        orch = PairingOrchestrator(
            on_state_change=capture,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        yield orch, capture, bus, mock_map


@pytest.fixture
def not_capable_ctx():
    """Orchestrator with NOT_CAPABLE adapter."""
    capture = _StateCapture()
    le_adv_mgr = _make_le_adv_mgr_success()
    bus = _make_bus(le_adv_mgr)

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=False),
        patch("tincand.pairing.BluezMap"),
    ):
        orch = PairingOrchestrator(
            on_state_change=capture,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        yield orch, capture


@pytest.fixture
def adv_fail_ctx():
    """Orchestrator where RegisterAdvertisement immediately fires the error handler."""
    capture = _StateCapture()
    le_adv_mgr = _make_le_adv_mgr_fail()
    bus = _make_bus(le_adv_mgr)

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=True),
        patch("tincand.pairing.BluezMap"),
    ):
        orch = PairingOrchestrator(
            on_state_change=capture,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        yield orch, capture


def _map_consent_run(mock_map):
    """Drive a consent-required orchestrator; return (capture, orch) after terminal state."""
    capture = _StateCapture()
    le_adv_mgr = _make_le_adv_mgr_success()
    bus = _make_bus(le_adv_mgr)
    consent_seen = threading.Event()

    original_capture = capture

    class _CapturingWithHook:
        def __init__(self):
            self.states = original_capture.states
            self.failure_reasons = original_capture.failure_reasons

        def __call__(self, state, failure_reason=None):
            original_capture(state, failure_reason)
            if state == PairingState.MAP_CONSENT_PROMPT:
                consent_seen.set()

    hooking_capture = _CapturingWithHook()

    with (
        patch("tincand.pairing.dbus.SystemBus", return_value=bus),
        patch("tincand.pairing.dbus.Interface", side_effect=bus._make_iface),
        patch("tincand.pairing.check_adapter_le_capable", return_value=True),
        patch("tincand.pairing.BluezMap", return_value=mock_map),
    ):
        orch = PairingOrchestrator(
            on_state_change=hooking_capture,
            adapter_path=_ADAPTER_PATH,
            pair_timeout=_FAST_TIMEOUT,
            ancs_timeout=_FAST_TIMEOUT,
        )
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        consent_seen.wait(timeout=2.0)
        orch.signal_map_consent()
        original_capture.wait_terminal(timeout=2.0)

    return original_capture, orch


# ---------------------------------------------------------------------------
# §1 Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Full happy path: CAPABLE adapter -> pair -> ANCS chars -> MAP -> SUCCESS."""

    def test_start_enters_checking_adapter(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        assert PairingState.CHECKING_ADAPTER in capture.states

    def test_capable_adapter_enters_advertising(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        assert PairingState.ADVERTISING in capture.states

    def test_pair_event_enters_verifying_ancs(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        assert PairingState.VERIFYING_ANCS in capture.states

    def test_ancs_chars_found_enters_map_session(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        assert PairingState.MAP_SESSION in capture.states

    def test_map_success_enters_verifying_map(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        assert PairingState.VERIFYING_MAP in capture.states

    def test_map_success_reaches_success_state(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        assert capture.last_state == PairingState.SUCCESS

    def test_success_state_has_no_failure_reason(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        assert capture.last_failure is None


# ---------------------------------------------------------------------------
# §2 Adapter NOT_CAPABLE
# ---------------------------------------------------------------------------

class TestAdapterNotCapable:
    """Adapter NOT_CAPABLE: FAILED(adapter_not_capable) without advertising."""

    def test_not_capable_reaches_failed_state(self, not_capable_ctx):
        orch, capture = not_capable_ctx
        orch.start()
        assert capture.last_state == PairingState.FAILED

    def test_not_capable_failure_reason_is_adapter_not_capable(self, not_capable_ctx):
        orch, capture = not_capable_ctx
        orch.start()
        assert capture.last_failure == FailureReason.ADAPTER_NOT_CAPABLE

    def test_not_capable_never_enters_advertising(self, not_capable_ctx):
        orch, capture = not_capable_ctx
        orch.start()
        assert PairingState.ADVERTISING not in capture.states

    def test_not_capable_enters_checking_adapter_first(self, not_capable_ctx):
        orch, capture = not_capable_ctx
        orch.start()
        assert capture.states[0] == PairingState.CHECKING_ADAPTER


# ---------------------------------------------------------------------------
# §3 Pairing timeout
# ---------------------------------------------------------------------------

class TestPairingTimeout:
    """iOS never initiates pair within timeout -> FAILED(pair_timeout)."""

    def test_pair_timeout_reaches_failed_state(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        # No _on_device_paired call — timeout fires via _FAST_TIMEOUT
        capture.wait_terminal(timeout=2.0)
        assert capture.last_state == PairingState.FAILED

    def test_pair_timeout_failure_reason_is_pair_timeout(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        capture.wait_terminal(timeout=2.0)
        assert capture.last_failure == FailureReason.PAIR_TIMEOUT

    def test_pair_timeout_enters_waiting_for_pair(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        capture.wait_terminal(timeout=2.0)
        assert PairingState.WAITING_FOR_PAIR in capture.states


# ---------------------------------------------------------------------------
# §4 ANCS chars absent after pair
# ---------------------------------------------------------------------------

class TestAncsNotExposed:
    """Device pairs but ANCS characteristics never appear -> FAILED(ancs_not_exposed)."""

    def test_ancs_absent_reaches_failed_state(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        # No _on_ancs_chars_appeared — ancs_timeout fires via _FAST_TIMEOUT
        capture.wait_terminal(timeout=2.0)
        assert capture.last_state == PairingState.FAILED

    def test_ancs_absent_failure_reason_is_ancs_not_exposed(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        capture.wait_terminal(timeout=2.0)
        assert capture.last_failure == FailureReason.ANCS_NOT_EXPOSED

    def test_ancs_absent_enters_verifying_ancs_before_failing(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        capture.wait_terminal(timeout=2.0)
        assert PairingState.VERIFYING_ANCS in capture.states


# ---------------------------------------------------------------------------
# §5 MAP 0x43 Forbidden → MAP_CONSENT_PROMPT → user retry → SUCCESS
# ---------------------------------------------------------------------------

class TestMapConsentPromptThenSuccess:
    """MAP returns 0x43 once; user signals consent; retry succeeds -> SUCCESS."""

    def test_map_consent_prompt_state_emitted(self):
        capture, _ = _map_consent_run(_make_map_403_then_success())
        assert PairingState.MAP_CONSENT_PROMPT in capture.states

    def test_user_retry_after_consent_reaches_success(self):
        capture, _ = _map_consent_run(_make_map_403_then_success())
        assert capture.last_state == PairingState.SUCCESS

    def test_verifying_map_entered_after_consent(self):
        capture, _ = _map_consent_run(_make_map_403_then_success())
        assert PairingState.VERIFYING_MAP in capture.states


# ---------------------------------------------------------------------------
# §6 MAP 0x43 Forbidden on retry → FAILED(map_consent_denied)
# ---------------------------------------------------------------------------

class TestMapConsentDenied:
    """MAP returns 0x43 on both calls -> FAILED(map_consent_denied)."""

    def test_double_forbidden_reaches_failed_state(self):
        capture, _ = _map_consent_run(_make_map_always_403())
        assert capture.last_state == PairingState.FAILED

    def test_double_forbidden_failure_reason_is_map_consent_denied(self):
        capture, _ = _map_consent_run(_make_map_always_403())
        assert capture.last_failure == FailureReason.MAP_CONSENT_DENIED


# ---------------------------------------------------------------------------
# §7 RegisterAdvertisement async error → FAILED(advertising_failed)
# ---------------------------------------------------------------------------

class TestAdvertisingFailed:
    """RegisterAdvertisement fires error_handler -> FAILED(advertising_failed)."""

    def test_adv_error_reaches_failed_state(self, adv_fail_ctx):
        orch, capture = adv_fail_ctx
        orch.start()
        assert capture.last_state == PairingState.FAILED

    def test_adv_error_failure_reason_is_advertising_failed(self, adv_fail_ctx):
        orch, capture = adv_fail_ctx
        orch.start()
        assert capture.last_failure == FailureReason.ADVERTISING_FAILED

    def test_adv_error_never_enters_waiting_for_pair(self, adv_fail_ctx):
        orch, capture = adv_fail_ctx
        orch.start()
        assert PairingState.WAITING_FOR_PAIR not in capture.states


# ---------------------------------------------------------------------------
# §8 State sequence on happy path
# ---------------------------------------------------------------------------

class TestStateSequence:
    """Happy path emits states in the correct order."""

    def test_happy_path_state_order(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)

        expected_subsequence = [
            PairingState.CHECKING_ADAPTER,
            PairingState.ADVERTISING,
            PairingState.WAITING_FOR_PAIR,
            PairingState.VERIFYING_ANCS,
            PairingState.MAP_SESSION,
            PairingState.VERIFYING_MAP,
            PairingState.SUCCESS,
        ]
        idx = 0
        for expected in expected_subsequence:
            found = False
            while idx < len(capture.states):
                if capture.states[idx] == expected:
                    found = True
                    idx += 1
                    break
                idx += 1
            assert found, f"{expected!r} not in order in {capture.states!r}"

    def test_state_starts_with_checking_adapter(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        assert capture.states[0] == PairingState.CHECKING_ADAPTER

    def test_state_ends_with_success_on_happy_path(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        assert capture.states[-1] == PairingState.SUCCESS

    def test_on_state_change_called_for_each_state(self, capable_ctx):
        orch, capture, *_ = capable_ctx
        orch.start()
        orch._on_device_paired(_DEV_PATH)
        orch._on_ancs_chars_appeared(_DEV_PATH)
        # Must emit at least 6 distinct states on happy path
        assert len(capture.states) >= 6
