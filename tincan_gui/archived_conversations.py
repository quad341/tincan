"""Persistent store for archived (hidden) conversation IDs (tincan-fbb7l)."""
from __future__ import annotations

import json
from pathlib import Path


class ArchivedConversations:
    """Persist a set of archived conversation IDs to disk.

    Conversations in the archived set are hidden from the active list but
    can be viewed and restored from an 'Archived' view.
    """

    _FILENAME = "archived_conversations.json"

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = Path.home() / ".local" / "share" / "tincan"
        self._path = Path(data_dir) / self._FILENAME
        self._ids: set[str] = self._load()

    def archive(self, conv_id: str) -> None:
        self._ids.add(conv_id)
        self._save()

    def restore(self, conv_id: str) -> None:
        self._ids.discard(conv_id)
        self._save()

    def is_archived(self, conv_id: str) -> bool:
        return conv_id in self._ids

    def all_archived(self) -> set[str]:
        return set(self._ids)

    def _load(self) -> set[str]:
        try:
            return set(json.loads(self._path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return set()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(sorted(self._ids), indent=2), encoding="utf-8"
        )
