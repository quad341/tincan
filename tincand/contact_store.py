"""Contact store: in-memory phonebook for resolved PBAP contacts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NON_DIGIT = re.compile(r"\D")


def normalize_phone(number: str) -> str:
    """Return a canonical digit key for *number*.

    Rules:
    1. Strip all non-digit characters.
    2. If result is 11 digits AND starts with '1', strip the leading 1.
    3. Return the canonical string (10-digit US/CA or full international).
    """
    digits = _NON_DIGIT.sub("", number)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


@dataclass
class Contact:
    normalized_phone: str   # PK — always result of normalize_phone()
    name: str
    photo: bytes | None     # raw JPEG/PNG bytes or None
    photo_fetched: bool = field(default=False)  # True once fetch attempted


class ContactStore:
    """Pure in-memory contact store; no thread safety needed (GLib main loop only)."""

    def __init__(self) -> None:
        self._contacts: dict[str, Contact] = {}

    def upsert(self, phone: str, name: str) -> None:
        key = normalize_phone(phone)
        if key in self._contacts:
            self._contacts[key].name = name
        else:
            self._contacts[key] = Contact(normalized_phone=key, name=name, photo=None)

    def set_photo(self, phone: str, photo: bytes | None) -> None:
        key = normalize_phone(phone)
        if key in self._contacts:
            self._contacts[key].photo = photo
            self._contacts[key].photo_fetched = True
        else:
            self._contacts[key] = Contact(
                normalized_phone=key, name="", photo=photo, photo_fetched=True
            )

    def get(self, phone: str) -> Contact | None:
        return self._contacts.get(normalize_phone(phone))

    def resolve_name(self, phone: str) -> str | None:
        contact = self.get(phone)
        return contact.name if contact else None

    def lookup_by_name(self, name: str) -> str | None:
        """Return the normalized_phone for the first contact matching *name* (case-insensitive)."""
        name_lower = name.lower()
        for contact in self._contacts.values():
            if contact.name.lower() == name_lower:
                return contact.normalized_phone
        return None

    def clear(self) -> None:
        self._contacts.clear()
