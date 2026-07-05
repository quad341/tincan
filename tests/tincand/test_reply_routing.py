"""Tests: reply routing and name-keyed conversation merge (tincan-g1vs).

Coverage:
  §1 _resolve_to_phone — name resolution priority order
     - Phone-shaped to passes through normalize_phone
     - Contact store lookup resolves name to phone (PBAP populated)
     - Conversation scan fallback (PBAP empty) resolves name via display_name match
     - Unknown name falls back unchanged

  §2 SendMessage routing — resolved phone passed to backend
     - Name-keyed conv routes to phone via contact store
     - Name-keyed conv routes to phone via conversation scan (PBAP empty)
     - Phone-shaped to passes through without alteration

  §3 update_contact — PBAP name merge removes duplicate name-keyed thread
     - After update_contact, name-keyed conv removed from _conversations
     - After update_contact, messages migrated to phone-keyed conv
     - After update_contact, ConversationUpdated emitted for merged phone-keyed conv
     - Name-keyed conv merged into existing phone-keyed slot (unread_count combined)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.service

from tincand.contact_store import normalize_phone
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
    return svc


def _connected_service_with_backend(backend=None) -> TincanService:
    svc = _make_service()
    svc._connected = True
    if backend is None:
        backend = MagicMock(name="backend")
        backend.send_message.return_value = "/org/obex/transfer1"
    svc._backend = backend
    return svc


# ---------------------------------------------------------------------------
# §1  _resolve_to_phone — name resolution priority order
# ---------------------------------------------------------------------------

class TestResolveToPhone:
    """_resolve_to_phone() must follow the 3-step resolution order."""

    def test_phone_shaped_to_passes_through(self):
        svc = _make_service()
        result = TincanService._resolve_to_phone("+15550001234", {}, svc._contact_store)
        assert result == normalize_phone("+15550001234")

    def test_contact_store_resolves_name_to_phone(self):
        svc = _make_service()
        svc._contact_store.upsert("8157916347", "Mom Wordelman")
        result = TincanService._resolve_to_phone("Mom Wordelman", {}, svc._contact_store)
        assert result == "8157916347"

    def test_conversation_scan_fallback_when_pbap_empty(self):
        svc = _make_service()
        convs = {
            "8157916347": Conversation(
                id="8157916347", display_name="Mom Wordelman"
            ),
        }
        result = TincanService._resolve_to_phone("Mom Wordelman", convs, svc._contact_store)
        assert result == "8157916347"

    def test_conversation_scan_case_insensitive(self):
        svc = _make_service()
        convs = {
            "8157916347": Conversation(id="8157916347", display_name="mom wordelman"),
        }
        result = TincanService._resolve_to_phone("Mom Wordelman", convs, svc._contact_store)
        assert result == "8157916347"

    def test_unknown_name_falls_back_unchanged(self):
        svc = _make_service()
        result = TincanService._resolve_to_phone("Unknown Person", {}, svc._contact_store)
        assert result == "Unknown Person"

    def test_contact_store_lookup_takes_priority_over_conv_scan(self):
        """PBAP lookup (step 2) wins over conversation scan (step 3)."""
        svc = _make_service()
        svc._contact_store.upsert("8157916347", "Mom Wordelman")
        # Conversation has a DIFFERENT phone-shaped id — contact store wins
        convs = {
            "9991234567": Conversation(id="9991234567", display_name="Mom Wordelman"),
        }
        result = TincanService._resolve_to_phone("Mom Wordelman", convs, svc._contact_store)
        assert result == "8157916347"


# ---------------------------------------------------------------------------
# §2  SendMessage routing
# ---------------------------------------------------------------------------

class TestSendMessageRouting:
    """SendMessage must pass a real phone to the backend even when to is a name."""

    def _seed_name_keyed_conv(self, svc: TincanService) -> None:
        svc._conversations["Mom Wordelman"] = Conversation(
            id="Mom Wordelman",
            display_name="Mom Wordelman",
            last_message_at="20260606T120000",
            last_message_preview="hi",
        )

    def test_name_keyed_routes_via_contact_store(self):
        svc = _connected_service_with_backend()
        self._seed_name_keyed_conv(svc)
        svc._contact_store.upsert("8157916347", "Mom Wordelman")

        svc.SendMessage("Mom Wordelman", "hello")

        svc._backend.send_message.assert_called_once()
        called_to = svc._backend.send_message.call_args[0][0]
        assert called_to == "8157916347", (
            f"backend received '{called_to}' — expected '8157916347'"
        )

    def test_name_keyed_routes_via_conv_scan_when_pbap_empty(self):
        """When contact store has no entry, scan conversations by display_name."""
        svc = _connected_service_with_backend()
        # Seed a PHONE-KEYED conversation with display_name matching the name-keyed one
        svc._conversations["8157916347"] = Conversation(
            id="8157916347", display_name="Mom Wordelman"
        )
        self._seed_name_keyed_conv(svc)

        svc.SendMessage("Mom Wordelman", "hello")

        svc._backend.send_message.assert_called_once()
        called_to = svc._backend.send_message.call_args[0][0]
        assert called_to == "8157916347"

    def test_phone_shaped_to_passes_to_backend(self):
        svc = _connected_service_with_backend()
        svc._conversations[normalize_phone("+15550009876")] = Conversation(
            id=normalize_phone("+15550009876"), display_name="Test Contact"
        )
        svc.SendMessage("+15550009876", "hello")

        svc._backend.send_message.assert_called_once()
        called_to = svc._backend.send_message.call_args[0][0]
        assert len(normalize_phone(called_to)) >= 7, (
            f"backend got non-phone '{called_to}'"
        )


# ---------------------------------------------------------------------------
# §3  update_contact — PBAP merge removes name-keyed thread
# ---------------------------------------------------------------------------

class TestUpdateContactMerge:
    """update_contact must merge name-keyed conversations into the phone-keyed slot."""

    def _seed(self, svc: TincanService) -> None:
        """Seed a name-keyed and a phone-keyed conversation for 'Mom Wordelman'."""
        svc._conversations["Mom Wordelman"] = Conversation(
            id="Mom Wordelman",
            display_name="Mom Wordelman",
            last_message_at="20260606T110000",
            last_message_preview="hey",
            unread_count=2,
        )
        svc._conversations["8157916347"] = Conversation(
            id="8157916347",
            display_name="+18157916347",
            last_message_at="20260606T090000",
            last_message_preview="",
            unread_count=1,
        )
        svc._messages["Mom Wordelman"] = [
            {"conversation_id": "Mom Wordelman", "body": "hey", "timestamp": "20260606T110000"},
        ]
        svc._message_keys.add(("Mom Wordelman", "20260606T110000", "hey"))

    def test_name_keyed_conv_removed_after_merge(self):
        svc = _make_service()
        self._seed(svc)
        svc.update_contact("+18157916347", "Mom Wordelman")
        assert "Mom Wordelman" not in svc._conversations

    def test_messages_migrated_to_phone_keyed_slot(self):
        svc = _make_service()
        self._seed(svc)
        svc.update_contact("+18157916347", "Mom Wordelman")
        msgs = svc._messages.get("8157916347", [])
        bodies = [m["body"] for m in msgs]
        assert "hey" in bodies

    def test_message_keys_re_keyed(self):
        svc = _make_service()
        self._seed(svc)
        svc.update_contact("+18157916347", "Mom Wordelman")
        # Old name-keyed tuple must be gone
        assert ("Mom Wordelman", "20260606T110000", "hey") not in svc._message_keys
        # New phone-keyed tuple must be present
        assert ("8157916347", "20260606T110000", "hey") in svc._message_keys

    def test_conversation_updated_emitted_for_merged_conv(self):
        svc = _make_service()
        self._seed(svc)
        svc.ConversationUpdated = MagicMock()
        svc.update_contact("+18157916347", "Mom Wordelman")
        updated_ids = [call.args[0]["id"] for call in svc.ConversationUpdated.call_args_list]
        assert "8157916347" in updated_ids

    def test_unread_count_combined_after_merge(self):
        svc = _make_service()
        self._seed(svc)
        svc.update_contact("+18157916347", "Mom Wordelman")
        merged = svc._conversations["8157916347"]
        assert merged.unread_count == 3  # 2 from name-keyed + 1 from phone-keyed

    def test_display_name_updated_on_phone_keyed_conv(self):
        svc = _make_service()
        self._seed(svc)
        svc.update_contact("+18157916347", "Mom Wordelman")
        assert svc._conversations["8157916347"].display_name == "Mom Wordelman"

