"""Tests: ConversationItem group card branch in conversation_list.py.
Bead: tincan-j3u2g

Coverage:
  §1 Avatar — is_group=True → GroupAvatarWidget, not AvatarWidget
  §2 Name label text — participants list formatted as 'A, B' or 'A, B & N more'
  §3 Name label style — font-size 13, not bold; color #f4f4f5 in styleSheet
  §4 Selection — is_group → #3f3f46 background and 2px teal left border on select
  §5 Selection — is_group=False → existing #bfdbfe background (non-group path unchanged)
  §6 Preview — preview_sender shown as 'Sender: body' prefix
  §7 Accessible — unread_count=2 accessible name contains 'Group conversation' and '2 unread'
  §8 Regression — is_group=True does NOT trigger participant_count > 1 suffix [N]
"""
from __future__ import annotations

from tincan_gui.avatar import AvatarWidget, GroupAvatarWidget
from tincan_gui.conversation_list import ConversationData, ConversationItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_data(**overrides) -> ConversationData:
    defaults = {
        "id": "g1",
        "name": "Group",
        "phone": "",
        "preview": "",
        "timestamp": "10:00",
        "unread": False,
        "unread_count": 0,
        "is_group": False,
        "participants": [],
        "preview_sender": "",
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


# ---------------------------------------------------------------------------
# §1 Avatar widget type
# ---------------------------------------------------------------------------


class TestGroupCardAvatar:
    """is_group=True uses GroupAvatarWidget; is_group=False uses AvatarWidget."""

    def test_is_group_true_avatar_is_group_avatar_widget(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        assert isinstance(item._avatar, GroupAvatarWidget)

    def test_is_group_false_avatar_is_avatar_widget_not_group(self, qtbot):
        item = ConversationItem(_make_data(is_group=False, name="Alice"))
        qtbot.addWidget(item)
        assert isinstance(item._avatar, AvatarWidget)
        assert not isinstance(item._avatar, GroupAvatarWidget)


# ---------------------------------------------------------------------------
# §2 Name label text — participant formatting
# ---------------------------------------------------------------------------


class TestGroupCardNameLabel:
    """Name label shows formatted participant list, not raw name field."""

    def test_two_participants_joined_with_comma(self, qtbot):
        item = ConversationItem(
            _make_data(is_group=True, participants=["Alice", "Bob"])
        )
        qtbot.addWidget(item)
        assert item._name_label.text() == "Alice, Bob"

    def test_three_participants_shows_two_and_one_more(self, qtbot):
        item = ConversationItem(
            _make_data(is_group=True, participants=["A", "B", "C"])
        )
        qtbot.addWidget(item)
        assert item._name_label.text() == "A, B & 1 more"

    def test_four_participants_shows_two_and_two_more(self, qtbot):
        item = ConversationItem(
            _make_data(is_group=True, participants=["A", "B", "C", "D"])
        )
        qtbot.addWidget(item)
        assert item._name_label.text() == "A, B & 2 more"


# ---------------------------------------------------------------------------
# §3 Name label style — font size and color
# ---------------------------------------------------------------------------


class TestGroupCardNameStyle:
    """Group name label uses font-size 13, not bold, with #f4f4f5 color."""

    def test_name_label_font_size_is_13(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        assert item._name_label.font().pointSize() == 13

    def test_name_label_is_not_bold(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        assert not item._name_label.font().bold()

    def test_name_label_stylesheet_contains_f4f4f5_color(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        assert "#f4f4f5" in item._name_label.styleSheet()


# ---------------------------------------------------------------------------
# §4 Selection — group card selected state
# ---------------------------------------------------------------------------


class TestGroupCardSelectedState:
    """set_selected(True) on a group card applies teal highlight, not default blue."""

    def test_selected_group_frame_has_3f3f46_background(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#3f3f46" in item._frame.styleSheet()

    def test_selected_group_frame_has_0d9488_border(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#0d9488" in item._frame.styleSheet()

    def test_selected_group_frame_has_2px_border(self, qtbot):
        item = ConversationItem(_make_data(is_group=True, participants=["Alice", "Bob"]))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "2px" in item._frame.styleSheet()


# ---------------------------------------------------------------------------
# §5 Selection — non-group card selected state (regression)
# ---------------------------------------------------------------------------


class TestNonGroupCardSelectedState:
    """set_selected(True) on a non-group card still applies #bfdbfe background."""

    def test_non_group_selected_frame_has_bfdbfe_background(self, qtbot):
        item = ConversationItem(_make_data(is_group=False, name="Alice"))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#bfdbfe" in item._frame.styleSheet()

    def test_non_group_selected_frame_does_not_have_teal_border(self, qtbot):
        item = ConversationItem(_make_data(is_group=False, name="Alice"))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#0d9488" not in item._frame.styleSheet()


# ---------------------------------------------------------------------------
# §6 Preview — sender attribution prefix
# ---------------------------------------------------------------------------


class TestGroupCardPreview:
    """preview_sender is prepended to the preview as 'Sender: body'."""

    def test_preview_shows_sender_prefix(self, qtbot):
        item = ConversationItem(
            _make_data(
                is_group=True,
                participants=["Alice", "Bob"],
                preview_sender="Alice",
                preview="hi",
            )
        )
        qtbot.addWidget(item)
        assert item._preview_label.text() == "Alice: hi"

    def test_preview_without_sender_shows_body_only(self, qtbot):
        item = ConversationItem(
            _make_data(
                is_group=True,
                participants=["Alice", "Bob"],
                preview_sender="",
                preview="standalone",
            )
        )
        qtbot.addWidget(item)
        assert "standalone" in item._preview_label.text()
        assert ": standalone" not in item._preview_label.text()


# ---------------------------------------------------------------------------
# §7 Accessible name — group conversation
# ---------------------------------------------------------------------------


class TestGroupCardAccessible:
    """Group conversation accessible name identifies as 'Group conversation'."""

    def test_accessible_name_contains_group_conversation(self, qtbot):
        item = ConversationItem(
            _make_data(is_group=True, participants=["Alice", "Bob"], unread_count=0)
        )
        qtbot.addWidget(item)
        assert "Group conversation" in item.accessibleName()

    def test_accessible_name_contains_unread_count_when_nonzero(self, qtbot):
        item = ConversationItem(
            _make_data(is_group=True, participants=["Alice", "Bob"], unread_count=2)
        )
        qtbot.addWidget(item)
        name = item.accessibleName()
        assert "2 unread" in name or "Unread: 2" in name


# ---------------------------------------------------------------------------
# §8 Regression — participant_count suffix not applied to group cards
# ---------------------------------------------------------------------------


class TestGroupCardParticipantCountRegression:
    """is_group=True does NOT append [N] suffix via the participant_count > 1 path."""

    def test_group_name_label_has_no_bracket_suffix(self, qtbot):
        item = ConversationItem(
            _make_data(
                is_group=True,
                participants=["Alice", "Bob", "Carol"],
                participant_count=3,
            )
        )
        qtbot.addWidget(item)
        assert "[" not in item._name_label.text()
        assert "]" not in item._name_label.text()
