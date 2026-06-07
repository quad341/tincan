"""Persistent per-conversation message cache (JSON files under XDG data home).

Stores sent and received messages so threads survive daemon restart.
Each conversation gets one JSON file; entries are deduplicated on load
by (direction, sort_key, body) so MAP results and cached sent messages
merge without repeats.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from tincan_gui import trace as _trace

_NON_ALNUM = re.compile(r"[^0-9a-z]")
_MAX_MESSAGES = 500  # cap per conversation to bound disk use


def _cache_dir() -> Path:
    return Path.home() / ".local" / "share" / "tincan" / "msg_cache"


def _safe_name(conv_id: str) -> str:
    return _NON_ALNUM.sub("", conv_id.lower())[:40] or "unknown"


class MessageCache:
    """Read/write a per-conversation JSON message cache."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = Path(cache_dir) if cache_dir else _cache_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conv_id: str) -> Path:
        return self._dir / f"{_safe_name(conv_id)}.json"

    def get_messages(self, conv_id: str) -> list[dict[str, Any]]:
        """Return cached messages for *conv_id*, oldest first."""
        try:
            data = json.loads(self._path(conv_id).read_text())
            msgs = data.get("messages", [])
            _trace.emit("cache_read", key=conv_id, hit=1, count=len(msgs))
            return msgs
        except (OSError, json.JSONDecodeError, KeyError):
            _trace.emit("cache_read", key=conv_id, hit=0, count=0)
            return []

    def add_message(
        self,
        conv_id: str,
        direction: str,
        body: str,
        sender: str,
        timestamp: str,
        sort_key: str,
    ) -> None:
        """Append a message to the cache; noop when body is empty."""
        if not body:
            return
        messages = self.get_messages(conv_id)
        if direction == "outbound":
            if any(m.get("direction") == "outbound" and m.get("body") == body for m in messages):
                _trace.emit("cache_dedup", key=conv_id, direction=direction)
                return
        else:
            dedup_key = (direction, sort_key or timestamp, body)
            existing_keys = {
                (m.get("direction"), m.get("sort_key") or m.get("timestamp"), m.get("body"))
                for m in messages
            }
            if dedup_key in existing_keys:
                _trace.emit("cache_dedup", key=conv_id, direction=direction)
                return
        messages.append(
            {
                "direction": direction,
                "body": body,
                "sender": sender,
                "timestamp": timestamp,
                "sort_key": sort_key,
                "cached_at": time.time(),
            }
        )
        if len(messages) > _MAX_MESSAGES:
            messages = messages[-_MAX_MESSAGES:]
        try:
            self._path(conv_id).write_text(json.dumps({"messages": messages}, indent=None))
            _trace.emit("cache_write", key=conv_id, direction=direction, count=len(messages))
        except OSError:
            pass

    def merge_into(self, dest_key: str, src_key: str) -> None:
        """Copy messages from src_key into dest_key; noop when keys share a file.

        Used to migrate messages written under the wrong cache key (e.g. conv_id
        instead of current_phone) into the canonical key without data loss.
        The dedup logic in add_message prevents duplicates on repeated calls.
        """
        if _safe_name(dest_key) == _safe_name(src_key):
            return
        src_msgs = self.get_messages(src_key)
        for m in src_msgs:
            self.add_message(
                dest_key,
                m.get("direction", "inbound"),
                str(m.get("body", "")),
                str(m.get("sender", "")),
                str(m.get("timestamp", "")),
                str(m.get("sort_key") or m.get("timestamp", "")),
            )
        _trace.emit("cache_merge", dest=dest_key, src=src_key, attempted=len(src_msgs))
