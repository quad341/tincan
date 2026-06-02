"""AncsBackend — ANCS notification backend for tincand.

Uses ancs4linux daemons (primary path) to receive iOS notifications via the
Apple Notification Center Service BLE GATT profile.  The backend is
receive-only: send_message() raises NotImplementedError because ANCS provides
no write path.

ANCS + MAP enrichment: this backend emits MessageReceived with the ANCS preview
body immediately.  When a MapBackend is also active, the caller can later
update the conversation's last_message_preview with the full MAP body — the
two paths use the same conversation_id (sender) so they don't duplicate.

Graceful degradation: if the ancs4linux daemons fail to start or the ANCS link
drops mid-session, set_capability('ancs', False) is called on the service and
MAP polling continues as the sole message path.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib

from tincand.backends.base import BackendInterface

_log = logging.getLogger(__name__)

_ANCS4LINUX_BUS = "se.mobiledevices.ancs4linux.observer"
_ANCS4LINUX_PATH = "/se/mobiledevices/ancs4linux/observer"
_ANCS4LINUX_IFACE = "se.mobiledevices.ancs4linux.Observer1"

_MESSAGES_APP_ID = "com.apple.MobileSMS"

# Seconds to wait for ancs4linux daemons to register their D-Bus names
_DAEMON_STARTUP_WAIT = 2.0


class AncsBackend(BackendInterface):
    """ANCS notification backend backed by ancs4linux daemons.

    Connects to the ancs4linux observer D-Bus interface; translates incoming
    notifications with AppID == com.apple.MobileSMS into on_message_received()
    callbacks on the TincanService.
    """

    def __init__(self) -> None:
        self._service: object | None = None
        self._procs: list[subprocess.Popen] = []
        self._bus: dbus.Bus | None = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def connect(self, device_addr: str) -> None:  # noqa: ARG002
        """Start ancs4linux daemons and subscribe to the notification signal.

        *device_addr* is accepted for interface consistency but is not used
        directly — ancs4linux advertises and the iPhone initiates the BLE
        connection automatically once paired.
        """
        # Ensure a GLib main loop is set as default for dbus-python
        if not dbus.mainloop.glib.DBusGMainLoop.is_default_main_loop_set():  # type: ignore[attr-defined]
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        self._start_daemons()

        try:
            self._bus = dbus.SessionBus()
            self._bus.add_signal_receiver(
                self._on_ancs_notification,
                signal_name="NotificationReceived",
                dbus_interface=_ANCS4LINUX_IFACE,
                bus_name=_ANCS4LINUX_BUS,
            )
            self._connected = True
            _log.info("AncsBackend: subscribed to ancs4linux observer")
            if self._service is not None:
                self._service.set_capability("ancs", True)  # type: ignore[attr-defined]
        except dbus.exceptions.DBusException as exc:
            _log.warning("AncsBackend: could not subscribe to ancs4linux: %s", exc)
            self._stop_daemons()
            if self._service is not None:
                self._service.set_capability("ancs", False)  # type: ignore[attr-defined]

    def disconnect(self) -> None:
        """Stop ancs4linux daemons and clean up."""
        self._connected = False
        self._stop_daemons()
        self._bus = None
        if self._service is not None:
            self._service.set_capability("ancs", False)  # type: ignore[attr-defined]
        _log.info("AncsBackend disconnected")

    def poll_inbox(self) -> list:
        """ANCS is push-based — returns empty list; events arrive via signal."""
        return []

    def get_message(self, handle: str) -> object:
        """ANCS does not support message fetch by handle — returns None."""
        return None

    def send_message(self, to: str, body: str) -> str:  # noqa: ARG002
        """ANCS is receive-only — always raises NotImplementedError."""
        raise NotImplementedError(
            "AncsBackend is receive-only. Use MapBackend for sending."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_daemons(self) -> None:
        for daemon in ("advertising", "observer"):
            try:
                p = subprocess.Popen(
                    [sys.executable, "-m", f"ancs4linux.{daemon}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._procs.append(p)
                _log.info("Started ancs4linux.%s (pid=%d)", daemon, p.pid)
            except FileNotFoundError:
                _log.warning(
                    "ancs4linux not installed — cannot start %s daemon", daemon
                )
        if self._procs:
            time.sleep(_DAEMON_STARTUP_WAIT)

    def _stop_daemons(self) -> None:
        for p in self._procs:
            p.terminate()
        self._procs.clear()

    def _on_ancs_notification(
        self,
        uid: int,
        app_id: str,
        title: str,
        message: str,
        subtitle: str = "",
    ) -> None:
        """Handle an incoming ANCS notification from the ancs4linux observer."""
        _log.debug(
            "ANCS notification: uid=%s app=%s title=%r message=%r",
            uid, app_id, title, message,
        )
        if str(app_id) != _MESSAGES_APP_ID:
            return
        if self._service is None:
            return

        sender = str(title) if title else "Unknown"
        body = str(message) if message else str(subtitle)
        # notification_uid used as message_handle for potential MAP correlation
        handle = str(uid)

        self._service.on_message_received({  # type: ignore[attr-defined]
            "conversation_id": sender,
            "body": body,
            "timestamp": "",
            "direction": "inbound",
            "status": "unread",
            "from": sender,
            "message_handle": handle,
        })
