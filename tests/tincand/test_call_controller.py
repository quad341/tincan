"""Tests: tincand/call_controller.py — CallController decision paths.
Bead: tincan-z2l9w, tincan-aggkh

Coverage:
  §1 __init__ — is_call_setup_ready()=False logs WARNING
  §2 _is_hfp_iphone_modem — True/False classification branches
  §3 _short_id — path component extraction
  §4 audio timeout — _on_audio_timeout sets audio_error=True and fires on_audio_error
  §5 AudioRestored — active-after-error path fires on_audio_restored;
     normal active fires on_call_connected
  §10 Adapter-aware modem selection — 6 NF1 scenarios (tincan-aggkh / tincan-3vc85):
      cold-start-both-offline, preferred-online, only-fallback-online, re-bind,
      no-adapter-configured, subscription-cleanup
  §11 T3/T4/FR6 additions (tincan-8gpmz):
      §D/§E via lambda capture, §I idempotent cancel, §J hci10 disambiguation, FR6 SetProperty
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a CallController with all external deps mocked
# ---------------------------------------------------------------------------

def _make_controller(*, setup_ready: bool = True):
    """Return a CallController with dbus and GLib fully mocked.

    Patches:
      - tincand.hfp_capability.is_call_setup_ready → ``setup_ready``
      - dbus.SystemBus, dbus.Interface, dbus.service.* → MagicMock
      - gi.repository.GLib → MagicMock (no real GLib main loop)
    """
    service = MagicMock()
    contact_store = MagicMock()
    contact_store.get_name.return_value = ""

    mock_bus = MagicMock()
    mock_manager = MagicMock()
    mock_manager.GetModems.return_value = []
    mock_bus.get_object.return_value = MagicMock()

    with (
        patch("tincand.call_controller.is_call_setup_ready", return_value=setup_ready),
        patch("dbus.SystemBus", return_value=mock_bus),
        patch("dbus.Interface", return_value=mock_manager),
        patch("tincand.call_controller.GLib") as mock_glib,
    ):
        mock_glib.timeout_add.return_value = 42
        from tincand.call_controller import CallController
        ctrl = CallController(service, contact_store)

    ctrl._service = service
    return ctrl


def _add_fake_call(ctrl, call_id: str = "call0", state: str = "incoming") -> object:
    """Inject a fake CallState into the controller's _calls dict."""
    from tincand.call_controller import CallState
    cs = CallState(
        call_id=call_id,
        ofono_path=f"/org/ofono/modem/{call_id}",
        state=state,
        number="+15550001234",
        direction="inbound",
    )
    ctrl._calls[call_id] = cs
    return cs


# ---------------------------------------------------------------------------
# §1 __init__ — is_call_setup_ready()=False logs WARNING
# ---------------------------------------------------------------------------

class TestInitCallSetupReadyWarning:
    """CallController logs a WARNING when call_setup_ready is False at construction."""

    def test_warning_logged_when_setup_not_ready(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_controller"):
            _make_controller(setup_ready=False)
        assert any("call_setup_ready is False" in r.message for r in caplog.records)

    def test_no_warning_when_setup_ready(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_controller"):
            _make_controller(setup_ready=True)
        assert not any("call_setup_ready is False" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# §2 _is_hfp_iphone_modem — classification branches
# ---------------------------------------------------------------------------

class TestIsHfpIphoneModem:
    """_is_hfp_iphone_modem returns True only for HFP type with iPhone MAC fragment."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_true_when_hfp_type_and_mac_fragment_present(self, ctrl):
        path = "/org/ofono/modem/d0_6b_78_33_46_20_iPhone"
        props = {"Type": "hfp"}
        assert ctrl._is_hfp_iphone_modem(path, props) is True

    def test_false_when_hfp_type_but_mac_fragment_absent(self, ctrl):
        path = "/org/ofono/modem/aa_bb_cc_dd_ee_ff_Android"
        props = {"Type": "hfp"}
        assert ctrl._is_hfp_iphone_modem(path, props) is False

    def test_false_when_wrong_type_even_with_mac_fragment(self, ctrl):
        path = "/org/ofono/modem/d0_6b_78_33_46_20_iPhone"
        props = {"Type": "wwan"}
        assert ctrl._is_hfp_iphone_modem(path, props) is False

    def test_false_when_type_missing(self, ctrl):
        path = "/org/ofono/modem/d0_6b_78_33_46_20_iPhone"
        props = {}
        assert ctrl._is_hfp_iphone_modem(path, props) is False

    def test_false_when_type_uppercase_hfp(self, ctrl):
        # Type comparison is lowercase-normalised
        path = "/org/ofono/modem/d0_6b_78_33_46_20_iPhone"
        props = {"Type": "HFP"}
        assert ctrl._is_hfp_iphone_modem(path, props) is False


# ---------------------------------------------------------------------------
# §3 _short_id — path component extraction
# ---------------------------------------------------------------------------

class TestShortId:
    """_short_id strips leading path components and trailing slashes."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_returns_last_component(self, ctrl):
        assert ctrl._short_id("/org/ofono/modem/call0") == "call0"

    def test_strips_trailing_slash(self, ctrl):
        assert ctrl._short_id("/org/ofono/modem/call0/") == "call0"

    def test_bare_name_unchanged(self, ctrl):
        assert ctrl._short_id("call0") == "call0"

    def test_two_level_path(self, ctrl):
        assert ctrl._short_id("/modem/vcall1") == "vcall1"


# ---------------------------------------------------------------------------
# §4 audio timeout — fires AudioError, marks calls audio_error=True
# ---------------------------------------------------------------------------

class TestAudioTimeout:
    """_on_audio_timeout emits on_audio_error('sco_timeout') and marks call.audio_error."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_on_audio_error_called_with_sco_timeout(self, ctrl):
        _add_fake_call(ctrl, "call0", state="active")
        ctrl._on_audio_timeout()
        ctrl._service.on_audio_error.assert_called_once_with("sco_timeout")

    def test_call_audio_error_flag_set_true(self, ctrl):
        cs = _add_fake_call(ctrl, "call0", state="active")
        assert cs.audio_error is False
        ctrl._on_audio_timeout()
        assert cs.audio_error is True

    def test_all_calls_flagged_on_timeout(self, ctrl):
        cs_a = _add_fake_call(ctrl, "call0", state="active")
        cs_b = _add_fake_call(ctrl, "call1", state="active")
        ctrl._on_audio_timeout()
        assert cs_a.audio_error is True
        assert cs_b.audio_error is True

    def test_timer_id_cleared_after_timeout(self, ctrl):
        ctrl._audio_timer_id = 42
        _add_fake_call(ctrl)
        ctrl._on_audio_timeout()
        assert ctrl._audio_timer_id is None

    def test_returns_false_so_glib_removes_timer(self, ctrl):
        _add_fake_call(ctrl)
        result = ctrl._on_audio_timeout()
        assert result is False


# ---------------------------------------------------------------------------
# §5 AudioRestored — active-after-error vs normal active
# ---------------------------------------------------------------------------

class TestCallPropertyChangedActive:
    """_on_call_property_changed: active-after-error fires on_audio_restored;
    normal active fires on_call_connected."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_active_after_error_fires_audio_restored(self, ctrl):
        cs = _add_fake_call(ctrl, state="incoming")
        cs.audio_error = True
        ctrl._on_call_property_changed("call0", "State", "active")
        ctrl._service.on_audio_restored.assert_called_once()
        ctrl._service.on_call_connected.assert_not_called()

    def test_active_after_error_clears_audio_error_flag(self, ctrl):
        cs = _add_fake_call(ctrl, state="incoming")
        cs.audio_error = True
        ctrl._on_call_property_changed("call0", "State", "active")
        assert cs.audio_error is False

    def test_normal_active_fires_call_connected(self, ctrl):
        cs = _add_fake_call(ctrl, state="incoming")
        cs.audio_error = False
        ctrl._on_call_property_changed("call0", "State", "active")
        ctrl._service.on_call_connected.assert_called_once()
        ctrl._service.on_audio_restored.assert_not_called()

    def test_terminated_fires_call_ended(self, ctrl):
        _add_fake_call(ctrl, state="active")
        ctrl._on_call_property_changed("call0", "State", "terminated")
        ctrl._service.on_call_ended.assert_called_once()

    def test_non_state_property_change_ignored(self, ctrl):
        _add_fake_call(ctrl, state="active")
        ctrl._on_call_property_changed("call0", "LineIdentification", "+15550001234")
        ctrl._service.on_call_connected.assert_not_called()
        ctrl._service.on_call_ended.assert_not_called()

    def test_unknown_call_id_ignored(self, ctrl):
        ctrl._on_call_property_changed("no-such-call", "State", "active")
        ctrl._service.on_call_connected.assert_not_called()


# ---------------------------------------------------------------------------
# §10 Adapter-aware modem selection — NF1 scenarios (tincan-aggkh)
#
# Tests cover FR1–FR5 + NF1 from docs/plans/hfp-modem-selection.md.
# Implementation: feat/hfp-adapter-aware-modem-selection-3vc85 (tincan-3vc85).
# Tests fail until that branch merges; pass on the combined branch.
# ---------------------------------------------------------------------------

_PREFERRED_PATH = "/hfp/org/bluez/hci1/dev_d0_6b_78_33_46_20"  # hci1 = preferred
_FALLBACK_PATH  = "/hfp/org/bluez/hci0/dev_d0_6b_78_33_46_20"  # hci0 = non-preferred
_HFP_ONLINE  = {"Type": "hfp", "Online": True}
_HFP_OFFLINE = {"Type": "hfp", "Online": False}


def _make_adapter_ctrl(modems, *, adapter_hci="hci1"):
    """Build a CallController with adapter_hci and the given initial modem list.

    Returns (ctrl, mock_mgr).  mock_mgr.GetModems can be updated before
    triggering _on_modem_added / _discover_modem in subsequent calls.
    """
    service = MagicMock()
    contact_store = MagicMock()
    contact_store.get_name.return_value = ""
    mock_bus = MagicMock()
    mock_mgr = MagicMock()
    mock_mgr.GetModems.return_value = modems
    mock_mgr.GetCalls.return_value = []
    mock_bus.get_object.return_value = MagicMock()

    with (
        patch("tincand.call_controller.is_call_setup_ready", return_value=True),
        patch("dbus.SystemBus", return_value=mock_bus),
        patch("dbus.Interface", return_value=mock_mgr),
        patch("tincand.call_controller.GLib") as mock_glib,
        patch("tincand.call_controller.call_audio"),
    ):
        mock_glib.timeout_add.return_value = 42
        from tincand.call_controller import CallController
        ctrl = CallController(
            service,
            contact_store,
            device_addr="D0:6B:78:33:46:20",
            adapter_hci=adapter_hci,
        )

    ctrl._service = service
    ctrl._system_bus = mock_bus
    ctrl._manager = mock_mgr
    return ctrl, mock_mgr


class TestColdStartBothOffline:
    """Scenario 1: cold start — both hci0 and hci1 Offline (tincan-aggkh).

    Preferred modem (hci1) exists but is Offline → controller defers bind,
    subscribes to PropertyChanged, and binds within 1s of Online=True.
    hci0 is NOT bound during the wait.
    """

    def test_defers_bind_when_preferred_offline(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._modem_path is None
        assert ctrl._pending_online_path == _PREFERRED_PATH

    def test_does_not_bind_non_preferred_while_deferring(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._modem_path != _FALLBACK_PATH

    def test_binds_preferred_after_online_signal(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        with (
            patch("dbus.Interface", return_value=mock_mgr),
            patch("tincand.call_controller.call_audio"),
        ):
            ctrl._on_pending_modem_property_changed(_PREFERRED_PATH, "Online", True)
        assert ctrl._modem_path == _PREFERRED_PATH

    def test_pending_cleared_after_bind_on_online_signal(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        with (
            patch("dbus.Interface", return_value=mock_mgr),
            patch("tincand.call_controller.call_audio"),
        ):
            ctrl._on_pending_modem_property_changed(_PREFERRED_PATH, "Online", True)
        assert ctrl._pending_online_path is None
        assert ctrl._pending_subscription is None

    def test_deferral_emits_gap1_info_log(self, caplog):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        with caplog.at_level(logging.INFO, logger="tincand.call_controller"):
            _make_adapter_ctrl(modems)
        assert any("deferring bind" in r.message for r in caplog.records)

    def test_non_preferred_online_signal_ignored(self):
        """PropertyChanged from hci0 path does NOT trigger bind while hci1 is pending."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        ctrl._on_pending_modem_property_changed(_FALLBACK_PATH, "Online", True)
        assert ctrl._modem_path is None

    def test_lambda_callback_triggers_preferred_bind(self):
        """T3/§D: PropertyChanged lambda from connect_to_signal fires bind correctly."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        callback = next(
            c[0][1]
            for c in mock_mgr.connect_to_signal.call_args_list
            if c[0][0] == "PropertyChanged"
        )
        with (
            patch("dbus.Interface", return_value=mock_mgr),
            patch("tincand.call_controller.call_audio"),
        ):
            callback("Online", True)
        assert ctrl._modem_path == _PREFERRED_PATH

    def test_lambda_callback_with_superseded_path_is_ignored(self):
        """T3/§E: lambda captured for old path is a no-op after subscription superseded."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        callback = next(
            c[0][1]
            for c in mock_mgr.connect_to_signal.call_args_list
            if c[0][0] == "PropertyChanged"
        )
        # Simulate subscription superseded: pending path changed to something else
        ctrl._pending_online_path = _FALLBACK_PATH
        # Fire the old lambda (closure still captures _PREFERRED_PATH)
        callback("Online", True)
        # Stale-path guard: _PREFERRED_PATH != _FALLBACK_PATH → no bind
        assert ctrl._modem_path is None


class TestPreferredOnlineAtDiscovery:
    """Scenario 2: preferred hci1 Online at discovery time (tincan-aggkh).

    FR1/FR5: controller binds hci1 immediately with an INFO log.
    """

    def test_binds_preferred_immediately(self):
        modems = [(_PREFERRED_PATH, _HFP_ONLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._modem_path == _PREFERRED_PATH

    def test_no_pending_subscription_when_preferred_online(self):
        modems = [(_PREFERRED_PATH, _HFP_ONLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._pending_online_path is None
        assert ctrl._pending_subscription is None

    def test_preferred_bind_emits_info_not_warning(self, caplog):
        modems = [(_PREFERRED_PATH, _HFP_ONLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        with caplog.at_level(logging.INFO, logger="tincand.call_controller"):
            _make_adapter_ctrl(modems)
        assert any(
            "preferred adapter" in r.message and r.levelno == logging.INFO
            for r in caplog.records
        )


class TestOnlyNonPreferredOnline:
    """Scenario 3: only non-preferred hci0 Online — fallback bind with WARN (tincan-aggkh).

    FR4/FR5: no preferred modem found → binds hci0 with a WARNING log.
    """

    def test_binds_fallback_when_no_preferred_modem(self):
        modems = [(_FALLBACK_PATH, _HFP_ONLINE)]  # hci1 absent
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._modem_path == _FALLBACK_PATH

    def test_fallback_bind_emits_warning_log(self, caplog):
        modems = [(_FALLBACK_PATH, _HFP_ONLINE)]
        with caplog.at_level(logging.WARNING, logger="tincand.call_controller"):
            _make_adapter_ctrl(modems)
        assert any(
            ("not available" in r.message or "fallback" in r.message)
            and r.levelno == logging.WARNING
            for r in caplog.records
        )


class TestRebindWhenPreferredComesOnline:
    """Scenario 4: controller bound to hci0; preferred hci1 added Online → re-bind (tincan-aggkh).

    FR3/FR5: _on_modem_added triggers _discover_modem; hci1 wins rank 0;
    _bind_modem emits Gap-2 INFO "re-binding to preferred adapter".
    """

    def test_rebinds_to_preferred_after_modem_added(self):
        ctrl, mock_mgr = _make_adapter_ctrl([(_FALLBACK_PATH, _HFP_ONLINE)])
        assert ctrl._modem_path == _FALLBACK_PATH

        mock_mgr.GetModems.return_value = [
            (_PREFERRED_PATH, _HFP_ONLINE),
            (_FALLBACK_PATH,  _HFP_ONLINE),
        ]
        mock_mgr.GetCalls.return_value = []

        with (
            patch("dbus.Interface", return_value=mock_mgr),
            patch("tincand.call_controller.call_audio"),
            patch("tincand.call_controller.GLib") as mock_glib,
        ):
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_added(_PREFERRED_PATH, _HFP_ONLINE)

        assert ctrl._modem_path == _PREFERRED_PATH

    def test_rebind_emits_gap2_info_log(self, caplog):
        ctrl, mock_mgr = _make_adapter_ctrl([(_FALLBACK_PATH, _HFP_ONLINE)])

        mock_mgr.GetModems.return_value = [
            (_PREFERRED_PATH, _HFP_ONLINE),
            (_FALLBACK_PATH,  _HFP_ONLINE),
        ]
        mock_mgr.GetCalls.return_value = []

        with caplog.at_level(logging.INFO, logger="tincand.call_controller"):
            with (
                patch("dbus.Interface", return_value=mock_mgr),
                patch("tincand.call_controller.call_audio"),
                patch("tincand.call_controller.GLib") as mock_glib,
            ):
                mock_glib.timeout_add.return_value = 42
                ctrl._on_modem_added(_PREFERRED_PATH, _HFP_ONLINE)

        assert any("re-binding" in r.message for r in caplog.records)


class TestNoAdapterConfigured:
    """Scenario 5: adapter_hci="" — falls through to Online-first sort, no regression (tincan-aggkh).

    NF2: with empty adapter_hci all candidates rank equally; Online still beats
    Offline; no deferred-bind path is triggered.
    """

    def test_online_modem_wins_when_no_adapter_hci(self):
        modems = [
            (_PREFERRED_PATH, _HFP_ONLINE),
            (_FALLBACK_PATH,  _HFP_OFFLINE),
        ]
        ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="")
        assert ctrl._modem_path == _PREFERRED_PATH

    def test_online_beats_offline_regardless_of_list_order(self):
        modems = [
            (_FALLBACK_PATH,  _HFP_OFFLINE),
            (_PREFERRED_PATH, _HFP_ONLINE),
        ]
        ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="")
        assert ctrl._modem_path == _PREFERRED_PATH

    def test_no_deferral_when_no_adapter_hci(self):
        """Empty adapter_hci never triggers deferred-bind; any modem is bound immediately."""
        modems = [
            (_PREFERRED_PATH, _HFP_OFFLINE),
            (_FALLBACK_PATH,  _HFP_OFFLINE),
        ]
        ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="")
        assert ctrl._pending_online_path is None
        assert ctrl._modem_path is not None


class TestSubscriptionCleanup:
    """Scenario 6: no stale PropertyChanged subscriptions after bind or modem-removed (tincan-aggkh).

    NF4: every subscription is cancelled on bind, modem-removed, or re-bind.
    """

    def test_subscription_set_during_deferred_bind(self):
        """Baseline: subscription IS created when preferred modem is Offline."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._pending_subscription is not None

    def test_no_pending_subscription_after_bind_on_online_signal(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        with (
            patch("dbus.Interface", return_value=mock_mgr),
            patch("tincand.call_controller.call_audio"),
        ):
            ctrl._on_pending_modem_property_changed(_PREFERRED_PATH, "Online", True)
        assert ctrl._pending_subscription is None
        assert ctrl._pending_online_path is None

    def test_subscription_cancelled_when_pending_modem_removed(self):
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._pending_online_path == _PREFERRED_PATH

        with patch("tincand.call_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_removed(_PREFERRED_PATH)

        assert ctrl._pending_online_path is None
        assert ctrl._pending_subscription is None

    def test_remove_called_on_subscription_object(self):
        """_pending_subscription.remove() is invoked when the watched modem is removed."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        mock_sub = ctrl._pending_subscription

        with patch("tincand.call_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_removed(_PREFERRED_PATH)

        mock_sub.remove.assert_called_once()

    def test_no_subscription_after_immediate_preferred_bind(self):
        """No subscription set when preferred modem is already Online at discovery."""
        modems = [(_PREFERRED_PATH, _HFP_ONLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        assert ctrl._pending_subscription is None

    def test_cancel_idempotent_on_double_call(self):
        """§I: _cancel_pending_subscription does not raise when called twice consecutively."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems)
        ctrl._cancel_pending_subscription()  # first: clears both fields
        ctrl._cancel_pending_subscription()  # second: already None, must not raise
        assert ctrl._pending_subscription is None
        assert ctrl._pending_online_path is None


# ---------------------------------------------------------------------------
# §11 Adapter-aware modem selection — T4 + FR6 additions (tincan-8gpmz)
#
# §J: hci10/hci1 disambiguation — preference check uses /{hci}/ (slashed)
#     so /hci10/ does not match adapter_hci="hci1". (tincan-t9met R5)
# FR6: proactive SetProperty Powered=true on preferred Offline modem.
#     (tincan-odlh9)
# ---------------------------------------------------------------------------

_HCI10_PATH = "/hfp/org/bluez/hci10/dev_d0_6b_78_33_46_20"


class TestHciDisambiguation:
    """§J: adapter_hci='hci1' does NOT match /hci10/ paths (tincan-8gpmz / tincan-t9met R5).

    Three cases distinguish correct (slashed) from wrong (bare substring) behaviour:
    (a) hci10 Online logged as fallback WARNING — not preferred INFO;
    (b) hci10 Offline triggers immediate fallback bind, not deferred subscription;
    (c) hci1 wins preference over hci10 when both are present.
    """

    def test_hci10_online_logged_as_fallback_not_preferred(self, caplog):
        """hci10 Online → fallback WARNING; bare-substring impl would emit INFO instead."""
        modems = [
            (_HCI10_PATH,    _HFP_ONLINE),
            (_FALLBACK_PATH, _HFP_OFFLINE),
        ]
        with caplog.at_level(logging.WARNING, logger="tincand.call_controller"):
            ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="hci1")
        assert ctrl._modem_path == _HCI10_PATH
        assert any(
            ("fallback" in r.message or "not available" in r.message)
            and r.levelno == logging.WARNING
            for r in caplog.records
        )

    def test_hci10_offline_no_deferred_bind_subscription(self):
        """hci10 Offline → immediate fallback bind; bare-substring impl would defer."""
        modems = [(_HCI10_PATH, _HFP_OFFLINE)]
        ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="hci1")
        assert ctrl._modem_path == _HCI10_PATH
        assert ctrl._pending_online_path is None

    def test_hci1_preferred_over_hci10_when_both_online(self):
        """hci1 wins rank=0; hci10 (non-preferred) ranks 2 — hci1 binds."""
        modems = [
            (_HCI10_PATH,    _HFP_ONLINE),
            (_PREFERRED_PATH, _HFP_ONLINE),
        ]
        ctrl, _ = _make_adapter_ctrl(modems, adapter_hci="hci1")
        assert ctrl._modem_path == _PREFERRED_PATH


class TestFR6SetPropertyPowered:
    """FR6: proactive SetProperty Powered=true on preferred Offline modem (tincan-8gpmz / tincan-odlh9).

    When rank=1 (preferred modem Offline), _subscribe_modem_online calls
    SetProperty("Powered", dbus.Boolean(True)) on the modem proxy before the
    PropertyChanged subscription. Errors from SetProperty are suppressed; the
    subscription is created regardless.
    """

    def test_set_property_powered_called_at_rank1(self):
        """SetProperty('Powered') invoked on modem proxy when rank=1 (preferred Offline)."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        _, mock_mgr = _make_adapter_ctrl(modems)
        powered_calls = [
            c for c in mock_mgr.SetProperty.call_args_list
            if c[0][0] == "Powered"
        ]
        assert len(powered_calls) == 1

    def test_set_property_not_called_when_preferred_already_online(self):
        """SetProperty('Powered') NOT called when preferred modem is already Online (rank=0)."""
        modems = [(_PREFERRED_PATH, _HFP_ONLINE)]
        _, mock_mgr = _make_adapter_ctrl(modems)
        powered_calls = [
            c for c in mock_mgr.SetProperty.call_args_list
            if c[0][0] == "Powered"
        ]
        assert len(powered_calls) == 0

    def test_set_property_not_called_without_adapter_hci(self):
        """With adapter_hci='', no deferred-bind path — SetProperty('Powered') not called."""
        modems = [(_PREFERRED_PATH, _HFP_OFFLINE), (_FALLBACK_PATH, _HFP_OFFLINE)]
        _, mock_mgr = _make_adapter_ctrl(modems, adapter_hci="")
        powered_calls = [
            c for c in mock_mgr.SetProperty.call_args_list
            if c[0][0] == "Powered"
        ]
        assert len(powered_calls) == 0

    def test_set_property_error_suppressed_subscription_still_created(self):
        """SetProperty exception does not propagate; _pending_subscription is still set."""
        modems = [(_PREFERRED_PATH, _HFP_ONLINE)]  # bind immediately, no pending sub yet
        ctrl, mock_mgr = _make_adapter_ctrl(modems)
        mock_mgr.SetProperty.side_effect = Exception("org.ofono.Error.InProgress")
        with patch("dbus.Interface", return_value=mock_mgr):
            ctrl._subscribe_modem_online(_PREFERRED_PATH)
        assert ctrl._pending_subscription is not None
        assert ctrl._pending_online_path == _PREFERRED_PATH
