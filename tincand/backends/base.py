"""BackendInterface — ABC for tincand data backends."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BackendInterface(ABC):
    """Contract between tincand and a data-source backend.

    The daemon registers a TincanService with the backend via
    register_service(), then calls start() to begin operation.
    The backend drives the service by calling its internal helpers
    (upsert_conversation, on_message_received, set_capability, Connect,
    Disconnect) rather than going through D-Bus.
    """

    @abstractmethod
    def list_conversations(self) -> list:
        """Return current conversations as Conversation dataclass instances."""

    @abstractmethod
    def register_service(self, service: object) -> None:
        """Attach the TincanService this backend should drive."""

    @abstractmethod
    def start(self) -> None:
        """Start the backend (connect, begin polling/timers, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the backend and release all resources."""
