"""Qt-free settings shim for tincand: configparser-backed DaemonSettings.

Provides the same call surface as QSettings so notification_filter.py and
other daemon code can read/write the shared tincan.ini without importing Qt.
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path


def _default_path() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "tincan"
        / "tincan.ini"
    )


class DaemonSettings:
    """QSettings-compatible wrapper over a configparser INI file."""

    def __init__(self) -> None:
        self._parser = configparser.ConfigParser()
        self._parser.optionxform = str  # preserve case for app-id keys
        self._path = _default_path()
        self._group_stack: list[str] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_section(self) -> str:
        return "/".join(self._group_stack) if self._group_stack else "General"

    def _split_key(self, key: str) -> tuple[str, str]:
        """Split a QSettings-style key into (section, option).

        Prepends the active group prefix when a group is open. Uses
        rsplit("/", 1) so nested paths like notifications/app_filter/bundle.id
        map to section=notifications/app_filter, option=bundle.id.
        """
        full_key = "/".join(self._group_stack) + "/" + key if self._group_stack else key
        if "/" in full_key:
            section, option = full_key.rsplit("/", 1)
        else:
            section, option = "General", full_key
        return section, option

    # ------------------------------------------------------------------
    # QSettings-compatible API
    # ------------------------------------------------------------------

    def value(self, key: str, default=None, type=None):
        """Return the stored value for *key*, coerced to *type*, or *default*."""
        self._parser.read(self._path)
        section, option = self._split_key(key)
        if not self._parser.has_option(section, option):
            return default
        if type is bool:
            return self._parser.getboolean(section, option)
        raw = self._parser.get(section, option)
        if type is int:
            return int(raw)
        return raw

    def setValue(self, key: str, value) -> None:
        """Store *value* for *key* in memory (call sync() to flush to disk)."""
        self._parser.read(self._path)
        section, option = self._split_key(key)
        if not self._parser.has_section(section):
            self._parser.add_section(section)
        if isinstance(value, bool):
            self._parser.set(section, option, "true" if value else "false")
        else:
            self._parser.set(section, option, str(value))

    def sync(self) -> None:
        """Atomically flush the in-memory parser to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            self._parser.write(fh)
        os.replace(tmp, self._path)
        self._path.chmod(0o600)

    def beginGroup(self, group: str) -> None:
        """Push *group* onto the group stack (QSettings.beginGroup semantics)."""
        self._group_stack.append(group)

    def endGroup(self) -> None:
        """Pop the most-recent group; no-op when stack is empty."""
        if self._group_stack:
            self._group_stack.pop()

    def childKeys(self) -> list[str]:
        """Return option names in the current section."""
        self._parser.read(self._path)
        section = self._current_section()
        if not self._parser.has_section(section):
            return []
        return list(self._parser.options(section))


def app_settings() -> DaemonSettings:
    """Return a fresh DaemonSettings instance (stateless, like QSettings on Linux)."""
    return DaemonSettings()
