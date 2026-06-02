"""bluez_map — pure-Python MAP helpers (no D-Bus).

Public API consumed by tests and by MapBackend:
  build_bmessage(body, **kwargs) -> str
  parse_map_messages(messages: dict) -> list[dict]
  map_messages_to_conversations(messages: list[dict]) -> dict
"""
from __future__ import annotations


def build_bmessage(
    body: str,
    *,
    sender: str = "",
    sender_tel: str = "",
    folder: str = "telecom/msg/inbox",
    status: str = "UNREAD",
    msg_type: str = "SMS_GSM",
) -> str:
    """Return a bMessage-format string for *body*.

    LENGTH is the UTF-8 byte count of the BEGIN:MSG…END:MSG block, so
    multi-byte characters (accented letters, emoji) count correctly.
    """
    msg_block = f"BEGIN:MSG\r\n{body}\r\nEND:MSG\r\n"
    length = len(msg_block.encode("utf-8"))

    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    if sender:
        vcard_lines.append(f"FN:{sender}")
    if sender_tel:
        vcard_lines.append(f"TEL:{sender_tel}")
    vcard_lines.append("END:VCARD")
    vcard = "\r\n".join(vcard_lines) + "\r\n"

    return (
        "BEGIN:BMESSAGE\r\n"
        "VERSION:1.0\r\n"
        f"STATUS:{status}\r\n"
        f"TYPE:{msg_type}\r\n"
        f"FOLDER:{folder}\r\n"
        "BEGIN:BENV\r\n"
        + vcard
        + "BEGIN:BBODY\r\n"
        "CHARSET:UTF-8\r\n"
        f"LENGTH:{length}\r\n"
        f"{msg_block}"
        "END:BBODY\r\n"
        "END:BENV\r\n"
        "END:BMESSAGE\r\n"
    )


def parse_map_messages(messages: dict) -> list[dict]:
    """Convert the a{oa{sv}} ListMessages dict to a list of normalised dicts.

    Each output dict has keys: handle, sender, timestamp, is_read, subject,
    msg_type.
    """
    result = []
    for _path, props in messages.items():
        result.append({
            "handle": str(props.get("Handle", "")),
            "sender": str(props.get("Sender", "")),
            "timestamp": str(props.get("Datetime", "")),
            "is_read": bool(props.get("Read", False)),
            "subject": str(props.get("Subject", "")),
            "msg_type": str(props.get("Type", "")),
        })
    return result


def map_messages_to_conversations(messages: list[dict]) -> dict:
    """Group a list of parsed messages by sender.

    Returns a dict keyed by sender string; each value is:
      {sender: str, messages: list[dict], unread_count: int}
    """
    convs: dict[str, dict] = {}
    for msg in messages:
        sender = msg["sender"]
        if sender not in convs:
            convs[sender] = {"sender": sender, "messages": [], "unread_count": 0}
        convs[sender]["messages"].append(msg)
        if not msg["is_read"]:
            convs[sender]["unread_count"] += 1
    return convs
