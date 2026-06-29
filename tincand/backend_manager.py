"""BackendManager — run multiple tincand backends concurrently.

One *primary* backend owns the BackendInterface contract (poll_inbox,
send_message, get_message).  Zero or more *secondary* backends share the same
TincanService and are started/stopped alongside the primary, but their
messaging methods are not delegated.

Design for extensibility:
  primary   = MapBackend  (messaging)
  secondary = ANCSBackend (push notifications)
  future    = VoiceBackend (add to secondaries list)
"""
from __future__ import annotations

import logging

from tincand.backends.base import BackendInterface

_log = logging.getLogger(__name__)


class BackendManager(BackendInterface):
    """Lifecycle coordinator for a primary + zero-or-more secondary backends.

    All backends share the same TincanService reference registered via
    register_service().  The primary backend owns messaging (poll_inbox,
    send_message, get_message); secondaries are started/stopped in order and
    call set_capability() independently without going through this class.
    """

    def __init__(
        self,
        primary: BackendInterface,
        secondaries: list[BackendInterface] | None = None,
    ) -> None:
        self._primary = primary
        self._secondaries: list[BackendInterface] = list(secondaries or [])

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def register_service(self, service: object) -> None:
        self._service = service  # type: ignore[attr-defined]
        self._primary.register_service(service)
        for s in self._secondaries:
            s.register_service(service)

    def connect(self, device_addr: str) -> None:
        """Connect primary then each secondary in order.

        A primary connect failure must NOT prevent secondaries from
        connecting. On a fresh iOS pairing the MAP/OBEX connect can be
        refused (0x43 Forbidden) while the device is otherwise reachable;
        ANCS (a secondary) must still solicit so iOS can prompt for
        notification access. So we attempt every secondary regardless of the
        primary's outcome, then re-raise any primary failure so the caller's
        existing retry path (MAP self-schedules a reconnect) is unchanged.
        """
        primary_exc: Exception | None = None
        try:
            self._primary.connect(device_addr)
        except Exception as exc:  # noqa: BLE001
            primary_exc = exc
            _log.warning(
                "BackendManager: primary %s connect failed (%s) — "
                "starting secondaries anyway",
                type(self._primary).__name__, exc,
            )
        for s in self._secondaries:
            try:
                s.connect(device_addr)
            except Exception as exc:
                _log.warning("BackendManager: secondary %s connect failed: %s",
                             type(s).__name__, exc)
        if primary_exc is not None:
            raise primary_exc

    def disconnect(self) -> None:
        """Disconnect each secondary in reverse order, then primary."""
        for s in reversed(self._secondaries):
            try:
                s.disconnect()
            except Exception as exc:
                _log.warning("BackendManager: secondary %s disconnect failed: %s",
                             type(s).__name__, exc)
        self._primary.disconnect()

    def poll_inbox(self) -> list:
        return self._primary.poll_inbox()

    def get_message(self, handle: str) -> object:
        return self._primary.get_message(handle)

    def send_message(self, to: str, body: str) -> str:
        return self._primary.send_message(to, body)

    def send_group_message(self, participants: list[str], body: str) -> str:
        return self._primary.send_group_message(participants, body)

    def schedule_reconnect(self) -> None:
        self._primary.schedule_reconnect()
