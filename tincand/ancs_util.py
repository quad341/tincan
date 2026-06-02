"""ancs_util — pure Python ANCS TLV parser and fragmentation buffer.

Zero imports from dbus, gi, or tincand — fully unit-testable with byte fixtures.

Public API:
  parse_notification_source(data: bytes) -> dict
  build_get_attrs_cmd(uid: int, attrs: list[int]) -> bytes
  parse_data_source(data: bytes) -> dict
  class ANCSDataBuffer
  class IncompleteResponseError
"""
from __future__ import annotations

import struct

# ---------------------------------------------------------------------------
# Attribute ID constants
# ---------------------------------------------------------------------------

ATTR_APP_ID = 0   # no length field in GetNotifAttrs command
ATTR_TITLE = 1    # max_len field required: 255
ATTR_MESSAGE = 3  # max_len field required: 255

# ---------------------------------------------------------------------------
# GATT UUID constants
# ---------------------------------------------------------------------------

ANCS_SERVICE_UUID = "7905F431-B5CE-4E99-A40F-4B1E122D00D6"
NOTIF_SOURCE_UUID = "9FBF120D-6301-42D9-8C58-25E699A21DBD"
CONTROL_POINT_UUID = "69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9"
DATA_SOURCE_UUID = "22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IncompleteResponseError(Exception):
    """Raised when a Data Source TLV payload is shorter than its declared length."""


# ---------------------------------------------------------------------------
# Parser functions
# ---------------------------------------------------------------------------

_CATEGORY_NAMES = {
    0: "other",
    1: "incoming_call",
    2: "missed_call",
    3: "voicemail",
    4: "social",
    5: "schedule",
    6: "email",
    7: "news",
    8: "health_and_fitness",
    9: "business_and_finance",
    10: "location",
    11: "entertainment",
}


def parse_notification_source(data: bytes) -> dict:
    """Parse an 8-byte Notification Source characteristic value.

    Wire format (little-endian):
      B  EventID        (0=Added, 1=Modified, 2=Removed)
      B  EventFlags     (bitmask)
      B  CategoryID
      B  CategoryCount
      L  NotificationUID (4-byte LE uint32)

    Raises ValueError if len(data) != 8.
    """
    if len(data) != 8:
        raise ValueError(f"Notification Source must be 8 bytes, got {len(data)}")
    event_id, event_flags, category_id, category_count, notification_uid = (
        struct.unpack("<BBBBL", data)
    )
    return {
        "event_id": event_id,
        "event_flags": event_flags,
        "category_id": category_id,
        "category_count": category_count,
        "notification_uid": notification_uid,
        "category": _CATEGORY_NAMES.get(category_id, "other"),
    }


def build_get_attrs_cmd(uid: int, attrs: list[int]) -> bytes:
    """Build a GetNotificationAttributes Control Point command.

    Format:
      CommandID=0 (1 byte) + UID (4 bytes LE) + attribute list
    ATTR_APP_ID (0): no length field
    ATTR_TITLE (1) / ATTR_MESSAGE (3): followed by max_len uint16 LE = 255
    """
    cmd = struct.pack("<BL", 0, uid)
    for attr_id in attrs:
        if attr_id in (ATTR_TITLE, ATTR_MESSAGE):
            cmd += struct.pack("<BH", attr_id, 255)
        else:
            cmd += struct.pack("<B", attr_id)
    return cmd


def parse_data_source(data: bytes) -> dict:
    """Parse a (complete) Data Source TLV payload.

    Header (5 bytes):
      B  CommandID (must be 0)
      L  NotificationUID (4-byte LE uint32)

    Then repeated TLV attributes:
      B  AttributeID
      H  Length (2-byte LE uint16)
      *  Value (Length bytes, UTF-8 with replace-mode decode)

    Returns:
      {"notification_uid": int, "attrs": {attr_id: str, ...}}

    Raises:
      ValueError if CommandID != 0 or data is shorter than header.
      IncompleteResponseError if a TLV value is truncated.
    """
    if len(data) < 5:
        raise ValueError(f"Data Source payload too short: {len(data)} bytes")

    command_id = data[0]
    if command_id != 0:
        raise ValueError(f"Unexpected CommandID {command_id!r} (expected 0)")

    notification_uid = struct.unpack_from("<L", data, 1)[0]

    attrs: dict[int, str] = {}
    offset = 5
    while offset < len(data):
        if offset + 3 > len(data):
            raise IncompleteResponseError(
                f"Truncated TLV header at offset {offset}"
            )
        attr_id = data[offset]
        length = struct.unpack_from("<H", data, offset + 1)[0]
        offset += 3
        if offset + length > len(data):
            raise IncompleteResponseError(
                f"Truncated TLV value for attr {attr_id}: "
                f"need {length} bytes at offset {offset}, have {len(data) - offset}"
            )
        value = data[offset: offset + length].decode("utf-8", errors="replace")
        attrs[attr_id] = value
        offset += length

    return {"notification_uid": notification_uid, "attrs": attrs}


# ---------------------------------------------------------------------------
# Fragmentation buffer
# ---------------------------------------------------------------------------


class ANCSDataBuffer:
    """Accumulate fragmented Data Source characteristic chunks per UID.

    Usage:
      buf = ANCSDataBuffer()
      complete = buf.accumulate(uid, chunk)  # returns None if still incomplete
      if complete is not None:
          result = parse_data_source(complete)
          buf.clear(uid)
    """

    def __init__(self) -> None:
        self._buffers: dict[int, bytearray] = {}

    def accumulate(self, notif_uid: int, chunk: bytes) -> bytes | None:
        """Append *chunk* to the buffer for *notif_uid*.

        Returns the complete payload bytes when the TLV is fully assembled,
        or None if more chunks are expected.

        Completeness heuristic: the header is parseable (≥5 bytes) and the
        total declared TLV payload fits within the accumulated buffer.
        """
        if notif_uid not in self._buffers:
            self._buffers[notif_uid] = bytearray()
        self._buffers[notif_uid].extend(chunk)
        buf = self._buffers[notif_uid]

        if len(buf) < 5:
            return None

        # Walk TLV to check for completeness.
        offset = 5
        while offset < len(buf):
            if offset + 3 > len(buf):
                return None  # truncated TLV header
            length = struct.unpack_from("<H", buf, offset + 1)[0]
            next_offset = offset + 3 + length
            if next_offset > len(buf):
                return None  # truncated TLV value
            offset = next_offset

        return bytes(buf)

    def clear(self, notif_uid: int) -> None:
        """Discard the accumulated buffer for *notif_uid*."""
        self._buffers.pop(notif_uid, None)

    def clear_all(self) -> None:
        """Discard all accumulated buffers (e.g. on device disconnect)."""
        self._buffers.clear()
