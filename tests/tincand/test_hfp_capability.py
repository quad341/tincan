"""Tests: hfp_capability detection and dbus_service integration.
Bead: tincan-arvln

Coverage:
  §1 detect_hfp_capability() — return values by SELinux + module state
     - CALLS_READY when Enforcing + module loaded
     - CALLS_NEED_SELINUX_MODULE when Enforcing + module absent (semodule -l succeeds, name not found)
     - SELINUX_NOT_ENFORCING when Permissive
     - SELINUX_NOT_ENFORCING when Disabled
     - CALLS_STATUS_UNKNOWN when Enforcing + semodule absent + no .pp marker

  §2 is_call_setup_ready() — bool wrapper
     - True for CALLS_READY
     - True for SELINUX_NOT_ENFORCING
     - False for CALLS_NEED_SELINUX_MODULE
     - False for CALLS_STATUS_UNKNOWN

  §3 GetStatus() — call_setup_ready key always present
     - call_setup_ready key present in capabilities dict after set_capability

  §4 Disconnect() — call_setup_ready persists
     - call_setup_ready=True survives Disconnect()
     - call_setup_ready=False survives Disconnect()

  §5 set_capability('call_setup_ready') — accepted by validation
     - True accepted without error or signal suppression
     - False accepted without error

  §6 _check_module_loaded() — selinux-store fallback path (tincan-uak1h)
     - store has matching module dir → True (semodule -l unavailable)
     - store populated but module dir absent, no .pp marker → None

  §7 call_link_ready — per-connection HFP link state (tincan-c7b8g)
     - key always present in GetStatus() capabilities, defaults False
     - accepted by set_capability, emits CapabilityChanged
     - Disconnect() RESETS it to False — opposite of call_setup_ready, which
       persists (call_setup_ready is SELinux-module presence; call_link_ready
       is a live VoiceCallManager bind, which cannot survive a disconnect)

All subprocess calls (getenforce, semodule) are mocked — no root required.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

import tincand.hfp_capability as hfp_mod
from tincand.hfp_capability import (
    CALLS_NEED_SELINUX_MODULE,
    CALLS_READY,
    CALLS_STATUS_UNKNOWN,
    SELINUX_NOT_ENFORCING,
    detect_hfp_capability,
    is_call_setup_ready,
)
from tincand.dbus_service import TincanService


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    """TincanService with mocked D-Bus registration — no real bus required."""
    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    svc.AppNotificationReceived = MagicMock()
    return svc


def _mock_run(stdout: str, returncode: int = 0):
    """Return a mock subprocess.CompletedProcess-like result."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# §1 detect_hfp_capability() — SELinux + module state matrix
# ---------------------------------------------------------------------------

class TestDetectHfpCapability:
    """detect_hfp_capability() returns correct constant for each SELinux/module state."""

    def test_enforcing_module_loaded_returns_calls_ready(self, monkeypatch):
        monkeypatch.setattr(
            hfp_mod.subprocess, "run",
            lambda cmd, **_kw: (
                _mock_run("Enforcing") if cmd == ["getenforce"]
                else _mock_run("tincan_hfp_sco\nother_module\n")
            ),
        )
        assert detect_hfp_capability() == CALLS_READY

    def test_enforcing_module_absent_returns_calls_need_selinux_module(self, monkeypatch):
        monkeypatch.setattr(
            hfp_mod.subprocess, "run",
            lambda cmd, **_kw: (
                _mock_run("Enforcing") if cmd == ["getenforce"]
                else _mock_run("some_other_module\n")
            ),
        )
        assert detect_hfp_capability() == CALLS_NEED_SELINUX_MODULE

    def test_permissive_returns_selinux_not_enforcing(self, monkeypatch):
        monkeypatch.setattr(
            hfp_mod.subprocess, "run",
            lambda cmd, **_kw: _mock_run("Permissive"),
        )
        assert detect_hfp_capability() == SELINUX_NOT_ENFORCING

    def test_disabled_returns_selinux_not_enforcing(self, monkeypatch):
        monkeypatch.setattr(
            hfp_mod.subprocess, "run",
            lambda cmd, **_kw: _mock_run("Disabled"),
        )
        assert detect_hfp_capability() == SELINUX_NOT_ENFORCING

    def test_enforcing_semodule_absent_no_marker_returns_unknown(
        self, monkeypatch, tmp_path
    ):
        def fake_run(cmd, **_kw):
            if cmd == ["getenforce"]:
                return _mock_run("Enforcing")
            raise FileNotFoundError("semodule not found")

        monkeypatch.setattr(hfp_mod.subprocess, "run", fake_run)
        # Patch Path.exists to return False (no .pp marker on disk)
        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert detect_hfp_capability() == CALLS_STATUS_UNKNOWN


# ---------------------------------------------------------------------------
# §2 is_call_setup_ready() — bool wrapper
# ---------------------------------------------------------------------------

class TestIsCallSetupReady:
    """is_call_setup_ready() returns True iff the result is CALLS_READY or SELINUX_NOT_ENFORCING."""

    def test_true_for_calls_ready(self, monkeypatch):
        monkeypatch.setattr(hfp_mod, "detect_hfp_capability", lambda: CALLS_READY)
        assert is_call_setup_ready() is True

    def test_true_for_selinux_not_enforcing(self, monkeypatch):
        monkeypatch.setattr(hfp_mod, "detect_hfp_capability", lambda: SELINUX_NOT_ENFORCING)
        assert is_call_setup_ready() is True

    def test_false_for_calls_need_selinux_module(self, monkeypatch):
        monkeypatch.setattr(hfp_mod, "detect_hfp_capability", lambda: CALLS_NEED_SELINUX_MODULE)
        assert is_call_setup_ready() is False

    def test_false_for_calls_status_unknown(self, monkeypatch):
        monkeypatch.setattr(hfp_mod, "detect_hfp_capability", lambda: CALLS_STATUS_UNKNOWN)
        assert is_call_setup_ready() is False


# ---------------------------------------------------------------------------
# §3 GetStatus() — call_setup_ready key always present
# ---------------------------------------------------------------------------

class TestGetStatusCallSetupReady:
    """GetStatus() capabilities dict always includes call_setup_ready."""

    def test_call_setup_ready_key_present_in_capabilities(self, service):
        caps = service.GetStatus()["capabilities"]
        assert "call_setup_ready" in caps

    def test_call_setup_ready_defaults_false(self, service):
        caps = service.GetStatus()["capabilities"]
        assert bool(caps["call_setup_ready"]) is False

    def test_call_setup_ready_true_after_set_capability(self, service):
        service.set_capability("call_setup_ready", True)
        caps = service.GetStatus()["capabilities"]
        assert bool(caps["call_setup_ready"]) is True


# ---------------------------------------------------------------------------
# §4 Disconnect() — call_setup_ready persists across disconnect
# ---------------------------------------------------------------------------

class TestDisconnectPreservesCallSetupReady:
    """Disconnect() does NOT reset call_setup_ready — it reflects SELinux state, not BT state."""

    def test_call_setup_ready_true_survives_disconnect(self, service):
        service.set_capability("call_setup_ready", True)
        service.Disconnect()
        assert service._capabilities["call_setup_ready"] is True

    def test_call_setup_ready_false_survives_disconnect(self, service):
        # Default is False; confirm it stays False after disconnect
        assert service._capabilities["call_setup_ready"] is False
        service.Disconnect()
        assert service._capabilities["call_setup_ready"] is False


# ---------------------------------------------------------------------------
# §5 set_capability('call_setup_ready') — accepted by _KNOWN_CAPABILITIES
# ---------------------------------------------------------------------------

class TestSetCapabilityCallSetupReady:
    """set_capability accepts call_setup_ready and emits CapabilityChanged."""

    def test_set_true_updates_capabilities_dict(self, service):
        service.set_capability("call_setup_ready", True)
        assert service._capabilities["call_setup_ready"] is True

    def test_set_true_emits_capability_changed(self, service):
        service.set_capability("call_setup_ready", True)
        service.CapabilityChanged.assert_called_once_with("call_setup_ready", True)

    def test_set_false_updates_capabilities_dict(self, service):
        service._capabilities["call_setup_ready"] = True
        service.set_capability("call_setup_ready", False)
        assert service._capabilities["call_setup_ready"] is False

    def test_set_false_emits_capability_changed(self, service):
        service.set_capability("call_setup_ready", False)
        service.CapabilityChanged.assert_called_once_with("call_setup_ready", False)


# ---------------------------------------------------------------------------
# §6 _check_module_loaded() — selinux-store fallback path (tincan-uak1h)
# ---------------------------------------------------------------------------

import pathlib as _pathlib


class TestCheckModuleLoadedSelinuxStore:
    """Fallback 1: /var/lib/selinux/<policy>/active/modules/<priority>/<name>/

    semodule -l raises FileNotFoundError in every case so the tests isolate
    the directory-scan path exclusively.  The /var/lib/selinux root and the
    .pp marker path are redirected to a tmp_path structure so no real
    SELinux store is required.
    """

    def _fail_semodule(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise FileNotFoundError("semodule not found")
        monkeypatch.setattr(hfp_mod.subprocess, "run", _raise)

    def _redirect_selinux_paths(self, monkeypatch, store_root, marker_root):
        """Redirect hfp_capability.pathlib.Path calls to our tmp dirs."""
        _orig = _pathlib.Path
        _marker_str = "/usr/share/selinux/packages/tincan_hfp_sco.pp"

        def _factory(*args, **kwargs):
            p = _orig(*args, **kwargs)
            s = str(p)
            if s == "/var/lib/selinux":
                return _orig(store_root)
            if s == _marker_str:
                return _orig(marker_root) / "tincan_hfp_sco.pp"
            return p

        monkeypatch.setattr(hfp_mod.pathlib, "Path", _factory)

    def test_store_with_module_dir_returns_true(self, monkeypatch, tmp_path):
        store = tmp_path / "store"
        (store / "targeted" / "active" / "modules" / "200" / "tincan_hfp_sco").mkdir(
            parents=True
        )
        marker_root = tmp_path / "marker"
        marker_root.mkdir()

        self._fail_semodule(monkeypatch)
        self._redirect_selinux_paths(monkeypatch, store, marker_root)

        assert hfp_mod._check_module_loaded() is True

    def test_store_without_module_dir_no_marker_returns_none(self, monkeypatch, tmp_path):
        # Store has the priority dir structure but NOT the module subdir.
        store = tmp_path / "store"
        (store / "targeted" / "active" / "modules" / "200").mkdir(parents=True)
        marker_root = tmp_path / "marker"
        marker_root.mkdir()  # tincan_hfp_sco.pp intentionally absent here

        self._fail_semodule(monkeypatch)
        self._redirect_selinux_paths(monkeypatch, store, marker_root)

        assert hfp_mod._check_module_loaded() is None


# ---------------------------------------------------------------------------
# §7 call_link_ready — per-connection HFP link state (tincan-c7b8g)
#
# call_link_ready mirrors call_setup_ready's shape (key always present,
# defaults False, accepted by set_capability) but is the OPPOSITE on
# Disconnect(): it RESETS to False (per-connection: does CallController have
# a live VoiceCallManager bind right now?) rather than persisting like
# call_setup_ready (system-level SELinux module presence, not BT state —
# see tincan-r41sx).
# ---------------------------------------------------------------------------

class TestGetStatusCallLinkReady:
    """GetStatus() capabilities dict always includes call_link_ready, defaulting False."""

    def test_call_link_ready_key_present_in_capabilities(self, service):
        caps = service.GetStatus()["capabilities"]
        assert "call_link_ready" in caps

    def test_call_link_ready_defaults_false(self, service):
        caps = service.GetStatus()["capabilities"]
        assert bool(caps["call_link_ready"]) is False

    def test_call_link_ready_true_after_set_capability(self, service):
        service.set_capability("call_link_ready", True)
        caps = service.GetStatus()["capabilities"]
        assert bool(caps["call_link_ready"]) is True


class TestDisconnectResetsCallLinkReady:
    """Disconnect() RESETS call_link_ready to False — opposite of call_setup_ready,
    which persists (tincan-c7b8g). A live VCM bind cannot survive a disconnect.

    Disconnect() early-returns as a no-op when self._connected is False (the
    `service` fixture starts disconnected) — every test here must set
    service._connected = True first or the reset body never runs, and the
    assertion below would hold vacuously instead of exercising the reset.
    """

    def test_call_link_ready_true_reset_false_on_disconnect(self, service):
        service._connected = True
        service.set_capability("call_link_ready", True)
        service.Disconnect()
        assert service._capabilities["call_link_ready"] is False

    def test_call_link_ready_stays_false_on_disconnect(self, service):
        service._connected = True
        assert service._capabilities["call_link_ready"] is False
        service.Disconnect()
        assert service._capabilities["call_link_ready"] is False

    def test_call_link_ready_resets_while_call_setup_ready_persists(self, service):
        """Direct contrast in one test: both set True, only call_setup_ready survives."""
        service._connected = True
        service.set_capability("call_setup_ready", True)
        service.set_capability("call_link_ready", True)
        service.Disconnect()
        assert service._capabilities["call_setup_ready"] is True
        assert service._capabilities["call_link_ready"] is False


class TestSetCapabilityCallLinkReady:
    """set_capability accepts call_link_ready and emits CapabilityChanged."""

    def test_set_true_updates_capabilities_dict(self, service):
        service.set_capability("call_link_ready", True)
        assert service._capabilities["call_link_ready"] is True

    def test_set_true_emits_capability_changed(self, service):
        service.set_capability("call_link_ready", True)
        service.CapabilityChanged.assert_called_once_with("call_link_ready", True)

    def test_set_false_updates_capabilities_dict(self, service):
        service._capabilities["call_link_ready"] = True
        service.set_capability("call_link_ready", False)
        assert service._capabilities["call_link_ready"] is False

    def test_set_false_emits_capability_changed(self, service):
        service.set_capability("call_link_ready", False)
        service.CapabilityChanged.assert_called_once_with("call_link_ready", False)
