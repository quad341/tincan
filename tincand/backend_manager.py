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

    @property
    def is_connected(self) -> bool:
        return getattr(self._primary, "is_connected", False)

    def register_service(self, service: object) -> None:
        self._service = service  # type: ignore[attr-defined]
        self._primary.register_service(service)
        for s in self._secondaries:
            s.register_service(service)

    def connect(self, device_addr: str) -> None:
        """Connect primary then each secondary in order."""
        self._primary.connect(device_addr)
        for s in self._secondaries:
            try:
                s.connect(device_addr)
            except Exception as exc:
                _log.warning("BackendManager: secondary %s connect failed: %s",
                             type(s).__name__, exc)

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
