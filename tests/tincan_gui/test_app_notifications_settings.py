"""Tests: App Notifications settings UI.
Bead: tincan-gc2ko

Coverage:
  §1 Required: 2 seen apps → 2 row widgets rendered with correct display names
  §2 Required: Deny button clicked → set_app_filter(app_id, 'deny'); Deny active, Allow inactive
  §3 Required: get_seen_apps() returns [] → empty-state label visible; list widget hidden
  §4 Required: global mirror CB toggled → set_notifications_enabled(bool) called immediately
  §5 label_hint used as display name when present; app_id used as fallback
  §6 Allow button clicked → set_app_filter(app_id, 'allow') called
  §7 Per-app list opacity reflects global toggle state
  §8 Buttons always visible (tincan-6a8t7): row widget min-width <= dialog width even with long app IDs
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QLabel, QSystemTrayIcon

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


def _make_client(
    seen_apps: list | None = None,
    filter_enabled: bool = True,
    app_filters: dict | None = None,
) -> MagicMock:
    """Minimal TincandClient mock for App Notifications tests."""
    if seen_apps is None:
        seen_apps = []
    if app_filters is None:
        app_filters = {}
    client = MagicMock()
    client.get_seen_apps.return_value = seen_apps
    client.get_notification_filter.return_value = {
        "enabled": filter_enabled,
        "apps": app_filters,
    }
    client.set_app_filter = MagicMock()
    client.set_notifications_enabled = MagicMock()
    return client


def _make_dialog(qtbot, client=None) -> SettingsDialog:
    """Create a SettingsDialog with patched QSettings and the given client mock."""
    with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings()):
        dlg = SettingsDialog(client=client)
    qtbot.addWidget(dlg)
    return dlg


_TWO_APPS = [
    {"app_id": "com.whatsapp", "label_hint": "WhatsApp"},
    {"app_id": "com.apple.mobilesms", "label_hint": "Messages"},
]


# ---------------------------------------------------------------------------
# §1 Required: 2 seen apps → 2 row widgets with correct display names
# ---------------------------------------------------------------------------

class TestTwoSeenAppsRendersTwoRows:
    """Mock daemon returning 2 seen apps → 2 row widgets with correct labels."""

    def test_two_apps_produce_two_row_widgets(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, client=client)
        assert len(dlg._row_widgets) == 2

    def test_first_row_shows_whatsapp_label(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, client=client)
        labels = [w.text() for w in dlg._row_widgets[0].findChildren(QLabel)]
        assert any("WhatsApp" in t for t in labels)

    def test_second_row_shows_messages_label(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, client=client)
        labels = [w.text() for w in dlg._row_widgets[1].findChildren(QLabel)]
        assert any("Messages" in t for t in labels)

    def test_list_widget_not_hidden_when_apps_present(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, client=client)
        assert not dlg._list_widget.isHidden()


# ---------------------------------------------------------------------------
# §2 Required: Deny button click → set_app_filter(app_id, 'deny'); states updated
# ---------------------------------------------------------------------------

class TestDenyButtonCallsSetAppFilter:
    """Clicking Deny calls set_app_filter(app_id, 'deny'); Deny active, Allow inactive."""

    def test_deny_click_calls_set_app_filter_with_deny(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)

        dlg._row_widgets[0].deny_button.click()

        client.set_app_filter.assert_called_once_with("com.whatsapp", "deny")

    def test_deny_button_active_after_click(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)

        dlg._row_widgets[0].deny_button.click()

        assert dlg._row_widgets[0].deny_button.isChecked()

    def test_allow_button_inactive_after_deny_click(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)

        dlg._row_widgets[0].deny_button.click()

        assert not dlg._row_widgets[0].allow_button.isChecked()

    def test_deny_click_uses_correct_app_id_for_second_row(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS)
        dlg = _make_dialog(qtbot, client=client)

        dlg._row_widgets[1].deny_button.click()

        client.set_app_filter.assert_called_once_with("com.apple.mobilesms", "deny")


# ---------------------------------------------------------------------------
# §3 Required: get_seen_apps() returns [] → empty-state label visible; list hidden
# ---------------------------------------------------------------------------

class TestEmptySeenAppsShowsEmptyState:
    """get_seen_apps() returns [] → empty-state label visible; list widget hidden."""

    def test_empty_label_not_hidden_when_no_apps(self, qtbot):
        client = _make_client(seen_apps=[])
        dlg = _make_dialog(qtbot, client=client)
        assert not dlg._empty_label.isHidden()

    def test_list_widget_hidden_when_no_apps(self, qtbot):
        client = _make_client(seen_apps=[])
        dlg = _make_dialog(qtbot, client=client)
        assert dlg._list_widget.isHidden()

    def test_empty_label_text_mentions_notifications(self, qtbot):
        client = _make_client(seen_apps=[])
        dlg = _make_dialog(qtbot, client=client)
        assert "notification" in dlg._empty_label.text().lower()


# ---------------------------------------------------------------------------
# §4 Required: global mirror CB toggled → set_notifications_enabled(bool)
# ---------------------------------------------------------------------------

class TestGlobalCheckboxCallsSetNotificationsEnabled:
    """Toggling mirror CB immediately calls set_notifications_enabled."""

    def test_uncheck_calls_set_notifications_enabled_false(self, qtbot):
        client = _make_client(filter_enabled=True)
        dlg = _make_dialog(qtbot, client=client)
        client.set_notifications_enabled.reset_mock()

        dlg._mirror_cb.setChecked(False)

        client.set_notifications_enabled.assert_called_once_with(False)

    def test_recheck_calls_set_notifications_enabled_true(self, qtbot):
        client = _make_client(filter_enabled=False)
        dlg = _make_dialog(qtbot, client=client)
        client.set_notifications_enabled.reset_mock()

        dlg._mirror_cb.setChecked(True)

        client.set_notifications_enabled.assert_called_once_with(True)


# ---------------------------------------------------------------------------
# §5 label_hint takes precedence; app_id used as fallback
# ---------------------------------------------------------------------------

class TestLabelHintPrecedence:
    """label_hint is used as display name; app_id used as fallback when missing."""

    def test_label_hint_shown_when_present(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)
        labels = [w.text() for w in dlg._row_widgets[0].findChildren(QLabel)]
        assert any("WhatsApp" in t for t in labels)

    def test_app_id_used_as_fallback_when_no_label_hint(self, qtbot):
        seen = [{"app_id": "com.example.myapp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)
        labels = [w.text() for w in dlg._row_widgets[0].findChildren(QLabel)]
        assert any("com.example.myapp" in t for t in labels)


# ---------------------------------------------------------------------------
# §6 Allow button click → set_app_filter(app_id, 'allow') called
# ---------------------------------------------------------------------------

class TestAllowButtonCallsSetAppFilter:
    """Clicking Allow calls set_app_filter(app_id, 'allow')."""

    def test_allow_click_calls_set_app_filter_with_allow(self, qtbot):
        seen = [{"app_id": "com.whatsapp", "label_hint": "WhatsApp"}]
        client = _make_client(seen_apps=seen, app_filters={"com.whatsapp": "deny"})
        dlg = _make_dialog(qtbot, client=client)

        dlg._row_widgets[0].allow_button.click()

        client.set_app_filter.assert_called_once_with("com.whatsapp", "allow")


# ---------------------------------------------------------------------------
# §7 Per-app list opacity reflects global toggle state
# ---------------------------------------------------------------------------

class TestPerAppListOpacityState:
    """_opacity_effect: 1.0 when mirror CB checked, 0.5 when unchecked."""

    def test_opacity_reduced_when_global_unchecked(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS, filter_enabled=True)
        dlg = _make_dialog(qtbot, client=client)
        client.set_notifications_enabled.reset_mock()

        dlg._mirror_cb.setChecked(False)

        assert dlg._opacity_effect.opacity() < 1.0

    def test_opacity_full_when_global_checked(self, qtbot):
        client = _make_client(seen_apps=_TWO_APPS, filter_enabled=False)
        dlg = _make_dialog(qtbot, client=client)
        client.set_notifications_enabled.reset_mock()

        dlg._mirror_cb.setChecked(True)

        assert dlg._opacity_effect.opacity() == 1.0


# ---------------------------------------------------------------------------
# §8 Buttons always visible (tincan-6a8t7)
# ---------------------------------------------------------------------------

class TestAppRowButtonsAlwaysVisible:
    """Allow/Deny buttons must not be pushed off-screen by a long app ID label.

    Root cause: _AppRowWidget used addStretch() between label and buttons,
    giving the label its full natural text width before placing buttons.
    With a long app ID (e.g. 'com.apple.mobilecal') the row minimum width
    could exceed the dialog width, causing horizontal scroll to reveal buttons.

    Fix: give the label a stretch factor of 1 with setMinimumWidth(0) so it
    fills available space but can shrink; buttons retain their minimum sizes.
    """

    def test_row_minimum_width_does_not_exceed_dialog_minimum(self, qtbot):
        long_app_id = "com.verylongcompanyname.app.notification.service.extended"
        seen = [{"app_id": long_app_id, "label_hint": "LongApp"}]
        client = _make_client(seen_apps=seen)
        dlg = _make_dialog(qtbot, client=client)

        row = dlg._row_widgets[0]
        row_min_width = row.minimumSizeHint().width()
        dialog_min_width = dlg.minimumWidth()  # 400 per setMinimumSize

        assert row_min_width <= dialog_min_width, (
            f"Row minimum width {row_min_width}px exceeds dialog minimum "
            f"{dialog_min_width}px — Allow/Deny buttons would be off-screen"
        )

    def test_allow_button_visible_geometry_in_narrow_row(self, qtbot):
        from tincan_gui.settings_dialog import _AppRowWidget
        long_app_id = "com.verylongcompanyname.app.notification.service.extended"
        row = _AppRowWidget(long_app_id, "LongApp", "allow", None, False)
        qtbot.addWidget(row)
        row.resize(400, row.minimumSizeHint().height() or 36)
        row.show()
        qtbot.waitExposed(row)

        allow_btn = row.allow_button
        btn_right = allow_btn.x() + allow_btn.width()
        assert btn_right <= row.width(), (
            f"Allow button right edge ({btn_right}px) exceeds row width ({row.width()}px)"
        )
