"""Tests: Layer-2 daemon + GUI integration over an isolated session D-Bus.
Bead: tincan-0ua

All tests start tincand under dbus-run-session (isolated session bus) and
subscribe to its D-Bus signals from a second in-process client.  They are
skipped — not failed — when dbus-run-session is not installed.

Coverage:
  - Connected signal emitted by daemon and received by client within 5 s
  - MessageReceived signal propagates from daemon.on_message_received() to client
  - Connect → on_message_received sequence: both signals received in order

No phone, no real obexd.  Run with:
  QT_QPA_PLATFORM=offscreen python -m pytest tests/tincand/ -v
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

# ---------------------------------------------------------------------------
# Skip gate — check once at import time
# ---------------------------------------------------------------------------

_DBUS_RUN_SESSION: str | None = shutil.which("dbus-run-session")

pytestmark = pytest.mark.skipif(
    _DBUS_RUN_SESSION is None,
    reason="dbus-run-session not installed — install dbus-tools or dbus-x11",
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

# Project root: the directory that contains tincand/ (two levels up from this file:
#   tests/tincand/ → tests/ → project root).
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _run_in_session(script: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run *script* inside an isolated dbus-run-session.

    PYTHONPATH is extended to include _PROJECT_ROOT so that ``import tincand``
    works even when the tests are run from the validator worktree which does not
    have the source tree on sys.path.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(_PROJECT_ROOT) + os.pathsep + existing if existing else str(_PROJECT_ROOT)
    )
    env["QT_QPA_PLATFORM"] = "offscreen"

    return subprocess.run(
        [_DBUS_RUN_SESSION, "--", sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
        env=env,
    )


# ---------------------------------------------------------------------------
# §1 TestLayer2Integration
# ---------------------------------------------------------------------------

class TestLayer2Integration:
    """Daemon + client signal propagation over a real (isolated) session bus."""

    def test_connected_signal_received_within_5s(self):
        """TincanService.Connected signal is received by a dbus-python subscriber
        within 5 s of calling Connect()."""
        result = _run_in_session("""
            import sys, threading, time
            import dbus, dbus.mainloop.glib
            from gi.repository import GLib
            from tincand.dbus_service import TincanService

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            loop = GLib.MainLoop()

            results = {}
            svc = TincanService(bus)

            def on_connected(device_address):
                results['connected'] = str(device_address)
                loop.quit()

            bus.add_signal_receiver(
                on_connected,
                signal_name='Connected',
                dbus_interface='im.tincan.Daemon',
                bus_name='im.tincan.Daemon',
            )

            def _trigger():
                time.sleep(0.1)
                svc.Connect('AA:BB:CC:DD:EE:FF')

            threading.Thread(target=_trigger, daemon=True).start()
            GLib.timeout_add_seconds(5,
                lambda: (results.setdefault('timeout', True), loop.quit(), False)[-1])
            loop.run()

            if results.get('connected') != 'AA:BB:CC:DD:EE:FF':
                print(f"FAIL: Connected not received — got {results}", file=sys.stderr)
                sys.exit(1)
        """)
        assert result.returncode == 0, (
            f"Connected signal not received within 5 s."
            f"\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_message_received_propagates(self):
        """TincanService.MessageReceived signal propagates to a dbus-python
        subscriber after on_message_received() is called."""
        result = _run_in_session("""
            import sys, threading, time
            import dbus, dbus.mainloop.glib
            from gi.repository import GLib
            from tincand.dbus_service import TincanService, Conversation

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            loop = GLib.MainLoop()

            results = {}
            svc = TincanService(bus)
            svc.upsert_conversation(Conversation(
                id='conv-1', display_name='Alice',
            ))

            def on_message_received(message):
                results['body'] = str(message.get('body', ''))
                loop.quit()

            bus.add_signal_receiver(
                on_message_received,
                signal_name='MessageReceived',
                dbus_interface='im.tincan.Messages',
                bus_name='im.tincan.Daemon',
            )

            def _trigger():
                time.sleep(0.1)
                svc.Connect('AA:BB:CC:DD:EE:FF')
                time.sleep(0.05)
                svc.on_message_received({
                    'conversation_id': 'conv-1',
                    'direction': 'inbound',
                    'status': 'unread',
                    'body': 'Integration test message',
                    'timestamp': '2024-01-01T11:00:00',
                })

            threading.Thread(target=_trigger, daemon=True).start()
            GLib.timeout_add_seconds(5,
                lambda: (results.setdefault('timeout', True), loop.quit(), False)[-1])
            loop.run()

            if results.get('body') != 'Integration test message':
                print(f"FAIL: MessageReceived not received — got {results}", file=sys.stderr)
                sys.exit(1)
        """)
        assert result.returncode == 0, (
            f"MessageReceived signal not received."
            f"\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_connect_then_message_received_in_order(self):
        """Both Connected and MessageReceived signals are received in the
        expected order: Connected fires before MessageReceived."""
        result = _run_in_session("""
            import sys, threading, time
            import dbus, dbus.mainloop.glib
            from gi.repository import GLib
            from tincand.dbus_service import TincanService, Conversation

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            loop = GLib.MainLoop()

            sequence = []
            svc = TincanService(bus)
            svc.upsert_conversation(Conversation(id='c1', display_name='Bob'))

            def on_connected(addr):
                sequence.append('connected')

            def on_message_received(msg):
                sequence.append('message')
                loop.quit()

            bus.add_signal_receiver(
                on_connected,
                signal_name='Connected',
                dbus_interface='im.tincan.Daemon',
                bus_name='im.tincan.Daemon',
            )
            bus.add_signal_receiver(
                on_message_received,
                signal_name='MessageReceived',
                dbus_interface='im.tincan.Messages',
                bus_name='im.tincan.Daemon',
            )

            def _trigger():
                time.sleep(0.1)
                svc.Connect('AA:BB:CC:DD:EE:FF')
                time.sleep(0.05)
                svc.on_message_received({
                    'conversation_id': 'c1',
                    'direction': 'inbound',
                    'status': 'unread',
                    'body': 'Hi',
                    'timestamp': '2024-01-01T12:00:00',
                })

            threading.Thread(target=_trigger, daemon=True).start()
            GLib.timeout_add_seconds(5,
                lambda: (sequence.append('timeout'), loop.quit(), False)[-1])
            loop.run()

            if 'timeout' in sequence:
                print(f"FAIL: timed out — sequence={sequence}", file=sys.stderr)
                sys.exit(1)
            if sequence != ['connected', 'message']:
                print(f"FAIL: wrong sequence {sequence}", file=sys.stderr)
                sys.exit(1)
        """)
        assert result.returncode == 0, (
            f"Signal ordering wrong.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
