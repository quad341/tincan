"""Tests: ANCS capability — daemon contract and GUI cold-start path.
Bead: tincan-4au  (parent: tincan-okm)
Updated: tincan-nbjrp (honest state model — ancs_status string)

Coverage:
  - Daemon GetStatus() always returns ancs key: False before connect,
    True after set_capability('ancs', True), False after set_capability('ancs', False).
  - Daemon GetStatus() returns ancs_status string reflecting ANCS state machine.
  - set_ancs_status() emits ANCSStatusChanged and keeps legacy booleans in sync.
  - set_capability rejects invalid feature names.
  - GUI cold-start: _sync_daemon_state applies ancs_status from GetStatus();
    State C banner shows only during HEALING, not during armed/disabled.
  - GUI runtime: _on_ancs_status_changed updates banners without full re-fetch.
  - GUI: State C banner shown only when ancs_status="healing".
  - GUI: status chip shows 'limited' text when messages=False (not when ANCS missing).
  - GUI: no regression on State A (disconnected) and State B (messages=False) transitions.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow

# ---------------------------------------------------------------------------
# Helpers — daemon
# ---------------------------------------------------------------------------

def _make_service():
    """TincanService with mocked D-Bus bus."""
    from tincand.dbus_service import TincanService

    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.ANCSStatusChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# §1 Daemon: GetStatus() ancs key lifecycle
# ---------------------------------------------------------------------------

class TestAncsInGetStatus:
    """GetStatus() reflects ancs capability: False by default, True after set_capability."""

    def test_ancs_false_before_connect(self):
        svc = _make_service()
        status = svc.GetStatus()
        assert bool(status["capabilities"]["ancs"]) is False

    def test_ancs_true_after_set_capability_ancs_true(self):
        svc = _make_service()
        svc.set_capability("ancs", True)
        status = svc.GetStatus()
        assert bool(status["capabilities"]["ancs"]) is True

    def test_ancs_false_after_set_capability_ancs_false(self):
        svc = _make_service()
        svc.set_capability("ancs", True)   # set True first
        svc.set_capability("ancs", False)  # then drop it
        status = svc.GetStatus()
        assert bool(status["capabilities"]["ancs"]) is False

    def test_messages_unaffected_when_ancs_changes(self):
        svc = _make_service()
        svc.set_capability("ancs", True)
        assert bool(svc.GetStatus()["capabilities"]["messages"]) is False


# ---------------------------------------------------------------------------
# §1b Daemon: set_ancs_status — string state, signal, and legacy sync
# ---------------------------------------------------------------------------

class TestSetAncsStatus:
    """set_ancs_status() emits ANCSStatusChanged and keeps legacy booleans in sync."""

    def test_status_disabled_by_default(self):
        svc = _make_service()
        assert str(svc.GetStatus()["ancs_status"]) == "disabled"

    def test_set_armed_emits_signal(self):
        svc = _make_service()
        svc.set_ancs_status("armed")
        svc.ANCSStatusChanged.assert_called_once_with("armed")

    def test_set_active_syncs_legacy_true(self):
        svc = _make_service()
        svc.set_ancs_status("active")
        assert bool(svc._capabilities["ancs"]) is True
        assert bool(svc._capabilities["ancs_needs_repair"]) is False

    def test_set_fallback_syncs_legacy_needs_repair(self):
        svc = _make_service()
        svc.set_ancs_status("fallback")
        assert bool(svc._capabilities["ancs"]) is False
        assert bool(svc._capabilities["ancs_needs_repair"]) is True

    def test_set_healing_keeps_both_false(self):
        svc = _make_service()
        svc.set_ancs_status("healing")
        assert bool(svc._capabilities["ancs"]) is False
        assert bool(svc._capabilities["ancs_needs_repair"]) is False

    def test_unknown_status_ignored(self):
        svc = _make_service()
        svc.set_ancs_status("bogus")
        svc.ANCSStatusChanged.assert_not_called()
        assert str(svc._ancs_status) == "disabled"


# ---------------------------------------------------------------------------
# §2 Daemon: set_capability validation for ANCS
# ---------------------------------------------------------------------------

class TestSetCapabilityAncs:
    """set_capability emits CapabilityChanged for valid ANCS; rejects invalid names."""

    def test_set_ancs_true_emits_capability_changed_ancs_true(self):
        svc = _make_service()
        svc.set_capability("ancs", True)
        svc.CapabilityChanged.assert_called_once_with("ancs", True)

    def test_set_ancs_false_emits_capability_changed_ancs_false(self):
        svc = _make_service()
        svc._capabilities["ancs"] = True
        svc.set_capability("ancs", False)
        svc.CapabilityChanged.assert_called_once_with("ancs", False)

    def test_invalid_feature_name_rejected(self):
        svc = _make_service()
        original = dict(svc._capabilities)
        svc.set_capability("notifications", True)  # not a known key
        assert svc._capabilities == original

    def test_invalid_feature_does_not_emit_signal(self):
        svc = _make_service()
        svc.set_capability("notifications", True)
        svc.CapabilityChanged.assert_not_called()


# ---------------------------------------------------------------------------
# §3 GUI cold-start: _sync_daemon_state calls _apply_capabilities
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesColdStart:
    """State C banner reflects ancs value from GetStatus() at startup."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        # Default patch → daemon absent; individual tests override with patch.object
        # for specific connected/capability states.
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    def test_state_c_banner_hidden_when_ancs_true_on_startup(self, qtbot):
        with patch.object(TincandClient, "get_status", return_value={
            "connected": True,
            "device_address": "AA:BB:CC:DD:EE:FF",
            "capabilities": {"messages": True, "contacts": True, "ancs": True},
        }):
            window = MainWindow()
            qtbot.addWidget(window)
            window.show()
        assert not window._banner_c.isVisible()

    def test_state_c_banner_shown_when_ancs_healing_on_startup(self, qtbot):
        """State C banner only shows during HEALING, not during armed/disabled."""
        with patch.object(TincandClient, "get_status", return_value={
            "connected": True,
            "device_address": "AA:BB:CC:DD:EE:FF",
            "capabilities": {"messages": True, "contacts": True, "ancs": False},
            "ancs_status": "healing",
        }):
            window = MainWindow()
            qtbot.addWidget(window)
            window.show()
        assert window._banner_c.isVisible()

    def test_state_c_banner_hidden_when_ancs_armed_on_startup(self, qtbot):
        """ARMED state (soliciting) must NOT show the State C banner."""
        with patch.object(TincandClient, "get_status", return_value={
            "connected": True,
            "device_address": "AA:BB:CC:DD:EE:FF",
            "capabilities": {"messages": True, "contacts": True, "ancs": False},
            "ancs_status": "armed",
        }):
            window = MainWindow()
            qtbot.addWidget(window)
            window.show()
        assert not window._banner_c.isVisible()

    def test_state_c_banner_not_shown_when_daemon_absent_on_startup(self, qtbot):
        # get_status returns {} → daemon absent → no capability check
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert not window._banner_c.isVisible()


# ---------------------------------------------------------------------------
# §4 GUI runtime: _on_capability_changed re-fetches GetStatus
# ---------------------------------------------------------------------------

class TestCapabilityChangedAncsRuntime:
    """_on_capability_changed re-fetches GetStatus() and calls _apply_capabilities."""

    @pytest.fixture(autouse=True)
    def _no_live_daemon(self, monkeypatch):
        # _on_capability_changed calls get_status(); patch to {} so the fallback
        # dict (defaults-True + reported feature) is used instead of live state.
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})

    def test_capability_changed_ancs_false_re_fetches_get_status(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._dbus_client.get_status = MagicMock(return_value={})
        window._on_capability_changed("ancs", False)

        window._dbus_client.get_status.assert_called_once()

    def test_capability_changed_does_not_show_banner_c_when_ancs_status_absent(self, qtbot):
        """CapabilityChanged alone cannot show StateCBanner — ancs_status="healing" is needed."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        # Daemon absent → fallback dict used; ancs_status defaults to "disabled"
        window._on_capability_changed("ancs", False)
        assert not window._banner_c.isVisible()

    def test_ancs_status_changed_healing_shows_banner_c(self, qtbot):
        """ANCSStatusChanged("healing") from daemon shows State C banner."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._on_ancs_status_changed("healing")
        assert window._banner_c.isVisible()

    def test_ancs_status_changed_active_hides_banner_c(self, qtbot):
        """ANCSStatusChanged("active") hides State C banner."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()  # start visible

        window._on_ancs_status_changed("active")
        assert not window._banner_c.isVisible()

    def test_capability_changed_ancs_true_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()  # start visible

        # Daemon absent → fallback dict used; ancs_status defaults to current ("disabled")
        window._on_capability_changed("ancs", True)
        assert not window._banner_c.isVisible()


# ---------------------------------------------------------------------------
# §5 GUI: State C banner and status chip
# ---------------------------------------------------------------------------

class TestApplyAncsStatusStateCBanner:
    """_apply_ancs_status shows/hides State C banner per ancs_status string."""

    def test_healing_shows_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._apply_ancs_status("healing")

        assert window._banner_c.isVisible()

    def test_armed_hides_banner_c(self, qtbot):
        """ARMED (soliciting, no link yet) must not show the banner — it is not HEALING."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._apply_ancs_status("armed")

        assert not window._banner_c.isVisible()

    def test_active_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._apply_ancs_status("active")

        assert not window._banner_c.isVisible()

    def test_disabled_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._apply_ancs_status("disabled")

        assert not window._banner_c.isVisible()


class TestStateCBannerStatusChip:
    """Status chip reflects messaging capability (primary), not ANCS (secondary).

    When MAP messaging works (messages=True), chip shows Connected regardless of ANCS.
    ANCS unavailability is surfaced via the State C banner, not the chip (tincan-o90z2).
    """

    def test_chip_shows_connected_when_messages_true_ancs_false(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._connected_device = "AA:BB:CC:DD:EE:FF"
        window._title_bar.set_connected("AA:BB:CC:DD:EE:FF")

        window._apply_capabilities({"messages": True, "contacts": True, "ancs": False})

        assert "limited" not in window._title_bar._status_chip.text().lower()
        assert "Connected" in window._title_bar._status_chip.text()

    def test_chip_shows_connected_limited_when_messages_false(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._connected_device = "AA:BB:CC:DD:EE:FF"
        window._title_bar.set_connected("AA:BB:CC:DD:EE:FF")

        window._apply_capabilities({"messages": False, "contacts": True, "ancs": False})

        assert "limited" in window._title_bar._status_chip.text().lower()

    def test_chip_shows_plain_connected_when_ancs_true(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._connected_device = "AA:BB:CC:DD:EE:FF"
        window._title_bar.set_connected_limited("AA:BB:CC:DD:EE:FF")  # start limited

        window._apply_capabilities({"messages": True, "contacts": True, "ancs": True})

        assert "limited" not in window._title_bar._status_chip.text().lower()
        assert "Connected" in window._title_bar._status_chip.text()


# ---------------------------------------------------------------------------
# §6 No regression: State A and State B transitions unaffected by ANCS
# ---------------------------------------------------------------------------

class TestNoRegressionStateAB:
    """ANCS capability handling must not interfere with State A/B banner behavior."""

    def test_disconnected_still_shows_banner_a(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_disconnected()

        assert window._banner_a.isVisible()

    def test_disconnected_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()

        window._on_daemon_disconnected()

        assert not window._banner_c.isVisible()

    def test_messages_false_shows_banner_b_independent_of_ancs(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._apply_capabilities({"messages": False, "contacts": True, "ancs": True})

        assert window._banner_b.isVisible()
        assert not window._banner_c.isVisible()  # ancs=True → C hidden

    def test_messages_true_ancs_healing_shows_only_banner_c(self, qtbot):
        """When messages=True and ANCS is healing, only banner_c is visible."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._apply_capabilities({"messages": True, "contacts": True, "ancs": False})
        window._apply_ancs_status("healing")

        assert not window._banner_b.isVisible()
        assert window._banner_c.isVisible()
