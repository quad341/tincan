"""Behavioral acceptance tests: BT adapter picker, restart banner, unavailable banner.
Bead: tincan-t53s7

Coverage:
  §1 Picker — normal state (2 adapters)
    - both adapter paths appear as combo items
    - capability badges rendered (HFP + LE) for the selected adapter
    - selection change persists to QSettings bluetooth/adapter_path
  §2 Picker — loading state
    - combo is disabled and shows 'Loading adapters…' placeholder while get_adapters() is in flight
  §3 Picker — BlueZ unavailable (get_adapters returns [])
    - BT section is disabled
    - 'Bluetooth service unavailable' label is shown
    - no QComboBox rendered in the BT section
  §4 Picker — single adapter
    - combo is disabled (cannot change what you don't have alternatives for)
    - capability badges still visible (opacity check omitted — behavioral, not visual)
  §5 Restart banner (settings_dialog)
    - adapter change → _adapter_restart_banner becomes visible
    - 'Later' button → banner hidden, dialog stays open
    - 'Restart Now' button → spawn_daemon called (mocked)
  §6 Unavailable banner (main window)
    - adapter_path_requested != adapter_path → banner visible, text contains both paths
    - ✕ dismiss button → banner hidden
    - after dismiss, re-triggering status check with same mismatch does NOT re-show banner

All tests mock TincandClient — no real D-Bus required.
Run with: python -m pytest tests/tincan_gui/test_adapter_picker.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.settings_dialog import SettingsDialog

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TWO_ADAPTERS = [
    {
        "path": "/org/bluez/hci0",
        "alias": "MT7925 (built-in)",
        "address": "00:E1:0D:9A:3F:12",
        "powered": True,
        "hfp_sco_capable": False,
        "le_capable": True,
    },
    {
        "path": "/org/bluez/hci1",
        "alias": "ASUS USB-BT500",
        "address": "D4:3B:04:12:AB:CD",
        "powered": True,
        "hfp_sco_capable": True,
        "le_capable": True,
    },
]

_ONE_ADAPTER = [_TWO_ADAPTERS[0]]


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


def _make_client(monkeypatch, adapters, status_extra=None):
    """Monkeypatch TincandClient.get_adapters and get_status."""
    monkeypatch.setattr(TincandClient, "get_adapters", lambda self: adapters)
    base_status = {"connected": False}
    if status_extra:
        base_status.update(status_extra)
    monkeypatch.setattr(TincandClient, "get_status", lambda self: base_status)


def _make_dialog(qtbot, monkeypatch, adapters, settings_override=None):
    """Create SettingsDialog with a mocked client returning `adapters`."""
    _make_client(monkeypatch, adapters)
    client = TincandClient.__new__(TincandClient)
    dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


# ---------------------------------------------------------------------------
# §1 Picker — normal state (2 adapters)
# ---------------------------------------------------------------------------

class TestPickerNormalState:
    """Two-adapter state: both listed, badges rendered, selection writes QSettings."""

    def test_both_adapter_paths_present_in_combo(self, qtbot, monkeypatch):
        """Combo must have one item per adapter returned by get_adapters()."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        paths = [
            dlg._adapter_combo.itemData(i, Qt.ItemDataRole.UserRole)
            for i in range(dlg._adapter_combo.count())
        ]
        assert "/org/bluez/hci0" in paths
        assert "/org/bluez/hci1" in paths

    def test_combo_count_matches_adapter_list(self, qtbot, monkeypatch):
        """Combo item count must equal the number of adapters."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._adapter_combo.count() == 2

    def test_hfp_badge_text_present_for_selected_adapter(self, qtbot, monkeypatch):
        """A badge widget below the combo must mention 'HFP call audio'."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        badge_text = dlg._adapter_badge_row.text() if hasattr(dlg._adapter_badge_row, "text") else \
            " ".join(
                w.text() for w in dlg._adapter_badge_row.findChildren(QLabel)
            )
        assert "HFP call audio" in badge_text, (
            f"Expected 'HFP call audio' badge text; got: {badge_text!r}"
        )

    def test_le_badge_text_present_for_selected_adapter(self, qtbot, monkeypatch):
        """A badge widget below the combo must mention 'LE advertising'."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        badge_text = dlg._adapter_badge_row.text() if hasattr(dlg._adapter_badge_row, "text") else \
            " ".join(
                w.text() for w in dlg._adapter_badge_row.findChildren(QLabel)
            )
        assert "LE advertising" in badge_text, (
            f"Expected 'LE advertising' badge text; got: {badge_text!r}"
        )

    def test_selection_change_writes_qsettings(self, qtbot, monkeypatch):
        """Selecting a different adapter must persist its path to QSettings."""
        written: dict = {}

        class FakeSettings:
            def setValue(self, key, val):
                written[key] = val
            def value(self, key, default=None, type=None):
                return written.get(key, default)
            def sync(self):
                pass

        monkeypatch.setattr(
            "tincan_gui.settings_dialog.app_settings", lambda: FakeSettings()
        )

        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        # Select the second adapter
        dlg._adapter_combo.setCurrentIndex(1)
        qtbot.waitUntil(lambda: "bluetooth/adapter_path" in written, timeout=1000)

        assert written["bluetooth/adapter_path"] == "/org/bluez/hci1"


# ---------------------------------------------------------------------------
# §2 Picker — loading state
# ---------------------------------------------------------------------------

class TestPickerLoadingState:
    """While get_adapters() is in flight, combo shows placeholder and is disabled."""

    def test_combo_disabled_during_loading(self, qtbot, monkeypatch):
        """_adapter_combo must be disabled before adapter data arrives."""
        import threading

        gate = threading.Event()

        def slow_get_adapters(self):
            gate.wait(timeout=5)
            return _TWO_ADAPTERS

        monkeypatch.setattr(TincandClient, "get_adapters", slow_get_adapters)
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})

        client = TincandClient.__new__(TincandClient)
        dlg = SettingsDialog(client=client)
        qtbot.addWidget(dlg)
        dlg.show()

        # Check immediately after show, before gate opens — combo must be disabled
        assert not dlg._adapter_combo.isEnabled(), (
            "_adapter_combo must be disabled while get_adapters() is in flight"
        )

        gate.set()

    def test_combo_placeholder_text_during_loading(self, qtbot, monkeypatch):
        """_adapter_combo placeholder text must say 'Loading adapters…' while loading."""
        import threading

        gate = threading.Event()

        def slow_get_adapters(self):
            gate.wait(timeout=5)
            return _TWO_ADAPTERS

        monkeypatch.setattr(TincandClient, "get_adapters", slow_get_adapters)
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})

        client = TincandClient.__new__(TincandClient)
        dlg = SettingsDialog(client=client)
        qtbot.addWidget(dlg)
        dlg.show()

        placeholder = dlg._adapter_combo.placeholderText()
        gate.set()

        assert "Loading adapters" in placeholder, (
            f"Expected 'Loading adapters…' placeholder; got {placeholder!r}"
        )


# ---------------------------------------------------------------------------
# §3 Picker — BlueZ unavailable (get_adapters returns [])
# ---------------------------------------------------------------------------

class TestPickerBlueZUnavailable:
    """Empty adapter list: BT section disabled, unavailability label shown, no combo."""

    def test_bt_section_disabled_when_no_adapters(self, qtbot, monkeypatch):
        """_bt_section must be disabled when get_adapters() returns []."""
        dlg = _make_dialog(qtbot, monkeypatch, [])
        assert not dlg._bt_section.isEnabled(), (
            "_bt_section must be disabled when BlueZ returns no adapters"
        )

    def test_unavailable_label_shown_when_no_adapters(self, qtbot, monkeypatch):
        """A label containing 'Bluetooth service unavailable' must be visible."""
        dlg = _make_dialog(qtbot, monkeypatch, [])
        label = dlg._adapter_unavailable_label
        assert label.isVisible(), "Unavailable label must be visible"
        assert "unavailable" in label.text().lower(), (
            f"Label must mention 'unavailable'; got {label.text()!r}"
        )

    def test_no_qcombobox_in_bt_section_when_unavailable(self, qtbot, monkeypatch):
        """QComboBox must NOT be visible in the BT section when get_adapters() returns []."""
        dlg = _make_dialog(qtbot, monkeypatch, [])
        # Either combo is hidden or doesn't exist
        combo_visible = (
            hasattr(dlg, "_adapter_combo") and dlg._adapter_combo.isVisible()
        )
        assert not combo_visible, (
            "_adapter_combo must not be visible when BlueZ has no adapters"
        )


# ---------------------------------------------------------------------------
# §4 Picker — single adapter
# ---------------------------------------------------------------------------

class TestPickerSingleAdapter:
    """Single adapter: combo disabled, badges still visible."""

    def test_combo_disabled_with_single_adapter(self, qtbot, monkeypatch):
        """_adapter_combo must be disabled when only one adapter is available."""
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_ADAPTER)
        assert not dlg._adapter_combo.isEnabled(), (
            "_adapter_combo must be disabled when there is only one adapter"
        )

    def test_badge_row_visible_with_single_adapter(self, qtbot, monkeypatch):
        """Badge row must still be visible (user needs capability info even if locked)."""
        dlg = _make_dialog(qtbot, monkeypatch, _ONE_ADAPTER)
        assert dlg._adapter_badge_row.isVisible(), (
            "_adapter_badge_row must be visible even with a single (disabled) adapter"
        )


# ---------------------------------------------------------------------------
# §5 Restart banner (settings_dialog)
# ---------------------------------------------------------------------------

class TestAdapterRestartBanner:
    """Restart banner lifecycle: appear on change, Later hides, Restart Now calls spawn_daemon."""

    def test_restart_banner_hidden_on_initial_load(self, qtbot, monkeypatch):
        """Banner must be hidden when the dialog opens (no adapter change yet)."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert not dlg._adapter_restart_banner.isVisible(), (
            "_adapter_restart_banner must be hidden on initial load"
        )

    def test_restart_banner_shown_on_adapter_change(self, qtbot, monkeypatch):
        """Selecting a different adapter must show the restart banner."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        dlg._adapter_combo.setCurrentIndex(1)
        qtbot.waitUntil(lambda: dlg._adapter_restart_banner.isVisible(), timeout=1000)

    def test_later_button_hides_banner(self, qtbot, monkeypatch):
        """Clicking 'Later' must hide the restart banner."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        dlg._adapter_combo.setCurrentIndex(1)
        qtbot.waitUntil(lambda: dlg._adapter_restart_banner.isVisible(), timeout=1000)

        dlg._adapter_restart_banner._later_btn.click()
        assert not dlg._adapter_restart_banner.isVisible(), (
            "Banner must be hidden after clicking 'Later'"
        )

    def test_restart_now_calls_spawn_daemon(self, qtbot, monkeypatch):
        """Clicking 'Restart Now' must invoke spawn_daemon (mocked)."""
        spawn_calls: list = []

        monkeypatch.setattr(
            "tincan_gui.settings_dialog.spawn_daemon",
            lambda *args, **kwargs: spawn_calls.append((args, kwargs)),
        )

        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        dlg._adapter_combo.setCurrentIndex(1)
        qtbot.waitUntil(lambda: dlg._adapter_restart_banner.isVisible(), timeout=1000)

        dlg._adapter_restart_banner._restart_btn.click()

        assert spawn_calls, "spawn_daemon must be called when 'Restart Now' is clicked"


# ---------------------------------------------------------------------------
# §6 Unavailable banner (main window)
# ---------------------------------------------------------------------------

class TestAdapterUnavailableBanner:
    """Unavailable-adapter banner: appears with correct paths, dismisses, no repeat."""

    def _make_window(self, qtbot, monkeypatch, adapter_path, adapter_path_requested):
        monkeypatch.setattr(
            TincandClient,
            "get_status",
            lambda self: {
                "connected": False,
                "adapter_path": adapter_path,
                "adapter_path_requested": adapter_path_requested,
            },
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        return window

    def test_banner_visible_when_adapter_path_mismatch(self, qtbot, monkeypatch):
        """Banner must be visible when adapter_path != adapter_path_requested."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci1",
            adapter_path_requested="/org/bluez/hci0",
        )
        assert window._adapter_unavailable_banner.isVisible(), (
            "_adapter_unavailable_banner must be visible when adapter path mismatches"
        )

    def test_banner_hidden_when_paths_match(self, qtbot, monkeypatch):
        """Banner must be hidden when adapter_path == adapter_path_requested."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci0",
            adapter_path_requested="/org/bluez/hci0",
        )
        assert not window._adapter_unavailable_banner.isVisible()

    def test_banner_hidden_when_adapter_path_requested_empty(self, qtbot, monkeypatch):
        """Banner must be hidden when adapter_path_requested is empty (no preference saved)."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci0",
            adapter_path_requested="",
        )
        assert not window._adapter_unavailable_banner.isVisible()

    def test_banner_text_contains_requested_path(self, qtbot, monkeypatch):
        """Banner text must include the adapter that was requested but unavailable."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci1",
            adapter_path_requested="/org/bluez/hci0",
        )
        banner_text = window._adapter_unavailable_banner.text() \
            if hasattr(window._adapter_unavailable_banner, "text") else \
            " ".join(
                w.text() for w in window._adapter_unavailable_banner.findChildren(QLabel)
            )
        assert "/org/bluez/hci0" in banner_text, (
            f"Banner must name the requested (unavailable) adapter; got: {banner_text!r}"
        )

    def test_banner_text_contains_actual_path(self, qtbot, monkeypatch):
        """Banner text must include the adapter that is actually in use."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci1",
            adapter_path_requested="/org/bluez/hci0",
        )
        banner_text = window._adapter_unavailable_banner.text() \
            if hasattr(window._adapter_unavailable_banner, "text") else \
            " ".join(
                w.text() for w in window._adapter_unavailable_banner.findChildren(QLabel)
            )
        assert "/org/bluez/hci1" in banner_text, (
            f"Banner must name the actual (fallback) adapter; got: {banner_text!r}"
        )

    def test_dismiss_button_hides_banner(self, qtbot, monkeypatch):
        """Clicking ✕ dismiss button must hide the banner."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci1",
            adapter_path_requested="/org/bluez/hci0",
        )
        window._adapter_unavailable_banner._dismiss_btn.click()
        assert not window._adapter_unavailable_banner.isVisible(), (
            "Banner must be hidden after clicking dismiss"
        )

    def test_banner_does_not_reappear_after_dismiss(self, qtbot, monkeypatch):
        """After dismissal, re-triggering status check with same mismatch must not re-show banner."""
        window = self._make_window(
            qtbot, monkeypatch,
            adapter_path="/org/bluez/hci1",
            adapter_path_requested="/org/bluez/hci0",
        )
        window._adapter_unavailable_banner._dismiss_btn.click()
        assert not window._adapter_unavailable_banner.isVisible()

        # Simulate a status re-check (e.g., after reconnect)
        window._refresh_adapter_unavailable_banner()

        assert not window._adapter_unavailable_banner.isVisible(), (
            "Banner must NOT reappear after session-dismiss, even on same mismatch"
        )
