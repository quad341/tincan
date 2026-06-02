"""Desktop notification dispatch for inbound messages.

Sends freedesktop.org Notify() calls via dbus-python. Dedup guard
tracks (body, timestamp) per conversation to suppress replay/reconnect
duplicates before the Notify() call.
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

_NOTIF_SERVICE = "org.freedesktop.Notifications"
_NOTIF_PATH = "/org/freedesktop/Notifications"
_NOTIF_IFACE = "org.freedesktop.Notifications"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class DesktopNotifier:
    """Send one desktop notification per new inbound message.

    The dedup guard (per conversation) lives here in the receive path — the
    Notify() call itself is always fire-and-forget with no dedup logic.
    """

    def __init__(self) -> None:
        self._seen: dict[str, set[tuple[str, str]]] = {}

    def dispatch(self, message: dict) -> None:
        """Send a desktop notification if the message warrants one."""
        if not self._should_notify(message):
            return
        self._notify(message)

    def _should_notify(self, message: dict) -> bool:
        from tincan_gui._settings import app_settings

        if not app_settings().value("notifications/desktop_enabled", True, type=bool):
            return False
        if str(message.get("direction", "")) != "inbound":
            return False
        if str(message.get("status", "")) not in ("unread", "new"):
            if not message.get("is_new"):
                return False

        conv_id = str(
            message.get("conversation_id") or message.get("from") or ""
        )
        body = str(message.get("body", ""))
        timestamp = str(message.get("timestamp", ""))
        key = (body, timestamp)
        seen = self._seen.setdefault(conv_id, set())
        if key in seen:
            return False
        seen.add(key)
        return True

    def _notify(self, message: dict) -> None:
        import dbus

        display_name = str(
            message.get("from") or message.get("conversation_id") or ""
        ).strip()
        summary = _truncate(display_name, 30) if display_name else "tincan"

        body_text = str(message.get("body", "")).strip()
        body = _truncate(body_text, 100) if body_text else "New message"

        try:
            bus = dbus.SessionBus()
            proxy = bus.get_object(_NOTIF_SERVICE, _NOTIF_PATH)
            iface = dbus.Interface(proxy, _NOTIF_IFACE)
            iface.Notify(
                "tincan",
                dbus.UInt32(0),
                "tincan",
                summary,
                body,
                dbus.Array([], signature="s"),
                dbus.Dictionary({}, signature="sv"),
                dbus.Int32(0),
            )
        except dbus.DBusException as exc:
            _log.warning("Desktop notification failed: %s", exc)
