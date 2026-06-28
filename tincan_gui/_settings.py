"""Shared QSettings factory for tincan GUI."""
from __future__ import annotations

import logging
import os
import pwd
from pathlib import Path

from PySide6.QtCore import QSettings

_LOG = logging.getLogger(__name__)
_HOME_WARNED = False


def _account_home() -> Path:
    """Real account home from /etc/passwd, ignoring any overridden $HOME."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return Path.home()  # non-POSIX / unknown uid fallback


def app_settings() -> QSettings:
    """Return the application QSettings instance (~/.config/tincan/tincan.ini).

    Resolves the home directory from /etc/passwd via pwd.getpwuid (ignoring any
    overridden $HOME) rather than QSettings("tincan","tincan") ($HOME env) so
    settings persist correctly when launched from a rig shell that overrides
    HOME (tincan-3s41m / OQ1 hardening).
    """
    global _HOME_WARNED
    if not _HOME_WARNED:
        _HOME_WARNED = True
        passwd_home = _account_home()
        env_home_str = os.environ.get("HOME", "")
        if env_home_str and Path(env_home_str) != passwd_home:
            _LOG.warning(
                "HOME env (%s) differs from /etc/passwd home (%s). "
                "Using /etc/passwd path for settings.",
                env_home_str,
                passwd_home,
            )
    return QSettings(
        str(_account_home() / ".config" / "tincan" / "tincan.ini"),
        QSettings.Format.IniFormat,
    )


def bool_value(settings: QSettings, key: str, default: bool = True) -> bool:
    """Read a bool setting, handling PySide6 INI string coercion of 'true'/'false'."""
    raw = settings.value(key, default)
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes")
    return bool(raw)
