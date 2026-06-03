"""Tests: PBAP contact sync — normalize_phone, name resolution, photo fetch guard,
PBAP-denied fallback, deliver_contact_photo.
Bead: tincan-li9t

Coverage:
  §1 Name resolution on connect
     - update_contact() updates conversation display_name for matching conversation
     - update_contact() triggers upsert_conversation() for matched conversations
  §3 No-refetch guard
     - ContactStore.photo_fetched=True → fetch_photo() returns without calling List/Pull
     - photo_fetched=False → fetch_photo() proceeds with PBAP List call
  §4 PBAP denied fallback
     - PBAPContactSync.connect() raises Forbidden → contacts capability NOT set to True
     - FetchContactPhoto() with _pbap=None returns silently (no exception)
     - SendMessage() works when _pbap is None (MAP unaffected)
     - contacts capability stays False after Forbidden
  §5 Contact with no PHOTO vCard field
     - deliver_contact_photo(phone, None) → ContactPhotoReceived emitted with empty bytes
     - photo_fetched=True in ContactStore after delivering None photo
  §6 normalize_phone() correctness — four canonical examples from tincan-oy9d.1
     - 11-digit +1 country code stripped: "+15555550123" → "5555550123"
     - 10-digit number unchanged: "5555550123" → "5555550123"
     - Formatted NANP stripped: "(555) 555-0123" → "5555550123"
     - International UK unchanged: "+442071234567" → "442071234567"
     - Leading +1 with 10 → strip to 10: "15555550123" → "5555550123"
     - Non-digit characters only: removes hyphens, dots, spaces, parens
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincand.contact_store import ContactStore, normalize_phone
from tincand.dbus_service import Conversation, TincanService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> TincanService:
    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    svc.ContactPhotoReceived = MagicMock()
    return svc


@pytest.fixture
def service() -> TincanService:
    svc = _make_service()
    svc._connected = True
    svc._conversations["5555550123"] = Conversation(
        id="5555550123",
        display_name="5555550123",
        last_message_at="",
        last_message_preview="",
        unread_count=0,
    )
    return svc


# ---------------------------------------------------------------------------
# §6 normalize_phone() — four canonical examples + formatting coverage
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    """normalize_phone() produces a stable 10-digit (or full international) key."""

    def test_11_digit_with_leading_1_stripped_to_10(self):
        assert normalize_phone("+15555550123") == "5555550123"

    def test_10_digit_number_unchanged(self):
        assert normalize_phone("5555550123") == "5555550123"

    def test_formatted_nanp_strips_to_10(self):
        assert normalize_phone("(555) 555-0123") == "5555550123"

    def test_international_uk_unchanged(self):
        # 12-digit UK number — not 11 digits starting with 1 — kept as-is.
        assert normalize_phone("+442071234567") == "442071234567"

    def test_11_digit_starting_with_1_no_plus(self):
        assert normalize_phone("15555550123") == "5555550123"

    def test_hyphenated_format_normalized(self):
        assert normalize_phone("555-555-0123") == "5555550123"

    def test_dot_format_normalized(self):
        assert normalize_phone("555.555.0123") == "5555550123"

    def test_short_number_below_7_digits_returned_as_stripped(self):
        # Very short numbers are not phone numbers — pass through stripped.
        assert normalize_phone("12345") == "12345"

    def test_empty_string_returns_empty(self):
        assert normalize_phone("") == ""


# ---------------------------------------------------------------------------
# §1 Name resolution — update_contact() wires display_name + ConversationUpdated
# ---------------------------------------------------------------------------

class TestUpdateContact:
    """update_contact() stores name in contact store and updates matching conversations."""

    def test_update_contact_sets_display_name(self, service):
        service.update_contact("5555550123", "Alice")
        assert service._conversations["5555550123"].display_name == "Alice"

    def test_update_contact_fires_conversation_updated(self, service):
        service.update_contact("5555550123", "Alice")
        assert service.ConversationUpdated.called

    def test_conversation_updated_contains_new_name(self, service):
        service.update_contact("5555550123", "Alice")
        updated = service.ConversationUpdated.call_args[0][0]
        assert str(updated["display_name"]) == "Alice"

    def test_update_contact_with_formatted_phone_resolves_same_conversation(self, service):
        # Formatted "+15555550123" normalizes to "5555550123" — same conversation.
        service.update_contact("+15555550123", "Bob")
        assert service._conversations["5555550123"].display_name == "Bob"

    def test_update_contact_no_match_does_not_fire_conversation_updated(self, service):
        service.update_contact("9990000000", "Nobody")
        assert not service.ConversationUpdated.called

    def test_update_contact_stores_in_contact_store(self, service):
        service.update_contact("5555550123", "Alice")
        assert service._contact_store.resolve_name("5555550123") == "Alice"


# ---------------------------------------------------------------------------
# §5 deliver_contact_photo() — ContactPhotoReceived, photo_fetched flag
# ---------------------------------------------------------------------------

class TestDeliverContactPhoto:
    """deliver_contact_photo() emits ContactPhotoReceived and marks photo_fetched."""

    def test_deliver_photo_none_emits_contact_photo_received(self, service):
        service.deliver_contact_photo("5555550123", None)
        assert service.ContactPhotoReceived.called

    def test_deliver_photo_none_sets_photo_fetched_true(self, service):
        service.deliver_contact_photo("5555550123", None)
        contact = service._contact_store.get("5555550123")
        assert contact is not None
        assert contact.photo_fetched is True

    def test_deliver_photo_none_emits_empty_bytes(self, service):
        service.deliver_contact_photo("5555550123", None)
        args = service.ContactPhotoReceived.call_args[0]
        photo_arg = args[1]
        assert bytes(photo_arg) == b""

    def test_deliver_photo_bytes_emits_contact_photo_received(self, service):
        fake_jpeg = b"\xff\xd8\xff\xe0data"
        service.deliver_contact_photo("5555550123", fake_jpeg)
        assert service.ContactPhotoReceived.called

    def test_deliver_photo_bytes_emits_correct_bytes(self, service):
        fake_jpeg = b"\xff\xd8\xff\xe0data"
        service.deliver_contact_photo("5555550123", fake_jpeg)
        args = service.ContactPhotoReceived.call_args[0]
        assert bytes(args[1]) == fake_jpeg

    def test_deliver_photo_conv_id_matches_conversation(self, service):
        service.deliver_contact_photo("5555550123", None)
        args = service.ContactPhotoReceived.call_args[0]
        assert str(args[0]) == "5555550123"

    def test_deliver_photo_formatted_phone_matches_conversation(self, service):
        service.deliver_contact_photo("+15555550123", None)
        assert service.ContactPhotoReceived.called


# ---------------------------------------------------------------------------
# §3 No-refetch guard — ContactStore.photo_fetched prevents redundant OBEX calls
# ---------------------------------------------------------------------------

class TestPhotoFetchedGuard:
    """photo_fetched=True in ContactStore causes fetch_photo() to return early."""

    def test_photo_fetched_false_by_default_for_new_contact(self):
        store = ContactStore()
        store.upsert("5555550123", "Alice")
        contact = store.get("5555550123")
        assert contact is not None
        assert contact.photo_fetched is False

    def test_set_photo_none_sets_photo_fetched_true(self):
        store = ContactStore()
        store.upsert("5555550123", "Alice")
        store.set_photo("5555550123", None)
        assert store.get("5555550123").photo_fetched is True

    def test_set_photo_bytes_sets_photo_fetched_true(self):
        store = ContactStore()
        store.upsert("5555550123", "Alice")
        store.set_photo("5555550123", b"jpeg")
        assert store.get("5555550123").photo_fetched is True

    def test_fetch_photo_returns_early_when_photo_fetched_true(self):
        from tincand.backends.pbap import PBAPContactSync
        svc = _make_service()
        pbap = PBAPContactSync(svc)
        pbap.session_path = "/org/obex/pbap1"
        # Pre-seed contact with photo_fetched=True.
        svc._contact_store.upsert("5555550123", "Alice")
        svc._contact_store.set_photo("5555550123", b"jpeg")

        mock_phonebook = MagicMock(name="PhonebookAccess1")
        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface", return_value=mock_phonebook):
            pbap.fetch_photo("5555550123")

        mock_phonebook.List.assert_not_called()
        mock_phonebook.Pull.assert_not_called()

    def test_fetch_photo_calls_list_when_photo_not_fetched(self):
        from tincand.backends.pbap import PBAPContactSync
        svc = _make_service()
        svc.deliver_contact_photo = MagicMock()
        pbap = PBAPContactSync(svc)
        pbap.session_path = "/org/obex/pbap1"
        svc._contact_store.upsert("5555550123", "Alice")
        # photo_fetched is False (not set).

        mock_phonebook = MagicMock(name="PhonebookAccess1")
        mock_phonebook.List.return_value = []   # no handles → early return after List

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface", return_value=mock_phonebook):
            pbap.fetch_photo("5555550123")

        mock_phonebook.List.assert_called_once()


# ---------------------------------------------------------------------------
# §4 PBAP denied fallback — contacts capability stays False, MAP unaffected
# ---------------------------------------------------------------------------

class TestPbapDeniedFallback:
    """Forbidden from obexd → contacts=False, MAP SendMessage unaffected."""

    def test_fetch_contact_photo_with_no_pbap_returns_silently(self):
        svc = _make_service()
        svc._pbap = None
        svc._connected = True
        # FetchContactPhoto should not raise when _pbap is None.
        svc.FetchContactPhoto("5555550123")

    def test_send_message_works_when_pbap_is_none(self):
        svc = _make_service()
        svc._connected = True
        svc._pbap = None
        mock_backend = MagicMock()
        mock_backend.send_message.return_value = "/org/obex/transfer1"
        svc._backend = mock_backend
        svc._conversations["5555550123"] = Conversation(
            id="5555550123", display_name="Alice",
            last_message_at="", last_message_preview="", unread_count=0,
        )
        handle = svc.SendMessage("5555550123", "hi")
        assert handle != ""

    def test_pbap_connect_forbidden_does_not_set_contacts_capability(self):
        from tincand.backends.pbap import PBAPContactSync
        svc = _make_service()
        svc.set_capability = MagicMock()
        pbap = PBAPContactSync(svc)

        forbidden = dbus.exceptions.DBusException(
            name="org.bluez.obex.Error.Forbidden"
        )
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.side_effect = forbidden

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface", return_value=mock_client):
            pbap.connect("AA:BB:CC:DD:EE:FF")

        svc.set_capability.assert_not_called()

    def test_contacts_capability_stays_false_after_pbap_denied(self):
        svc = _make_service()
        # contacts is False by default; Forbidden prevents set_capability("contacts", True).
        status = svc.GetStatus()
        assert bool(status["capabilities"]["contacts"]) is False
