"""Shared QSettings factory for tincan GUI."""
from __future__ import annotations

from PySide6.QtCore import QSettings


def app_settings() -> QSettings:
    """Return the application QSettings instance (~/.config/tincan/tincan.ini)."""
    return QSettings("tincan", "tincan")
