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
