"""Fixture: ANCS Notification Source characteristic payloads (8 bytes each).

Wire format (Apple ANCS specification):
  Offset  Size  Field
  0       1     EventID       (0=Added, 1=Modified, 2=Removed)
  1       1     EventFlags    (bitmask)
  2       1     CategoryID    (0=Other, 1=IncomingCall, 2=MissedCall, 4=Social/Messages)
  3       1     CategoryCount
  4       4     NotificationUID (big-endian uint32)
"""

# EventID=Added(0x00), Flags=0x00, Category=Messages(0x04),
# Count=1, UID=0x00012345
NOTIF_MESSAGES = bytes([0x00, 0x00, 0x04, 0x01, 0x00, 0x01, 0x23, 0x45])

# EventID=Added(0x00), Flags=0x00, Category=IncomingCall(0x01),
# Count=1, UID=0x0000ABCD
NOTIF_INCOMING_CALL = bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0xAB, 0xCD])

# EventID=Added(0x00), Flags=0x02 (NegativeAction), Category=MissedCall(0x02),
# Count=2, UID=0xFFFFFFFE
NOTIF_MISSED_CALL = bytes([0x00, 0x02, 0x02, 0x02, 0xFF, 0xFF, 0xFF, 0xFE])
