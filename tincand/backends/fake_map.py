"""FakeMapBackend — iOS-faithful test double for integration and unit tests.

Reproduces the key iOS MAP quirks that real code must handle:
  (a) Sent folder returns 0 messages — iOS does not expose sent history over MAP.
      poll_inbox() returns ONLY inbound messages; callers must reconstruct sent
      state from their own optimistic cache.
  (b) Inbox message shapes including MMS with base64-encoded attachments.
  (c) Lazy PBAP contact resolution — display_name starts as a phone number;
      a separate PBAP step later resolves it to a human name.
  (d) Group messages — participants list has multiple entries.
  (e) Configurable send failures — send_message() / send_group_message() can
      raise an exception for specific targets.

No GLib, no D-Bus, no phone needed.  Pure Python — safe to import in any test.
"""
from __future__ import annotations

import itertools
import json
from typing import Union

from tincand.backends.base import BackendInterface

_handle_seq = itertools.count(1)


def _next_handle(prefix: str = "fake") -> str:
    return f"{prefix}-{next(_handle_seq)}"


class FakeMapBackend(BackendInterface):
    """Scripted MAP backend that faithfully models iOS MAP quirks for tests.

    Usage::

        backend = FakeMapBackend()

        # Populate inbox with an inbound SMS
        backend.add_inbound("+15550001", "Hey!", conv_id="5550001")

        # Populate inbox with an MMS with attachment
        backend.add_inbound(
            sender="+15550002",
            body="Check this out",
            conv_id="5550002",
            msg_type="MMS",
            attachments=[{"mime_type": "image/jpeg", "data": "base64..."}],
        )

        # Make send fail for a specific number
        backend.set_send_failure("+15550003", RuntimeError("MAP send rejected"))

        # Wire into daemon service (optional)
        backend.register_service(my_service)
        backend.connect("AA:BB:CC:DD:EE:FF")

        # poll_inbox returns only inbound — no sent history (iOS quirk a)
        msgs = backend.poll_inbox()
    """

    def __init__(self) -> None:
        self._inbox: list[dict] = []
        self._handles: dict[str, dict] = {}
        self._send_results: dict[str, Union[str, Exception]] = {}

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def connect(self, device_addr: str) -> None:
        """No-op connect — test harness controls state directly."""

    def disconnect(self) -> None:
        """No-op disconnect."""

    def poll_inbox(self) -> list:
        """Return canned inbound messages.

        iOS MAP quirk (a): no sent/outbound messages are ever returned here.
        The real iOS device exposes an empty 'sent' folder; callers must track
        outbound state via an optimistic local cache.
        """
        return list(self._inbox)

    def get_message(self, handle: str) -> object:
        """Return the full message dict for *handle*, or None if unknown."""
        return self._handles.get(handle)

    def send_message(self, to: str, body: str) -> str:
        """Return a handle on success; raise configured exception on failure."""
        result = self._send_results.get(to)
        if isinstance(result, Exception):
            raise result
        handle = _next_handle()
        self._handles[handle] = {
            "handle": handle,
            "sender": to,
            "display_name": to,
            "body": body,
            "direction": "outbound",
            "msg_type": "SMS_GSM",
            "read": True,
            "timestamp": "",
            "conv_id": to,
            "participants": [],
            "attachments": "[]",
        }
        return handle

    def send_group_message(self, participants: list[str], body: str) -> str:
        """Return a handle on success; raise configured exception on failure."""
        key = ",".join(sorted(participants))
        result = self._send_results.get(key)
        if isinstance(result, Exception):
            raise result
        handle = _next_handle("fake-group")
        self._handles[handle] = {
            "handle": handle,
            "sender": participants[0] if participants else "",
            "display_name": "",
            "body": body,
            "direction": "outbound",
            "msg_type": "MMS",
            "read": True,
            "timestamp": "",
            "conv_id": key,
            "participants": list(participants),
            "attachments": "[]",
        }
        return handle

    # ------------------------------------------------------------------
    # Test-builder helpers
    # ------------------------------------------------------------------

    def add_inbound(
        self,
        sender: str,
        body: str,
        *,
        conv_id: str = "",
        msg_type: str = "SMS_GSM",
        attachments: list[dict] | None = None,
        read: bool = False,
        timestamp: str = "",
        display_name: str = "",
        participants: list[str] | None = None,
    ) -> str:
        """Add a canned inbound message to poll_inbox() and return its handle.

        iOS MAP quirk (c): if display_name is omitted, it defaults to the sender
        phone number — real names are resolved later via PBAP (a separate backend).

        iOS MAP quirk (b): pass msg_type='MMS' with a non-empty attachments list
        to simulate a media message.

        iOS MAP quirk (d): pass participants with multiple entries for a group MMS.
        """
        handle = _next_handle()
        msg: dict = {
            "path": f"/fake/msg/{handle}",
            "handle": handle,
            "sender": sender,
            "display_name": display_name or sender,  # (c) name absent until PBAP
            "body": body,
            "direction": "inbound",
            "msg_type": msg_type,
            "read": read,
            "timestamp": timestamp,
            "conv_id": conv_id or sender,
            "participants": list(participants or []),
            "attachments": json.dumps(attachments or []),
        }
        self._inbox.append(msg)
        self._handles[handle] = msg
        return handle

    def set_send_failure(self, target: str, exc: Exception) -> None:
        """Cause send_message(target) or send_group_message(...) to raise exc.

        For group targets, pass the comma-joined sorted participant list as target,
        or use set_group_send_failure() for convenience.

        iOS MAP quirk (e): MAP send can fail with an exception (e.g. obexd
        'Internal Server Error') — callers must handle this gracefully.
        """
        self._send_results[target] = exc

    def set_group_send_failure(self, participants: list[str], exc: Exception) -> None:
        """Convenience: cause send_group_message(participants, ...) to raise exc."""
        self._send_results[",".join(sorted(participants))] = exc

    def resolve_contact_name(self, sender: str, name: str) -> None:
        """Simulate PBAP resolving a phone number to a human name.

        iOS MAP quirk (c): updates display_name on all cached inbound messages
        from this sender, as would happen after a PBAP contact sync.
        """
        for msg in self._inbox:
            if msg["sender"] == sender:
                msg["display_name"] = name
        for msg in self._handles.values():
            if msg["sender"] == sender:
                msg["display_name"] = name

    def reset(self) -> None:
        """Clear all canned messages, handles, and send-failure rules."""
        self._inbox.clear()
        self._handles.clear()
        self._send_results.clear()
