"""BackendInterface — ABC for tincand data backends."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BackendInterface(ABC):
    """Contract between tincand and a data-source backend.

    Concrete backends receive a TincanService reference via register_service()
    and drive it by calling its helpers (upsert_conversation,
    on_message_received, set_capability, Connect, Disconnect) rather than
    going through D-Bus.
    """

    def register_service(self, service: object) -> None:
        """Wire the TincanService this backend should drive."""
        self._service = service  # type: ignore[attr-defined]

    @abstractmethod
    def connect(self, device_addr: str) -> None:
        """Establish connection to device at *device_addr*."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection and release resources."""

    @abstractmethod
    def poll_inbox(self) -> list:
        """Return new/unread messages available since last poll."""

    @abstractmethod
    def get_message(self, handle: str) -> object:
        """Fetch the full message body for *handle*."""

    @abstractmethod
    def send_message(self, to: str, body: str) -> str:
        """Send *body* to *to*; return the assigned message handle."""
