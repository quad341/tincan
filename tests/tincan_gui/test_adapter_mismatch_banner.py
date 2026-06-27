"""Tests: AdapterMismatchBanner widget, MainWindow refresh/poll, SettingsDialog annotation.
Bead: tincan-5m88a (tincan-5y8km.2)

Coverage:
  §1 AdapterMismatchBanner — instantiation, accessible name, update_warning(), style, hide state
  §2 _refresh_adapter_mismatch_banner() — show/hide banner based on adapter_warning; timer control
  §3 _poll_adapter_mismatch() — delegates to _refresh_adapter_mismatch_banner(); returns None
  §4 _refresh_adapter_mismatch_annotation() — AC6: label show/hide, (wanted: hciX) parse, accessible name

All tests fail until feat/adapter-mismatch-banner-5y8km.2 is merged.
Run with: python -m pytest tests/tincan_gui/test_adapter_mismatch_banner.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QLabel, QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


# ---------------------------------------------------------------------------
# §1 AdapterMismatchBanner — widget smoke tests
# ---------------------------------------------------------------------------

class TestAdapterMismatchBanner:
    """AdapterMismatchBanner exposes accessible name and update_warning()."""

    def test_instantiates_without_error(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)

    def test_accessible_name_is_adapter_mismatch_warning(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        assert banner.accessibleName() == "adapter mismatch warning"

    def test_update_warning_sets_label_text(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        banner.update_warning("iPhone on hci0 (no SCO). Connect to hci1.")
        assert "hci0" in banner._label.text() or "iPhone" in banner._label.text()

    def test_update_warning_sets_accessible_description(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        warning = "iPhone on hci0. Use hci1 instead."
        banner.update_warning(warning)
        assert banner.accessibleDescription() == warning

    def test_style_has_amber_background(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        style = banner.styleSheet()
        assert "#fff3bf" in style

    def test_style_has_amber_border(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        style = banner.styleSheet()
        assert "#f59f00" in style

    def test_label_style_has_dark_amber_text(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        assert "#7c4f00" in banner._label.styleSheet()

    def test_not_dismissible_no_close_button(self, qtbot):
        from tincan_gui.degradation_banners import AdapterMismatchBanner
        from PySide6.QtWidgets import QPushButton, QToolButton
        banner = AdapterMismatchBanner()
        qtbot.addWidget(banner)
        close_btns = [
            b for b in list(banner.findChildren(QPushButton)) + list(banner.findChildren(QToolButton))
            if "dismiss" in (b.text() + b.accessibleName()).lower()
            or "✕" in b.text() or "×" in b.text()
        ]
        assert close_btns == []


# ---------------------------------------------------------------------------
# §2 _refresh_adapter_mismatch_banner — show/hide, timer control
# ---------------------------------------------------------------------------

class TestRefreshAdapterMismatchBanner:
    """_refresh_adapter_mismatch_banner() shows/hides banner and controls timer."""

    def test_banner_shown_when_adapter_warning_non_empty(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._refresh_adapter_mismatch_banner({"adapter_warning": "iPhone on hci0. Use hci1."})
        assert window._adapter_mismatch_banner.isVisible()

    def test_banner_hidden_when_adapter_warning_empty(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._adapter_mismatch_banner.show()  # pre-show it
        window._refresh_adapter_mismatch_banner({"adapter_warning": ""})
        assert not window._adapter_mismatch_banner.isVisible()

    def test_banner_hidden_when_adapter_warning_absent(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._refresh_adapter_mismatch_banner({})
        assert not window._adapter_mismatch_banner.isVisible()

    def test_timer_started_when_banner_shown(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._adapter_mismatch_timer.stop()  # ensure it's stopped first
        window._refresh_adapter_mismatch_banner({"adapter_warning": "use hci1"})
        assert window._adapter_mismatch_timer.isActive()

    def test_timer_stopped_when_banner_hidden(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._adapter_mismatch_timer.start()  # ensure it's running first
        window._refresh_adapter_mismatch_banner({"adapter_warning": ""})
        assert not window._adapter_mismatch_timer.isActive()


# ---------------------------------------------------------------------------
# §3 _poll_adapter_mismatch — delegates to _refresh and returns None
# ---------------------------------------------------------------------------

class TestPollAdapterMismatch:
    """_poll_adapter_mismatch() calls _refresh_adapter_mismatch_banner and returns None."""

    def test_poll_calls_refresh(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        called = []
        original = window._refresh_adapter_mismatch_banner
        window._refresh_adapter_mismatch_banner = lambda *a, **k: called.append(True) or original(*a, **k)
        window._poll_adapter_mismatch()
        assert called

    def test_poll_returns_none(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        result = window._poll_adapter_mismatch()
        assert result is None


# ---------------------------------------------------------------------------
# §4 _refresh_adapter_mismatch_annotation — AC6 settings dialog label
# ---------------------------------------------------------------------------

def _make_dialog_with_annotation(qtbot):
    """Create a SettingsDialog with a manually injected annotation label.

    Sets _adapters_list to a non-empty stub so the FR-C3 guard in
    _refresh_adapter_mismatch_annotation does not suppress the annotation.
    """
    from tincan_gui.settings_dialog import SettingsDialog
    dlg = SettingsDialog()
    qtbot.addWidget(dlg)
    dlg._adapters_list = [{"path": "/org/bluez/hci0", "alias": "test", "address": "AA:BB:CC:DD:EE:FF"}]
    label = QLabel()
    label.hide()
    dlg._adapter_mismatch_annotation = label
    return dlg, label


class TestRefreshAdapterMismatchAnnotation:
    """_refresh_adapter_mismatch_annotation() shows/hides label and parses (wanted: hciX)."""

    def test_label_shown_when_warning_non_empty(self, qtbot):
        dlg, label = _make_dialog_with_annotation(qtbot)
        dlg._refresh_adapter_mismatch_annotation(
            "iPhone on hci0 (hci1) for call audio"
        )
        assert label.isVisible()

    def test_label_hidden_when_warning_empty(self, qtbot):
        dlg, label = _make_dialog_with_annotation(qtbot)
        label.show()
        dlg._refresh_adapter_mismatch_annotation("")
        assert not label.isVisible()

    def test_label_text_contains_wanted_adapter(self, qtbot):
        dlg, label = _make_dialog_with_annotation(qtbot)
        dlg._refresh_adapter_mismatch_annotation(
            "iPhone connected on hci0 (no SCO). Connect iPhone to (hci1) for call audio."
        )
        assert "hci1" in label.text()

    def test_label_text_shows_warning_symbol(self, qtbot):
        dlg, label = _make_dialog_with_annotation(qtbot)
        dlg._refresh_adapter_mismatch_annotation(
            "iPhone on hci0 (hci1) for call audio"
        )
        assert "⚠" in label.text()

    def test_fallback_text_when_pattern_not_matched(self, qtbot):
        dlg, label = _make_dialog_with_annotation(qtbot)
        dlg._refresh_adapter_mismatch_annotation("unexpected format warning")
        assert label.isVisible()
        assert "see warning above" in label.text()

    def test_no_annotation_attribute_is_a_noop(self, qtbot):
        from tincan_gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog()
        qtbot.addWidget(dlg)
        if hasattr(dlg, "_adapter_mismatch_annotation"):
            delattr(dlg, "_adapter_mismatch_annotation")
        dlg._refresh_adapter_mismatch_annotation("some warning")

    def test_annotation_accessible_name_is_wrong_adapter_detected(self, qtbot):
        from tincan_gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog()
        qtbot.addWidget(dlg)
        label = QLabel()
        label.setAccessibleName("wrong adapter detected")
        label.hide()
        dlg._adapter_mismatch_annotation = label
        dlg._refresh_adapter_mismatch_annotation("iPhone on hci0 (hci1) for call audio")
        assert dlg._adapter_mismatch_annotation.accessibleName() == "wrong adapter detected"
