"""Dev-mode log capture and exception surfacing.

Gate via the TINCAN_DEBUG=1 environment variable. Nothing in this module
changes production behavior when the variable is unset.

Usage (already wired in tincan_gui.main.main()):

    TINCAN_DEBUG=1 python -m tincan_gui

When active:
  - sys.excepthook shows a QMessageBox.critical popup for unhandled exceptions.
  - A RecentLogBuffer handler (WARNING+) accumulates recent log records so the
    Settings → Developer section can display them inline.
"""
from __future__ import annotations

import logging
import sys
import traceback
from collections import deque
from typing import Optional

_MAX_RECORDS = 200


class RecentLogBuffer(logging.Handler):
    """In-process ring buffer of recent log records (WARNING and above)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self._records: deque[logging.LogRecord] = deque(maxlen=_MAX_RECORDS)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)

    def get_text(self) -> str:
        if not self._records:
            return "(no recent warnings)"
        return "\n".join(self.format(r) for r in self._records)


_buffer: Optional[RecentLogBuffer] = None


def install() -> None:
    """Attach RecentLogBuffer to the root logger. Idempotent."""
    global _buffer
    if _buffer is not None:
        return
    _buffer = RecentLogBuffer()
    logging.getLogger().addHandler(_buffer)


def get_recent_logs() -> str:
    """Return recent WARNING+ log records as a formatted multi-line string."""
    if _buffer is None:
        return "(debug logging not enabled — set TINCAN_DEBUG=1)"
    return _buffer.get_text()


def _show_popup(text: str) -> None:
    """Show a blocking critical dialog for an unhandled exception.

    Extracted to a module-level function so tests can replace it:

        monkeypatch.setattr(debug_log, "_show_popup", lambda t: None)
    """
    from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: PLC0415
    if QApplication.instance():
        QMessageBox.critical(None, "Unhandled Exception", text[:3000])


def install_excepthook() -> None:
    """Override sys.excepthook to show a QMessageBox for unhandled exceptions.

    The original hook (stderr print) still fires first so logs are never lost.
    The popup is delegated to _show_popup() which tests can patch to a no-op.
    """
    _orig = sys.excepthook

    def _hook(exc_type: type, exc_value: BaseException, exc_tb: object) -> None:
        _orig(exc_type, exc_value, exc_tb)
        try:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _show_popup(text)
        except Exception:  # noqa: BLE001
            pass  # never recurse into the hook

    sys.excepthook = _hook
