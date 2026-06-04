"""Tests: per-app notification filter settings UI (App Notifications section).
Bead: tincan-d5lae

Coverage:
  §1 Required: 2 seen apps → 2 rows rendered with correct display names
  §2 Required: toggle Allow checkbox for an app → SetAppFilter(app_id, 'deny') called
  §3 Required: GetSeenApps() returns [] → empty-state QLabel visible; list hidden
  §4 Required: global checkbox unchecked → SetNotificationsEnabled(False) called
  §5 label_hint takes precedence over app_id as display name when both present
  §6 SetNotificationsEnabled(True) called when global checkbox re-checked
  §7 Per-app list setEnabled(False) when global toggle off; setEnabled(True) when on
  §8 DBusException from GetSeenApps() handled gracefully (no crash; empty state shown)
  §9 setMinimumSize reflects 400x480
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QCheckBox, QLabel, QScrollArea, QSystemTrayIcon

from tincan_gui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(desktop_enabled: bool = True) -> MagicMock:
    s = MagicMock()
    s.value.return_value = desktop_enabled
    return s


def _make_dbus_client(
    seen_apps: list | None = None,
    filter_enabled: bool = True,
    app_filters: dict | None = None,
    raise_on_get_seen: bool = False,
) -> MagicMock:
    """Minimal dbus_client mock for App Notifications tests.

    seen_apps: list of {'app_id': ..., 'label_hint': ...} dicts
    filter_enabled: value of GetNotificationFilter()['enabled']
    app_filters: dict of {app_id: 'allow'|'deny'}
    raise_on_get_seen: simulate DBusException from get_seen_apps()
    """
    if seen_apps is None:
        seen_apps = []
    if app_filters is None:
        app_filters = {}

    client = MagicMock()

    if raise_on_get_seen:
        try:
            import dbus
            exc_cls = dbus.DBusException
        except ImportError:
            exc_cls = Exception
        client.get_seen_apps.side_effect = exc_cls("service not available")
    else:
        client.get_seen_apps.return_value = seen_apps

    client.get_notification_filter.return_value = {
        "enabled": filter_enabled,
        "apps": app_filters,
    }
    client.set_app_filter = MagicMock()
    client.set_notifications_enabled = MagicMock()

    return client


def _make_dialog(qtbot, dbus_client=None, desktop_enabled: bool = True) -> SettingsDialog:
    """Create a SettingsDialog with patched QSettings and the given dbus_client mock."""
    with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(desktop_enabled)):
        dlg = SettingsDialog(dbus_client=dbus_client)
    qtbot.addWidget(dlg)
    return dlg


_TWO_APPS = [
    {"app_id": "com.whatsapp", "label_hint": "WhatsApp"},
    {"app_id": "com.apple.mobilesms", "label_hint": "Messages"},
]


# ---------------------------------------------------------------------------
# §1 Required: 2 seen apps → 2 rows rendered with correct display names
# ---------------------------------------------------------------------------

class TestTwoSeenAppsRendersTwoRows:
    """Mock daemon returning 2 seen apps → list renders 2 rows."""

    def test_two_apps_produce_two_rows(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, dbus_client=client)

        rows = dlg.findChildren(QCheckBox)
        allow_cbs = [cb for cb in rows if "allow" in cb.text().lower() or
                     cb is getattr(dlg, "_mirror_cb", None).__class__
                     and "mirror" not in cb.text().lower()]
        # The per-app list should have exactly 2 Allow checkboxes (one per app row)
        per_app_cbs = _per_app_checkboxes(dlg)
        assert len(per_app_cbs) == 2

    def test_first_row_displays_whatsapp_label_hint(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, dbus_client=client)

        labels = _visible_name_labels(dlg)
        names = [lbl.text() for lbl in labels]
        assert any("WhatsApp" in n for n in names)

    def test_second_row_displays_messages_label_hint(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, dbus_client=client)

        labels = _visible_name_labels(dlg)
        names = [lbl.text() for lbl in labels]
        assert any("Messages" in n for n in names)

    def test_per_app_list_is_visible_when_apps_present(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, dbus_client=client)

        scroll = _app_list_scroll(dlg)
        assert scroll is not None
        assert scroll.isVisible()


# ---------------------------------------------------------------------------
# §2 Required: toggle Allow checkbox for an app → SetAppFilter called
# ---------------------------------------------------------------------------

class TestToggleAllowCallsSetAppFilter:
    """User unchecks Allow for an app → set_app_filter(app_id, 'deny') called."""

    def test_uncheck_allow_calls_set_app_filter_with_deny(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_dbus_client(seen_apps=seen, app_filters={"com.whatsapp": "allow"})
        dlg = _make_dialog(qtbot, dbus_client=client)

        per_app = _per_app_checkboxes(dlg)
        assert len(per_app) == 1
        # Checkbox starts checked (app is 'allow'); unchecking → 'deny'
        per_app[0].setChecked(False)

        client.set_app_filter.assert_called_once_with("com.whatsapp", "deny")

    def test_check_allow_calls_set_app_filter_with_allow(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_dbus_client(seen_apps=seen, app_filters={"com.whatsapp": "deny"})
        dlg = _make_dialog(qtbot, dbus_client=client)

        per_app = _per_app_checkboxes(dlg)
        assert len(per_app) == 1
        # Checkbox starts unchecked (app is 'deny'); checking → 'allow'
        per_app[0].setChecked(True)

        client.set_app_filter.assert_called_once_with("com.whatsapp", "allow")

    def test_set_app_filter_passes_correct_app_id_for_second_app(self, qtbot):
        seen = [
            {"app_id": "com.whatsapp", "label_hint": "WhatsApp"},
            {"app_id": "com.apple.mobilesms", "label_hint": "Messages"},
        ]
        client = _make_dbus_client(seen_apps=seen,
                                   app_filters={"com.whatsapp": "allow",
                                                "com.apple.mobilesms": "allow"})
        dlg = _make_dialog(qtbot, dbus_client=client)

        per_app = _per_app_checkboxes(dlg)
        assert len(per_app) == 2

        # Uncheck the second app row
        per_app[1].setChecked(False)

        client.set_app_filter.assert_called_once_with("com.apple.mobilesms", "deny")


# ---------------------------------------------------------------------------
# §3 Required: GetSeenApps() returns [] → empty-state visible; list hidden
# ---------------------------------------------------------------------------

class TestEmptySeenAppsShowsEmptyState:
    """GetSeenApps() returns [] → empty-state QLabel visible; per-app list hidden."""

    def test_empty_state_label_is_visible_when_no_apps(self, qtbot):
        client = _make_dbus_client(seen_apps=[])
        dlg = _make_dialog(qtbot, dbus_client=client)

        empty = _empty_state_label(dlg)
        assert empty is not None
        assert empty.isVisible()

    def test_per_app_scroll_hidden_or_absent_when_no_apps(self, qtbot):
        client = _make_dbus_client(seen_apps=[])
        dlg = _make_dialog(qtbot, dbus_client=client)

        scroll = _app_list_scroll(dlg)
        # Either there's no scroll area, or it's hidden
        assert scroll is None or not scroll.isVisible()

    def test_empty_state_text_mentions_notifications(self, qtbot):
        client = _make_dbus_client(seen_apps=[])
        dlg = _make_dialog(qtbot, dbus_client=client)

        empty = _empty_state_label(dlg)
        assert empty is not None
        assert "notification" in empty.text().lower()


# ---------------------------------------------------------------------------
# §4 Required: global checkbox unchecked → SetNotificationsEnabled(False)
# ---------------------------------------------------------------------------

class TestGlobalCheckboxCallsSetNotificationsEnabled:
    """Toggling global checkbox calls set_notifications_enabled immediately."""

    def test_uncheck_global_calls_set_notifications_enabled_false(self, qtbot):
        client = _make_dbus_client(filter_enabled=True)
        dlg = _make_dialog(qtbot, dbus_client=client)

        assert dlg._mirror_cb.isChecked() is True
        dlg._mirror_cb.setChecked(False)

        client.set_notifications_enabled.assert_called_once_with(False)

    def test_recheck_global_calls_set_notifications_enabled_true(self, qtbot):
        client = _make_dbus_client(filter_enabled=False)
        dlg = _make_dialog(qtbot, dbus_client=client)

        assert dlg._mirror_cb.isChecked() is False
        dlg._mirror_cb.setChecked(True)

        client.set_notifications_enabled.assert_called_once_with(True)


# ---------------------------------------------------------------------------
# §5 label_hint takes precedence over app_id as display name
# ---------------------------------------------------------------------------

class TestLabelHintPrecedence:
    """label_hint is used as display name when present; app_id used as fallback."""

    def test_label_hint_shown_when_present(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_dbus_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, dbus_client=client)

        names = [lbl.text() for lbl in _visible_name_labels(dlg)]
        assert any("WhatsApp" in n for n in names)

    def test_app_id_shown_as_fallback_when_no_label_hint(self, qtbot):
        seen = [{"app_id": "com.example.myapp"}]
        client = _make_dbus_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, dbus_client=client)

        names = [lbl.text() for lbl in _visible_name_labels(dlg)]
        assert any("com.example.myapp" in n for n in names)

    def test_label_hint_not_app_id_when_both_present(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_dbus_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, dbus_client=client)

        names = [lbl.text() for lbl in _visible_name_labels(dlg)]
        # Display name should be "WhatsApp", not "com.whatsapp"
        assert not any(n == "com.whatsapp" for n in names)
        assert any(n == "WhatsApp" for n in names)


# ---------------------------------------------------------------------------
# §6 SetNotificationsEnabled(True) called when global checkbox re-checked
# ---------------------------------------------------------------------------

class TestGlobalCheckboxRecheck:
    """Global checkbox checked from False state calls set_notifications_enabled(True)."""

    def test_recheck_after_uncheck_calls_true_then_false(self, qtbot):
        client = _make_dbus_client(filter_enabled=True)
        dlg = _make_dialog(qtbot, dbus_client=client)

        dlg._mirror_cb.setChecked(False)
        dlg._mirror_cb.setChecked(True)

        calls = [c.args[0] for c in client.set_notifications_enabled.call_args_list]
        assert calls == [False, True]


# ---------------------------------------------------------------------------
# §7 Per-app list setEnabled reflects global toggle state
# ---------------------------------------------------------------------------

class TestPerAppListEnabledState:
    """Per-app list is disabled when global toggle is off, enabled when on."""

    def test_per_app_list_disabled_when_global_unchecked(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS, filter_enabled=True)
        dlg = _make_dialog(qtbot, dbus_client=client)

        dlg._mirror_cb.setChecked(False)

        scroll = _app_list_scroll(dlg)
        assert scroll is not None
        assert not scroll.isEnabled()

    def test_per_app_list_enabled_when_global_checked(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS, filter_enabled=False)
        dlg = _make_dialog(qtbot, dbus_client=client)

        dlg._mirror_cb.setChecked(True)

        scroll = _app_list_scroll(dlg)
        assert scroll is not None
        assert scroll.isEnabled()

    def test_per_app_list_starts_disabled_when_filter_initially_off(self, qtbot):
        client = _make_dbus_client(seen_apps=_TWO_APPS, filter_enabled=False)
        dlg = _make_dialog(qtbot, dbus_client=client)

        scroll = _app_list_scroll(dlg)
        assert scroll is not None
        assert not scroll.isEnabled()


# ---------------------------------------------------------------------------
# §8 DBusException from GetSeenApps() handled gracefully
# ---------------------------------------------------------------------------

class TestDbusExceptionHandling:
    """DBusException from get_seen_apps() must not crash the dialog."""

    def test_no_crash_when_get_seen_apps_raises(self, qtbot):
        client = _make_dbus_client(raise_on_get_seen=True)
        # Must not raise
        dlg = _make_dialog(qtbot, dbus_client=client)
        assert dlg is not None

    def test_empty_state_or_error_shown_when_get_seen_apps_raises(self, qtbot):
        client = _make_dbus_client(raise_on_get_seen=True)
        dlg = _make_dialog(qtbot, dbus_client=client)

        # Either an empty-state label is shown OR the per-app scroll is absent/hidden
        empty = _empty_state_label(dlg)
        scroll = _app_list_scroll(dlg)
        has_empty = empty is not None and empty.isVisible()
        has_hidden_scroll = scroll is None or not scroll.isVisible()
        assert has_empty or has_hidden_scroll

    def test_no_per_app_rows_when_get_seen_apps_raises(self, qtbot):
        client = _make_dbus_client(raise_on_get_seen=True)
        dlg = _make_dialog(qtbot, dbus_client=client)

        assert len(_per_app_checkboxes(dlg)) == 0


# ---------------------------------------------------------------------------
# §9 setMinimumSize reflects 400x480
# ---------------------------------------------------------------------------

class TestMinimumSize:
    """setMinimumSize(400, 480) accommodates the App Notifications section."""

    def test_minimum_width_is_400(self, qtbot):
        client = _make_dbus_client()
        dlg = _make_dialog(qtbot, dbus_client=client)

        assert dlg.minimumWidth() == 400

    def test_minimum_height_is_480(self, qtbot):
        client = _make_dbus_client()
        dlg = _make_dialog(qtbot, dbus_client=client)

        assert dlg.minimumHeight() == 480


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def _per_app_checkboxes(dlg: SettingsDialog) -> list[QCheckBox]:
    """Return all QCheckBox widgets that belong to per-app rows (not the global toggles)."""
    known_cbs = {
        getattr(dlg, "_mirror_cb", None),
        getattr(dlg, "_desktop_cb", None),
        getattr(dlg, "_close_to_tray_cb", None),
    }
    return [
        cb for cb in dlg.findChildren(QCheckBox)
        if cb not in known_cbs
    ]


def _visible_name_labels(dlg: SettingsDialog) -> list[QLabel]:
    """Return QLabel widgets that look like per-app name labels (non-empty, inside scroll area)."""
    scroll = _app_list_scroll(dlg)
    if scroll is None:
        return []
    return [
        lbl for lbl in scroll.findChildren(QLabel)
        if lbl.text() and lbl.isVisible()
        # Exclude tiny muted bundle-ID labels by filtering for the primary name label
        # (builder is expected to use a larger point size for the name vs id label)
    ]


def _app_list_scroll(dlg: SettingsDialog) -> QScrollArea | None:
    """Return the per-app QScrollArea if present."""
    return getattr(dlg, "_app_list_scroll", None) or (
        dlg.findChildren(QScrollArea)[0]
        if dlg.findChildren(QScrollArea)
        else None
    )


def _empty_state_label(dlg: SettingsDialog) -> QLabel | None:
    """Return the empty-state QLabel if the builder named it _empty_state_label."""
    if hasattr(dlg, "_empty_state_label"):
        return dlg._empty_state_label
    # Fallback: search for a visible QLabel containing 'no app' or 'notification'
    for lbl in dlg.findChildren(QLabel):
        t = lbl.text().lower()
        if ("no app" in t or "no notifications" in t or "notifications will appear" in t
                or "received yet" in t):
            return lbl
    return None
