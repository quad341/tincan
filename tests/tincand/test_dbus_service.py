"""Tests: tincand D-Bus service state transitions and on_message_received coverage.
Bead: tincan-f0e  (ref: review finding F1, tincan-mj3)

Coverage:
  - GetStatus() returns all 3 capability keys (messages/contacts/ancs) defaulting False.
  - set_capability('ancs', True) updates _capabilities and emits CapabilityChanged('ancs', True).
  - set_capability with unknown feature is silently ignored — no signal emitted.
  - Connect() resets unread_count for all conversations to 0.
  - on_message_received: unread_count increments for inbound+unread; NOT for outbound.
  - on_message_received: last_message_preview updated when timestamp >= current.
  - on_message_received: last_message_preview NOT updated when timestamp < current.
  - on_message_received: MessageReceived emitted; ConversationUpdated emitted for known conv_id.
  - on_message_received: unknown conv_id → no ConversationUpdated emitted.
  - Conversation.to_dbus() always includes last_message_preview='' and unread_count=0 as defaults.
  - MarkConversationRead: resets unread_count and emits ConversationUpdated (tincan-fdvu).

No D-Bus infrastructure needed — TincanService is instantiated with a mocked bus.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincand.dbus_service import Conversation, TincanService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    """TincanService with mocked D-Bus registration — no real bus required."""
    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    svc.AppNotificationReceived = MagicMock()
    return svc


@pytest.fixture
def connected_service(service):
    """Service fixture already in connected state with one conversation."""
    service._connected = True
    service._conversations["conv-1"] = Conversation(
        id="conv-1",
        display_name="Alice",
        last_message_at="2024-01-01T10:00:00",
        last_message_preview="",
        unread_count=0,
    )
    return service


# ---------------------------------------------------------------------------
# §1 Conversation.to_dbus — default field presence
# ---------------------------------------------------------------------------

class TestConversationToDbus:
    """to_dbus() always includes last_message_preview and unread_count."""

    def test_always_has_last_message_preview_key(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert "last_message_preview" in d

    def test_last_message_preview_defaults_to_empty_string(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert str(d["last_message_preview"]) == ""

    def test_always_has_unread_count_key(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert "unread_count" in d

    def test_unread_count_defaults_to_zero(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert int(d["unread_count"]) == 0

    def test_unread_count_is_uint32_type(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert isinstance(d["unread_count"], dbus.UInt32)


# ---------------------------------------------------------------------------
# §2 GetStatus — capability keys always present
# ---------------------------------------------------------------------------

class TestGetStatus:
    """GetStatus() returns all three capability keys defaulting to False when disconnected."""

    def test_returns_messages_key_false_when_disconnected(self, service):
        status = service.GetStatus()
        assert bool(status["capabilities"]["messages"]) is False

    def test_returns_contacts_key_false_when_disconnected(self, service):
        status = service.GetStatus()
        assert bool(status["capabilities"]["contacts"]) is False

    def test_returns_ancs_key_false_when_disconnected(self, service):
        status = service.GetStatus()
        assert bool(status["capabilities"]["ancs"]) is False

    def test_all_three_capability_keys_present(self, service):
        caps = service.GetStatus()["capabilities"]
        assert set(caps.keys()) >= {"messages", "contacts", "ancs"}


# ---------------------------------------------------------------------------
# §3 set_capability
# ---------------------------------------------------------------------------

class TestSetCapability:
    """set_capability updates _capabilities and emits CapabilityChanged."""

    def test_ancs_true_updates_capabilities_dict(self, service):
        service.set_capability("ancs", True)
        assert service._capabilities["ancs"] is True

    def test_ancs_true_emits_capability_changed(self, service):
        service.set_capability("ancs", True)
        service.CapabilityChanged.assert_called_once_with("ancs", True)

    def test_ancs_false_updates_capabilities_dict(self, service):
        service._capabilities["ancs"] = True
        service.set_capability("ancs", False)
        assert service._capabilities["ancs"] is False

    def test_unknown_feature_does_not_update_capabilities(self, service):
        original = dict(service._capabilities)
        service.set_capability("unknown_feature", True)
        assert service._capabilities == original

    def test_unknown_feature_does_not_emit_signal(self, service):
        service.set_capability("unknown_feature", True)
        service.CapabilityChanged.assert_not_called()


# ---------------------------------------------------------------------------
# §4 Connect — resets unread_count
# ---------------------------------------------------------------------------

class TestConnect:
    """Connect() resets unread_count to 0 for all conversations."""

    def test_connect_resets_single_conversation_unread_count(self, service):
        service._conversations["c1"] = Conversation(
            id="c1", display_name="Alice", unread_count=5,
        )
        service.Connect("AA:BB:CC:DD:EE:FF")
        assert service._conversations["c1"].unread_count == 0

    def test_connect_resets_multiple_conversation_unread_counts(self, service):
        service._conversations["c1"] = Conversation(
            id="c1", display_name="Alice", unread_count=3,
        )
        service._conversations["c2"] = Conversation(
            id="c2", display_name="Bob", unread_count=7,
        )
        service.Connect("AA:BB:CC:DD:EE:FF")
        assert service._conversations["c1"].unread_count == 0
        assert service._conversations["c2"].unread_count == 0

    def test_connect_with_zero_unread_count_stays_zero(self, service):
        service._conversations["c1"] = Conversation(
            id="c1", display_name="Alice", unread_count=0,
        )
        service.Connect("AA:BB:CC:DD:EE:FF")
        assert service._conversations["c1"].unread_count == 0


# ---------------------------------------------------------------------------
# §5 on_message_received — unread_count and preview logic
# ---------------------------------------------------------------------------

class TestOnMessageReceivedUnreadCount:
    """unread_count increments only for inbound+unread messages."""

    def test_inbound_unread_increments_count(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Hey",
            "timestamp": "2024-01-01T11:00:00",
        })
        assert connected_service._conversations["conv-1"].unread_count == 1

    def test_inbound_unread_increments_count_again(self, connected_service):
        connected_service._conversations["conv-1"].unread_count = 2
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Another",
            "timestamp": "2024-01-01T11:01:00",
        })
        assert connected_service._conversations["conv-1"].unread_count == 3

    def test_outbound_does_not_increment_count(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "outbound",
            "status": "sent",
            "body": "Reply",
            "timestamp": "2024-01-01T11:00:00",
        })
        assert connected_service._conversations["conv-1"].unread_count == 0

    def test_inbound_read_does_not_increment_count(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "read",
            "body": "Already read",
            "timestamp": "2024-01-01T11:00:00",
        })
        assert connected_service._conversations["conv-1"].unread_count == 0


class TestOnMessageReceivedPreview:
    """last_message_preview updated only when timestamp >= current last_message_at."""

    def test_preview_updated_when_timestamp_is_newer(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "New message",
            "timestamp": "2024-01-01T11:00:00",  # after 10:00:00
        })
        assert connected_service._conversations["conv-1"].last_message_preview == "New message"

    def test_preview_updated_when_timestamp_is_equal(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Same time",
            "timestamp": "2024-01-01T10:00:00",  # equal to last_message_at
        })
        assert connected_service._conversations["conv-1"].last_message_preview == "Same time"

    def test_preview_not_updated_when_timestamp_is_older(self, connected_service):
        connected_service._conversations["conv-1"].last_message_preview = "Recent"
        connected_service._conversations["conv-1"].last_message_at = "2024-01-01T10:00:00"
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Stale message",
            "timestamp": "2024-01-01T09:00:00",  # before 10:00:00
        })
        assert connected_service._conversations["conv-1"].last_message_preview == "Recent"


class TestOnMessageReceivedSignals:
    """MessageReceived always emitted; ConversationUpdated only for known conv_id."""

    def test_message_received_signal_emitted(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Hi",
            "timestamp": "2024-01-01T11:00:00",
        })
        connected_service.MessageReceived.assert_called_once()

    def test_conversation_updated_emitted_for_known_conv_id(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "Hi",
            "timestamp": "2024-01-01T11:00:00",
        })
        connected_service.ConversationUpdated.assert_called_once()

    def test_message_received_emitted_for_unknown_conv_id(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "unknown-conv",
            "direction": "inbound",
            "status": "unread",
            "body": "Hi",
            "timestamp": "2024-01-01T11:00:00",
        })
        connected_service.MessageReceived.assert_called_once()

    def test_conversation_updated_not_emitted_for_unknown_conv_id(self, connected_service):
        connected_service.on_message_received({
            "conversation_id": "unknown-conv",
            "direction": "inbound",
            "status": "unread",
            "body": "Hi",
            "timestamp": "2024-01-01T11:00:00",
        })
        connected_service.ConversationUpdated.assert_not_called()


# ---------------------------------------------------------------------------
# §N MarkConversationRead (tincan-fdvu)
# ---------------------------------------------------------------------------

class TestMarkConversationRead:
    """MarkConversationRead resets unread_count and emits ConversationUpdated."""

    def test_resets_unread_count_to_zero(self, service):
        service._conversations["conv-1"] = Conversation(
            id="conv-1", display_name="Alice", unread_count=5,
        )
        service.MarkConversationRead("conv-1")
        assert service._conversations["conv-1"].unread_count == 0

    def test_emits_conversation_updated(self, service):
        service._conversations["conv-1"] = Conversation(
            id="conv-1", display_name="Alice", unread_count=3,
        )
        service.MarkConversationRead("conv-1")
        service.ConversationUpdated.assert_called_once()

    def test_emitted_payload_has_zero_unread_count(self, service):
        service._conversations["conv-1"] = Conversation(
            id="conv-1", display_name="Alice", unread_count=2,
        )
        service.MarkConversationRead("conv-1")
        args = service.ConversationUpdated.call_args[0][0]
        assert int(args["unread_count"]) == 0

    def test_noop_when_already_zero_no_signal(self, service):
        service._conversations["conv-1"] = Conversation(
            id="conv-1", display_name="Alice", unread_count=0,
        )
        service.MarkConversationRead("conv-1")
        service.ConversationUpdated.assert_not_called()

    def test_noop_for_unknown_conversation_id(self, service):
        service.MarkConversationRead("no-such-conv")
        service.ConversationUpdated.assert_not_called()


# ---------------------------------------------------------------------------
# §N AppNotificationReceived signal + filter API (tincan-9kav TDD spec)
# ---------------------------------------------------------------------------

_APP_NOTIF = {
    "app_id": "com.whatsapp.WhatsApp",
    "title": "Alice",
    "subtitle": "",
    "body": "Hey!",
    "category": "",
    "category_id": 0,
    "event_flags": 0,
}


@pytest.fixture
def notif_service(service):
    """service fixture with filter enabled+allowed by default."""
    service._notification_filter = MagicMock()
    service._notification_filter.is_enabled.return_value = True
    service._notification_filter.is_allowed.return_value = True
    service._notification_filter.get_all_filters.return_value = {}
    service._seen_apps = MagicMock()
    return service


class TestOnAppNotificationReceivedAllowed:
    """§N1: filter enabled+allowed → AppNotificationReceived emitted."""

    def test_signal_emitted_when_allowed(self, notif_service):
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service.AppNotificationReceived.assert_called_once()

    def test_seen_apps_registered_when_allowed(self, notif_service):
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service._seen_apps.register.assert_called_once_with(
            "com.whatsapp.WhatsApp", label_hint="Alice"
        )


class TestOnAppNotificationReceivedGlobalDisabled:
    """§N2: global mirroring disabled → signal NOT emitted, no registry write."""

    def test_signal_not_emitted_when_disabled(self, notif_service):
        notif_service._notification_filter.is_enabled.return_value = False
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service.AppNotificationReceived.assert_not_called()

    def test_no_registry_write_when_disabled(self, notif_service):
        notif_service._notification_filter.is_enabled.return_value = False
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service._seen_apps.register.assert_not_called()


class TestOnAppNotificationReceivedAppDenied:
    """§N3/N7: app denied → signal NOT emitted, register() NOT called."""

    def test_signal_not_emitted_when_denied(self, notif_service):
        notif_service._notification_filter.is_allowed.return_value = False
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service.AppNotificationReceived.assert_not_called()

    def test_register_not_called_when_denied(self, notif_service):
        """Denied app must NOT appear in seen-apps list (UX correctness constraint)."""
        notif_service._notification_filter.is_allowed.return_value = False
        notif_service.on_app_notification_received(_APP_NOTIF)
        notif_service._seen_apps.register.assert_not_called()


class TestGetNotificationFilter:
    """§N4: GetNotificationFilter returns {enabled: bool, apps: dict}."""

    def test_returns_enabled_bool(self, notif_service):
        notif_service._notification_filter.is_enabled.return_value = True
        result = notif_service.GetNotificationFilter()
        assert bool(result["enabled"]) is True

    def test_returns_apps_dict(self, notif_service):
        notif_service._notification_filter.get_all_filters.return_value = {
            "com.foo.App": "deny"
        }
        result = notif_service.GetNotificationFilter()
        assert "apps" in result
        assert "com.foo.App" in result["apps"]
        assert str(result["apps"]["com.foo.App"]["action"]) == "deny"


class TestSetAppFilterInvalidArgument:
    """§N5: SetAppFilter with invalid action raises im.tincan.Error.InvalidArgument."""

    def test_invalid_action_raises_dbus_exception(self, notif_service):
        import dbus.exceptions
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            notif_service.SetAppFilter("com.foo.App", "badvalue")
        assert "InvalidArgument" in str(exc_info.value)

    def test_valid_action_allow_does_not_raise(self, notif_service):
        notif_service.SetAppFilter("com.foo.App", "allow")  # must not raise

    def test_valid_action_deny_does_not_raise(self, notif_service):
        notif_service.SetAppFilter("com.foo.App", "deny")  # must not raise


class TestAppNotificationPayloadKeys:
    """§N6: emitted signal dict always contains all 7 required keys."""

    def test_payload_has_all_7_keys(self, notif_service):
        notif_service.on_app_notification_received(_APP_NOTIF)
        payload = notif_service.AppNotificationReceived.call_args[0][0]
        required = {
            "app_id", "title", "subtitle", "body", "category", "category_id", "event_flags"
        }
        assert required <= set(payload.keys())

    def test_missing_optional_fields_default_to_empty(self, notif_service):
        minimal = {"app_id": "com.foo.App", "title": ""}
        notif_service.on_app_notification_received(minimal)
        payload = notif_service.AppNotificationReceived.call_args[0][0]
        assert str(payload["subtitle"]) == ""
        assert str(payload["body"]) == ""
        assert str(payload["category"]) == ""
        assert int(payload["category_id"]) == 0
        assert int(payload["event_flags"]) == 0


# ---------------------------------------------------------------------------
# §GetContacts — PBAP contact list via D-Bus (tincan-d86aj)
# ---------------------------------------------------------------------------

class TestGetContacts:
    """GetContacts returns PBAP-synced contacts; upsert_conversation wires group participants."""

    def test_get_contacts_empty_when_no_pbap(self, service):
        assert service.GetContacts() == []

    def test_get_contacts_returns_upserted_contacts(self, service):
        service._contact_store.upsert("8157916347", "Mom Wordelman")
        service._contact_store.upsert("4155550001", "Alice")
        contacts = service.GetContacts()
        phones = [str(c["phone"]) for c in contacts]
        names = [str(c["name"]) for c in contacts]
        assert "8157916347" in phones
        assert "4155550001" in phones
        assert "Mom Wordelman" in names
        assert "Alice" in names

    def test_get_contacts_excludes_nameless_entries(self, service):
        service._contact_store.upsert("8157916347", "")
        contacts = service.GetContacts()
        assert contacts == []

    def test_upsert_group_conv_populates_group_participants(self, service):
        service.upsert_conversation(Conversation(
            id="grp-xyz",
            display_name="A, B",
            participants=["4155550001", "4155550002"],
            is_group=True,
        ))
        assert "grp-xyz" in service._group_participants
        assert set(service._group_participants["grp-xyz"]) == {"4155550001", "4155550002"}


# ---------------------------------------------------------------------------
# §GetHFPDevices — oFono HFP modem enumeration (PR #146, tincan-d5yyu)
# ---------------------------------------------------------------------------

class TestGetHFPDevices:
    """GetHFPDevices enumerates oFono HFP modems; filters non-HFP; falls back to []."""

    @staticmethod
    def _modems():
        """One HFP modem + one non-HFP modem returned by org.ofono.Manager.GetModems()."""
        return [
            (
                "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
                {"Type": "hfp", "Name": "iPhone 15 Pro"},
            ),
            (
                "/sim900_0",
                {"Type": "hardware", "Name": "Builtin Modem"},
            ),
        ]

    def test_filters_out_non_hfp_modems(self, service):
        manager = MagicMock()
        manager.GetModems.return_value = self._modems()
        with patch("dbus.SystemBus"), patch("dbus.Interface", return_value=manager):
            result = service.GetHFPDevices()
        assert len(result) == 1
        assert str(result[0]["path"]) == "/org/ofono/hfp/dev_D0_6B_78_33_46_20"

    def test_extracts_mac_from_device_path(self, service):
        manager = MagicMock()
        manager.GetModems.return_value = self._modems()
        with patch("dbus.SystemBus"), patch("dbus.Interface", return_value=manager):
            result = service.GetHFPDevices()
        assert str(result[0]["mac"]) == "D0:6B:78:33:46:20"

    def test_result_has_path_mac_name_fields(self, service):
        manager = MagicMock()
        manager.GetModems.return_value = self._modems()
        with patch("dbus.SystemBus"), patch("dbus.Interface", return_value=manager):
            result = service.GetHFPDevices()
        assert set(result[0].keys()) >= {"path", "mac", "name"}
        assert str(result[0]["name"]) == "iPhone 15 Pro"

    def test_skips_hfp_modem_with_unparseable_path(self, service):
        manager = MagicMock()
        manager.GetModems.return_value = [
            ("/org/ofono/hfp/no_mac_here", {"Type": "hfp", "Name": "Mystery"}),
        ]
        with patch("dbus.SystemBus"), patch("dbus.Interface", return_value=manager):
            result = service.GetHFPDevices()
        assert result == []

    def test_returns_empty_when_ofono_unavailable(self, service):
        with patch("dbus.SystemBus", side_effect=Exception("no system bus")):
            assert service.GetHFPDevices() == []


# ---------------------------------------------------------------------------
# §update_contact — name-keyed conversation merge (tincan-gfiuv, tincan-6zfcq)
# ---------------------------------------------------------------------------

class TestUpdateContactMerge:
    """update_contact() merges name-keyed conversations into phone-keyed ones.

    Re-verifies tincan-gfiuv (self-conversation no sendable number) and
    tincan-6zfcq (country-code normalization splits thread) on main.
    """

    def test_phone_keyed_conv_gets_display_name(self, service):
        """Phone-keyed conversation: update_contact sets display_name and emits."""
        service.upsert_conversation(Conversation(id="8157916347", display_name="8157916347"))
        service.update_contact("8157916347", "Jim Wordelman")
        conv = service._conversations["8157916347"]
        assert conv.display_name == "Jim Wordelman"
        service.ConversationUpdated.assert_called()

    def test_name_keyed_conv_merges_into_phone_slot(self, service):
        """Name-keyed conversation merges into phone-keyed slot on contact load (tincan-gfiuv)."""
        service.upsert_conversation(Conversation(
            id="Jim Wordelman",
            display_name="Jim Wordelman",
            last_message_preview="hey",
            last_message_at="2026-06-10T12:00:00",
            unread_count=1,
        ))
        service.update_contact("8157916347", "Jim Wordelman")

        # Old name-keyed slot removed
        assert "Jim Wordelman" not in service._conversations
        # New phone-keyed slot present
        assert "8157916347" in service._conversations
        conv = service._conversations["8157916347"]
        assert conv.display_name == "Jim Wordelman"
        assert conv.unread_count == 1
        assert conv.last_message_preview == "hey"

    def test_merged_conv_id_is_phone_so_gui_can_reply(self, service):
        """After merge, conv.id is the phone number so the GUI send_target fallback works."""
        service.upsert_conversation(Conversation(id="Jim Wordelman", display_name="Jim Wordelman"))
        service.update_contact("8157916347", "Jim Wordelman")
        conv = service._conversations["8157916347"]
        # GUI uses send_target or id as phone; id must be dialable
        phone = conv.send_target or conv.id
        assert len(phone) >= 7
        assert phone == "8157916347"

    def test_messages_migrate_on_name_merge(self, service):
        """Messages stored under name-keyed conv_id move to phone key on merge."""
        service.upsert_conversation(Conversation(id="Jim Wordelman", display_name="Jim Wordelman"))
        service._messages["Jim Wordelman"] = [
            {"conversation_id": "Jim Wordelman", "body": "hi", "timestamp": "t1"}
        ]
        service._message_keys.add(("Jim Wordelman", "t1", "hi"))
        service.update_contact("8157916347", "Jim Wordelman")
        assert "Jim Wordelman" not in service._messages
        assert len(service._messages.get("8157916347", [])) == 1
        assert ("8157916347", "t1", "hi") in service._message_keys

    def test_country_code_prefix_normalizes_to_same_conv(self, service):
        """18157916347 and 8157916347 resolve to the same conversation (tincan-6zfcq)."""
        from tincand.contact_store import normalize_phone
        assert normalize_phone("18157916347") == normalize_phone("8157916347") == "8157916347"

        service.upsert_conversation(Conversation(id="8157916347", display_name="8157916347"))
        service.update_contact("18157916347", "Jim Wordelman")
        # update_contact normalizes "18157916347" → "8157916347"
        conv = service._conversations.get("8157916347")
        assert conv is not None
        assert conv.display_name == "Jim Wordelman"
        # No extra conversation created under the 11-digit key
        assert "18157916347" not in service._conversations

    def test_two_convs_same_number_different_prefix_merge(self, service):
        """Conversations keyed by 8157916347 and by name both collapse (tincan-6zfcq)."""
        service.upsert_conversation(Conversation(
            id="8157916347", display_name="8157916347",
            last_message_preview="first", last_message_at="2026-01-01T00:00:00",
        ))
        service.upsert_conversation(Conversation(
            id="Jim Wordelman", display_name="Jim Wordelman",
            last_message_preview="second", last_message_at="2026-06-10T00:00:00",
            unread_count=2,
        ))
        service.update_contact("8157916347", "Jim Wordelman")
        # Only one conversation remains
        assert "Jim Wordelman" not in service._conversations
        conv = service._conversations["8157916347"]
        # Newest message wins
        assert conv.last_message_preview == "second"
        assert conv.unread_count == 2
