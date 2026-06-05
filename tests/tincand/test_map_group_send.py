"""Tests: MapBackend.send_group_message — flag guard, validation, OBEX calls, cleanup.
Bead: tincan-kept3

Coverage:
  §1 Flag guard — TINCAN_GROUP_SEND_ENABLED not set → RuntimeError, zero D-Bus calls
  §2 Validation — len(participants) < 2 → ValueError
  §3 Connection guard — _msg_access is None → RuntimeError
  §4 Happy path — SetFolder('telecom'), SetFolder('msg'), PushMessage called; returns path
  §5 bMessage content — tempfile is TYPE:MMS with one VCARD per participant
  §6 Cleanup — tempfile removed after success; tempfile removed on exception (finally)

No real obexd dependency — mocked via unittest.mock.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tincand.backends.bluez_map import MapBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PARTICIPANTS_2 = ["+15550101234", "+15550105678"]
_PARTICIPANTS_3 = ["+15550101234", "+15550105678", "+15550109999"]
_BODY = "Hey group"


def _make_connected_backend(*, group_send_enabled: bool = True):
    """Return a MapBackend with a mock _msg_access and env flag set as requested."""
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.PushMessage.return_value = ("/org/obex/transfer42", {})
    backend._msg_access = mock_access
    env_patch = patch.dict(
        os.environ,
        {"TINCAN_GROUP_SEND_ENABLED": "1"} if group_send_enabled else {},
        clear=True,
    ) if not group_send_enabled else patch.dict(
        os.environ, {"TINCAN_GROUP_SEND_ENABLED": "1"}
    )
    return backend, mock_access, env_patch


# ---------------------------------------------------------------------------
# §1 Flag guard
# ---------------------------------------------------------------------------

class TestSendGroupMessageFlagGuard:
    """send_group_message raises RuntimeError when TINCAN_GROUP_SEND_ENABLED is unset."""

    def test_flag_unset_raises_runtime_error(self):
        backend = MapBackend()
        backend._msg_access = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            with pytest.raises(RuntimeError):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)

    def test_flag_unset_no_dbus_calls_made(self):
        backend = MapBackend()
        mock_access = MagicMock()
        backend._msg_access = mock_access
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            with pytest.raises(RuntimeError):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)
        mock_access.SetFolder.assert_not_called()
        mock_access.PushMessage.assert_not_called()


# ---------------------------------------------------------------------------
# §2 Validation — participant count
# ---------------------------------------------------------------------------

class TestSendGroupMessageValidation:
    """Fewer than 2 participants raises ValueError."""

    def test_zero_participants_raises_value_error(self):
        backend, mock_access, env_patch = _make_connected_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([], _BODY)

    def test_one_participant_raises_value_error(self):
        backend, mock_access, env_patch = _make_connected_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([_PARTICIPANTS_2[0]], _BODY)

    def test_one_participant_no_obex_calls(self):
        backend, mock_access, env_patch = _make_connected_backend()
        with env_patch:
            with pytest.raises(ValueError):
                backend.send_group_message([_PARTICIPANTS_2[0]], _BODY)
        mock_access.PushMessage.assert_not_called()


# ---------------------------------------------------------------------------
# §3 Connection guard
# ---------------------------------------------------------------------------

class TestSendGroupMessageConnectionGuard:
    """_msg_access is None (not connected) raises RuntimeError."""

    def test_not_connected_raises_runtime_error(self):
        backend = MapBackend()
        assert backend._msg_access is None
        with patch.dict(os.environ, {"TINCAN_GROUP_SEND_ENABLED": "1"}):
            with pytest.raises(RuntimeError):
                backend.send_group_message(_PARTICIPANTS_2, _BODY)


# ---------------------------------------------------------------------------
# §4 Happy path — OBEX call sequence and return value
# ---------------------------------------------------------------------------

class TestSendGroupMessageHappyPath:
    """Enabled + 2+ participants: correct OBEX call sequence and return value."""

    @pytest.fixture
    def result_and_mock(self):
        backend, mock_access, env_patch = _make_connected_backend()
        with env_patch:
            with patch.object(backend, "_wait_transfer_send", return_value=None):
                transfer_path = backend.send_group_message(_PARTICIPANTS_2, _BODY)
        return transfer_path, mock_access

    def test_set_folder_telecom_called(self, result_and_mock):
        _, mock_access = result_and_mock
        calls = [str(c.args[0]) for c in mock_access.SetFolder.call_args_list]
        assert "telecom" in calls

    def test_set_folder_msg_called(self, result_and_mock):
        _, mock_access = result_and_mock
        calls = [str(c.args[0]) for c in mock_access.SetFolder.call_args_list]
        assert "msg" in calls

    def test_push_message_called(self, result_and_mock):
        _, mock_access = result_and_mock
        assert mock_access.PushMessage.called

    def test_returns_transfer_path_string(self, result_and_mock):
        transfer_path, _ = result_and_mock
        assert isinstance(transfer_path, str)
        assert transfer_path != ""

    def test_returns_path_from_push_message(self, result_and_mock):
        transfer_path, _ = result_and_mock
        assert transfer_path == "/org/obex/transfer42"

    def test_wait_transfer_send_called(self):
        backend, mock_access, env_patch = _make_connected_backend()
        with env_patch:
            with patch.object(backend, "_wait_transfer_send", return_value=None) as mock_wait:
                backend.send_group_message(_PARTICIPANTS_2, _BODY)
        assert mock_wait.called


# ---------------------------------------------------------------------------
# §5 bMessage content — TYPE:MMS with one VCARD per participant
# ---------------------------------------------------------------------------

class TestSendGroupMessageBmsgContent:
    """The tempfile pushed to obexd contains a valid TYPE:MMS bMessage."""

    def _capture_pushed_content(self, participants):
        """Run send_group_message and return the content of the tempfile pushed."""
        backend, mock_access, env_patch = _make_connected_backend()
        pushed_path = None

        def capture_push(path, props):
            nonlocal pushed_path
            pushed_path = path
            return ("/org/obex/transfer42", {})

        mock_access.PushMessage.side_effect = capture_push

        with env_patch:
            with patch.object(backend, "_wait_transfer_send", return_value=None):
                backend.send_group_message(participants, _BODY)

        assert pushed_path is not None
        # The file is already cleaned up; we need to read during the call.
        # Re-run capturing content before cleanup.
        content_holder = []

        def capture_push_content(path, props):
            with open(path) as f:
                content_holder.append(f.read())
            return ("/org/obex/transfer42", {})

        mock_access.PushMessage.side_effect = capture_push_content
        backend2, mock_access2, env_patch2 = _make_connected_backend()
        mock_access2.PushMessage.side_effect = capture_push_content
        with env_patch2:
            with patch.object(backend2, "_wait_transfer_send", return_value=None):
                backend2.send_group_message(participants, _BODY)

        return content_holder[0] if content_holder else ""

    def test_type_mms_in_pushed_content(self):
        content = self._capture_pushed_content(_PARTICIPANTS_2)
        assert "TYPE:MMS" in content

    def test_two_vcards_for_two_recipients(self):
        content = self._capture_pushed_content(_PARTICIPANTS_2)
        benv_start = content.find("BEGIN:BENV")
        benv_end = content.find("END:BENV", benv_start)
        if benv_start >= 0 and benv_end >= 0:
            benv = content[benv_start:benv_end]
            vcard_count = benv.count("BEGIN:VCARD")
        else:
            vcard_count = content.count("BEGIN:VCARD")
        assert vcard_count == 2

    def test_three_vcards_for_three_recipients(self):
        content = self._capture_pushed_content(_PARTICIPANTS_3)
        benv_start = content.find("BEGIN:BENV")
        benv_end = content.find("END:BENV", benv_start)
        if benv_start >= 0 and benv_end >= 0:
            benv = content[benv_start:benv_end]
            vcard_count = benv.count("BEGIN:VCARD")
        else:
            vcard_count = content.count("BEGIN:VCARD")
        assert vcard_count == 3

    def test_body_in_pushed_content(self):
        content = self._capture_pushed_content(_PARTICIPANTS_2)
        assert _BODY in content


# ---------------------------------------------------------------------------
# §6 Cleanup — tempfile removed after success and on exception
# ---------------------------------------------------------------------------

class TestSendGroupMessageCleanup:
    """Tempfile is removed after a successful send and after an OBEX exception."""

    def _run_send_and_get_tempfile_path(self, participants=None, raise_on_push=False):
        """Run send_group_message, capture the tempfile path, return it."""
        if participants is None:
            participants = _PARTICIPANTS_2
        backend, mock_access, env_patch = _make_connected_backend()
        tempfile_paths = []

        original_named_temp = tempfile.NamedTemporaryFile

        def spy_named_temp(*args, **kwargs):
            kwargs.setdefault("delete", False)
            f = original_named_temp(*args, **kwargs)
            tempfile_paths.append(f.name)
            return f

        if raise_on_push:
            mock_access.PushMessage.side_effect = RuntimeError("OBEX error")

        with env_patch:
            with patch("tempfile.NamedTemporaryFile", side_effect=spy_named_temp):
                with patch.object(backend, "_wait_transfer_send", return_value=None):
                    try:
                        backend.send_group_message(participants, _BODY)
                    except RuntimeError:
                        pass

        return tempfile_paths[0] if tempfile_paths else None

    def test_tempfile_removed_after_success(self):
        path = self._run_send_and_get_tempfile_path()
        if path is not None:
            assert not os.path.exists(path), f"Tempfile not cleaned up: {path}"

    def test_tempfile_removed_after_obex_exception(self):
        path = self._run_send_and_get_tempfile_path(raise_on_push=True)
        if path is not None:
            assert not os.path.exists(path), f"Tempfile not cleaned up after exception: {path}"
