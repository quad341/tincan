"""Desktop notification dispatch for inbound messages and system alerts.

Sends freedesktop.org Notify() calls via dbus-python. Dedup guard
tracks (body, timestamp) per conversation to suppress replay/reconnect
duplicates before the Notify() call. ActionInvoked listener raises
the main window and selects the conversation on click.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tincan_gui import trace as _trace

_ICON_PATH = str(Path(__file__).parent / "assets" / "tincan-icon.png")
_ICON_HINT_CACHE: object | None = None


def _get_icon_hint() -> object | None:
    """Return a cached freedesktop image-data hint (64×64 RGBA) for the app icon.

    Scales the 1254×1254 icon down to 64×64 so notification daemons that reject
    large icons still display the image. Returns None if PySide6 is unavailable.
    """
    global _ICON_HINT_CACHE
    if _ICON_HINT_CACHE is not None:
        return _ICON_HINT_CACHE
    try:
        import dbus
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        img = QImage(_ICON_PATH)
        if img.isNull():
            return None
        img = img.scaled(
            64, 64,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h, rowstride = img.width(), img.height(), img.bytesPerLine()
        data = bytes(img.constBits())
        _ICON_HINT_CACHE = dbus.Struct(
            [
                dbus.Int32(w), dbus.Int32(h), dbus.Int32(rowstride),
                dbus.Boolean(True), dbus.Int32(8), dbus.Int32(4),
                dbus.Array(data, signature="y"),
            ],
            signature="iiibiiay",
        )
    except Exception:  # noqa: BLE001
        pass
    return _ICON_HINT_CACHE

_log = logging.getLogger(__name__)

_NOTIF_SERVICE = "org.freedesktop.Notifications"
_NOTIF_PATH = "/org/freedesktop/Notifications"
_NOTIF_IFACE = "org.freedesktop.Notifications"


_HISTORY_SIZE = 100  # max entries kept in the in-memory notification history


@dataclass
class NotificationEntry:
    """One record in the in-app notification history."""
    ts: float         # time.time() at dispatch
    kind: str         # 'sms' or 'app'
    sender: str       # contact name / app display name
    summary: str      # one-line heading
    body: str         # preview text (may be truncated)
    conv_id: str      # conversation ID for SMS; '' for app notifications


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class DesktopNotifier:
    """Send one desktop notification per new inbound message.

    The dedup guard (per conversation) lives here in the receive path — the
    Notify() call itself is always fire-and-forget with no dedup logic.

    on_action_invoked: optional Callable(conversation_id) called when the user
    clicks a notification (ActionInvoked with action_id='default').
    """

    # Suppress app-notification duplicates arriving within this many seconds
    # (covers iOS retry delivery; does not permanently block recurring notifications).
    _APP_NOTIF_DEDUP_TTL = 30.0

    def __init__(
        self,
        on_action_invoked: Callable[[str], None] | None = None,
        on_mark_read: Callable[[str], None] | None = None,
    ) -> None:
        self._seen: dict[str, set[tuple[str, str]]] = {}
        self._seen_app: dict[tuple[str, str, str], float] = {}  # key → monotonic timestamp
        self._notif_to_conv: dict[int, str] = {}
        self._on_action_invoked = on_action_invoked
        self._on_mark_read = on_mark_read
        self._action_sub = None
        self._bus = None
        self._repair_notif_id: int = 0
        self._repair_on_reconnect: Callable[[], None] | None = None
        self._history: collections.deque[NotificationEntry] = collections.deque(
            maxlen=_HISTORY_SIZE
        )

    def history(self) -> list[NotificationEntry]:
        """Return notification history (oldest first)."""
        return list(self._history)

    def _ensure_bus(self) -> object | None:
        if self._bus is not None:
            return self._bus
        try:
            import dbus
            import dbus.mainloop.glib
            # The GUI runs under Qt/GLib; install GLib as the dbus mainloop so
            # add_signal_receiver() actually dispatches incoming signals.  Without
            # this, ActionInvoked is never received even though the subscription
            # succeeds — GLib events are pumped by Qt but only for the default
            # mainloop.  set_as_default=True is safe here because the Qt event
            # loop is already driving the GLib loop on Linux.
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SessionBus()
            if self._on_action_invoked or self._on_mark_read:
                self._bus.add_signal_receiver(
                    self._on_action_invoked_signal,
                    signal_name="ActionInvoked",
                    dbus_interface=_NOTIF_IFACE,
                    bus_name=_NOTIF_SERVICE,
                    path=_NOTIF_PATH,
                )
        except Exception as exc:  # noqa: BLE001
            _log.debug("Could not subscribe to ActionInvoked: %s", exc)
        return self._bus

    def _on_action_invoked_signal(self, notif_id: int, action_id: str) -> None:
        nid = int(notif_id)
        conv_id = self._notif_to_conv.get(nid, "")
        _trace.emit("notif_action", notif_id=nid, action_id=action_id, conv_id=conv_id)
        if nid == self._repair_notif_id and self._repair_notif_id != 0:
            if action_id == "default" and self._repair_on_reconnect:
                self._repair_on_reconnect()
            return
        if action_id == "mark-read":
            if self._on_mark_read and conv_id:
                self._on_mark_read(conv_id)
        elif action_id in ("default", "open", "reply"):
            if self._on_action_invoked and nid in self._notif_to_conv:
                self._on_action_invoked(conv_id)

    def dispatch(self, message: dict) -> None:
        """Send a desktop notification if the message warrants one."""
        if not self._should_notify(message):
            _trace.emit("notif_suppressed", conv_id=str(message.get("conversation_id", "")))
            return
        _log.debug("DesktopNotifier.dispatch: sending notification for conv=%s",
                   message.get("conversation_id", "?"))
        _trace.emit("notif_dispatch", conv_id=str(message.get("conversation_id", "")),
                    body_len=len(str(message.get("body", ""))))
        sender = str(
            message.get("display_name") or message.get("from")
            or message.get("conversation_id") or ""
        ).strip()
        self._history.append(NotificationEntry(
            ts=time.time(),
            kind="sms",
            sender=sender or "Unknown",
            summary=sender or "tincan",
            body=str(message.get("body", "")).strip(),
            conv_id=str(message.get("conversation_id") or message.get("from") or ""),
        ))
        self._notify(message)

    def dispatch_app_notification(self, notif: dict) -> None:
        """Send a desktop notification for a non-SMS iOS app notification."""
        from tincan_gui._settings import app_settings
        if not app_settings().value("notifications/desktop_enabled", True, type=bool):
            return

        app_id = str(notif.get("app_id", ""))
        title = str(notif.get("title", ""))
        subtitle = str(notif.get("subtitle", ""))
        body_text = str(notif.get("body", ""))

        key = (app_id, title, body_text)
        now = time.monotonic()
        last = self._seen_app.get(key)
        if last is not None and now - last < self._APP_NOTIF_DEDUP_TTL:
            return
        # Prune expired entries (prevent unbounded growth in long sessions)
        self._seen_app = {k: t for k, t in self._seen_app.items() if now - t < self._APP_NOTIF_DEDUP_TTL}  # noqa: E501
        self._seen_app[key] = now

        summary = title if title else (f"Notification from {app_id}".strip() or "Notification")
        if subtitle:
            body = f"{subtitle}: {body_text}" if body_text else subtitle
        elif body_text:
            body = body_text
        else:
            body = "New notification"

        self._history.append(NotificationEntry(
            ts=time.time(),
            kind="app",
            sender=app_id or "Unknown app",
            summary=summary,
            body=body,
            conv_id="",
        ))

        import dbus

        try:
            bus = self._ensure_bus()
            if bus is None:
                bus = dbus.SessionBus()
            proxy = bus.get_object(_NOTIF_SERVICE, _NOTIF_PATH)
            iface = dbus.Interface(proxy, _NOTIF_IFACE)
            _hints_app: dict = {}
            _icon_app = _get_icon_hint()
            if _icon_app is not None:
                _hints_app["image-data"] = _icon_app
            notif_id = iface.Notify(
                "tincan",
                dbus.UInt32(0),
                _ICON_PATH,
                _truncate(summary, 30),
                _truncate(body, 100),
                dbus.Array(["open", "Open"], signature="s"),
                dbus.Dictionary(_hints_app, signature="sv"),
                dbus.Int32(0),
            )
            self._notif_to_conv[int(notif_id)] = ""  # no conv to select; raises window only
        except Exception as exc:  # noqa: BLE001
            _log.warning("App notification failed: %s", exc)

    def dispatch_repair(self, on_reconnect: Callable[[], None] | None = None) -> None:
        """Send ANCS repair notification with Reconnect and Dismiss actions.

        Rate-limiting is the caller's responsibility (_repair_notified flag in MainWindow).
        on_reconnect is called when the user activates the Reconnect action.
        """
        import dbus

        self._repair_on_reconnect = on_reconnect
        try:
            bus = self._ensure_bus()
            if bus is None:
                bus = dbus.SessionBus()
            proxy = bus.get_object(_NOTIF_SERVICE, _NOTIF_PATH)
            iface = dbus.Interface(proxy, _NOTIF_IFACE)
            _hints_rep: dict = {}
            _icon_rep = _get_icon_hint()
            if _icon_rep is not None:
                _hints_rep["image-data"] = _icon_rep
            notif_id = iface.Notify(
                "Tin Can",
                dbus.UInt32(0),
                _ICON_PATH,
                "iPhone notifications unavailable",
                "The Bluetooth LE link could not be re-armed after 3 attempts.",
                dbus.Array(
                    ["default", "Reconnect...", "dismiss", "Dismiss"],
                    signature="s",
                ),
                dbus.Dictionary(_hints_rep, signature="sv"),
                dbus.Int32(0),
            )
            self._repair_notif_id = int(notif_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("ANCS repair notification failed: %s", exc)

    def _should_notify(self, message: dict) -> bool:
        from tincan_gui._settings import app_settings

        if not app_settings().value("notifications/desktop_enabled", True, type=bool):
            _log.debug("_should_notify: skip — desktop notifications disabled in settings")
            return False
        direction = str(message.get("direction", ""))
        if direction != "inbound":
            return False
        status = str(message.get("status", ""))
        if status not in ("unread", "new"):
            if not message.get("is_new"):
                _log.debug(
                    "_should_notify: skip — status=%r is_new=%r",
                    status, message.get("is_new"),
                )
                return False

        conv_id = str(
            message.get("conversation_id") or message.get("from") or ""
        )
        body = str(message.get("body", ""))
        timestamp = str(message.get("timestamp", ""))
        key = (body, timestamp)
        seen = self._seen.setdefault(conv_id, set())
        if key in seen:
            _log.debug("_should_notify: skip — dedup hit for conv=%s", conv_id)
            return False
        seen.add(key)
        return True

    def _notify(self, message: dict) -> None:
        import dbus

        display_name = str(
            message.get("display_name")
            or message.get("from")
            or message.get("conversation_id")
            or ""
        ).strip()
        summary = _truncate(display_name, 30) if display_name else "tincan"

        body_text = str(message.get("body", "")).strip()
        body = _truncate(body_text, 100) if body_text else "New message"

        conv_id = str(
            message.get("conversation_id") or message.get("from") or ""
        )

        try:
            bus = self._ensure_bus()
            if bus is None:
                import dbus
                bus = dbus.SessionBus()
            proxy = bus.get_object(_NOTIF_SERVICE, _NOTIF_PATH)
            iface = dbus.Interface(proxy, _NOTIF_IFACE)
            _hints: dict = {}
            _icon = _get_icon_hint()
            if _icon is not None:
                _hints["image-data"] = _icon
            notif_id = iface.Notify(
                "tincan",
                dbus.UInt32(0),
                _ICON_PATH,
                summary,
                body,
                dbus.Array(
                    ["default", "Open", "mark-read", "Mark as Read"],
                    signature="s",
                ),
                dbus.Dictionary(_hints, signature="sv"),
                dbus.Int32(0),
            )
            if conv_id:
                self._notif_to_conv[int(notif_id)] = conv_id
            _log.debug("Desktop notification sent (id=%s) for %s", notif_id, conv_id)
        except dbus.DBusException as exc:
            _log.warning("Desktop notification failed (DBusException): %s", exc)
        except Exception as exc:  # noqa: BLE001
            # Broad catch: non-DBusException errors are silently swallowed by Qt's
            # slot dispatcher — log them here so they appear in /tmp/tincan-gui.log.
            _log.warning("Desktop notification unexpected error: %s", exc)
