"""Local structured bug report capture (tincan-il293).

Writes a JSON report file to ~/.local/share/tincan/bug-reports/bug-<epoch>.json
containing the operator's note, a timestamp, app state, and the recent trace
slice so the builder can debug from data rather than guesses.

Reports are local-only; the mayor ingests them manually.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
)

from tincan_gui.theme import apply_dark_theme


class BugReportDialog(QDialog):
    """Dialog for filing a structured bug report (tincan-dz9f7)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_theme(self)
        self.setWindowTitle("File a Bug Report")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        prompt = QLabel("Describe what looks wrong:")
        prompt_font = QFont()
        prompt_font.setPointSize(12)
        prompt.setFont(prompt_font)
        layout.addWidget(prompt)

        self._note_edit = QTextEdit()
        self._note_edit.setPlaceholderText(
            "e.g. 'sent message shows 3 bubbles instead of 1 (~14:32)'"
        )
        self._note_edit.setFixedHeight(80)
        layout.addWidget(self._note_edit)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Submit Report")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def note(self) -> str:
        """Return the trimmed note text entered by the user."""
        return self._note_edit.toPlainText().strip()


def _report_dir() -> Path:
    d = Path.home() / ".local" / "share" / "tincan" / "bug-reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_report(
    note: str,
    app_state: dict[str, Any],
    trace_events: list[dict],
) -> Path:
    """Write a structured bug report JSON file and return its path.

    Args:
        note: operator's free-text description of the symptom
        app_state: snapshot of relevant MainWindow state fields
        trace_events: recent events from tincan_gui.trace.recent_events()
    """
    epoch = int(time.time())
    report: dict[str, Any] = {
        "schema": "tincan-bug-report-v1",
        "timestamp": epoch,
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)),
        "pid": os.getpid(),
        "note": note.strip(),
        "app_state": app_state,
        "trace_enabled": bool(trace_events),
        "trace_event_count": len(trace_events),
        "trace_events": trace_events,
    }
    path = _report_dir() / f"bug-{epoch}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path
