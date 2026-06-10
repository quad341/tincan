"""spawn_daemon must NOT launch a real detached daemon under pytest.

Regression for the session-bus FD-exhaustion leak (bead tincan-itk9m): GUI tests
build a real MainWindow, whose _maybe_spawn_daemon() calls spawn_daemon(). Before
the guard, each such test leaked a detached `tincand` onto the session bus —
hundreds accumulated, exhausting dbus-broker's FD limit and crashing the desktop
session. The guard makes spawn_daemon a no-op whenever pytest is loaded, unless
TINCAN_ALLOW_DAEMON_SPAWN is set.
"""
from __future__ import annotations

from unittest.mock import patch

from tincan_gui import daemon_launcher


def test_spawn_daemon_is_noop_under_pytest():
    """We are running under pytest → spawn_daemon must skip Popen and return None."""
    with patch.object(daemon_launcher.subprocess, "Popen") as popen:
        result = daemon_launcher.spawn_daemon("map", "AA:BB:CC:DD:EE:FF")
    assert result is None
    popen.assert_not_called()


def test_spawn_daemon_override_allows_real_spawn(monkeypatch):
    """With TINCAN_ALLOW_DAEMON_SPAWN set, it proceeds to Popen (stubbed here)."""
    monkeypatch.setenv("TINCAN_ALLOW_DAEMON_SPAWN", "1")
    with patch.object(daemon_launcher.subprocess, "Popen") as popen:
        popen.return_value.pid = 4242
        result = daemon_launcher.spawn_daemon("mock", "")
    popen.assert_called_once()
    assert result is not None
    # the command is built correctly (no --device when empty)
    cmd = popen.call_args.args[0]
    assert cmd[1:4] == ["-m", "tincand", "--backend"]
    assert "--device" not in cmd
