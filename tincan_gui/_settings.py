"""Shared QSettings factory for tincan GUI."""
from __future__ import annotations

from PySide6.QtCore import QSettings


def app_settings() -> QSettings:
    """Return the application QSettings instance (~/.config/tincan/tincan.ini)."""
    return QSettings("tincan", "tincan")


def bool_value(settings: QSettings, key: str, default: bool = True) -> bool:
    """Read a bool setting, handling PySide6 INI string coercion of 'true'/'false'."""
    raw = settings.value(key, default)
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes")
    return bool(raw)
