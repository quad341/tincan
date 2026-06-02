"""Fixture: ANCS GetNotificationAttributes response payload (Data Source characteristic).

Wire format:
  Offset  Size  Field
  0       1     CommandID (0=GetNotificationAttributes)
  1       4     NotificationUID (big-endian uint32)
  5+      TLV   Attributes: [AttributeID(1) | Length(2 little-endian) | Value(Length)]

Attribute IDs:
  0   AppIdentifier
  1   Title
  3   Message
"""

# CommandID=0x00, UID=0x00012345, Title="Hello" (5 bytes), Message="World" (5 bytes)
GET_ATTRS_TITLE_AND_MESSAGE = bytes([
    0x00,                           # CommandID = GetNotificationAttributes
    0x00, 0x01, 0x23, 0x45,         # NotificationUID big-endian = 0x00012345
    0x01, 0x05, 0x00,               # AttributeID=Title, Length=5 (LE)
    0x48, 0x65, 0x6C, 0x6C, 0x6F,  # "Hello"
    0x03, 0x05, 0x00,               # AttributeID=Message, Length=5 (LE)
    0x57, 0x6F, 0x72, 0x6C, 0x64,  # "World"
])
