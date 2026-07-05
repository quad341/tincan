"""Detect HFP/SCO call readiness without requiring root privileges."""
from __future__ import annotations

import logging
import pathlib
import subprocess

_log = logging.getLogger(__name__)

CALLS_READY = "CALLS_READY"
CALLS_NEED_SELINUX_MODULE = "CALLS_NEED_SELINUX_MODULE"
SELINUX_NOT_ENFORCING = "SELINUX_NOT_ENFORCING"
CALLS_STATUS_UNKNOWN = "CALLS_STATUS_UNKNOWN"

_MODULE_NAME = "tincan_hfp_sco"


def _get_enforce_mode() -> str:
    """Return 'Enforcing', 'Permissive', or 'Disabled'."""
    try:
        result = subprocess.run(
            ["getenforce"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "Disabled"


def _check_module_loaded(module_name: str = _MODULE_NAME) -> bool | None:
    """Return True if module is loaded, False if not, None if unknown.

    Tries semodule -l first; if that fails (denied for non-root on Fedora 44+),
    falls back to two unprivileged reads:
      1. /var/lib/selinux/<policy>/active/modules/<priority>/<name>/ (world-readable)
      2. /usr/share/selinux/packages/<name>.pp  (created by install.sh)
    """
    try:
        result = subprocess.run(
            ["semodule", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return module_name in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        _log.debug("semodule -l unavailable: %s", exc)

    # Fallback 1: SELinux module store — world-readable, no root needed.
    # Structure: /var/lib/selinux/<policy>/active/modules/<priority>/<module>/
    selinux_store = pathlib.Path("/var/lib/selinux")
    if selinux_store.exists():
        for policy_dir in selinux_store.iterdir():
            mods_root = policy_dir / "active" / "modules"
            if not mods_root.exists():
                continue
            for priority_dir in mods_root.iterdir():
                if (priority_dir / module_name).is_dir():
                    _log.debug(
                        "Found %s in SELinux store: %s", module_name, priority_dir / module_name
                    )
                    return True

    # Fallback 2: marker file copied by install.sh into the standard packages dir.
    marker = pathlib.Path(f"/usr/share/selinux/packages/{module_name}.pp")
    if marker.exists():
        return True

    return None


def detect_hfp_capability() -> str:
    """Probe HFP call readiness using only unprivileged operations.

    Returns one of:
      CALLS_READY              — SELinux module loaded (or SELinux not enforcing)
      CALLS_NEED_SELINUX_MODULE — Enforcing, module confirmed absent
      SELINUX_NOT_ENFORCING    — Permissive/Disabled, no module needed
      CALLS_STATUS_UNKNOWN     — Enforcing but module presence could not be determined
    """
    mode = _get_enforce_mode()
    _log.info("SELinux enforce mode: %s", mode)

    if mode in ("Permissive", "Disabled", ""):
        return SELINUX_NOT_ENFORCING

    loaded = _check_module_loaded()
    if loaded is True:
        return CALLS_READY
    if loaded is False:
        return CALLS_NEED_SELINUX_MODULE
    return CALLS_STATUS_UNKNOWN


def is_call_setup_ready() -> bool:
    """Return True iff calls are expected to work (SELinux module loaded or not enforcing)."""
    result = detect_hfp_capability()
    return result in (CALLS_READY, SELINUX_NOT_ENFORCING)
