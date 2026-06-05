"""Tests: build_bmsg_multi and MapBackend.send_group_message.
Bead: tincan-g9wf8

Coverage:
  §1 build_bmsg_multi 2 recipients — BENV has exactly 2 VCARDs, TYPE=MMS
  §2 build_bmsg_multi 5 recipients — exactly 5 VCARDs in BENV
  §3 build_bmsg_multi body encoding — body present under BEGIN:MSG/END:MSG
  §4 build_bmsg_multi does not call build_bmsg — no regression to 1:1 path
  §5 send_group_message flag not set — raises RuntimeError, no OBEX call
  §6 send_group_message flag set + 1 participant — raises ValueError, no OBEX call
  §7 send_group_message flag set + 2 participants — calls PushMessage, temp file cleaned up
  §8 send_group_message OBEX error — temp file still cleaned up (finally block)
  §9 build_bmsg 1:1 path unchanged — TYPE:SMS_GSM, single VCARD, not MMS

No real obexd dependency — mocked via unittest.mock.
"""
from __future__ import annotations

import os
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tincand.backends.bluez_map import MapBackend, build_bmsg, build_bmsg_multi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PARTICIPANTS_2 = ["+15550101234", "+15550105678"]
_PARTICIPANTS_5 = ["+15550101234", "+15550105678", "+15550109999", "+15550108888", "+15550107777"]
_BODY = "Hey group"

_VCARD_RE = re.compile(r"BEGIN:VCARD")


def _count_vcards_in_benv(text: str) -> int:
    benv_start = text.find("BEGIN:BENV")
    benv_end = text.find("END:BENV", benv_start)
    if benv_start < 0 or benv_end < 0:
        return 0
    return len(_VCARD_RE.findall(text[benv_start:benv_end]))


def _make_backend(*, flag: bool = True):
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.PushMessage.return_value = ("/org/obex/transfer99", {})
    backend._msg_access = mock_access
    env = {"TINCAN_GROUP_SEND_ENABLED": "1"} if flag else {}
    return backend, mock_access, patch.dict(os.environ, env, clear=True)


def _capture_pushed_content(participants, body=_BODY):
    """Run send_group_message and return the bMessage text pushed via PushMessage."""
    backend, mock_access, env_patch = _make_backend()
    content_holder = []

    def _capture(path, props):
        with open(path) as fh:
            content_holder.append(fh.read())
        return ("/org/obex/transfer99", {})

    mock_access.PushMessage.side_effect = _capture
    with env_patch:
        with patch.object(backend, "_wait_transfer_send", return_value=None):
            backend.send_group_message(participants, body)
    return content_holder[0] if content_holder else ""


# ---------------------------------------------------------------------------
# §1 build_bmsg_multi — 2 recipients
# ---------------------------------------------------------------------------

class TestBuildBmsgMultiTwoRecipients:
    """2 recipients → exactly 2 VCARDs inside BENV, TYPE=MMS."""

    def test_two_vcards_in_benv(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        assert _count_vcards_in_benv(bmsg) == 2

    def test_type_mms_present(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        assert "TYPE:MMS" in bmsg

    def test_begin_benv_end_benv_present(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        assert "BEGIN:BENV" in bmsg
        assert "END:BENV" in bmsg


# ---------------------------------------------------------------------------
# §2 build_bmsg_multi — 5 recipients
# ---------------------------------------------------------------------------

class TestBuildBmsgMultiFiveRecipients:
    """5 recipients → exactly 5 VCARDs inside BENV."""

    def test_five_vcards_in_benv(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_5, _BODY)
        assert _count_vcards_in_benv(bmsg) == 5

    def test_each_recipient_has_begin_end_vcard_pair(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_5, _BODY)
        benv_start = bmsg.find("BEGIN:BENV")
        benv_end = bmsg.find("END:BENV", benv_start)
        benv = bmsg[benv_start:benv_end]
        assert benv.count("BEGIN:VCARD") == benv.count("END:VCARD") == 5


# ---------------------------------------------------------------------------
# §3 build_bmsg_multi — body encoding
# ---------------------------------------------------------------------------

class TestBuildBmsgMultiBody:
    """Body appears inside BEGIN:MSG/END:MSG block."""

    def test_body_present(self):
        body = "Hello group 🎉"
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, body)
        assert body in bmsg

    def test_begin_msg_present(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        assert "BEGIN:MSG" in bmsg

    def test_end_msg_present(self):
        bmsg = build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        assert "END:MSG" in bmsg


# ---------------------------------------------------------------------------
# §4 build_bmsg_multi does not call build_bmsg
# ---------------------------------------------------------------------------

class TestBuildBmsgMultiNoBuildBmsgCall:
    """build_bmsg_multi must not delegate to build_bmsg (no 1:1 fallback)."""

    def test_build_bmsg_not_called(self):
        with patch("tincand.backends.bluez_map.build_bmsg") as mock_build:
            build_bmsg_multi(_PARTICIPANTS_2, _BODY)
        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# §5 send_group_message — flag not set raises RuntimeError
# ---------------------------------------------------------------------------

class TestSendGroupMessageFlagUnset:
    """TINCAN_GROUP_SEND_ENABLED unset → RuntimeError before any OBEX call."""

    def test_runtime_error_raised(self):
        backend, mock_access, _ = _make_backend(flag=False)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            with pytest.raises(RuntimeError):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)

    def test_no_obex_calls_made(self):
        backend, mock_access, _ = _make_backend(flag=False)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            with pytest.raises(RuntimeError):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)
        mock_access.PushMessage.assert_not_called()
        mock_access.SetFolder.assert_not_called()


# ---------------------------------------------------------------------------
# §6 send_group_message — 1 participant raises ValueError
# ---------------------------------------------------------------------------

class TestSendGroupMessageOneParticipant:
    """Flag set but only 1 participant → ValueError, no OBEX call."""

    def test_zero_participants_raises_value_error(self):
        backend, mock_access, env_patch = _make_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([], _BODY)

    def test_one_participant_raises_value_error(self):
        backend, mock_access, env_patch = _make_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([_PARTICIPANTS_2[0]], _BODY)

    def test_one_participant_no_push_message_call(self):
        backend, mock_access, env_patch = _make_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([_PARTICIPANTS_2[0]], _BODY)
        mock_access.PushMessage.assert_not_called()


# ---------------------------------------------------------------------------
# §7 send_group_message — happy path (2 participants)
# ---------------------------------------------------------------------------

class TestSendGroupMessageHappyPath:
    """Flag set + ≥2 participants: PushMessage called, tempfile cleaned up."""

    def test_push_message_called(self):
        backend, mock_access, env_patch = _make_backend()
        with env_patch:
            with patch.object(backend, "_wait_transfer_send", return_value=None):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)
        assert mock_access.PushMessage.called

    def test_type_mms_in_pushed_content(self):
        content = _capture_pushed_content(_PARTICIPANTS_2)
        assert "TYPE:MMS" in content

    def test_two_vcards_in_pushed_content(self):
        content = _capture_pushed_content(_PARTICIPANTS_2)
        assert _count_vcards_in_benv(content) == 2

    def test_tempfile_cleaned_up_after_success(self):
        backend, mock_access, env_patch = _make_backend()
        paths = []

        def spy_temp(*a, **kw):
            kw.setdefault("delete", False)
            f = tempfile.NamedTemporaryFile(*a, **kw)
            paths.append(f.name)
            return f

        with env_patch:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_temp):
                with patch.object(backend, "_wait_transfer_send", return_value=None):
                    backend.send_group_message(_PARTICIPANTS_2, _BODY)

        assert paths, "NamedTemporaryFile was never called"
        assert not os.path.exists(paths[0]), f"Tempfile not cleaned up: {paths[0]}"


# ---------------------------------------------------------------------------
# §8 send_group_message — OBEX error still cleans up tempfile
# ---------------------------------------------------------------------------

class TestSendGroupMessageObexError:
    """OBEX exception during PushMessage: tempfile still removed (finally block)."""

    def test_tempfile_removed_on_obex_error(self):
        backend, mock_access, env_patch = _make_backend()
        mock_access.PushMessage.side_effect = RuntimeError("OBEX error")
        paths = []

        def spy_temp(*a, **kw):
            kw.setdefault("delete", False)
            f = tempfile.NamedTemporaryFile(*a, **kw)
            paths.append(f.name)
            return f

        with env_patch:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_temp):
                with patch.object(backend, "_wait_transfer_send", return_value=None):
                    with pytest.raises(RuntimeError):
                        backend.send_group_message(_PARTICIPANTS_2, _BODY)

        assert paths, "NamedTemporaryFile was never called"
        assert not os.path.exists(paths[0]), f"Tempfile not cleaned up after exception: {paths[0]}"


# ---------------------------------------------------------------------------
# §9 build_bmsg 1:1 regression — unchanged by multi-recipient changes
# ---------------------------------------------------------------------------

class TestBuildBmsgOneToOneRegression:
    """build_bmsg 1:1 is not affected by multi-recipient additions."""

    def test_type_sms_gsm(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert "TYPE:SMS_GSM" in bmsg

    def test_single_vcard_in_benv(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert _count_vcards_in_benv(bmsg) == 1

    def test_no_mms_type(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert "TYPE:MMS" not in bmsg
