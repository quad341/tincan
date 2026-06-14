"""Repro: MAP bodies truncated to the listing Subject preview (tincan-fu6xq).

PROVEN ROOT CAUSE — see /tmp/fu6xq-evidence.txt (live session 2026-06-07,
daemon "tincand starting with backend=map device=<your-device-mac>"):

On real BlueZ/obexd, ``org.bluez.obex.Message1.Get()`` raises
``org.freedesktop.DBus.Error.UnknownObject`` for EVERY message — the live log
shows 16/16 Get failures and 0 successful body transfers. ``poll_inbox()``
therefore falls through to ``props["Subject"]`` (bluez_map.py:424-428 inbound,
:479-483 sent), which obexd delivers as a TRUNCATED preview. For a 142-byte SMS
the Subject is clipped mid-URL, producing the user-visible "URL clipped" bug
(conv 898287, bug-1780850312).

SAME failure class as tincan-572zo, DIFFERENT D-Bus error:
572zo / PR #46 targeted ``MessageAccess1.GetMessage`` -> ``UnknownMethod`` and
was verified by mocked tests that ASSUME ``Message1.Get`` SUCCEEDS
(test_map_get_message_fix.py §3 "TestBlueZ566ForcedMessage1GetPath" sets
``mock_msg1.Get.return_value = (_TRANSFER_PATH, {})``). No existing test
simulates ``Message1.Get`` raising ``UnknownObject`` — the real hardware
behavior — so PR #46 went GREEN while the live body-fetch path stayed broken.

This module reproduces the live failure at the unit level. The REAL fix must be
verified on live hardware (a long-URL SMS displaying in full), not by a mock
that pretends Get succeeds.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.exceptions

from tincand.backends.bluez_map import MapBackend

_MSG_PATH = "/org/bluez/obex/client/session0/message935478217369271909"

# Exactly what obexd's ListMessages delivers for the real message (from the live
# daemon log). Note it is clipped: the trailing link is a bare "https://stspg.io"
# with no path, and the string is shorter than the advertised Size of 142 bytes.
_TRUNCATED_SUBJECT = (
    "[Claude status] Resolved: Elevated errors on Claude Opus 4.7 "
    "https://stspg.io/8qky14s62z49. Manage subscription https://stspg.io"
)
_ADVERTISED_SIZE = 142  # props["Size"] — the full body the phone shows

_INBOX_PROPS = {
    "Folder": "/telecom/msg/inbox",
    "Subject": _TRUNCATED_SUBJECT,
    "Timestamp": "20260607T085259",
    "Sender": "78774",
    "SenderAddressing": "78774",
    "Type": "sms-gsm",
    "Size": str(_ADVERTISED_SIZE),
    "Read": True,
}


def _unknown_object() -> dbus.exceptions.DBusException:
    """The exact live error: Message1.Get on a stale/absent obex object path."""
    return dbus.exceptions.DBusException(
        'Method "Get" with signature "ss" on interface '
        '"org.freedesktop.DBus.Properties" doesn\'t exist',
        name="org.freedesktop.DBus.Error.UnknownObject",
    )


def _make_backend():
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.ListMessages.side_effect = (
        lambda folder, opts={}: {_MSG_PATH: dict(_INBOX_PROPS)} if folder == "inbox" else {}
    )
    backend._msg_access = mock_access
    mock_msg1 = MagicMock(name="Message1")
    mock_msg1.Get.side_effect = _unknown_object()
    return backend, mock_msg1


def test_BUG_message1_get_unknownobject_truncates_body_to_subject_preview():
    """poll_inbox falls back to the truncated Subject when Message1.Get raises
    UnknownObject — the body the GUI renders is clipped mid-URL.

    This test PASSES today: it documents the live defect. When the body-fetch
    path is fixed to retrieve the full bMessage on real hardware, poll_inbox
    will return the full 142-byte body and the final two assertions flip — at
    which point this test should be replaced by a green full-body assertion.
    """
    backend, mock_msg1 = _make_backend()
    with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
         patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1):
        result = backend.poll_inbox()

    assert result, "poll_inbox must return the message"
    body = result[0]["body"]

    # The full-body fetch was attempted and failed (the live UnknownObject path)…
    assert mock_msg1.Get.called, "Message1.Get must have been attempted"
    assert _MSG_PATH in backend._failed_handles, "failed Get must be cached"

    # …so the body is the truncated listing Subject, NOT the full message.
    assert body == _TRUNCATED_SUBJECT

    # Proof of truncation, grounded only in observable log facts:
    # (1) the rendered body is shorter than the advertised full-body Size, and
    assert len(body) < _ADVERTISED_SIZE
    # (2) the final URL is clipped to a bare host with no path — "cut off
    #     mid-link", exactly the operator's bug report for conv 898287.
    assert body.endswith("https://stspg.io")
    assert "https://stspg.io/" in body  # the FIRST link kept its path…
    assert body.count("https://stspg.io/") == 1  # …but the SECOND is truncated


def test_DISPROOF_gui_linkify_preserves_full_url():
    """Disprove the bead's secondary hypothesis (GUI thread_view truncates URLs).

    Feed a long URL through the GUI's _linkify (the only transform between the
    body string and the rendered QLabel). It HTML-escapes, wraps URLs in <a>,
    and inserts U+200B (&#8203;) break hints for layout — but drops NO
    characters. The href attribute and the visible text both retain the full
    URL, so the GUI cannot be the truncation site. The truncation is upstream,
    in the daemon's Subject fallback (the test above).
    """
    from tincan_gui.thread_view import _linkify

    long_url = "https://stspg.io/8qky14s62z49abcdefghijklmnopqrstuvwxyz0123456789"
    html = _linkify(f"Manage subscription {long_url}")

    # href attribute is built before break-hint insertion and never split.
    assert f'href="{long_url}"' in html
    # Visible text retains every character once the (invisible) ZW breaks are removed.
    assert long_url in html.replace("&#8203;", "")
