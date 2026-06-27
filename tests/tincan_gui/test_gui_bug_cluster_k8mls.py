"""Tests: post-PR-144 GUI bug cluster behavioral coverage.
Bead: tincan-k8mls

Coverage:
  §1 FR-C3 (tincan-easo3): adapter_combo/unavailable_frame state table (A/B/C)
  §2 FR-C3 (tincan-easo3): _refresh_adapter_mismatch_annotation — client-read show/hide
  §3 FR-D (tincan-bz9go): compose-new button disabled at startup + click signal guard
  §4 FR-D (tincan-bz9go): MainWindow wiring — connected/disconnected/sync_state
  §5 FR-C2 (tincan-0oxkd): _first_valid_icon — theme hit / all-miss
  §6 FR-C1 (tincan-psnc5): BT combo minimumWidth >= 360 after dialog init

Run with: python -m pytest tests/tincan_gui/test_gui_bug_cluster_k8mls.py -v
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon, QToolButton

from tincan_gui.dbus_client import TincandClient


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


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


def _make_dialog(qtbot, monkeypatch, adapters, status_override=None):
    """Create SettingsDialog with mocked client."""
    from tincan_gui.settings_dialog import SettingsDialog
    monkeypatch.setattr(TincandClient, "get_adapters", lambda self: adapters)
    status = {"connected": False}
    if status_override:
        status.update(status_override)
    monkeypatch.setattr(TincandClient, "get_status", lambda self: status)
    client = TincandClient.__new__(TincandClient)
    dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


# ---------------------------------------------------------------------------
# §1 FR-C3: adapter_combo / unavailable_frame state table
# ---------------------------------------------------------------------------

class TestAdapterStateTable:
    """Show/hide invariants for adapter_combo and unavailable_frame across states."""

    def test_state_a_startup_combo_hidden(self, qtbot, monkeypatch):
        """State A: adapter_combo hidden before adapters load (no-adapters path)."""
        from tincan_gui.settings_dialog import SettingsDialog, _AdapterLoader
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        client = TincandClient.__new__(TincandClient)
        with patch.object(_AdapterLoader, "start", lambda *a, **kw: None):
            dlg = SettingsDialog(client=client)
            qtbot.addWidget(dlg)
            assert not dlg._adapter_combo.isVisible(), (
                "adapter_combo must be hidden at startup before loading completes"
            )

    def test_state_a_startup_unavailable_shown(self, qtbot, monkeypatch):
        """State A: unavailable_frame shown before adapters load.

        Uses isHidden() rather than isVisible(): the parent dialog is not shown
        here so isVisible() propagates False up the parent chain. isHidden()
        reflects only this widget's own show/hide state.
        """
        from tincan_gui.settings_dialog import SettingsDialog, _AdapterLoader
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        client = TincandClient.__new__(TincandClient)
        with patch.object(_AdapterLoader, "start", lambda *a, **kw: None):
            dlg = SettingsDialog(client=client)
            qtbot.addWidget(dlg)
            assert not dlg._adapter_unavailable_frame.isHidden(), (
                "unavailable_frame must not be hidden at startup before loading completes"
            )

    def test_state_b_adapters_loaded_combo_shown(self, qtbot, monkeypatch):
        """State B: adapter_combo visible after load with adapters present."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._adapter_combo.isVisible(), (
            "adapter_combo must be visible after adapters are loaded"
        )

    def test_state_b_adapters_loaded_unavailable_hidden(self, qtbot, monkeypatch):
        """State B: unavailable_frame hidden after load with adapters present."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert not dlg._adapter_unavailable_frame.isVisible(), (
            "unavailable_frame must be hidden after adapters are loaded"
        )

    def test_state_b_no_adapters_combo_hidden(self, qtbot, monkeypatch):
        """State B (empty): adapter_combo still hidden when no adapters returned."""
        dlg = _make_dialog(qtbot, monkeypatch, [])
        assert not dlg._adapter_combo.isVisible(), (
            "adapter_combo must remain hidden when no adapters available"
        )

    def test_state_b_no_adapters_unavailable_shown(self, qtbot, monkeypatch):
        """State B (empty): unavailable_frame still shown when no adapters returned."""
        dlg = _make_dialog(qtbot, monkeypatch, [])
        assert dlg._adapter_unavailable_frame.isVisible(), (
            "unavailable_frame must remain shown when no adapters available"
        )

    def test_state_c_adapter_change_combo_still_shown(self, qtbot, monkeypatch):
        """State C: adapter_combo stays visible after an adapter selection change."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        dlg._on_adapter_changed(1)
        assert dlg._adapter_combo.isVisible(), (
            "adapter_combo must stay visible after adapter selection change"
        )

    def test_state_c_adapter_change_unavailable_still_hidden(self, qtbot, monkeypatch):
        """State C: unavailable_frame stays hidden after an adapter selection change."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        dlg._on_adapter_changed(1)
        assert not dlg._adapter_unavailable_frame.isVisible(), (
            "unavailable_frame must stay hidden after adapter selection change"
        )


# ---------------------------------------------------------------------------
# §2 FR-C3: _refresh_adapter_mismatch_annotation — reads from client.get_status()
# ---------------------------------------------------------------------------

def _dialog_with_adapters(qtbot, monkeypatch, adapter_warning):
    """Create a shown dialog with adapters loaded and a specific adapter_warning in get_status."""
    from tincan_gui.settings_dialog import SettingsDialog
    monkeypatch.setattr(TincandClient, "get_adapters", lambda self: _TWO_ADAPTERS)
    monkeypatch.setattr(
        TincandClient, "get_status",
        lambda self: {"connected": False, "adapter_warning": adapter_warning},
    )
    client = TincandClient.__new__(TincandClient)
    dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


class TestRefreshAdapterMismatchAnnotationNew:
    """_refresh_adapter_mismatch_annotation() reads adapter_warning from client.get_status()."""

    def test_annotation_shown_when_adapter_warning_non_empty(self, qtbot, monkeypatch):
        """Annotation label is visible when client reports a non-empty adapter_warning."""
        dlg = _dialog_with_adapters(qtbot, monkeypatch, "iPhone on hci0. Use hci1.")
        dlg._refresh_adapter_mismatch_annotation()
        assert dlg._adapter_mismatch_annotation.isVisible(), (
            "_adapter_mismatch_annotation must show when adapter_warning is non-empty"
        )

    def test_annotation_text_set_to_warning(self, qtbot, monkeypatch):
        """Annotation label text matches the adapter_warning from get_status()."""
        warning = "iPhone on hci0 (no SCO). Connect to hci1."
        dlg = _dialog_with_adapters(qtbot, monkeypatch, warning)
        dlg._refresh_adapter_mismatch_annotation()
        assert dlg._adapter_mismatch_annotation.text() == warning

    def test_annotation_hidden_when_adapter_warning_empty(self, qtbot, monkeypatch):
        """Annotation label is hidden when adapter_warning is empty string."""
        dlg = _dialog_with_adapters(qtbot, monkeypatch, "")
        dlg._adapter_mismatch_annotation.show()  # pre-show to verify hide
        dlg._refresh_adapter_mismatch_annotation()
        assert not dlg._adapter_mismatch_annotation.isVisible(), (
            "_adapter_mismatch_annotation must hide when adapter_warning is empty"
        )

    def test_annotation_hidden_when_adapter_warning_absent(self, qtbot, monkeypatch):
        """Annotation label is hidden when get_status() returns no adapter_warning key."""
        from tincan_gui.settings_dialog import SettingsDialog
        monkeypatch.setattr(TincandClient, "get_adapters", lambda self: _TWO_ADAPTERS)
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        client = TincandClient.__new__(TincandClient)
        dlg = SettingsDialog(client=client)
        qtbot.addWidget(dlg)
        dlg._adapter_mismatch_annotation.show()  # pre-show
        dlg._refresh_adapter_mismatch_annotation()
        assert not dlg._adapter_mismatch_annotation.isVisible()

    def test_annotation_hidden_when_no_adapters_list(self, qtbot, monkeypatch):
        """Guard: annotation hidden when _adapters_list is empty (no adapters loaded)."""
        from tincan_gui.settings_dialog import SettingsDialog
        monkeypatch.setattr(TincandClient, "get_adapters", lambda self: [])
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"adapter_warning": "some warning"},
        )
        client = TincandClient.__new__(TincandClient)
        dlg = SettingsDialog(client=client)
        qtbot.addWidget(dlg)
        dlg._adapter_mismatch_annotation.show()  # pre-show
        dlg._adapters_list = []
        dlg._refresh_adapter_mismatch_annotation()
        assert not dlg._adapter_mismatch_annotation.isVisible(), (
            "annotation must be suppressed when _adapters_list is empty"
        )

    def test_annotation_hidden_when_get_status_raises(self, qtbot, monkeypatch):
        """Annotation hidden when client.get_status() raises an exception."""
        def _raises(self):
            raise RuntimeError("D-Bus unavailable")
        from tincan_gui.settings_dialog import SettingsDialog
        monkeypatch.setattr(TincandClient, "get_adapters", lambda self: _TWO_ADAPTERS)
        monkeypatch.setattr(TincandClient, "get_status", _raises)
        client = TincandClient.__new__(TincandClient)
        dlg = SettingsDialog(client=client)
        qtbot.addWidget(dlg)
        dlg._adapter_mismatch_annotation.show()  # pre-show
        dlg._refresh_adapter_mismatch_annotation()
        assert not dlg._adapter_mismatch_annotation.isVisible(), (
            "annotation must hide when get_status raises"
        )


# ---------------------------------------------------------------------------
# §3 FR-D: compose-new button disabled at startup + click signal guard
# ---------------------------------------------------------------------------

class TestComposeNewDisabledAtStartup:
    """Compose-new (+) button is disabled until a device connects."""

    def test_button_starts_disabled(self, qtbot):
        from tincan_gui.conversation_list import ConversationListWidget
        w = ConversationListWidget()
        qtbot.addWidget(w)
        plus_btns = [b for b in w.findChildren(QToolButton) if b.text() == "+"]
        assert plus_btns, "No '+' QToolButton found"
        assert not plus_btns[0].isEnabled(), "Compose button must start disabled"

    def test_disabled_tooltip_mentions_iphone_or_connect(self, qtbot):
        from tincan_gui.conversation_list import ConversationListWidget
        w = ConversationListWidget()
        qtbot.addWidget(w)
        plus_btn = next(b for b in w.findChildren(QToolButton) if b.text() == "+")
        tip = plus_btn.toolTip().lower()
        assert "iphone" in tip or "connect" in tip, (
            f"Disabled tooltip must explain how to enable; got {plus_btn.toolTip()!r}"
        )

    def test_click_does_not_emit_signal_when_disabled(self, qtbot):
        from tincan_gui.conversation_list import ConversationListWidget
        w = ConversationListWidget()
        qtbot.addWidget(w)
        signals = []
        w.compose_new_requested.connect(lambda: signals.append(1))
        plus_btn = next(b for b in w.findChildren(QToolButton) if b.text() == "+")
        assert not plus_btn.isEnabled(), "precondition: button is disabled"
        plus_btn.click()
        assert signals == [], "compose_new_requested must not emit when button is disabled"

    def test_enabled_after_set_compose_new_enabled_true(self, qtbot):
        from tincan_gui.conversation_list import ConversationListWidget
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.set_compose_new_enabled(True)
        plus_btn = next(b for b in w.findChildren(QToolButton) if b.text() == "+")
        assert plus_btn.isEnabled(), "Compose button must be enabled after set_compose_new_enabled(True)"

    def test_tooltip_reverts_to_new_conversation_when_enabled(self, qtbot):
        from tincan_gui.conversation_list import ConversationListWidget
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.set_compose_new_enabled(True)
        plus_btn = next(b for b in w.findChildren(QToolButton) if b.text() == "+")
        assert plus_btn.toolTip() == "New conversation"


# ---------------------------------------------------------------------------
# §4 FR-D: MainWindow wiring — set_compose_new_enabled called correctly
# ---------------------------------------------------------------------------

class TestMainWindowComposeWiring:
    """MainWindow wires compose-new state to daemon connection signals."""

    def _make_window(self, qtbot, monkeypatch, connected=False):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {
                "connected": connected,
                "device_address": "D0:6B:78:33:46:20",
                "device_name": "iPhone",
            },
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        return window

    def test_on_daemon_connected_enables_compose(self, qtbot, monkeypatch):
        window = self._make_window(qtbot, monkeypatch, connected=False)
        assert not window._conv_list._compose_btn.isEnabled(), (
            "compose must be disabled when disconnected"
        )
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"connected": True, "device_name": "iPhone"},
        )
        window._on_daemon_connected("D0:6B:78:33:46:20")
        assert window._conv_list._compose_btn.isEnabled(), (
            "_on_daemon_connected must enable compose-new button"
        )

    def test_on_daemon_disconnected_disables_compose(self, qtbot, monkeypatch):
        window = self._make_window(qtbot, monkeypatch, connected=True)
        window._conv_list.set_compose_new_enabled(True)
        window._on_daemon_disconnected()
        assert not window._conv_list._compose_btn.isEnabled(), (
            "_on_daemon_disconnected must disable compose-new button"
        )

    def test_on_daemon_disconnected_sets_connection_tooltip(self, qtbot, monkeypatch):
        window = self._make_window(qtbot, monkeypatch, connected=False)
        window._on_daemon_disconnected()
        tip = window._conv_list._compose_btn.toolTip().lower()
        assert "connect" in tip or "iphone" in tip, (
            f"Disconnected tooltip must explain connection requirement; got {tip!r}"
        )

    def test_sync_daemon_state_enables_compose_when_connected(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"connected": True, "device_address": "D0:6B:78:33:46:20"},
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window._conv_list.set_compose_new_enabled(False)  # reset to known state
        window._sync_daemon_state()
        assert window._conv_list._compose_btn.isEnabled(), (
            "_sync_daemon_state must enable compose when status.connected=True"
        )

    def test_sync_daemon_state_disables_compose_when_disconnected(self, qtbot, monkeypatch):
        from tincan_gui.main import MainWindow
        monkeypatch.setattr(
            TincandClient, "get_status",
            lambda self: {"connected": False},
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window._conv_list.set_compose_new_enabled(True)  # reset to known state
        window._sync_daemon_state()
        assert not window._conv_list._compose_btn.isEnabled(), (
            "_sync_daemon_state must disable compose when status.connected=False"
        )


# ---------------------------------------------------------------------------
# §5 FR-C2: _first_valid_icon — theme hit / all-miss
# ---------------------------------------------------------------------------

class TestFirstValidIcon:
    """_first_valid_icon returns the first non-null theme icon or a null QIcon."""

    def test_returns_non_null_when_theme_name_hits(self, qtbot):
        from tincan_gui.main import _first_valid_icon
        from PySide6.QtGui import QIcon
        from unittest.mock import MagicMock
        fake_icon = MagicMock(spec=QIcon)
        fake_icon.isNull.return_value = False
        with patch("tincan_gui.main.QIcon.fromTheme", return_value=fake_icon):
            result = _first_valid_icon("configure", "preferences-system")
        assert not result.isNull(), (
            "_first_valid_icon must return the first non-null icon from the theme"
        )

    def test_returns_null_icon_when_all_names_miss(self, qtbot):
        from tincan_gui.main import _first_valid_icon
        from PySide6.QtGui import QIcon
        from unittest.mock import MagicMock
        null_icon = MagicMock(spec=QIcon)
        null_icon.isNull.return_value = True
        with patch("tincan_gui.main.QIcon.fromTheme", return_value=null_icon):
            result = _first_valid_icon("configure", "preferences-system", "emblem-system")
        assert result.isNull(), (
            "_first_valid_icon must return a null QIcon when all theme names miss"
        )

    def test_stops_at_first_non_null(self, qtbot):
        """First non-null name is returned without checking subsequent names."""
        from tincan_gui.main import _first_valid_icon
        from PySide6.QtGui import QIcon
        from unittest.mock import MagicMock, call
        icons = {
            "miss-a": MagicMock(spec=QIcon, **{"isNull.return_value": True}),
            "hit-b": MagicMock(spec=QIcon, **{"isNull.return_value": False}),
        }
        with patch("tincan_gui.main.QIcon.fromTheme", side_effect=lambda n: icons.get(n, icons["miss-a"])) as m:
            result = _first_valid_icon("miss-a", "hit-b", "never-checked")
        assert not result.isNull()
        # 'never-checked' should never have been queried
        called_names = [c.args[0] for c in m.call_args_list]
        assert "never-checked" not in called_names, (
            "Should not query names after the first hit"
        )


# ---------------------------------------------------------------------------
# §6 FR-C1: BT combo minimumWidth >= 360 after init
# ---------------------------------------------------------------------------

class TestBtComboMinWidth:
    """Both BT combos must have minimumWidth >= 360 to avoid truncation."""

    def test_adapter_combo_min_width_at_least_360(self, qtbot, monkeypatch):
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._adapter_combo.minimumWidth() >= 360, (
            f"adapter_combo.minimumWidth()={dlg._adapter_combo.minimumWidth()} < 360"
        )

    def test_device_combo_min_width_at_least_360(self, qtbot, monkeypatch):
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._device_combo.minimumWidth() >= 360, (
            f"device_combo.minimumWidth()={dlg._device_combo.minimumWidth()} < 360"
        )

    def test_adapter_combo_min_contents_length(self, qtbot, monkeypatch):
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._adapter_combo.minimumContentsLength() >= 42, (
            f"adapter_combo.minimumContentsLength()={dlg._adapter_combo.minimumContentsLength()} < 42"
        )

    def test_device_combo_min_contents_length(self, qtbot, monkeypatch):
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS)
        assert dlg._device_combo.minimumContentsLength() >= 42, (
            f"device_combo.minimumContentsLength()={dlg._device_combo.minimumContentsLength()} < 42"
        )
