"""Tests: ComposePanel send-error bar — visibility, retry, dismiss, accessibility.
Bead: tincan-klpm

Coverage:
  §3 Send failure: error bar shown
     - show_send_error() makes error bar visible
     - show_send_error() stores failed text for retry
     - hide_send_error() hides error bar
     - hide_send_error() clears stored retry text
     - Dismiss button click hides the error bar
     - Retry button click hides the error bar and restores text to input
  §4 Error bar accessibility
     - Error bar has accessible name 'Send error notification'
     - Error bar has QAccessible.Role.Alert
     - Retry button accessible name is 'Retry sending message'
     - Dismiss button accessible name is 'Dismiss send error'
"""
from __future__ import annotations

from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QToolButton

from tincan_gui.compose_panel import ComposePanel

# ---------------------------------------------------------------------------
# §3 Send failure: error bar shown
# ---------------------------------------------------------------------------

class TestErrorBarVisibility:
    """show_send_error() and hide_send_error() toggle bar visibility.

    isHidden() reflects the explicit hide/show state regardless of whether
    the parent widget is on-screen — correct for headless unit tests.
    """

    def test_error_bar_hidden_by_default(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        assert panel._error_bar.isHidden()

    def test_show_send_error_makes_bar_not_hidden(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Hello")
        assert not panel._error_bar.isHidden()

    def test_hide_send_error_hides_bar(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Hello")
        panel.hide_send_error()
        assert panel._error_bar.isHidden()

    def test_show_stores_failed_text(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Try again text")
        assert panel._retry_text == "Try again text"

    def test_hide_clears_retry_text(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Stored")
        panel.hide_send_error()
        assert panel._retry_text == ""

    def test_show_sets_focus_to_retry_button(self, qtbot):
        # hasFocus() requires an OS-active window; focusWidget() works offscreen.
        panel = ComposePanel()
        panel.show()
        qtbot.addWidget(panel)
        panel.show_send_error("Failed message")
        assert panel.focusWidget() is panel._retry_btn


class TestDismissButton:
    """Clicking the Dismiss (×) button hides the error bar."""

    def _find_dismiss(self, panel: ComposePanel) -> QToolButton:
        btns = panel._error_bar.findChildren(QToolButton)
        for btn in btns:
            if btn.text() == "×":
                return btn
        raise AssertionError("Dismiss button not found in error bar")

    def test_dismiss_button_exists_in_error_bar(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        dismiss = self._find_dismiss(panel)
        assert dismiss is not None

    def test_dismiss_click_hides_error_bar(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Oops")
        assert not panel._error_bar.isHidden()
        dismiss = self._find_dismiss(panel)
        dismiss.click()
        assert panel._error_bar.isHidden()

    def test_dismiss_click_clears_retry_text(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Oops")
        dismiss = self._find_dismiss(panel)
        dismiss.click()
        assert panel._retry_text == ""


class TestRetryButton:
    """Retry button hides the error bar and restores the failed text to the input."""

    def test_retry_hides_error_bar(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("Msg")
        # Intercept the re-send signal so the test doesn't need a live daemon.
        emitted = []
        panel.send_requested.connect(emitted.append)
        panel._retry_btn.click()
        assert panel._error_bar.isHidden()

    def test_retry_re_emits_send_requested_with_original_text(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("retry me")
        sent = []
        panel.send_requested.connect(sent.append)
        panel._retry_btn.click()
        assert sent == ["retry me"]

    def test_retry_clears_error_bar_retry_text(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.show_send_error("retry me")
        panel.send_requested.connect(lambda _: None)   # absorb signal
        panel._retry_btn.click()
        assert panel._retry_text == ""


# ---------------------------------------------------------------------------
# §4 Error bar accessibility
# ---------------------------------------------------------------------------

class TestErrorBarAccessibility:
    """Error bar widget has accessible name and role expected by AT."""

    def test_error_bar_accessible_name_is_send_error_notification(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        assert panel._error_bar.accessibleName() == "Send error notification"

    def test_error_bar_accessible_description_mentions_failed(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        desc = panel._error_bar.accessibleDescription()
        assert "failed" in desc.lower() or "send" in desc.lower()

    def test_error_bar_role_is_alert_message(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        iface = QAccessible.queryAccessibleInterface(panel._error_bar)
        assert iface is not None
        assert iface.role() == QAccessible.Role.AlertMessage


class TestRetryButtonAccessibility:
    """Retry button accessible name is discoverable by AT."""

    def test_retry_button_accessible_name(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        assert panel._retry_btn.accessibleName() == "Retry sending message"


class TestDismissButtonAccessibility:
    """Dismiss button accessible name is discoverable by AT."""

    def _find_dismiss(self, panel: ComposePanel) -> QToolButton:
        for btn in panel._error_bar.findChildren(QToolButton):
            if btn.text() == "×":
                return btn
        raise AssertionError("Dismiss button not found")

    def test_dismiss_button_accessible_name(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        dismiss = self._find_dismiss(panel)
        assert dismiss.accessibleName() == "Dismiss send error"


# ---------------------------------------------------------------------------
# §5 Pure functions: _is_ucs2 and _sms_segments (tincan-7qzj)
# ---------------------------------------------------------------------------

from tincan_gui.compose_panel import _is_ucs2, _sms_segments  # noqa: E402


class TestIsUcs2:
    """_is_ucs2() returns True only when text contains non-GSM-7 characters."""

    def test_empty_string_is_not_ucs2(self):
        assert _is_ucs2("") is False

    def test_pure_ascii_is_not_ucs2(self):
        assert _is_ucs2("Hello, world!") is False

    def test_gsm7_euro_sign_is_not_ucs2(self):
        assert _is_ucs2("€") is False

    def test_gsm7_inverted_exclamation_is_not_ucs2(self):
        assert _is_ucs2("¡") is False

    def test_gsm7_a_umlaut_is_not_ucs2(self):
        assert _is_ucs2("ä") is False

    def test_emoji_requires_ucs2(self):
        assert _is_ucs2("😀") is True

    def test_mixed_ascii_and_emoji_requires_ucs2(self):
        assert _is_ucs2("Hello 😀") is True

    def test_cjk_character_requires_ucs2(self):
        assert _is_ucs2("中") is True


class TestSmsSegments:
    """_sms_segments() returns (chars, segments, chars_in_last) with GSM-7 or UCS-2 limits."""

    def test_empty_returns_all_zeros(self):
        assert _sms_segments("") == (0, 0, 0)

    def test_single_ascii_char_is_one_segment(self):
        assert _sms_segments("A") == (1, 1, 1)

    def test_exactly_160_ascii_chars_is_one_segment(self):
        assert _sms_segments("A" * 160) == (160, 1, 160)

    def test_161_ascii_chars_splits_into_two_segments(self):
        total, parts, last = _sms_segments("A" * 161)
        assert total == 161
        assert parts == 2
        assert last == 8  # 161 - 153

    def test_306_ascii_chars_fills_two_segments_exactly(self):
        assert _sms_segments("A" * 306) == (306, 2, 153)

    def test_307_ascii_chars_needs_three_segments(self):
        total, parts, last = _sms_segments("A" * 307)
        assert total == 307
        assert parts == 3
        assert last == 1  # 307 - 2*153

    def test_single_emoji_is_ucs2_one_segment(self):
        assert _sms_segments("😀") == (1, 1, 1)

    def test_exactly_70_emojis_is_one_segment(self):
        assert _sms_segments("😀" * 70) == (70, 1, 70)

    def test_71_emojis_splits_into_two_ucs2_segments(self):
        total, parts, last = _sms_segments("😀" * 71)
        assert total == 71
        assert parts == 2
        assert last == 4  # 71 - 67

    def test_134_emojis_fills_two_ucs2_segments_exactly(self):
        assert _sms_segments("😀" * 134) == (134, 2, 67)

    def test_135_emojis_needs_three_ucs2_segments(self):
        total, parts, last = _sms_segments("😀" * 135)
        assert total == 135
        assert parts == 3
        assert last == 1  # 135 - 2*67
