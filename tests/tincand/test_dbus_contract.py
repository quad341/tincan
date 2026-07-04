"""Tests: D-Bus contract — daemon signals/methods match GUI subscriptions/calls.
Bead: tincan-7c5l4

Introspects tincand's exported D-Bus interface (im.tincan.Daemon and
im.tincan.Messages) and asserts that:

  1. Every signal the GUI subscribes to actually exists in TincanService.
  2. Every GUI signal-handler method has a @Slot decorator so Qt routes the
     signal correctly (missing @Slot causes silent connection failure).
  3. Every D-Bus method the GUI calls exists in TincanService.

A test FAILS when:
  - GUI subscribes to a signal TincanService does not emit.
  - A handler method is missing @Slot (would have caught the
    _on_contact_photo_received mismatch at 2026-06-06 deploy: 7/8 signals
    connected silently because @Slot(str, bytes) was absent).
  - GUI calls a D-Bus method that TincanService does not export.

No D-Bus session bus needed — all checks are pure Python introspection.
Run with: python -m pytest tests/tincand/test_dbus_contract.py -v
"""
from __future__ import annotations

import inspect
import re

import pytest

from tincan_gui.dbus_client import TincandClient
from tincand.dbus_service import IFACE_CALLS, IFACE_DAEMON, IFACE_MESSAGES, TincanService

# ---------------------------------------------------------------------------
# Daemon interface introspection
# ---------------------------------------------------------------------------

def _daemon_signals() -> dict[tuple[str, str], str]:
    """Return {(iface, signal_name): dbus_signature} from TincanService."""
    result: dict[tuple[str, str], str] = {}
    for name in dir(TincanService):
        method = getattr(TincanService, name, None)
        if method and getattr(method, "_dbus_is_signal", False):
            result[(method._dbus_interface, name)] = method._dbus_signature
    return result


def _daemon_methods() -> dict[tuple[str, str], tuple[str, str]]:
    """Return {(iface, method_name): (in_sig, out_sig)} from TincanService."""
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for name in dir(TincanService):
        method = getattr(TincanService, name, None)
        if method and getattr(method, "_dbus_is_method", False):
            result[(method._dbus_interface, name)] = (
                method._dbus_in_signature,
                method._dbus_out_signature,
            )
    return result


# ---------------------------------------------------------------------------
# GUI subscription and call inventory
# (Extracted from TincandClient._subscribe() and method call sites)
# ---------------------------------------------------------------------------

# (interface, signal_name, handler_method_name, slot_signature_fragment)
# slot_signature_fragment: the Qt type list inside "1_handler(HERE)"
_GUI_SUBSCRIPTIONS: list[tuple[str, str, str, str]] = [
    (IFACE_DAEMON,   "Connected",               "_on_connected",               "QString"),
    (IFACE_DAEMON,   "Disconnected",             "_on_disconnected",            ""),
    (IFACE_DAEMON,   "CapabilityChanged",        "_on_capability_changed",      "QString,bool"),
    (IFACE_DAEMON,   "ANCSStatusChanged",        "_on_ancs_status_changed",     "QString"),
    (IFACE_DAEMON,   "AppNotificationReceived",  "_on_app_notification_received", "QVariantMap"),
    (IFACE_MESSAGES, "MessageReceived",          "_on_message_received",        "QVariantMap"),
    (IFACE_MESSAGES, "MessageSent",             "_on_message_sent",            "QString"),
    (IFACE_MESSAGES, "ConversationUpdated",     "_on_conversation_updated",    "QVariantMap"),
    (IFACE_MESSAGES, "ContactPhotoReceived",    "_on_contact_photo_received",  "QString,QByteArray"),
    # im.tincan.Calls — HFP call signals (landed via tincan-0e6na)
    (IFACE_CALLS, "IncomingCall",   "_on_call_incoming",  "QString,QString"),
    (IFACE_CALLS, "CallConnected",  "_on_call_connected", ""),
    (IFACE_CALLS, "CallEnded",      "_on_call_ended",     ""),
    (IFACE_CALLS, "AudioError",     "_on_audio_error",    "QString"),
    (IFACE_CALLS, "AudioRestored",  "_on_audio_restored", ""),
    # multi-call signals (tincan-o9klv)
    (IFACE_CALLS, "CallActive",     "_on_call_active",    "QString,QString"),
    (IFACE_CALLS, "CallHeld",       "_on_call_held",      "QString,QString"),
    (IFACE_CALLS, "CallWaiting",    "_on_call_waiting",   "QString,QString,QString"),
    (IFACE_CALLS, "CallRemoved",    "_on_call_removed",   "QString"),
]

# (interface, method_name) — every iface.call()/asyncCall()/_dbus_call() in TincandClient
_GUI_METHOD_CALLS: list[tuple[str, str]] = [
    (IFACE_DAEMON,   "GetStatus"),
    (IFACE_DAEMON,   "GetAdapters"),       # pre-existing gap — add for parity
    (IFACE_DAEMON,   "GetHFPDevices"),     # new in PR #146
    (IFACE_DAEMON,   "GetNotificationFilter"),
    (IFACE_DAEMON,   "SetNotificationsEnabled"),
    (IFACE_DAEMON,   "SetAppFilter"),
    (IFACE_DAEMON,   "GetSeenApps"),
    (IFACE_DAEMON,   "RequestReconnect"),
    (IFACE_MESSAGES, "ListConversations"),
    (IFACE_MESSAGES, "GetMessages"),
    (IFACE_MESSAGES, "SendMessage"),
    (IFACE_MESSAGES, "MarkConversationRead"),
    (IFACE_MESSAGES, "FetchContactPhoto"),
    (IFACE_MESSAGES, "GetContacts"),
    (IFACE_CALLS, "Dial"),
    (IFACE_CALLS, "Answer"),
    (IFACE_CALLS, "Hangup"),
    (IFACE_CALLS, "SendDtmf"),
    # multi-call methods (tincan-o9klv)
    (IFACE_CALLS, "GetCalls"),
    (IFACE_CALLS, "SwapCalls"),
    (IFACE_CALLS, "HoldAndAnswer"),
    (IFACE_CALLS, "ReleaseAndAnswer"),
]

# D-Bus signature → expected @Slot argument count (used in compatibility checks)
_DBUS_SIG_ARG_COUNT = {
    "": 0,       # no arguments
    "s": 1,      # string
    "b": 1,      # bool
    "sb": 2,     # string + bool
    "ss": 2,     # two strings (e.g. IncomingCall: caller_name, caller_number)
    "a{sv}": 1,  # variant map
    "say": 2,    # string + byte array
}

# Interfaces whose signals are not yet exported by the daemon.
# §1 (test_signal_exists_in_daemon) xfails (strict=True) for entries whose iface is
# in this dict, keyed by iface with the xfail reason as the value, so the contract
# table stays complete without requiring the daemon to implement those interfaces
# first. strict=True mirrors conftest.py's _KNOWN_BROKEN_CONTRACT: once the iface
# is exported the case XPASSES and CI fails until the entry is removed here, so a
# landed interface can't rot silently (see tincan-73eki).
_KNOWN_PENDING_DAEMON_IFACES: dict[str, str] = {
    # im.tincan.Calls xfail removed: the daemon now exports all 9 Calls signals
    # (landed via tincan-0e6na) so the contract cases pass for real (tincan-73eki).
}


# ---------------------------------------------------------------------------
# Source-inspection helpers
# ---------------------------------------------------------------------------

def _has_slot_decorator(cls: type, method_name: str) -> bool:
    """Return True if the named method has a @Slot(...) decorator in its source.

    Missing @Slot causes Qt's bus.connect() to silently return False: the signal
    arrives on the bus but is never dispatched to the handler.
    """
    method = getattr(cls, method_name, None)
    if method is None:
        return False
    try:
        src = inspect.getsource(method)
    except (OSError, TypeError):
        return False

    decorator_lines: list[str] = []
    for line in src.split("\n"):
        stripped = line.strip()
        if re.match(r"def\s+", stripped):
            break
        decorator_lines.append(stripped)

    return any(re.match(r"@\s*Slot\s*\(", line) for line in decorator_lines)


def _slot_arg_count(cls: type, method_name: str) -> int | None:
    """Return the number of type args in the @Slot decorator, or None if absent."""
    method = getattr(cls, method_name, None)
    if method is None:
        return None
    try:
        src = inspect.getsource(method)
    except (OSError, TypeError):
        return None

    for line in src.split("\n"):
        stripped = line.strip()
        if re.match(r"def\s+", stripped):
            break
        m = re.match(r"@\s*Slot\s*\((.*)\)\s*$", stripped)
        if m:
            args_str = m.group(1).strip()
            if not args_str:
                return 0
            # Count comma-separated arguments, respecting quoted strings crudely.
            return len([a for a in args_str.split(",") if a.strip()])
    return None


# ---------------------------------------------------------------------------
# §1 Every GUI signal subscription names a real daemon signal
# ---------------------------------------------------------------------------

class TestGuiSubscriptionsMatchDaemonSignals:
    """Every (iface, signal_name) in GUI subscriptions must exist in TincanService."""

    @pytest.mark.parametrize(
        "iface,signal,handler,slot_types",
        _GUI_SUBSCRIPTIONS,
        ids=[f"{iface.split('.')[-1]}.{sig}" for iface, sig, *_ in _GUI_SUBSCRIPTIONS],
    )
    def test_signal_exists_in_daemon(self, request, iface, signal, handler, slot_types):
        if iface in _KNOWN_PENDING_DAEMON_IFACES:
            request.node.add_marker(
                pytest.mark.xfail(
                    strict=True, reason=_KNOWN_PENDING_DAEMON_IFACES[iface]
                )
            )
        signals = _daemon_signals()
        assert (iface, signal) in signals, (
            f"GUI subscribes to {iface}.{signal} but TincanService has no "
            f"@dbus.service.signal with that interface and name.\n"
            f"Available signals: {sorted(signals.keys())}"
        )


# ---------------------------------------------------------------------------
# §2 Every signal handler has @Slot so Qt can route the signal
# ---------------------------------------------------------------------------

class TestSignalHandlersHaveSlotDecorator:
    """Every GUI handler for a subscribed signal must have @Slot.

    Missing @Slot causes bus.connect() to silently return False and the signal
    to never reach the handler — the bug that caused _on_contact_photo_received
    to be silently disconnected at the 2026-06-06 deploy.
    """

    @pytest.mark.parametrize(
        "iface,signal,handler,slot_types",
        _GUI_SUBSCRIPTIONS,
        ids=[handler for _, _, handler, _ in _GUI_SUBSCRIPTIONS],
    )
    def test_handler_has_slot_decorator(self, iface, signal, handler, slot_types):
        assert _has_slot_decorator(TincandClient, handler), (
            f"Handler TincandClient.{handler} (for {iface}.{signal}) "
            f"has no @Slot decorator.\n"
            f"Qt will silently fail to route the signal to the handler, "
            f"making the subscription a no-op at runtime."
        )

    @pytest.mark.parametrize(
        "iface,signal,handler,slot_types",
        _GUI_SUBSCRIPTIONS,
        ids=[handler for _, _, handler, _ in _GUI_SUBSCRIPTIONS],
    )
    def test_handler_slot_arg_count_matches_signal_signature(
        self, iface, signal, handler, slot_types
    ):
        """@Slot argument count must match the D-Bus signal's argument count."""
        signals = _daemon_signals()
        if (iface, signal) not in signals:
            pytest.skip(f"{iface}.{signal} not in daemon (caught by §1)")

        dbus_sig = signals[(iface, signal)]
        expected_args = _DBUS_SIG_ARG_COUNT.get(dbus_sig)
        if expected_args is None:
            pytest.skip(f"Unknown arg count for dbus signature {dbus_sig!r}")

        actual_args = _slot_arg_count(TincandClient, handler)
        if actual_args is None:
            pytest.skip(f"No @Slot found on {handler} (caught by §2.a)")

        assert actual_args == expected_args, (
            f"TincandClient.{handler}: @Slot has {actual_args} type arg(s) "
            f"but {iface}.{signal} has dbus signature {dbus_sig!r} "
            f"({expected_args} arg(s)).\n"
            f"A mismatched arg count causes Qt to drop or misroute the signal."
        )


# ---------------------------------------------------------------------------
# §3 Every GUI method call names a real daemon method
# ---------------------------------------------------------------------------

class TestGuiMethodCallsMatchDaemonMethods:
    """Every (iface, method_name) called by TincandClient must exist in TincanService."""

    @pytest.mark.parametrize(
        "iface,method",
        _GUI_METHOD_CALLS,
        ids=[f"{iface.split('.')[-1]}.{m}" for iface, m in _GUI_METHOD_CALLS],
    )
    def test_called_method_exists_in_daemon(self, iface, method):
        methods = _daemon_methods()
        assert (iface, method) in methods, (
            f"GUI calls {iface}.{method} but TincanService has no "
            f"@dbus.service.method with that interface and name.\n"
            f"The call will silently return an error or do nothing at runtime.\n"
            f"Available methods: {sorted(methods.keys())}"
        )


# ---------------------------------------------------------------------------
# §4 No orphan daemon signals — every daemon signal is subscribed by GUI
# ---------------------------------------------------------------------------

class TestNoDaemonSignalsOrphaned:
    """Every daemon signal should be subscribed to by TincandClient.

    An unsubscribed daemon signal means the GUI misses user-visible updates.
    This is a WARNING class of test — it may fail legitimately when the daemon
    adds a new signal that the GUI hasn't wired up yet.
    """

    def test_all_daemon_signals_are_subscribed(self):
        signals = _daemon_signals()
        subscribed = {(iface, sig) for iface, sig, *_ in _GUI_SUBSCRIPTIONS}

        # Exclude org.freedesktop.DBus.* signals (infrastructure, not app signals)
        app_signals = {
            k: v for k, v in signals.items()
            if not k[0].startswith("org.freedesktop")
        }

        unsubscribed = set(app_signals.keys()) - subscribed
        assert not unsubscribed, (
            "Daemon signals not subscribed by TincandClient — GUI will miss "
            "these updates:\n"
            + "\n".join(f"  {iface}.{name}({sig})"
                        for (iface, name), sig in sorted(
                            (k, app_signals[k]) for k in unsubscribed
                        ))
        )


# ---------------------------------------------------------------------------
# §5 Subscription count sanity
# ---------------------------------------------------------------------------

class TestSubscriptionCountSanity:
    """TincandClient._subscribe() must register the expected number of signals."""

    def test_subscription_count_matches_inventory(self):
        """The static _GUI_SUBSCRIPTIONS inventory must cover all subscriptions.

        This test fails if someone adds a subscription to _subscribe() without
        updating the _GUI_SUBSCRIPTIONS table (or vice versa), preventing the
        §1-§4 tests from silently missing a subscription.
        """
        from unittest.mock import MagicMock, patch

        recorded: list[tuple[str, str]] = []

        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = True

        def _record(bus_name, obj, iface, signal, *rest):
            recorded.append((iface, signal))
            return True

        mock_bus.connect.side_effect = _record

        with patch("tincan_gui.dbus_client.QDBusConnection") as mock_qdb:
            mock_qdb.sessionBus.return_value = mock_bus
            TincandClient()

        actual = set(recorded)
        expected = {(iface, sig) for iface, sig, *_ in _GUI_SUBSCRIPTIONS}

        missing_from_inventory = actual - expected
        extra_in_inventory = expected - actual

        assert not missing_from_inventory, (
            "These subscriptions are registered in _subscribe() but missing from "
            "_GUI_SUBSCRIPTIONS (add them to ensure §1-§4 cover them):\n"
            + "\n".join(f"  {iface}.{sig}" for iface, sig in sorted(missing_from_inventory))
        )
        assert not extra_in_inventory, (
            "These entries are in _GUI_SUBSCRIPTIONS but not in _subscribe() "
            "(remove the stale entries):\n"
            + "\n".join(f"  {iface}.{sig}" for iface, sig in sorted(extra_in_inventory))
        )
