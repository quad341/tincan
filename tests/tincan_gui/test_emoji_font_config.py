"""Tests: toolbar button rendering + _NotifRow badge emoji font (tincan-3so6e / tincan-0oxkd).

Coverage:
  §1 TitleBar — three toolbar buttons use QIcon.fromTheme + BMP Unicode fallback
     - gear button has non-null icon OR non-empty fallback text
     - bug button has non-null icon OR non-empty fallback text
     - bell button has non-null icon OR non-empty fallback text
  §2 _NotifRow badge
     - SMS kind badge font includes emoji families
     - app kind badge font includes emoji families
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

_FAKE_EMOJI_FAMILIES = ["FakeEmoji", "NotoColorEmoji"]


@pytest.fixture
def _fake_emoji_families():
    """Patch _emoji_font_families() in every module that imports it directly."""
    with patch("tincan_gui.main._emoji_font_families", return_value=_FAKE_EMOJI_FAMILIES), \
         patch("tincan_gui.notification_center._emoji_font_families",
               return_value=_FAKE_EMOJI_FAMILIES):
        yield _FAKE_EMOJI_FAMILIES


# ---------------------------------------------------------------------------
# §1 TitleBar button rendering (QIcon.fromTheme + BMP fallback, tincan-0oxkd)
# ---------------------------------------------------------------------------

class TestTitleBarButtonRendering:
    """TitleBar toolbar buttons display either a theme icon or a BMP Unicode fallback."""

    def test_gear_button_has_icon_or_fallback_text(self, qtbot):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        btn = tb.gear_button
        assert not btn.icon().isNull() or btn.text() != "", (
            "gear button must show either a theme icon or fallback text '⚙'"
        )

    def test_bug_button_has_icon_or_fallback_text(self, qtbot):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        btn = tb.bug_button
        assert not btn.icon().isNull() or btn.text() != "", (
            "bug button must show either a theme icon or fallback text '⚠'"
        )

    def test_bell_button_has_icon_or_fallback_text(self, qtbot):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        btn = tb.bell_button
        assert not btn.icon().isNull() or btn.text() != "", (
            "bell button must show either a theme icon or fallback text '☆'"
        )


# ---------------------------------------------------------------------------
# §2 _NotifRow badge font
# ---------------------------------------------------------------------------

class TestNotifRowBadgeEmojiFontConfig:
    """_NotifRow badge QLabel uses _emoji_font_families() for emoji glyph rendering."""

    def _find_badge(self, row):
        from PySide6.QtWidgets import QLabel
        labels = row.findChildren(QLabel)
        return next((lbl for lbl in labels if lbl.text() in ("💬", "🔔")), None)

    def test_sms_badge_font_includes_emoji_families(self, qtbot, _fake_emoji_families):
        from tincan_gui.notification_center import _NotifRow
        from tincan_gui.notifications import NotificationEntry
        entry = NotificationEntry(ts=0.0, kind="sms", sender="Alice", summary="Hi",
                                  body="", conv_id="")
        row = _NotifRow(entry, dark=False)
        qtbot.addWidget(row)

        badge = self._find_badge(row)
        assert badge is not None, "SMS badge label (💬) not found in _NotifRow"
        families = badge.font().families()
        for fam in _FAKE_EMOJI_FAMILIES:
            assert fam in families, \
                f"'{fam}' missing from SMS badge font families: {families}"

    def test_app_badge_font_includes_emoji_families(self, qtbot, _fake_emoji_families):
        from tincan_gui.notification_center import _NotifRow
        from tincan_gui.notifications import NotificationEntry
        entry = NotificationEntry(ts=0.0, kind="app", sender="Gmail", summary="Email",
                                  body="", conv_id="")
        row = _NotifRow(entry, dark=False)
        qtbot.addWidget(row)

        badge = self._find_badge(row)
        assert badge is not None, "app badge label (🔔) not found in _NotifRow"
        families = badge.font().families()
        for fam in _FAKE_EMOJI_FAMILIES:
            assert fam in families, \
                f"'{fam}' missing from app badge font families: {families}"
