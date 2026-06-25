"""Tests: tincand/call_controller.py — CallController decision paths.
Bead: tincan-z2l9w

Coverage:
  §1 __init__ — is_call_setup_ready()=False logs WARNING
  §2 _is_hfp_iphone_modem — True/False classification branches
  §3 _short_id — path component extraction
  §4 audio timeout — FR2: scoped to _audio_timer_call_id (tincan-yeh0r)
  §5 AudioRestored — active-after-error; terminated defers to CallRemoved (tincan-yeh0r)
  §6 _discover_modem — prefers the Online HFP modem over an offline one
     (tincan-a6yeb: dual-adapter dial regression)
  §7 on_call_removed multi-call guard — FR1 (tincan-yeh0r / tincan-3e2ul)
  §8 on_call_active / on_call_held ordering — FR3 (tincan-yeh0r / tincan-3e2ul)
  §9 on_call_waiting from _on_call_added — FR4 (tincan-yeh0r / tincan-3e2ul)
  §10 per-call SignalMatch cleanup (tincan-yeh0r / tincan-3e2ul)
  §11 get_calls / swap_calls / hold_and_answer / release_and_answer
      (tincan-yeh0r / tincan-3e2ul)
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a CallController with all external deps mocked
# ---------------------------------------------------------------------------

def _make_controller(*, setup_ready: bool = True, device_addr: str = "D0:6B:78:33:46:20"):
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
        ctrl = CallController(service, contact_store, device_addr=device_addr)

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


def _add_fake_call_with_sig(ctrl, call_id: str = "call0", state: str = "incoming"):
    """Add a fake CallState AND a mock SignalMatch to _call_sigs; return (cs, mock_sig)."""
    cs = _add_fake_call(ctrl, call_id, state)
    mock_sig = MagicMock()
    ctrl._call_sigs[call_id] = mock_sig
    return cs, mock_sig


def _trigger_call_added(ctrl, path: str, props: dict) -> MagicMock:
    """Invoke _on_call_added with dbus.Interface patched; return the mock SignalMatch."""
    mock_sig = MagicMock()
    mock_iface = MagicMock()
    mock_iface.connect_to_signal.return_value = mock_sig
    with patch("dbus.Interface", return_value=mock_iface):
        ctrl._on_call_added(path, props)
    return mock_sig


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

    def test_false_when_mac_fragment_empty(self):
        # empty device_addr → mac_fragment="" → vacuous match guard kicks in
        ctrl = _make_controller(device_addr="")
        path = "/org/ofono/modem/d0_6b_78_33_46_20_iPhone"
        props = {"Type": "hfp"}
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
        ctrl._audio_timer_call_id = "call0"
        ctrl._on_audio_timeout()
        assert cs.audio_error is True

    def test_only_timed_out_call_flagged_on_timeout(self, ctrl):
        # FR2: audio_error scoped to _audio_timer_call_id; other calls untouched
        cs_a = _add_fake_call(ctrl, "call0", state="active")
        cs_b = _add_fake_call(ctrl, "call1", state="active")
        ctrl._audio_timer_call_id = "call0"
        ctrl._on_audio_timeout()
        assert cs_a.audio_error is True
        assert cs_b.audio_error is False

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

    def test_terminated_does_not_fire_call_ended(self, ctrl):
        # FR3: terminated in PropertyChanged defers teardown to CallRemoved
        _add_fake_call(ctrl, state="active")
        ctrl._on_call_property_changed("call0", "State", "terminated")
        ctrl._service.on_call_ended.assert_not_called()

    def test_non_state_property_change_ignored(self, ctrl):
        _add_fake_call(ctrl, state="active")
        ctrl._on_call_property_changed("call0", "LineIdentification", "+15550001234")
        ctrl._service.on_call_connected.assert_not_called()
        ctrl._service.on_call_ended.assert_not_called()

    def test_unknown_call_id_ignored(self, ctrl):
        ctrl._on_call_property_changed("no-such-call", "State", "active")
        ctrl._service.on_call_connected.assert_not_called()


# ---------------------------------------------------------------------------
# §6 _discover_modem — Online modem preference (tincan-a6yeb)
# ---------------------------------------------------------------------------

_IPHONE_PATH_ONLINE = "/org/ofono/modem/d0_6b_78_33_46_20_hfp_1"
_IPHONE_PATH_OFFLINE = "/org/ofono/modem/d0_6b_78_33_46_20_hfp_0"


def _make_controller_with_modems(modems: list) -> object:
    """Return a CallController whose GetModems returns *modems*.

    Mocks call_audio to prevent any real PipeWire/BlueZ interaction.
    """
    service = MagicMock()
    contact_store = MagicMock()
    contact_store.get_name.return_value = ""

    mock_bus = MagicMock()
    mock_manager = MagicMock()
    mock_manager.GetModems.return_value = modems
    mock_manager.GetCalls.return_value = []
    mock_bus.get_object.return_value = MagicMock()

    with (
        patch("tincand.call_controller.is_call_setup_ready", return_value=True),
        patch("dbus.SystemBus", return_value=mock_bus),
        patch("dbus.Interface", return_value=mock_manager),
        patch("tincand.call_controller.GLib") as mock_glib,
        patch("tincand.call_controller.call_audio"),
    ):
        mock_glib.timeout_add.return_value = 42
        from tincand.call_controller import CallController
        # device_addr must match the fixture modems' MAC so _mac_fragment
        # actually discriminates (an empty fragment matches every HFP modem).
        ctrl = CallController(service, contact_store, device_addr="D0:6B:78:33:46:20")

    ctrl._service = service
    return ctrl


class TestDiscoverModemOnlinePreference:
    """_discover_modem binds the Online HFP modem when multiple candidates exist."""

    def test_online_modem_wins_over_offline(self):
        """Online modem is bound when listed after the offline one."""
        modems = [
            (_IPHONE_PATH_OFFLINE, {"Type": "hfp", "Online": False}),
            (_IPHONE_PATH_ONLINE, {"Type": "hfp", "Online": True}),
        ]
        ctrl = _make_controller_with_modems(modems)
        assert ctrl._modem_path == _IPHONE_PATH_ONLINE

    def test_online_modem_wins_when_listed_first(self):
        """Online modem wins regardless of GetModems ordering."""
        modems = [
            (_IPHONE_PATH_ONLINE, {"Type": "hfp", "Online": True}),
            (_IPHONE_PATH_OFFLINE, {"Type": "hfp", "Online": False}),
        ]
        ctrl = _make_controller_with_modems(modems)
        assert ctrl._modem_path == _IPHONE_PATH_ONLINE

    def test_offline_modem_bound_when_no_online_available(self):
        """When all iPhone HFP modems are offline the first candidate is still bound."""
        modems = [(_IPHONE_PATH_OFFLINE, {"Type": "hfp", "Online": False})]
        ctrl = _make_controller_with_modems(modems)
        assert ctrl._modem_path == _IPHONE_PATH_OFFLINE

    def test_non_matching_modem_not_bound(self):
        """A modem whose path doesn't contain the iPhone MAC fragment is skipped."""
        android_path = "/org/ofono/modem/aa_bb_cc_dd_ee_ff_hfp"
        modems = [(android_path, {"Type": "hfp", "Online": True})]
        ctrl = _make_controller_with_modems(modems)
        assert ctrl._modem_path is None


# ---------------------------------------------------------------------------
# §7 on_call_removed multi-call guard — FR1 (tincan-yeh0r / tincan-3e2ul)
#
# _on_call_removed always emits on_call_removed(call_id).
# Audio teardown and on_call_ended only fire when _calls is empty after removal.
# ---------------------------------------------------------------------------

class TestCallRemovedMultiCallGuard:
    """FR1: on_call_removed fires per removal; on_call_ended only when last call gone."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_on_call_removed_fires_with_call_id(self, ctrl):
        _add_fake_call(ctrl, "call0")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        ctrl._service.on_call_removed.assert_called_once_with("call0")

    def test_removed_call_no_longer_in_calls_dict(self, ctrl):
        _add_fake_call(ctrl, "call0")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        assert "call0" not in ctrl._calls

    def test_on_call_ended_fires_when_last_call_removed(self, ctrl):
        _add_fake_call(ctrl, "call0")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        ctrl._service.on_call_ended.assert_called_once()

    def test_on_call_ended_not_fired_while_second_call_active(self, ctrl):
        _add_fake_call(ctrl, "call0")
        _add_fake_call(ctrl, "call1")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        ctrl._service.on_call_ended.assert_not_called()

    def test_on_call_removed_still_fires_when_second_call_active(self, ctrl):
        _add_fake_call(ctrl, "call0")
        _add_fake_call(ctrl, "call1")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        ctrl._service.on_call_removed.assert_called_once_with("call0")

    def test_on_call_removed_unknown_path_is_noop(self, ctrl):
        ctrl._on_call_removed("/org/ofono/modem/ghost")
        ctrl._service.on_call_removed.assert_called_once_with("ghost")
        ctrl._service.on_call_ended.assert_called_once()  # _calls empty → fires


# ---------------------------------------------------------------------------
# §8 on_call_active / on_call_held ordering — FR3 (tincan-yeh0r / tincan-3e2ul)
#
# active: on_call_active(call_id, number) fires BEFORE on_call_connected /
#         on_audio_restored.
# held:   on_call_held(call_id, number) fires.
# ---------------------------------------------------------------------------

class TestCallActiveHeld:
    """FR3: on_call_active fires before connected/restored; on_call_held on held."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_on_call_active_fires_on_active_state(self, ctrl):
        cs = _add_fake_call(ctrl, "call0", state="incoming")
        ctrl._on_call_property_changed("call0", "State", "active")
        ctrl._service.on_call_active.assert_called_once_with("call0", cs.number)

    def test_on_call_active_fires_before_on_call_connected(self, ctrl):
        _add_fake_call(ctrl, "call0", state="incoming")
        call_order = []
        ctrl._service.on_call_active.side_effect = lambda *a: call_order.append("active")
        ctrl._service.on_call_connected.side_effect = lambda: call_order.append("connected")
        ctrl._on_call_property_changed("call0", "State", "active")
        assert call_order == ["active", "connected"]

    def test_on_call_active_fires_before_on_audio_restored(self, ctrl):
        cs = _add_fake_call(ctrl, "call0", state="incoming")
        cs.audio_error = True
        call_order = []
        ctrl._service.on_call_active.side_effect = lambda *a: call_order.append("active")
        ctrl._service.on_audio_restored.side_effect = lambda: call_order.append("restored")
        ctrl._on_call_property_changed("call0", "State", "active")
        assert call_order == ["active", "restored"]

    def test_on_call_held_fires_on_held_state(self, ctrl):
        cs = _add_fake_call(ctrl, "call0", state="active")
        ctrl._on_call_property_changed("call0", "State", "held")
        ctrl._service.on_call_held.assert_called_once_with("call0", cs.number)

    def test_on_call_held_does_not_fire_on_call_ended(self, ctrl):
        _add_fake_call(ctrl, "call0", state="active")
        ctrl._on_call_property_changed("call0", "State", "held")
        ctrl._service.on_call_ended.assert_not_called()

    def test_on_call_active_not_fired_on_held_state(self, ctrl):
        _add_fake_call(ctrl, "call0", state="incoming")
        ctrl._on_call_property_changed("call0", "State", "held")
        ctrl._service.on_call_active.assert_not_called()


# ---------------------------------------------------------------------------
# §9 on_call_waiting from _on_call_added — FR4 (tincan-yeh0r / tincan-3e2ul)
#
# When CallAdded has State=="waiting", on_call_waiting(call_id, number, caller_name)
# fires; on_call_incoming does NOT.
# ---------------------------------------------------------------------------

class TestCallWaitingOnCallAdded:
    """FR4: waiting state fires on_call_waiting; on_call_incoming not fired."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_on_call_waiting_fires_for_waiting_state(self, ctrl):
        _trigger_call_added(
            ctrl,
            "/org/ofono/modem/call1",
            {"State": "waiting", "LineIdentification": "+15550009999"},
        )
        ctrl._service.on_call_waiting.assert_called_once()
        args = ctrl._service.on_call_waiting.call_args[0]
        assert args[0] == "call1"
        assert args[1] == "+15550009999"

    def test_on_call_incoming_not_fired_for_waiting_state(self, ctrl):
        _trigger_call_added(
            ctrl,
            "/org/ofono/modem/call1",
            {"State": "waiting", "LineIdentification": "+15550009999"},
        )
        ctrl._service.on_call_incoming.assert_not_called()

    def test_on_call_incoming_fires_for_incoming_state(self, ctrl):
        _trigger_call_added(
            ctrl,
            "/org/ofono/modem/call0",
            {"State": "incoming", "LineIdentification": "+15550001111"},
        )
        ctrl._service.on_call_incoming.assert_called_once()
        ctrl._service.on_call_waiting.assert_not_called()

    def test_waiting_call_added_to_calls_dict(self, ctrl):
        _trigger_call_added(
            ctrl,
            "/org/ofono/modem/call1",
            {"State": "waiting"},
        )
        assert "call1" in ctrl._calls
        assert ctrl._calls["call1"].state == "waiting"


# ---------------------------------------------------------------------------
# §10 Per-call SignalMatch cleanup (tincan-yeh0r / tincan-3e2ul)
#
# _call_sigs[call_id] stores the SignalMatch returned by connect_to_signal.
# On CallRemoved: sig.remove() is called and the entry is cleared.
# On modem removal: every sig.remove() is called and on_call_removed fires per call.
# ---------------------------------------------------------------------------

class TestCallSignalMatchCleanup:
    """Per-call SignalMatch stored in _call_sigs; removed on CallRemoved and modem removal."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_call_sig_removed_on_call_removed(self, ctrl):
        _, mock_sig = _add_fake_call_with_sig(ctrl, "call0")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        mock_sig.remove.assert_called_once()

    def test_call_sig_cleared_from_dict_on_call_removed(self, ctrl):
        _add_fake_call_with_sig(ctrl, "call0")
        ctrl._on_call_removed("/org/ofono/modem/call0")
        assert "call0" not in ctrl._call_sigs

    def test_call_sig_remove_not_called_when_no_sig_registered(self, ctrl):
        _add_fake_call(ctrl, "call0")  # no sig in _call_sigs
        ctrl._on_call_removed("/org/ofono/modem/call0")  # must not raise

    def test_all_call_sigs_removed_on_modem_removed(self, ctrl):
        _, mock_sig_a = _add_fake_call_with_sig(ctrl, "call0")
        _, mock_sig_b = _add_fake_call_with_sig(ctrl, "call1")
        ctrl._modem_path = "/org/ofono/modem/hfp0"
        with patch("tincand.call_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_removed("/org/ofono/modem/hfp0")
        mock_sig_a.remove.assert_called_once()
        mock_sig_b.remove.assert_called_once()

    def test_on_call_removed_fired_per_call_on_modem_removed(self, ctrl):
        _add_fake_call_with_sig(ctrl, "call0")
        _add_fake_call_with_sig(ctrl, "call1")
        ctrl._modem_path = "/org/ofono/modem/hfp0"
        with patch("tincand.call_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_removed("/org/ofono/modem/hfp0")
        removed_ids = {c[0][0] for c in ctrl._service.on_call_removed.call_args_list}
        assert removed_ids == {"call0", "call1"}

    def test_call_sigs_empty_after_modem_removed(self, ctrl):
        _add_fake_call_with_sig(ctrl, "call0")
        ctrl._modem_path = "/org/ofono/modem/hfp0"
        with patch("tincand.call_controller.GLib") as mock_glib:
            mock_glib.timeout_add.return_value = 42
            ctrl._on_modem_removed("/org/ofono/modem/hfp0")
        assert ctrl._call_sigs == {}


# ---------------------------------------------------------------------------
# §11 get_calls / swap_calls / hold_and_answer / release_and_answer
#     (tincan-yeh0r / tincan-3e2ul)
#
# get_calls() — returns list(self._calls.values()).
# swap_calls / hold_and_answer / release_and_answer — delegate to _vcm; raise
# RuntimeError when _vcm is None.
# ---------------------------------------------------------------------------

class TestMultiCallControlMethods:
    """get_calls, swap_calls, hold_and_answer, release_and_answer delegation and guard."""

    @pytest.fixture
    def ctrl(self):
        return _make_controller()

    def test_get_calls_returns_empty_list_when_no_calls(self, ctrl):
        assert ctrl.get_calls() == []

    def test_get_calls_returns_list_of_active_call_states(self, ctrl):
        cs_a = _add_fake_call(ctrl, "call0")
        cs_b = _add_fake_call(ctrl, "call1")
        result = ctrl.get_calls()
        assert sorted(r.call_id for r in result) == ["call0", "call1"]
        assert cs_a in result and cs_b in result

    def test_get_calls_returns_list_not_dict_view(self, ctrl):
        _add_fake_call(ctrl, "call0")
        result = ctrl.get_calls()
        assert isinstance(result, list)

    def test_swap_calls_delegates_to_vcm(self, ctrl):
        mock_vcm = MagicMock()
        ctrl._vcm = mock_vcm
        ctrl.swap_calls()
        mock_vcm.SwapCalls.assert_called_once_with()

    def test_swap_calls_raises_when_vcm_none(self, ctrl):
        ctrl._vcm = None
        with pytest.raises(RuntimeError):
            ctrl.swap_calls()

    def test_hold_and_answer_delegates_to_vcm(self, ctrl):
        mock_vcm = MagicMock()
        ctrl._vcm = mock_vcm
        ctrl.hold_and_answer()
        mock_vcm.HoldAndAnswer.assert_called_once_with()

    def test_hold_and_answer_raises_when_vcm_none(self, ctrl):
        ctrl._vcm = None
        with pytest.raises(RuntimeError):
            ctrl.hold_and_answer()

    def test_release_and_answer_delegates_to_vcm(self, ctrl):
        mock_vcm = MagicMock()
        ctrl._vcm = mock_vcm
        ctrl.release_and_answer()
        mock_vcm.ReleaseAndAnswer.assert_called_once_with()

    def test_release_and_answer_raises_when_vcm_none(self, ctrl):
        ctrl._vcm = None
        with pytest.raises(RuntimeError):
            ctrl.release_and_answer()
