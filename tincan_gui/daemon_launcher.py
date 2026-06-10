"""Spawn tincand in the background if it is not already running."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

_log = logging.getLogger(__name__)


def spawn_daemon(backend: str, device: str) -> Optional[subprocess.Popen]:
    """Launch tincand as a detached background process.

    Uses start_new_session=True so the child outlives the GUI if the GUI exits,
    and so SIGINT to the GUI does not propagate to the daemon.
    """
    # Safety net: never spawn a real detached daemon from within a test run.
    # GUI tests construct a real MainWindow, which calls this; without the guard
    # each such test leaked a detached tincand onto the session bus — hundreds
    # piled up, exhausting dbus-broker's FDs and crashing the desktop session.
    # ("pytest" in sys.modules holds throughout collection, fixtures, and tests.)
    # Set TINCAN_ALLOW_DAEMON_SPAWN=1 to override for an intentional live spawn.
    if "pytest" in sys.modules and not os.environ.get("TINCAN_ALLOW_DAEMON_SPAWN"):
        _log.warning(
            "spawn_daemon: skipped — running under pytest "
            "(set TINCAN_ALLOW_DAEMON_SPAWN=1 to force a real spawn)"
        )
        return None
    cmd = [sys.executable, "-m", "tincand", "--backend", backend]
    if device:
        cmd += ["--device", device]
    try:
        proc = subprocess.Popen(cmd, start_new_session=True)
        _log.info(
            "tincand spawned (pid %d) with backend=%s device=%s",
            proc.pid,
            backend,
            device,
        )
        return proc
    except OSError as exc:
        _log.warning("failed to spawn tincand: %s", exc)
        return None
