"""Fixture: ANCS Notification Source payloads for tincand.ancs_util (8 bytes each).

Wire format per Apple ANCS spec (struct.unpack('<BBBBL', data)):
  Offset  Size  Field
  0       1     EventID       (0=Added, 1=Modified, 2=Removed)
  1       1     EventFlags    (bitmask)
  2       1     CategoryID
  3       1     CategoryCount
  4       4     NotificationUID (LITTLE-endian uint32)

Note: UID is little-endian — bytes [0x01, 0x00, 0x00, 0x00] → UID=1
"""

# EventID=Added(0), Flags=0, CategoryID=6 (Social/SMS), Count=1, UID=0x00000001 LE
NOTIF_UTIL_SOCIAL = bytes([0x00, 0x00, 0x06, 0x01, 0x01, 0x00, 0x00, 0x00])

# EventID=Added(0), Flags=0, CategoryID=4 (IncomingCall), Count=1, UID=0x0000ABCD LE
NOTIF_UTIL_INCOMING = bytes([0x00, 0x00, 0x04, 0x01, 0xCD, 0xAB, 0x00, 0x00])

# EventID=Modified(1), Flags=0x02 (NegativeAction), CategoryID=2, Count=2, UID=0xFFFFFFFE LE
NOTIF_UTIL_MODIFIED = bytes([0x01, 0x02, 0x02, 0x02, 0xFE, 0xFF, 0xFF, 0xFF])

# ---------------------------------------------------------------------------
# GetNotificationAttributes / Data Source fixtures (parse_data_source)
# Wire format:
#   Offset 0    CommandID (must be 0)
#   Offset 1..4 NotificationUID LITTLE-endian uint32
#   Offset 5+   TLV: [attr_id(1) | length(2 LE) | value(length bytes UTF-8)]
#     Attr 0 = AppIdentifier, 1 = Title, 3 = Message
# ---------------------------------------------------------------------------

# CommandID=0, UID=0x00000001 LE, Title="Hello" (5 bytes), Message="World" (5 bytes)
GET_ATTRS_TITLE_AND_MESSAGE_LE = bytes([
    0x00,                            # CommandID = GetNotificationAttributes
    0x01, 0x00, 0x00, 0x00,          # NotificationUID LE = 1
    0x01, 0x05, 0x00,                # AttrID=Title(1), Length=5 LE
    0x48, 0x65, 0x6C, 0x6C, 0x6F,   # "Hello"
    0x03, 0x05, 0x00,                # AttrID=Message(3), Length=5 LE
    0x57, 0x6F, 0x72, 0x6C, 0x64,   # "World"
])

# CommandID=0, UID=0x0000ABCD LE, Title only (no message attr)
GET_ATTRS_TITLE_ONLY_LE = bytes([
    0x00,
    0xCD, 0xAB, 0x00, 0x00,          # UID=0x0000ABCD LE
    0x01, 0x04, 0x00,                # AttrID=Title, Length=4
    0x54, 0x65, 0x73, 0x74,          # "Test"
])
