"""Tests: TitleBar toolbar button icons and _NotifRow badge (tincan-3so6e, tincan-0oxkd).

Coverage:
  §1 TitleBar — three toolbar buttons (FR-C2: QIcon.fromTheme + BMP fallback)
     - gear button has icon or BMP fallback text; does NOT use emoji font
     - bug button has icon or BMP fallback text; does NOT use emoji font
     - bell button has icon or BMP fallback text; does NOT use emoji font
  §2 _NotifRow badge
     - SMS kind badge font includes emoji families
     - app kind badge font includes emoji families
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

_FAKE_EMOJI_FAMILIES = ["FakeEmoji", "NotoColorEmoji"]
_BMP_FALLBACKS = {"⚙", "⚠", "☆"}


@pytest.fixture
def _fake_emoji_families():
    """Patch _emoji_font_families() in every module that imports it directly."""
    with patch("tincan_gui.notification_center._emoji_font_families",
               return_value=_FAKE_EMOJI_FAMILIES):
        yield _FAKE_EMOJI_FAMILIES


# ---------------------------------------------------------------------------
# §1 TitleBar toolbar button icons (FR-C2)
# ---------------------------------------------------------------------------

class TestTitleBarEmojiFontConfig:
    """TitleBar toolbar buttons use QIcon.fromTheme with BMP fallback; no emoji font."""

    def _assert_button_icon_or_bmp(self, btn, name: str) -> None:
        has_icon = not btn.icon().isNull()
        has_text = bool(btn.text())
        assert has_icon or has_text, f"{name} button has neither icon nor text"
        if has_text:
            assert btn.text() in _BMP_FALLBACKS, (
                f"{name} button text {btn.text()!r} is not a BMP fallback"
            )
            for fam in _FAKE_EMOJI_FAMILIES:
                assert fam not in btn.font().families(), (
                    f"{name} button uses emoji font family {fam!r} (should use default font)"
                )

    def test_gear_button_has_icon_or_fallback_text(self, qtbot):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        self._assert_button_icon_or_bmp(tb.gear_button, "gear")

    def test_bug_button_font_includes_emoji_families(self, qtbot, _fake_emoji_families):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        self._assert_button_icon_or_bmp(tb.bug_button, "bug")

    def test_bell_button_font_includes_emoji_families(self, qtbot, _fake_emoji_families):
        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        self._assert_button_icon_or_bmp(tb.bell_button, "bell")


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
