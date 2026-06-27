"""Behavioral acceptance tests: _populate_adapter_combo two-pass selection (FR-A1).
Bead: tincan-pazk7 (tincan-50sym / tincan-mybn5)

Coverage:
  §1 saved path matches adapter → selected over daemon is_selected
  §2 saved path present but no match → daemon is_selected fallback
  §3 no saved path → daemon is_selected governs
  §4 empty adapters list → disabled placeholder, item not selectable, accessible name set

All tests mock TincandClient — no real D-Bus required.
Run with: python -m pytest tests/tincan_gui/test_adapter_two_pass_50sym.py -v
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


_HCI0 = {
    "path": "/org/bluez/hci0",
    "alias": "Built-in BT",
    "address": "00:11:22:33:44:55",
    "powered": True,
    "hfp_sco_capable": False,
    "le_capable": True,
    "is_selected": False,
}
_HCI1 = {
    "path": "/org/bluez/hci1",
    "alias": "USB BT",
    "address": "AA:BB:CC:DD:EE:FF",
    "powered": True,
    "hfp_sco_capable": True,
    "le_capable": True,
    "is_selected": True,
}

_TWO_ADAPTERS = [_HCI0, _HCI1]


class _FakeSettings:
    def __init__(self, adapter_path=None):
        self._data: dict = {}
        if adapter_path is not None:
            self._data["bluetooth/adapter_path"] = adapter_path

    def value(self, key, default=None, type=None):
        return self._data.get(key, default)

    def setValue(self, key, val):
        self._data[key] = val

    def sync(self):
        pass


def _make_dialog(qtbot, monkeypatch, adapters, saved_path=None):
    monkeypatch.setattr(TincandClient, "get_adapters", lambda self: adapters)
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
    monkeypatch.setattr(
        "tincan_gui.settings_dialog.app_settings",
        lambda: _FakeSettings(saved_path),
    )
    client = TincandClient.__new__(TincandClient)
    dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


# ---------------------------------------------------------------------------
# §1 saved path matches adapter → selected over daemon is_selected
# ---------------------------------------------------------------------------

class TestSavedPathMatchesAdapter:
    """Saved bluetooth/adapter_path wins unconditionally over daemon is_selected."""

    def test_saved_hci0_wins_over_daemon_is_selected_hci1(self, qtbot, monkeypatch):
        """Saved /org/bluez/hci0 must be selected even though daemon prefers hci1."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS, saved_path="/org/bluez/hci0")
        selected = dlg._adapter_combo.currentData()
        assert selected == "/org/bluez/hci0", (
            f"Saved path hci0 must win over daemon is_selected hci1; got {selected!r}"
        )

    def test_saved_hci1_selected_when_it_matches(self, qtbot, monkeypatch):
        """Saved /org/bluez/hci1 is selected when it matches an adapter."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS, saved_path="/org/bluez/hci1")
        selected = dlg._adapter_combo.currentData()
        assert selected == "/org/bluez/hci1", (
            f"Saved path hci1 must be selected when it matches; got {selected!r}"
        )

    def test_first_match_wins_when_saved_path_appears_twice(self, qtbot, monkeypatch):
        """Only the first adapter matching the saved path is selected (saved_idx == -1 guard)."""
        dup_adapters = [
            {**_HCI0, "path": "/org/bluez/hci0", "is_selected": False},
            {**_HCI1, "path": "/org/bluez/hci0", "alias": "Duplicate hci0", "is_selected": True},
        ]
        dlg = _make_dialog(qtbot, monkeypatch, dup_adapters, saved_path="/org/bluez/hci0")
        assert dlg._adapter_combo.currentIndex() == 0, (
            "First matching adapter must be selected when saved path appears at multiple indices"
        )


# ---------------------------------------------------------------------------
# §2 saved path present but no adapter match → daemon is_selected fallback
# ---------------------------------------------------------------------------

class TestSavedPathNoMatch:
    """Unknown saved path causes fall-through to daemon is_selected."""

    def test_daemon_is_selected_used_when_saved_path_is_unknown(self, qtbot, monkeypatch):
        """Saved path for a removed adapter → fall back to daemon is_selected (hci1)."""
        dlg = _make_dialog(
            qtbot, monkeypatch, _TWO_ADAPTERS, saved_path="/org/bluez/hci99"
        )
        selected = dlg._adapter_combo.currentData()
        assert selected == "/org/bluez/hci1", (
            f"Unmatched saved path must fall back to daemon is_selected hci1; got {selected!r}"
        )


# ---------------------------------------------------------------------------
# §3 no saved path → daemon is_selected governs
# ---------------------------------------------------------------------------

class TestNoSavedPath:
    """Without a saved path, adapter with is_selected=True is chosen."""

    def test_daemon_is_selected_adapter_chosen_when_no_saved_path(self, qtbot, monkeypatch):
        """No saved path → adapter with is_selected=True (hci1) is the initial selection."""
        dlg = _make_dialog(qtbot, monkeypatch, _TWO_ADAPTERS, saved_path=None)
        selected = dlg._adapter_combo.currentData()
        assert selected == "/org/bluez/hci1", (
            f"Adapter with is_selected=True must be chosen when no saved path; got {selected!r}"
        )

    def test_index_zero_fallback_when_no_saved_path_and_no_is_selected(
        self, qtbot, monkeypatch
    ):
        """No saved path, no is_selected → index 0 is the last-resort fallback."""
        adapters = [
            {**_HCI0, "is_selected": False},
            {**_HCI1, "is_selected": False},
        ]
        dlg = _make_dialog(qtbot, monkeypatch, adapters, saved_path=None)
        assert dlg._adapter_combo.currentIndex() == 0, (
            "Index 0 must be selected when there is no saved path and no is_selected adapter"
        )


# ---------------------------------------------------------------------------
# §4 empty adapters list → disabled placeholder, not selectable, accessible name
# ---------------------------------------------------------------------------

class TestEmptyAdapterList:
    """_populate_adapter_combo([]) must set a disabled placeholder and update accessible name."""

    @pytest.fixture(autouse=True)
    def _dlg(self, qtbot, monkeypatch):
        self.dlg = _make_dialog(qtbot, monkeypatch, [], saved_path=None)

    def test_combo_is_disabled(self):
        assert not self.dlg._adapter_combo.isEnabled(), (
            "_adapter_combo must be disabled when get_adapters returns []"
        )

    def test_placeholder_item_is_present(self):
        assert self.dlg._adapter_combo.count() >= 1, (
            "At least one placeholder item must be added to the empty adapter combo"
        )

    def test_placeholder_item_is_not_selectable(self):
        item = self.dlg._adapter_combo.model().item(0)
        assert item is not None, "Placeholder model item must exist"
        assert not bool(item.flags() & Qt.ItemFlag.ItemIsEnabled), (
            "Placeholder item must not be selectable (ItemIsEnabled flag must be cleared)"
        )

    def test_accessible_name_mentions_none_found(self):
        name = self.dlg._adapter_combo.accessibleName()
        lower = name.lower()
        assert "none found" in lower or "no bluetooth" in lower or "not found" in lower, (
            f"Accessible name must communicate that no adapter was found; got {name!r}"
        )
