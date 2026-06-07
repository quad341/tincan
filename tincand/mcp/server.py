"""FastMCP server for tincan — Phase 1 tools + resources.

Exposes tincan messaging and notification controls via the Model Context
Protocol. AI clients connect by launching `python -m tincand.mcp` and
communicating over stdio.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ResourceError, ToolError

from tincand.mcp.dbus_bridge import (
    TincandDBusBridge,
    TincandError,
    TincandInvalidArgument,
    TincandNotConnected,
    TincandNotRunning,
)

mcp = FastMCP(
    "tincan",
    instructions=(
        "tincan is a Linux daemon that bridges iPhone messages and notifications "
        "over Bluetooth. Use list_conversations and get_messages to read message "
        "threads. Use send_message to send an SMS or iMessage to a contact. "
        "Check get_daemon_status first — if connected is false, most tools will "
        "fail with a NotConnected error."
    ),
)

_bridge = TincandDBusBridge()


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _mcp_error(exc: Exception) -> None:
    if isinstance(exc, TincandNotRunning):
        raise ToolError(
            "tincan daemon is not running. Start it with: python -m tincand"
        ) from exc
    if isinstance(exc, TincandNotConnected):
        raise ToolError(
            "tincan is not connected to a Bluetooth device. "
            "Use get_daemon_status to check connectivity."
        ) from exc
    if isinstance(exc, TincandInvalidArgument):
        raise ToolError(f"Invalid argument: {exc}") from exc
    if isinstance(exc, TincandError):
        raise ToolError(f"Daemon error ({exc.dbus_name}): {exc}") from exc
    raise ToolError(f"Daemon error: {exc}") from exc


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_daemon_status() -> dict:
    """Return the current connection status of the tincan daemon.

    Returns a status dict:
      connected (bool): True when a Bluetooth device is active.
      device_address (str): Bluetooth MAC address of the paired device, or "".
      device_name (str): Human-readable device name (e.g. "Jim's iPhone"), or "".
      capabilities (dict): Feature flags for the connected device:
        messages (bool): MAP message sync is available.
        contacts (bool): PBAP contact sync is available.
        contacts_empty (bool): PBAP synced but found 0 contacts.
        ancs (bool): Apple Notification Center Service is available.
        ancs_needs_repair (bool): ANCS bond needs re-pairing.

    Always succeeds — never raises even when disconnected.
    Call this first to check connectivity before using message tools.
    """
    try:
        return _bridge.get_status()
    except TincandNotRunning:
        return {
            "connected": False,
            "device_address": "",
            "device_name": "",
            "capabilities": {
                "messages": False,
                "contacts": False,
                "contacts_empty": True,
                "ancs": False,
                "ancs_needs_repair": False,
            },
        }
    except (TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def list_conversations() -> list[dict]:
    """Return all known message conversations, sorted newest-first.

    Each conversation dict contains:
      id (str): Unique conversation identifier (usually a phone number).
      display_name (str): Contact name or phone number shown in the UI.
      participants (list[str]): Phone numbers of all participants.
      last_message_at (str): ISO 8601 timestamp of the last message, or "".
      last_message_preview (str): Truncated text of the last message.
      last_message_direction (str): "inbound" or "outbound" or "".
      unread_count (int): Number of unread messages in this conversation.
      send_target (str): Canonical phone number to use when replying.
      is_group (bool): True for group conversations.
      group_name (str): Group display name, or "" for 1-on-1 conversations.

    Raises NotConnected if the daemon is not connected to a device.
    Returns [] if no conversations have been synced yet.
    """
    try:
        return _bridge.list_conversations()
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def get_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    """Return messages in a conversation, oldest first.

    Args:
      conversation_id: The id field from list_conversations.
      limit: Maximum number of messages to return (default 50, max 200).
             Pass 0 to return all stored messages.

    Each message dict contains:
      id (str): Unique message identifier.
      conversation_id (str): The conversation this message belongs to.
      body (str): Message text.
      timestamp (str): ISO 8601 send/receive time.
      direction (str): "inbound" (received) or "outbound" (sent).
      status (str): "read" or "unread".
      from (str): Sender phone number, or "" for outbound messages.

    Raises NotConnected if the daemon is not connected to a device.
    Returns [] for unknown conversation IDs.
    """
    try:
        msgs = _bridge.get_messages(conversation_id)
        if limit and limit > 0:
            cap = min(limit, 200)
            msgs = msgs[-cap:]
        return msgs
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def get_contacts() -> list[dict]:
    """Return all PBAP-synced contacts from the connected device.

    Each contact dict contains:
      phone (str): Phone number in E.164 format where possible.
      name (str): Contact display name.

    Returns [] if PBAP sync has not completed or found no contacts
    (check get_daemon_status capabilities.contacts and contacts_empty).
    Raises NotConnected if the daemon is not connected to a device.
    """
    try:
        return _bridge.get_contacts()
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def get_notification_filter() -> dict:
    """Return the current ANCS notification filter configuration.

    Returns:
      enabled (bool): True when app notification mirroring is globally on.
      apps (dict): Mapping of app_id -> "allow" or "deny" for all apps
                   with explicit filter entries. Apps not in this dict
                   default to "allow".

    Does not require the daemon to be connected — reads local config.
    """
    try:
        return _bridge.get_notification_filter()
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def get_seen_apps() -> list[dict]:
    """Return apps that have sent at least one ANCS notification this session.

    Each entry contains:
      app_id (str): iOS bundle identifier (e.g. "com.apple.mobilesms").
      label_hint (str): Most-recent notification title seen from this app.
                        Not an app name — it is a sender/event name.

    Use this to discover app_id values before calling set_app_filter.
    Does not require the daemon to be connected — reads local config.
    """
    try:
        return _bridge.get_seen_apps()
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@mcp.tool()
def mark_conversation_read(conversation_id: str) -> dict:
    """Mark all messages in a conversation as read.

    ⚠️  SIDE EFFECT: Resets the unread badge count for this conversation
    in the tincan UI. This is a local-only operation — it does not send
    a read receipt to the sender.

    Args:
      conversation_id: The id field from list_conversations.

    Returns {"ok": true} on success.
    Raises NotConnected if the daemon is not connected to a device.
    No-ops silently for unknown conversation IDs.
    """
    try:
        _bridge.mark_conversation_read(conversation_id)
        return {"ok": True}
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def set_notifications_enabled(enabled: bool) -> dict:
    """Enable or disable global ANCS notification mirroring.

    ⚠️  SIDE EFFECT: Persists immediately to ~/.config/tincan/tincan.ini.
    When disabled, NO app notifications from the phone will be shown on
    the desktop, regardless of per-app filter settings.

    Args:
      enabled: True to enable notification mirroring, False to disable.

    Returns {"ok": true, "enabled": <new value>} on success.
    Does not require the daemon to be connected.
    """
    try:
        _bridge.set_notifications_enabled(enabled)
        return {"ok": True, "enabled": enabled}
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def set_app_filter(app_id: str, action: str) -> dict:
    """Set the notification filter action for a specific app.

    ⚠️  SIDE EFFECT: Persists immediately to ~/.config/tincan/tincan.ini.
    Takes effect on the next notification from this app — does not affect
    any notifications already queued.

    Args:
      app_id: iOS bundle identifier (e.g. "com.apple.mobilesms").
              Use get_seen_apps to discover valid app_id values.
      action: "allow" to show notifications, "deny" to suppress them.

    Returns {"ok": true, "app_id": <id>, "action": <new action>} on success.
    Raises InvalidArgument if action is not "allow" or "deny".
    Does not require the daemon to be connected.
    """
    try:
        _bridge.set_app_filter(app_id, action)
        return {"ok": True, "app_id": app_id, "action": action}
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def send_message(to: str, body: str) -> dict:
    """Send an SMS or iMessage to a phone number.

    ⚠️  SIDE EFFECT: Sends a real message to a real person via the paired
    iPhone over Bluetooth. This action cannot be undone after the daemon
    transmits it to the phone.

    Confirm the recipient and message content with the user before calling
    this tool.

    Args:
      to: Recipient phone number. International format recommended
          (e.g. "+14155550123"). The daemon normalizes the number.
      body: Message text. Must be non-empty.

    Returns:
      {"message_id": str, "status": "sent"} on success.

    Raises:
      NotConnected — daemon is not connected to a Bluetooth device.
      InvalidArgument — to or body is empty.
    """
    try:
        message_id = _bridge.send_message(to, body)
        return {"message_id": message_id, "status": "sent"}
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


@mcp.tool()
def send_group_message(recipients: list[str], body: str) -> dict:
    """Start a group conversation and send an opening message.

    ⚠️  SIDE EFFECT: Creates a new group thread and sends a real message
    to all recipients via the paired iPhone. This action cannot be undone.

    Confirm all recipients and message content with the user before calling
    this tool.

    Args:
      recipients: List of at least 2 phone numbers.
                  International format recommended (e.g. "+14155550123").
      body: Opening message text. Must be non-empty.

    Returns:
      {"conversation_id": str, "status": "sent"} on success.

    Raises:
      NotConnected — daemon is not connected to a Bluetooth device.
      InvalidArgument — fewer than 2 recipients, or body is empty.
    """
    try:
        conv_id = _bridge.send_group_message(recipients, body)
        return {"conversation_id": conv_id, "status": "sent"}
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        _mcp_error(e)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("tincan://status")
def resource_status() -> str:
    """Current tincan daemon status as JSON."""
    try:
        return json.dumps(_bridge.get_status(), ensure_ascii=False)
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        raise ResourceError(str(e)) from e


@mcp.resource("tincan://conversations")
def resource_conversations() -> str:
    """All synced conversations as a JSON array, sorted newest-first."""
    try:
        return json.dumps(_bridge.list_conversations(), ensure_ascii=False)
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        raise ResourceError(str(e)) from e


@mcp.resource("tincan://conversations/{id}/messages")
def resource_messages(id: str) -> str:
    """Messages for a single conversation as a JSON array, oldest first.
    Returns an empty array for unknown conversation IDs.
    """
    try:
        return json.dumps(_bridge.get_messages(id), ensure_ascii=False)
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        raise ResourceError(str(e)) from e


@mcp.resource("tincan://contacts")
def resource_contacts() -> str:
    """All PBAP-synced contacts as a JSON array."""
    try:
        return json.dumps(_bridge.get_contacts(), ensure_ascii=False)
    except (TincandNotRunning, TincandNotConnected, TincandInvalidArgument, TincandError) as e:
        raise ResourceError(str(e)) from e
