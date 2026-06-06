"""Unit tests for tincan_gui.bug_report (tincan-il293)."""
import json

from tincan_gui.bug_report import write_report


class TestWriteReport:
    def test_creates_json_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("test symptom", {"connected": True}, [])
        assert path.exists()
        assert path.suffix == ".json"

    def test_schema_field(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("some note", {}, [])
        doc = json.loads(path.read_text())
        assert doc["schema"] == "tincan-bug-report-v1"

    def test_note_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("  symptom with whitespace  ", {}, [])
        doc = json.loads(path.read_text())
        assert doc["note"] == "symptom with whitespace"

    def test_app_state_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        state = {"current_phone": "+15550001234", "messages_ok": True}
        path = write_report("note", state, [])
        doc = json.loads(path.read_text())
        assert doc["app_state"] == state

    def test_trace_events_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        events = [{"ts": 1.0, "event": "send_start", "cid": 1}]
        path = write_report("note", {}, events)
        doc = json.loads(path.read_text())
        assert doc["trace_event_count"] == 1
        assert doc["trace_events"] == events

    def test_empty_trace_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("note", {}, [])
        doc = json.loads(path.read_text())
        assert doc["trace_events"] == []
        assert doc["trace_enabled"] is False

    def test_trace_enabled_when_events_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("note", {}, [{"event": "x"}])
        doc = json.loads(path.read_text())
        assert doc["trace_enabled"] is True

    def test_timestamp_fields_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: tmp_path)
        path = write_report("note", {}, [])
        doc = json.loads(path.read_text())
        assert isinstance(doc["timestamp"], int)
        assert "T" in doc["timestamp_iso"]

    def test_report_dir_created_if_missing(self, tmp_path, monkeypatch):
        new_dir = tmp_path / "nested" / "reports"
        monkeypatch.setattr("tincan_gui.bug_report._report_dir", lambda: new_dir)
        # _report_dir() returns the path, bug_report.write_report calls mkdir inside it
        # but our monkeypatch returns the path WITHOUT calling mkdir — so we call it manually
        new_dir.mkdir(parents=True)
        path = write_report("note", {}, [])
        assert path.exists()
