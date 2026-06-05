"""Spawn tincand in the background if it is not already running."""
from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

_log = logging.getLogger(__name__)


def spawn_daemon(backend: str, device: str) -> Optional[subprocess.Popen]:
    """Launch tincand as a detached background process.

    Uses start_new_session=True so the child outlives the GUI if the GUI exits,
    and so SIGINT to the GUI does not propagate to the daemon.
    """
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
