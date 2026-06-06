"""Structured per-session JSON-lines trace (TINCAN_TRACE=1).

When TINCAN_TRACE=1, each GUI event is written as a JSON-line to
~/.local/share/tincan/traces/trace-<pid>.jsonl so the full call graph
for a session can be reconstructed from an observed symptom (e.g. '3x
echo ~12:34').

Usage:
    TINCAN_TRACE=1 python -m tincan_gui
    tail -f ~/.local/share/tincan/traces/trace-$(pgrep -f tincan_gui).jsonl | python -m json.tool

Correlation IDs (CIDs):
    Each top-level user action (send, conversation-switch, notification click)
    calls new_cid() to start a new CID.  All downstream events in that chain
    (bubble append, cache write, D-Bus call) call emit() with the same CID so
    the full chain can be joined in one grep.

Design:
    emit() is a no-op when disabled — zero production cost.
    body text is hashed (crc32 hex) so trace files don't leak message content.
    All fields are strings/ints to keep JSON serialisation simple.
"""
from __future__ import annotations

import binascii
import collections
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

_ENABLED: bool = bool(os.environ.get("TINCAN_TRACE"))
_trace_file: Any = None  # opened lazily on first emit
_CID: int = 0            # current correlation ID
_RING_SIZE: int = 200    # max events kept in memory for bug-report capture
_ring: collections.deque = collections.deque(maxlen=_RING_SIZE)


def _trace_dir() -> Path:
    return Path.home() / ".local" / "share" / "tincan" / "traces"


def _open_trace_file() -> Any:
    global _trace_file
    if _trace_file is None:
        d = _trace_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"trace-{os.getpid()}.jsonl"
        _trace_file = path.open("a", buffering=1)  # line-buffered
        emit("trace_start", path=str(path), pid=os.getpid())
    return _trace_file


def body_hash(text: str) -> str:
    """Return 8-char crc32 hex of text — identifies without revealing content."""
    return f"{binascii.crc32(text.encode()) & 0xFFFFFFFF:08x}"


def new_cid() -> int:
    """Start a new correlation ID for a top-level user action. Returns the new CID."""
    global _CID
    _CID += 1
    return _CID


def current_cid() -> int:
    """Return the current correlation ID without incrementing."""
    return _CID


def emit(event: str, cid: Optional[int] = None, **fields: Any) -> None:
    """Write one JSON-line trace event. No-op when TINCAN_TRACE is not set."""
    if not _ENABLED:
        return
    rec: dict[str, Any] = {
        "ts": round(time.monotonic(), 4),
        "event": event,
        "cid": cid if cid is not None else _CID,
    }
    rec.update(fields)
    _ring.append(rec)
    try:
        _open_trace_file().write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass


def recent_events(n: int = 100) -> list[dict]:
    """Return the most recent n events from the in-memory ring buffer."""
    events = list(_ring)
    return events[-n:] if n < len(events) else events
