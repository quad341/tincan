"""Shared QSettings factory for tincan GUI."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QSettings

_LOG = logging.getLogger(__name__)
_HOME_WARNED = False


def app_settings() -> QSettings:
    """Return the application QSettings instance (~/.config/tincan/tincan.ini).

    Uses Path.home() (reads /etc/passwd) rather than QSettings("tincan","tincan")
    ($HOME env) so settings persist correctly when launched from a rig shell that
    overrides HOME (tincan-3s41m / OQ1 hardening).
    """
    global _HOME_WARNED
    if not _HOME_WARNED:
        _HOME_WARNED = True
        passwd_home = Path.home()
        env_home_str = os.environ.get("HOME", "")
        if env_home_str and Path(env_home_str) != passwd_home:
            _LOG.warning(
                "HOME env (%s) differs from /etc/passwd home (%s). "
                "Using /etc/passwd path for settings.",
                env_home_str,
                passwd_home,
            )
    return QSettings(
        str(Path.home() / ".config" / "tincan" / "tincan.ini"),
        QSettings.Format.IniFormat,
    )


def bool_value(settings: QSettings, key: str, default: bool = True) -> bool:
    """Read a bool setting, handling PySide6 INI string coercion of 'true'/'false'."""
    raw = settings.value(key, default)
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes")
    return bool(raw)
