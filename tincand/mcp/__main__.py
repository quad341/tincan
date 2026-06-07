"""Entry point for python -m tincand.mcp."""
from __future__ import annotations

import sys

_HELP = """\
usage: python -m tincand.mcp [--help]

tincan MCP server — exposes tincan messaging and notification controls
via the Model Context Protocol (stdio transport).

AI clients (Claude Code, etc.) connect by launching this process and
communicating over stdin/stdout using the MCP protocol.

Requirements:
  - A running D-Bus session bus (Linux desktop environment)
  - tincand running: python -m tincand  (optional at startup, required for most tools)

Tools available:
  get_daemon_status        Check daemon connectivity
  list_conversations       List message threads
  get_messages             Read messages in a thread
  send_message             Send an SMS or iMessage (⚠ real-world side effect)
  send_group_message       Start a group thread (⚠ real-world side effect)
  get_contacts             List PBAP-synced contacts
  mark_conversation_read   Clear unread count
  get_notification_filter  Read ANCS filter config
  set_notifications_enabled Toggle notification mirroring
  set_app_filter           Allow or deny an app's notifications
  get_seen_apps            List apps that have sent notifications

Resources:
  tincan://status
  tincan://conversations
  tincan://conversations/{id}/messages
  tincan://contacts
"""

_DBUS_ADVICE = """\
tincan-mcp requires a D-Bus session (Linux desktop or systemd --user session).
It cannot run in headless SSH sessions without X11 forwarding.

To run in a desktop session:
  ssh -X user@host python -m tincand.mcp

Or start a D-Bus session explicitly:
  dbus-run-session python -m tincand.mcp\
"""


def _check_dbus() -> str | None:
    """Return an error message if D-Bus session bus is unavailable, else None."""
    import os
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return "DBUS_SESSION_BUS_ADDRESS not set"
    try:
        import dbus
        dbus.SessionBus()
        return None
    except Exception as e:
        return str(e)


def _check_tincand() -> bool:
    """Return True if tincand is reachable on the session bus."""
    try:
        import dbus
        bus = dbus.SessionBus()
        bus.get_object("im.tincan.Daemon", "/im/tincan")
        return True
    except Exception:
        return False


def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(_HELP)
        sys.exit(0)

    err = _check_dbus()
    if err:
        print(
            f"error: D-Bus session bus is not available.\n\n{_DBUS_ADVICE}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("tincan MCP server starting (stdio transport)", file=sys.stderr)
    if _check_tincand():
        print("Connected to tincan daemon at im.tincan.Daemon", file=sys.stderr)
    else:
        print(
            "Warning: tincand daemon is not running.\n"
            "  Start it with: python -m tincand\n"
            "  Most tools will fail until the daemon is connected.",
            file=sys.stderr,
        )
    print("Ready for connections.", file=sys.stderr)

    from tincand.mcp.server import mcp
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
