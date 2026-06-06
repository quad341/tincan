"""Unit tests for tincan_gui.trace (TINCAN_TRACE structured tracing)."""
import io
import json

import pytest

import tincan_gui.trace as trace


@pytest.fixture(autouse=True)
def _reset_trace_state():
    """Restore trace module globals after each test to prevent leakage."""
    prev_enabled = trace._ENABLED
    prev_file = trace._trace_file
    prev_cid = trace._CID
    yield
    trace._ENABLED = prev_enabled
    trace._trace_file = prev_file
    trace._CID = prev_cid


class TestBodyHash:
    def test_returns_8_hex_chars(self):
        h = trace.body_hash("hello")
        assert len(h) == 8
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert trace.body_hash("abc") == trace.body_hash("abc")

    def test_different_inputs_differ(self):
        assert trace.body_hash("foo") != trace.body_hash("bar")

    def test_empty_string(self):
        h = trace.body_hash("")
        assert len(h) == 8


class TestCorrelationIds:
    def test_new_cid_increments(self):
        trace._CID = 0
        c1 = trace.new_cid()
        c2 = trace.new_cid()
        assert c2 == c1 + 1

    def test_current_cid_does_not_increment(self):
        trace._CID = 5
        assert trace.current_cid() == 5
        assert trace.current_cid() == 5
        assert trace._CID == 5

    def test_new_cid_returns_new_value(self):
        trace._CID = 10
        result = trace.new_cid()
        assert result == 11
        assert trace._CID == 11


class TestEmit:
    def test_noop_when_disabled(self):
        trace._ENABLED = False
        trace._trace_file = None  # ensure no file opened
        trace.emit("test_event", key="value")
        assert trace._trace_file is None  # still None — no file created

    def test_writes_json_line_when_enabled(self, tmp_path):
        out = io.StringIO()
        trace._ENABLED = True
        trace._trace_file = out
        trace._CID = 0

        trace.emit("test_event", key="value")

        out.seek(0)
        line = out.readline()
        record = json.loads(line)
        assert record["event"] == "test_event"
        assert record["key"] == "value"
        assert "ts" in record
        assert "cid" in record

    def test_uses_current_cid_when_none_given(self, tmp_path):
        out = io.StringIO()
        trace._ENABLED = True
        trace._trace_file = out
        trace._CID = 7

        trace.emit("ev")

        out.seek(0)
        rec = json.loads(out.readline())
        assert rec["cid"] == 7

    def test_explicit_cid_overrides_current(self):
        out = io.StringIO()
        trace._ENABLED = True
        trace._trace_file = out
        trace._CID = 99

        trace.emit("ev", cid=42)

        out.seek(0)
        rec = json.loads(out.readline())
        assert rec["cid"] == 42

    def test_fields_present_in_output(self):
        out = io.StringIO()
        trace._ENABLED = True
        trace._trace_file = out
        trace._CID = 1

        trace.emit("cache_read", key="+15551234567", hit=1, count=5)

        out.seek(0)
        rec = json.loads(out.readline())
        assert rec["event"] == "cache_read"
        assert rec["key"] == "+15551234567"
        assert rec["hit"] == 1
        assert rec["count"] == 5

    def test_multiple_events_each_on_own_line(self):
        out = io.StringIO()
        trace._ENABLED = True
        trace._trace_file = out
        trace._CID = 0

        trace.emit("ev1")
        trace.emit("ev2")

        out.seek(0)
        lines = [ln for ln in out.readlines() if ln.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "ev1"
        assert json.loads(lines[1])["event"] == "ev2"
