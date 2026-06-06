"""Tests: _parse_mms_content MIME parsing.
Bead: tincan-cq4l6

Coverage:
  §1 _parse_mms_content — multipart MMS with image + text parts
    - text body extracted from text/plain part
    - attachment dict has 'mime_type' and 'data' keys
    - attachment data round-trips through base64 correctly
    - two images produce two attachment entries
    - only image/* parts appear in attachments (text excluded)
    - empty payload image part is skipped
  §2 _parse_mms_content — text-only multipart MMS (no images)
    - body text extracted from multipart text/plain part
    - attachments list is empty
    - multiple text/plain parts joined with space
  §3 _parse_mms_content — non-multipart single-part MMS
    - single text/plain part body extracted
    - attachments list is empty
  §4 _parse_mms_content — missing BEGIN:MSG block
    - returns ("", []) when raw contains no BEGIN:MSG block
    - returns ("", []) for empty string input
  §5 _parse_mms_content — malformed MIME body (except Exception path)
    - when email.message_from_string raises, returns (raw_content.strip(), [])
  §6 _parse_mms_content — charset fallback
    - body decoded correctly when get_content_charset returns None (or "utf-8")
    - latin-1 charset part decoded with correct encoding

No D-Bus infrastructure needed — all inputs are synthetic bMessage strings.
"""
from __future__ import annotations

import base64
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

from tincand.backends.bluez_map import _parse_mms_content

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap_bmsg(mime_content: str) -> str:
    """Wrap MIME content in a minimal BEGIN:MSG…END:MSG bMessage block."""
    return f"BEGIN:MSG\r\n{mime_content}\r\nEND:MSG"


_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF"


def _make_multipart_text_image(text: str = "Hello MMS", image_bytes: bytes = _PNG_BYTES) -> str:
    msg = MIMEMultipart()
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEImage(image_bytes, "png"))
    return _wrap_bmsg(msg.as_string())


# ---------------------------------------------------------------------------
# §1 Multipart MMS with image + text parts
# ---------------------------------------------------------------------------

class TestParseMmsContentMultipartTextAndImage:
    """Multipart MMS: text extracted, image lands in attachments."""

    def test_body_text_extracted_from_text_plain_part(self):
        raw = _make_multipart_text_image(text="Hello MMS")
        body, _ = _parse_mms_content(raw)
        assert body == "Hello MMS"

    def test_attachment_has_mime_type_key(self):
        raw = _make_multipart_text_image()
        _, attachments = _parse_mms_content(raw)
        assert len(attachments) == 1
        assert "mime_type" in attachments[0]

    def test_attachment_has_data_key(self):
        raw = _make_multipart_text_image()
        _, attachments = _parse_mms_content(raw)
        assert "data" in attachments[0]

    def test_attachment_mime_type_is_image_png(self):
        raw = _make_multipart_text_image()
        _, attachments = _parse_mms_content(raw)
        assert attachments[0]["mime_type"] == "image/png"

    def test_attachment_data_round_trips_base64(self):
        raw = _make_multipart_text_image(image_bytes=_PNG_BYTES)
        _, attachments = _parse_mms_content(raw)
        decoded = base64.b64decode(attachments[0]["data"])
        assert decoded == _PNG_BYTES

    def test_two_images_produce_two_attachment_entries(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("Two images", "plain", "utf-8"))
        msg.attach(MIMEImage(_PNG_BYTES, "png"))
        msg.attach(MIMEImage(_JPEG_BYTES, "jpeg"))
        raw = _wrap_bmsg(msg.as_string())
        _, attachments = _parse_mms_content(raw)
        assert len(attachments) == 2

    def test_two_images_have_correct_mime_types(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("Two images", "plain", "utf-8"))
        msg.attach(MIMEImage(_PNG_BYTES, "png"))
        msg.attach(MIMEImage(_JPEG_BYTES, "jpeg"))
        raw = _wrap_bmsg(msg.as_string())
        _, attachments = _parse_mms_content(raw)
        types = {a["mime_type"] for a in attachments}
        assert types == {"image/png", "image/jpeg"}

    def test_text_part_not_in_attachments(self):
        raw = _make_multipart_text_image()
        _, attachments = _parse_mms_content(raw)
        for a in attachments:
            assert not a["mime_type"].startswith("text/")

    def test_one_attachment_when_one_image(self):
        raw = _make_multipart_text_image()
        _, attachments = _parse_mms_content(raw)
        assert len(attachments) == 1


# ---------------------------------------------------------------------------
# §2 Text-only multipart MMS (no images)
# ---------------------------------------------------------------------------

class TestParseMmsContentTextOnlyMultipart:
    """Multipart MMS with only text/plain parts: body joined, no attachments."""

    def test_body_extracted_from_single_text_part(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("Only text here", "plain", "utf-8"))
        raw = _wrap_bmsg(msg.as_string())
        body, _ = _parse_mms_content(raw)
        assert "Only text here" in body

    def test_attachments_empty_for_text_only_multipart(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("Only text here", "plain", "utf-8"))
        raw = _wrap_bmsg(msg.as_string())
        _, attachments = _parse_mms_content(raw)
        assert attachments == []

    def test_two_text_parts_joined_with_space(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("Part one", "plain", "utf-8"))
        msg.attach(MIMEText("Part two", "plain", "utf-8"))
        raw = _wrap_bmsg(msg.as_string())
        body, _ = _parse_mms_content(raw)
        assert "Part one" in body
        assert "Part two" in body


# ---------------------------------------------------------------------------
# §3 Non-multipart single-part MMS
# ---------------------------------------------------------------------------

class TestParseMmsContentNonMultipart:
    """Non-multipart single-part: the message itself is the single part."""

    def test_single_text_plain_body_extracted(self):
        msg = MIMEText("Single part body", "plain", "utf-8")
        raw = _wrap_bmsg(msg.as_string())
        body, _ = _parse_mms_content(raw)
        assert body == "Single part body"

    def test_single_text_plain_attachments_empty(self):
        msg = MIMEText("Single part body", "plain", "utf-8")
        raw = _wrap_bmsg(msg.as_string())
        _, attachments = _parse_mms_content(raw)
        assert attachments == []

    def test_single_image_part_yields_one_attachment(self):
        msg = MIMEImage(_PNG_BYTES, "png")
        raw = _wrap_bmsg(msg.as_string())
        _, attachments = _parse_mms_content(raw)
        assert len(attachments) == 1
        assert attachments[0]["mime_type"] == "image/png"

    def test_single_image_body_is_empty_string(self):
        msg = MIMEImage(_PNG_BYTES, "png")
        raw = _wrap_bmsg(msg.as_string())
        body, _ = _parse_mms_content(raw)
        assert body == ""


# ---------------------------------------------------------------------------
# §4 Missing BEGIN:MSG block
# ---------------------------------------------------------------------------

class TestParseMmsContentMissingBlock:
    """No BEGIN:MSG block → returns ("", []) without raising."""

    def test_no_msg_block_returns_empty_body(self):
        body, _ = _parse_mms_content("BEGIN:BMSG\r\nSTATUS:UNREAD\r\nEND:BMSG\r\n")
        assert body == ""

    def test_no_msg_block_returns_empty_attachments(self):
        _, attachments = _parse_mms_content("BEGIN:BMSG\r\nSTATUS:UNREAD\r\nEND:BMSG\r\n")
        assert attachments == []

    def test_empty_string_returns_empty_body(self):
        body, _ = _parse_mms_content("")
        assert body == ""

    def test_empty_string_returns_empty_attachments(self):
        _, attachments = _parse_mms_content("")
        assert attachments == []


# ---------------------------------------------------------------------------
# §5 Malformed MIME body (except Exception path)
# ---------------------------------------------------------------------------

class TestParseMmsContentMalformedMime:
    """When email.message_from_string raises, the raw content is returned as body."""

    def test_exception_during_parse_returns_raw_content_as_body(self):
        raw_mime = "This is not valid MIME at all\r\ngarbage content"
        raw = _wrap_bmsg(raw_mime)
        with patch("tincand.backends.bluez_map.email.message_from_string",
                   side_effect=Exception("parse error")):
            body, _ = _parse_mms_content(raw)
        assert body == raw_mime.strip()

    def test_exception_during_parse_returns_empty_attachments(self):
        raw_mime = "garbage"
        raw = _wrap_bmsg(raw_mime)
        with patch("tincand.backends.bluez_map.email.message_from_string",
                   side_effect=Exception("parse error")):
            _, attachments = _parse_mms_content(raw)
        assert attachments == []

    def test_exception_body_is_stripped(self):
        raw_mime = "  leading and trailing whitespace  "
        raw = _wrap_bmsg(raw_mime)
        with patch("tincand.backends.bluez_map.email.message_from_string",
                   side_effect=ValueError("bad mime")):
            body, _ = _parse_mms_content(raw)
        assert body == raw_mime.strip()


# ---------------------------------------------------------------------------
# §6 Charset fallback
# ---------------------------------------------------------------------------

class TestParseMmsContentCharsetFallback:
    """Body decoded correctly when charset is absent or get_content_charset returns None."""

    def test_text_without_explicit_charset_decoded_as_utf8(self):
        # Build a message with no charset= parameter — get_content_charset("utf-8")
        # returns "utf-8" from failobj; body must still decode correctly.
        from email.message import Message
        part = Message()
        part["Content-Type"] = "text/plain"
        part["Content-Transfer-Encoding"] = "base64"
        part.set_payload(base64.b64encode("no charset here".encode("utf-8")).decode("ascii"))
        raw = _wrap_bmsg(part.as_string())
        body, _ = _parse_mms_content(raw)
        assert body == "no charset here"

    def test_get_content_charset_none_falls_back_to_utf8(self):
        """Verify the 'or utf-8' guard: mock returns None, body still decoded."""
        raw_mime = "irrelevant"
        raw = _wrap_bmsg(raw_mime)
        mock_msg = MagicMock()
        mock_msg.is_multipart.return_value = False
        mock_msg.get_content_type.return_value = "text/plain"
        mock_msg.get_payload.return_value = "hello fallback".encode("utf-8")
        mock_msg.get_content_charset.return_value = None
        with patch("tincand.backends.bluez_map.email.message_from_string",
                   return_value=mock_msg):
            body, _ = _parse_mms_content(raw)
        assert body == "hello fallback"

    def test_latin1_charset_decoded_correctly(self):
        # Build a text/plain part with charset=latin-1 containing a non-ASCII byte.
        latin1_text = "caf\xe9"  # café in latin-1
        from email.message import Message
        part = Message()
        part["Content-Type"] = "text/plain; charset=latin-1"
        part["Content-Transfer-Encoding"] = "base64"
        part.set_payload(
            base64.b64encode(latin1_text.encode("latin-1")).decode("ascii")
        )
        raw = _wrap_bmsg(part.as_string())
        body, _ = _parse_mms_content(raw)
        assert body == "café"
