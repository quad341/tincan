"""Tests: tincand/call_controller.py — CallController decision paths.
Bead: tincan-z2l9w, tincan-hzcfj.2

Coverage:
  §1 __init__ — is_call_setup_ready()=False logs WARNING
  §2 _is_hfp_iphone_modem — True/False classification branches
  §3 _short_id — path component extraction
  §4 audio timeout — _on_audio_timeout sets audio_error=True and fires on_audio_error
  §5 AudioRestored — active-after-error path fires on_audio_restored;
     normal active fires on_call_connected
  §6 _discover_modem — prefers the Online HFP modem over an offline one
     (tincan-a6yeb: dual-adapter dial regression)
  §7 adapter_hci — constructor stores kwarg as self._adapter_hci (tincan-hzcfj.2)
  §8 _bind_modem propagation — adapter_hci forwarded to verify_dongle_adapter (tincan-hzcfj.2)
  §9 __main__ hciN extraction — regex derives hciN from adapter_path (tincan-hzcfj.2)
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a CallController with all external deps mocked
# ---------------------------------------------------------------------------

def _make_controller(*, setup_ready: bool = True, device_addr: str = "D0:6B:78:33:46:20", adapter_hci: str = ""):
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
        ctrl = CallController(service, contact_store, device_addr=device_addr, adapter_hci=adapter_hci)

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
# §7 adapter_hci — constructor stores kwarg (tincan-hzcfj.2)
# ---------------------------------------------------------------------------

class TestConstructorAdapterHci:
    """CallController stores the adapter_hci kwarg as self._adapter_hci."""

    def test_stores_supplied_adapter_hci(self):
        ctrl = _make_controller(adapter_hci="hci1")
        assert ctrl._adapter_hci == "hci1"

    def test_default_adapter_hci_is_empty_string(self):
        ctrl = _make_controller()
        assert ctrl._adapter_hci == ""


# ---------------------------------------------------------------------------
# §8 _bind_modem propagation — adapter_hci forwarded to verify_dongle_adapter
#    (tincan-hzcfj.2)
# ---------------------------------------------------------------------------

class TestBindModemAdapterHciPropagation:
    """_bind_modem passes self._adapter_hci to call_audio.verify_dongle_adapter."""

    def test_passes_hci1_to_verify_dongle_adapter(self):
        ctrl = _make_controller(adapter_hci="hci1")
        modem_path = "/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20"
        with (
            patch("tincand.call_controller.call_audio") as mock_ca,
            patch("dbus.Interface") as mock_iface,
        ):
            mock_iface.return_value.GetCalls.return_value = []
            ctrl._bind_modem(modem_path)
            mock_ca.verify_dongle_adapter.assert_called_once_with(modem_path, "hci1")

    def test_passes_empty_hci_no_exception(self):
        ctrl = _make_controller(adapter_hci="")
        modem_path = "/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20"
        with (
            patch("tincand.call_controller.call_audio") as mock_ca,
            patch("dbus.Interface") as mock_iface,
        ):
            mock_ca.verify_dongle_adapter.return_value = False
            mock_iface.return_value.GetCalls.return_value = []
            ctrl._bind_modem(modem_path)
            mock_ca.verify_dongle_adapter.assert_called_once_with(modem_path, "")


# ---------------------------------------------------------------------------
# §9 __main__ hciN extraction — regex pattern (tincan-hzcfj.2)
# ---------------------------------------------------------------------------

import re as _re


class TestMainAdapterHciExtraction:
    """adapter_hci is derived from adapter_path by extracting trailing hciN.

    This mirrors the logic in tincand/__main__.py:
        _hci_m = re.search(r'(hci\\d+)$', adapter_path)
        adapter_hci = _hci_m.group(1) if _hci_m else ""
    """

    _PATTERN = r"(hci\d+)$"

    def _extract(self, adapter_path: str) -> str:
        m = _re.search(self._PATTERN, adapter_path)
        return m.group(1) if m else ""

    def test_hci1_extracted(self):
        assert self._extract("/org/bluez/hci1") == "hci1"

    def test_hci0_extracted(self):
        assert self._extract("/org/bluez/hci0") == "hci0"

    def test_empty_path_yields_empty(self):
        assert self._extract("") == ""

    def test_path_without_hci_yields_empty(self):
        assert self._extract("/org/bluez/adapter0") == ""
