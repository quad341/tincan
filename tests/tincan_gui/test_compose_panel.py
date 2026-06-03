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

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QPushButton, QToolButton

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
