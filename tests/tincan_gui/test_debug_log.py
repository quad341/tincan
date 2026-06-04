"""Tests: TINCAN_DEBUG mode — debug_log module.
Bead: tincan-tkfk  (commit c4c338b)

Coverage:
  §1 RecentLogBuffer
     - emits records at WARNING+, not at DEBUG/INFO
     - buffers up to 200 records (ring buffer)
     - get_text() returns formatted records
     - get_text() returns '(no recent warnings)' when buffer is empty

  §2 install()
     - idempotent (second call does not add second handler)
     - attaches handler to root logger
     - subsequent WARNING log appears in get_recent_logs()

  §3 install_excepthook()
     - original sys.excepthook still called when new hook fires
     - popup skipped when QApplication.instance() is None (no app running)

  §4 get_recent_logs()
     - returns sentinel string when debug logging not enabled (install not called)
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

import tincan_gui.debug_log as debug_log_mod
from tincan_gui.debug_log import RecentLogBuffer


@pytest.fixture(autouse=True)
def _reset_debug_log_state():
    """Reset module-level _buffer to None between tests."""
    original = debug_log_mod._buffer
    debug_log_mod._buffer = None
    yield
    debug_log_mod._buffer = original


@pytest.fixture(autouse=True)
def _restore_root_handlers():
    """Remove any RecentLogBuffer handlers added during tests."""
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)


@pytest.fixture(autouse=True)
def _restore_excepthook():
    original = sys.excepthook
    yield
    sys.excepthook = original


# ---------------------------------------------------------------------------
# §1 RecentLogBuffer
# ---------------------------------------------------------------------------

class TestRecentLogBufferLevel:
    """Only WARNING+ records reach the buffer (level gate enforced by logging machinery)."""

    def _buf_with_logger(self, name: str):
        buf = RecentLogBuffer()
        logger = logging.getLogger(name)
        logger.addHandler(buf)
        logger.setLevel(logging.DEBUG)
        return buf, logger

    def test_warning_record_is_buffered(self):
        buf, logger = self._buf_with_logger("test.buf.warn")
        try:
            logger.warning("warn msg")
            assert len(buf._records) == 1
        finally:
            logger.removeHandler(buf)

    def test_error_record_is_buffered(self):
        buf, logger = self._buf_with_logger("test.buf.error")
        try:
            logger.error("err msg")
            assert len(buf._records) == 1
        finally:
            logger.removeHandler(buf)

    def test_debug_record_is_not_buffered(self):
        buf, logger = self._buf_with_logger("test.buf.debug")
        try:
            logger.debug("debug msg")
            assert len(buf._records) == 0
        finally:
            logger.removeHandler(buf)

    def test_info_record_is_not_buffered(self):
        buf, logger = self._buf_with_logger("test.buf.info")
        try:
            logger.info("info msg")
            assert len(buf._records) == 0
        finally:
            logger.removeHandler(buf)

    def test_handler_level_is_warning(self):
        buf = RecentLogBuffer()
        assert buf.level == logging.WARNING


class TestRecentLogBufferCapacity:
    """Ring buffer wraps at 200 records."""

    def test_200_records_all_retained(self):
        buf = RecentLogBuffer()
        for i in range(200):
            buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, f"msg{i}", (), None))
        assert len(buf._records) == 200

    def test_201st_record_drops_oldest(self):
        buf = RecentLogBuffer()
        for i in range(201):
            buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, f"msg{i}", (), None))
        assert len(buf._records) == 200
        first_text = buf.format(buf._records[0])
        assert "msg1" in first_text

    def test_maxlen_is_200(self):
        buf = RecentLogBuffer()
        assert buf._records.maxlen == 200


class TestRecentLogBufferGetText:
    """get_text() returns formatted records or sentinel."""

    def test_empty_buffer_returns_sentinel(self):
        buf = RecentLogBuffer()
        assert buf.get_text() == "(no recent warnings)"

    def test_get_text_contains_message(self):
        buf = RecentLogBuffer()
        buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, "hello world", (), None))
        assert "hello world" in buf.get_text()

    def test_get_text_contains_multiple_lines_for_multiple_records(self):
        buf = RecentLogBuffer()
        buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, "first", (), None))
        buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, "second", (), None))
        text = buf.get_text()
        assert "first" in text
        assert "second" in text

    def test_get_text_is_newline_separated(self):
        buf = RecentLogBuffer()
        buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, "a", (), None))
        buf.emit(logging.LogRecord("t", logging.WARNING, "", 0, "b", (), None))
        lines = buf.get_text().splitlines()
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# §2 install()
# ---------------------------------------------------------------------------

class TestInstall:
    """install() attaches RecentLogBuffer to root logger, idempotent."""

    def test_install_attaches_handler_to_root_logger(self):
        from tincan_gui.debug_log import install
        install()
        root = logging.getLogger()
        assert any(isinstance(h, RecentLogBuffer) for h in root.handlers)

    def test_install_is_idempotent(self):
        from tincan_gui.debug_log import install
        install()
        install()
        root = logging.getLogger()
        count = sum(1 for h in root.handlers if isinstance(h, RecentLogBuffer))
        assert count == 1

    def test_warning_after_install_appears_in_get_recent_logs(self):
        from tincan_gui.debug_log import install, get_recent_logs
        install()
        logging.getLogger("tincan_test").warning("test warning message")
        assert "test warning message" in get_recent_logs()

    def test_second_install_does_not_create_second_buffer(self):
        from tincan_gui.debug_log import install
        install()
        buf_after_first = debug_log_mod._buffer
        install()
        assert debug_log_mod._buffer is buf_after_first


# ---------------------------------------------------------------------------
# §3 install_excepthook()
# ---------------------------------------------------------------------------

class TestInstallExcepthook:
    """install_excepthook() wraps sys.excepthook; original still fires first."""

    def test_original_excepthook_still_called(self):
        from tincan_gui.debug_log import install_excepthook
        orig_mock = MagicMock()
        sys.excepthook = orig_mock
        install_excepthook()

        try:
            raise ValueError("test exc")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)

        assert orig_mock.called

    def test_popup_skipped_when_no_qapplication(self):
        from tincan_gui.debug_log import install_excepthook
        # Use a mock for the original so nothing leaks to stderr or Qt.
        sys.excepthook = MagicMock()
        install_excepthook()

        with patch("PySide6.QtWidgets.QApplication.instance", return_value=None):
            with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
                try:
                    raise RuntimeError("no app")
                except RuntimeError as exc:
                    sys.excepthook(type(exc), exc, exc.__traceback__)

                mock_critical.assert_not_called()

    def test_new_excepthook_replaces_sys_excepthook(self):
        from tincan_gui.debug_log import install_excepthook
        original = sys.excepthook
        install_excepthook()
        assert sys.excepthook is not original


# ---------------------------------------------------------------------------
# §4 get_recent_logs()
# ---------------------------------------------------------------------------

class TestGetRecentLogs:
    """get_recent_logs() returns sentinel when install() has not been called."""

    def test_returns_sentinel_when_not_installed(self):
        from tincan_gui.debug_log import get_recent_logs
        assert debug_log_mod._buffer is None
        result = get_recent_logs()
        assert "TINCAN_DEBUG" in result or "not enabled" in result

    def test_returns_non_sentinel_after_install(self):
        from tincan_gui.debug_log import install, get_recent_logs
        install()
        result = get_recent_logs()
        assert "not enabled" not in result
