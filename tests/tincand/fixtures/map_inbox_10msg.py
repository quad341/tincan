"""Fixture: 10-message MAP inbox in a{oa{sv}} format (plain Python dicts).

Represents the structure returned by obex.MessageAccess1.ListMessages() after
normalisation — keyed by object path, values are property dicts matching the
spike output from m01_map.py.

Conversation breakdown (used in test assertions):
  Alice  — 3 messages, 2 unread (SMS_GSM)
  Bob    — 4 messages, 1 unread (SMS_CDMA)
  Carol  — 3 messages, 0 unread (SMS_GSM, iMessage reported as SMS_GSM type)

Total: 10 messages, 3 unread.
"""

MAP_INBOX_10MSG: dict[str, dict] = {
    # ── Alice: 3 messages, 2 unread ──────────────────────────────────────────
    "/org/bluez/obex/message/00001": {
        "Handle": "00001",
        "Sender": "Alice",
        "SenderAddressing": "+15551000001",
        "Datetime": "20240101T100000",
        "Read": False,
        "Subject": "Hey",
        "Type": "SMS_GSM",
    },
    "/org/bluez/obex/message/00002": {
        "Handle": "00002",
        "Sender": "Alice",
        "SenderAddressing": "+15551000001",
        "Datetime": "20240101T103000",
        "Read": True,
        "Subject": "Are you there?",
        "Type": "SMS_GSM",
    },
    "/org/bluez/obex/message/00003": {
        "Handle": "00003",
        "Sender": "Alice",
        "SenderAddressing": "+15551000001",
        "Datetime": "20240101T110000",
        "Read": False,
        "Subject": "Hello?",
        "Type": "SMS_GSM",
    },
    # ── Bob: 4 messages, 1 unread ─────────────────────────────────────────────
    "/org/bluez/obex/message/00004": {
        "Handle": "00004",
        "Sender": "Bob",
        "SenderAddressing": "+15552000001",
        "Datetime": "20240101T090000",
        "Read": True,
        "Subject": "How's it going",
        "Type": "SMS_CDMA",
    },
    "/org/bluez/obex/message/00005": {
        "Handle": "00005",
        "Sender": "Bob",
        "SenderAddressing": "+15552000001",
        "Datetime": "20240101T091500",
        "Read": True,
        "Subject": "OK",
        "Type": "SMS_CDMA",
    },
    "/org/bluez/obex/message/00006": {
        "Handle": "00006",
        "Sender": "Bob",
        "SenderAddressing": "+15552000001",
        "Datetime": "20240101T093000",
        "Read": False,
        "Subject": "Wait",
        "Type": "SMS_CDMA",
    },
    "/org/bluez/obex/message/00007": {
        "Handle": "00007",
        "Sender": "Bob",
        "SenderAddressing": "+15552000001",
        "Datetime": "20240101T094500",
        "Read": True,
        "Subject": "Never mind",
        "Type": "SMS_CDMA",
    },
    # ── Carol: 3 messages, 0 unread (iMessage reported as SMS_GSM) ───────────
    "/org/bluez/obex/message/00008": {
        "Handle": "00008",
        "Sender": "Carol",
        "SenderAddressing": "+15553000001",
        "Datetime": "20240101T080000",
        "Read": True,
        "Subject": "iMessage test",
        "Type": "SMS_GSM",
    },
    "/org/bluez/obex/message/00009": {
        "Handle": "00009",
        "Sender": "Carol",
        "SenderAddressing": "+15553000001",
        "Datetime": "20240101T081500",
        "Read": True,
        "Subject": "Another iMessage",
        "Type": "SMS_GSM",
    },
    "/org/bluez/obex/message/00010": {
        "Handle": "00010",
        "Sender": "Carol",
        "SenderAddressing": "+15553000001",
        "Datetime": "20240101T083000",
        "Read": True,
        "Subject": "Final message",
        "Type": "SMS_GSM",
    },
}

# Expected aggregates — used in test assertions.
EXPECTED_SENDER_COUNT = 3          # Alice, Bob, Carol
EXPECTED_TOTAL_MESSAGES = 10
EXPECTED_TOTAL_UNREAD = 3          # Alice:2, Bob:1, Carol:0
EXPECTED_ALICE_UNREAD = 2
EXPECTED_BOB_UNREAD = 1
EXPECTED_CAROL_UNREAD = 0
