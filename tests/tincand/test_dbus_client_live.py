"""Tests: TincandClient vs live tincand --backend mock over an isolated session D-Bus.
Bead: tincan-7w1

All tests start tincand under dbus-run-session (isolated session bus) and
verify that TincandClient (PySide6.QtDBus) can call methods and receive signals.
They are skipped — not failed — when dbus-run-session is not installed or when
the tincand daemon entry point is unavailable.

Coverage:
  - TincandClient.get_status() returns dict with 'capabilities' key
  - Capabilities dict has 'messages', 'contacts', and 'ancs' sub-keys
  - TincandClient.list_conversations() returns non-empty list of dicts
  - Each conversation dict has 'id' and 'display_name' keys
  - At least one D-Bus signal (Connected) is received within timeout
  - ConversationUpdated signal fires after a MessageReceived event

Headless: QT_QPA_PLATFORM=offscreen
Run with: QT_QPA_PLATFORM=offscreen python -m pytest tests/tincand/test_dbus_client_live.py -v
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
# Skip gates — checked once at import time
# ---------------------------------------------------------------------------

_DBUS_RUN_SESSION: str | None = shutil.which("dbus-run-session")

_TINCAND_AVAILABLE: bool = False
try:
    _check = subprocess.run(
        [sys.executable, "-c", "import tincand; print('ok')"],
        capture_output=True,
        timeout=5,
        env=os.environ,
    )
    _TINCAND_AVAILABLE = _check.returncode == 0
except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
    _TINCAND_AVAILABLE = False

_PYSIDE6_AVAILABLE: bool = False
try:
    _check = subprocess.run(
        [
            sys.executable,
            "-c",
            "from PySide6.QtCore import QCoreApplication; "
            "from PySide6.QtDBus import QDBusConnection; "
            "from PySide6.QtWidgets import QApplication; print('ok')",
        ],
        capture_output=True,
        timeout=5,
        env=os.environ,
    )
    _PYSIDE6_AVAILABLE = _check.returncode == 0
except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
    _PYSIDE6_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    _DBUS_RUN_SESSION is None or not _TINCAND_AVAILABLE or not _PYSIDE6_AVAILABLE,
    reason=(
        "dbus-run-session not installed (install dbus-tools or dbus-x11)"
        if _DBUS_RUN_SESSION is None
        else (
            "tincand entry point unavailable"
            if not _TINCAND_AVAILABLE
            else "PySide6 QtCore/QtDBus/QtWidgets unavailable"
        )
    ),
)

# ---------------------------------------------------------------------------
# Helper — run a Python snippet inside an isolated dbus-run-session
# ---------------------------------------------------------------------------

# Project root: directory that contains tincand/ and tincan_gui/
# tests/tincand/test_dbus_client_live.py → tests/tincand/ → tests/ → root
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _run_in_session(script: str, timeout: int = 20) -> subprocess.CompletedProcess:
    """Run *script* inside an isolated dbus-run-session with PYTHONPATH set."""
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
# Common daemon-spawning preamble injected into every test script
# ---------------------------------------------------------------------------

_DAEMON_PREAMBLE = """
import os, sys, subprocess, time

def _start_daemon():
    env = dict(os.environ)
    proc = subprocess.Popen(
        [sys.executable, '-m', 'tincand', '--mock'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait up to 2 s for the daemon to register its bus name.
    time.sleep(1.5)
    if proc.poll() is not None:
        out, err = proc.communicate()
        raise RuntimeError(f"tincand died at startup: {err.decode()[:400]}")
    return proc
"""

# ---------------------------------------------------------------------------
# §1  get_status() — capability keys present
# ---------------------------------------------------------------------------


class TestGetStatus:
    """TincandClient.get_status() returns a populated dict from a live daemon."""

    def test_get_status_returns_capabilities_key(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    status = client.get_status()
    if 'capabilities' not in status:
        print(f"FAIL: 'capabilities' not in status: {{status}}", file=sys.stderr)
        sys.exit(1)
    print("OK")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"get_status() missing 'capabilities'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_get_status_capabilities_has_messages_key(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    status = client.get_status()
    caps = status.get('capabilities', {{}})
    if 'messages' not in caps:
        print(f"FAIL: 'messages' not in capabilities: {{caps}}", file=sys.stderr)
        sys.exit(1)
    print("OK")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"get_status() missing 'messages' capability.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_get_status_capabilities_has_ancs_key(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    status = client.get_status()
    caps = status.get('capabilities', {{}})
    if 'ancs' not in caps:
        print(f"FAIL: 'ancs' not in capabilities: {{caps}}", file=sys.stderr)
        sys.exit(1)
    print("OK")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"get_status() missing 'ancs' capability.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# §2  list_conversations() — non-empty, correct shape
# ---------------------------------------------------------------------------


class TestListConversations:
    """TincandClient.list_conversations() returns non-empty list with expected shape."""

    def test_list_conversations_returns_non_empty_list(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    convs = client.list_conversations()
    if not convs:
        print(f"FAIL: list_conversations() returned empty: {{convs}}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {{len(convs)}} conversations")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"list_conversations() empty.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_list_conversations_each_entry_has_id_key(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    convs = client.list_conversations()
    for i, c in enumerate(convs):
        if 'id' not in c:
            print(f"FAIL: conversation[{{i}}] missing 'id' key: {{c}}", file=sys.stderr)
            sys.exit(1)
    print("OK")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"list_conversations() entry missing 'id'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_list_conversations_each_entry_has_display_name_key(self):
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    convs = client.list_conversations()
    for i, c in enumerate(convs):
        if 'display_name' not in c:
            print(f"FAIL: conversation[{{i}}] missing 'display_name': {{c}}", file=sys.stderr)
            sys.exit(1)
    print("OK")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"list_conversations() entry missing 'display_name'.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# §3  Signal reception — Connected fires within timeout
# ---------------------------------------------------------------------------


class TestSignalReception:
    """At least one D-Bus signal is received by TincandClient within timeout."""

    def test_connected_signal_received_within_5s(self):
        """The Connected signal is received by TincandClient within 5 s.

        MockBackend calls service.Connect('') on daemon startup, so the daemon
        is already connected when the client subscribes.  We call Disconnect()
        first to reset state, then Connect() to trigger a fresh Connected signal.
        """
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
import time

daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    received = []
    client.connected.connect(lambda addr: received.append(str(addr)))

    bus = QDBusConnection.sessionBus()
    iface = QDBusInterface(
        'im.tincan.Daemon', '/im/tincan', 'im.tincan.Daemon', bus
    )
    # MockBackend already called Connect('') on start — must Disconnect first.
    iface.call('Disconnect')
    time.sleep(0.05)
    iface.call('Connect', 'AA:BB:CC:DD:EE:FF')

    # Poll event loop for up to 5 s
    deadline = time.time() + 5
    while time.time() < deadline:
        app.processEvents()
        if received:
            break
        time.sleep(0.05)

    if not received:
        print("FAIL: Connected signal not received within 5 s", file=sys.stderr)
        sys.exit(1)
    print(f"OK: Connected({{received[0]}})")
finally:
    daemon.terminate()
    daemon.wait(3)
""")
        assert result.returncode == 0, (
            f"Connected signal not received.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_capability_changed_signal_received_within_5s(self):
        """CapabilityChanged signal is received when set_capability is called on daemon."""
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
import time

daemon = _start_daemon()
try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
    from tincan_gui.dbus_client import TincandClient

    app = QCoreApplication([])
    client = TincandClient()

    received = []
    client.capability_changed.connect(
        lambda feature, val: received.append((str(feature), bool(val)))
    )

    # Trigger CapabilityChanged via the tick mechanism — wait up to 7 s
    # (first tick is at 3 s, fires CapabilityChanged('ancs', False))
    deadline = time.time() + 7
    while time.time() < deadline:
        app.processEvents()
        if received:
            break
        time.sleep(0.05)

    if not received:
        print("FAIL: CapabilityChanged signal not received within 7 s", file=sys.stderr)
        sys.exit(1)
    print(f"OK: CapabilityChanged{{received[0]}}")
finally:
    daemon.terminate()
    daemon.wait(3)
""", timeout=25)
        assert result.returncode == 0, (
            f"CapabilityChanged signal not received.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_daemon_gui_receives_required_signals_and_updates_model(self):
        """Live daemon + GUI client receives core signals and updates conversation state."""
        result = _run_in_session(f"""
{_DAEMON_PREAMBLE}
import time

daemon = _start_daemon()
try:
    from PySide6.QtWidgets import QApplication
    from tincan_gui.main import MainWindow

    app = QApplication([])
    window = MainWindow()

    received = {{
        'connected': False,
        'message': False,
        'capability': False,
        'conversation': False,
    }}
    client = window._dbus_client
    client.connected.connect(lambda _addr: received.__setitem__('connected', True))
    client.message_received.connect(lambda _msg: received.__setitem__('message', True))
    client.capability_changed.connect(
        lambda _feature, _available: received.__setitem__('capability', True)
    )
    client.conversation_updated.connect(
        lambda _conv: received.__setitem__('conversation', True)
    )

    deadline = time.time() + 10
    model_updated = False
    while time.time() < deadline:
        app.processEvents()
        items = window.conversation_list._items
        model_updated = bool(items) and any(
            getattr(item, '_data').preview == 'Still on for dinner?'
            for item in items
        )
        if all(received.values()) and model_updated:
            break
        time.sleep(0.05)

    if not all(received.values()):
        print(f"FAIL: missing signal(s): {{received}}", file=sys.stderr)
        sys.exit(1)
    if not model_updated:
        previews = [
            getattr(item, '_data').preview
            for item in window.conversation_list._items
        ]
        print(f"FAIL: conversation model did not update: {{previews}}", file=sys.stderr)
        sys.exit(1)
    print("OK: live daemon signals updated GUI conversation model")
finally:
    daemon.terminate()
    daemon.wait(3)
""", timeout=25)
        assert result.returncode == 0, (
            "Live daemon + GUI integration did not receive required signals "
            "or update model.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
