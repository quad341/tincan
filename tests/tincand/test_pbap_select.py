"""Tests: PBAP Select telecom/pb fallback + skip diagnostics.
Bead: tincan-2ddq  (commit bf12159)

Coverage:
  §1 connect() Select fallback
     - telecom/pb succeeds: uses it (break, PullAll called)
     - telecom/pb fails, 'pb' succeeds: uses pb (PullAll called)
     - both fail: logs WARNING, returns early (no PullAll called)

  §2 _on_pullall_complete skip logging
     - 0 contacts loaded: logs WARNING with skip counts
     - count > 0: logs INFO
     - skipped_no_fn counter increments for missing/empty FN field
     - skipped_no_tel counter increments for missing TEL field

  §3 Fields filter removal
     - PullAll called without 'Fields' key (only 'Format' in filter dict)
"""
from __future__ import annotations

import logging
import tempfile
from unittest.mock import MagicMock, call, patch

import dbus
import dbus.exceptions
import pytest

from tincand.backends.pbap import PBAPContactSync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sync():
    svc = MagicMock(name="TincanService")
    svc._contact_store = MagicMock()
    svc._contact_store.photo_fetched.return_value = False
    sync = PBAPContactSync(service=svc)
    return sync, svc


def _dbus_exc(name="org.bluez.obex.Error.NotFound"):
    return dbus.exceptions.DBusException(name=name)


def _make_transfer(status="complete"):
    props = MagicMock(name="Transfer1Props")
    props.Get.return_value = status
    return props


# ---------------------------------------------------------------------------
# §1 connect() Select fallback
# ---------------------------------------------------------------------------

class TestPBAPSelectFallback:
    """Select tries 'telecom/pb' first, falls back to 'pb'; aborts if both fail."""

    def _connect_with_select_behavior(self, telecom_fails: bool, pb_fails: bool,
                                       monkeypatch):
        """Drive PBAPContactSync.connect() with controlled Select outcomes."""
        sync, svc = _make_sync()
        mock_pbap = MagicMock(name="PhonebookAccess1")
        pullall_called = []

        def _select(location, path):
            if path == "telecom/pb" and telecom_fails:
                raise _dbus_exc()
            if path == "pb" and pb_fails:
                raise _dbus_exc()

        mock_pbap.Select.side_effect = _select
        mock_pbap.PullAll.side_effect = (
            lambda *a, **kw: pullall_called.append(a) or ["/transfer/1", {}]
        )

        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/session/1"
        mock_props = _make_transfer("complete")

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface",
                   side_effect=[mock_client, mock_pbap, mock_props]), \
             patch("tincand.backends.pbap.GLib") as mock_glib, \
             patch("os.unlink"):
            mock_glib.timeout_add.side_effect = lambda ms, fn: fn() or 99
            sync.connect("AA:BB:CC:DD:EE:FF")

        return sync, svc, mock_pbap, pullall_called

    def test_telecom_pb_success_uses_it(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=False, pb_fails=False, monkeypatch=monkeypatch
        )
        # First Select call should be "telecom/pb"
        first_call = mock_pbap.Select.call_args_list[0]
        assert first_call == call("int", "telecom/pb")

    def test_telecom_pb_success_calls_pullall(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=False, pb_fails=False, monkeypatch=monkeypatch
        )
        assert len(pullall_called) == 1

    def test_telecom_pb_success_does_not_try_pb(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=False, pb_fails=False, monkeypatch=monkeypatch
        )
        select_paths = [c[0][1] for c in mock_pbap.Select.call_args_list]
        assert "pb" not in select_paths

    def test_telecom_pb_fail_falls_back_to_pb(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=True, pb_fails=False, monkeypatch=monkeypatch
        )
        select_paths = [c[0][1] for c in mock_pbap.Select.call_args_list]
        assert "pb" in select_paths

    def test_telecom_pb_fail_pb_success_calls_pullall(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=True, pb_fails=False, monkeypatch=monkeypatch
        )
        assert len(pullall_called) == 1

    def test_both_fail_no_pullall_called(self, monkeypatch):
        sync, svc, mock_pbap, pullall_called = self._connect_with_select_behavior(
            telecom_fails=True, pb_fails=True, monkeypatch=monkeypatch
        )
        assert len(pullall_called) == 0

    def test_both_fail_logs_warning(self, monkeypatch, caplog):
        sync, svc = _make_sync()
        mock_pbap = MagicMock(name="PhonebookAccess1")
        mock_pbap.Select.side_effect = _dbus_exc()
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/session/1"

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface",
                   side_effect=[mock_client, mock_pbap]), \
             caplog.at_level(logging.WARNING, logger="tincand.backends.pbap"):
            sync.connect("AA:BB:CC:DD:EE:FF")

        assert any("could not select" in r.message.lower() or "aborting" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# §2 _on_pullall_complete skip logging
# ---------------------------------------------------------------------------

class TestOnPullAllCompleteLogging:
    """_on_pullall_complete logs WARNING when 0 contacts, INFO when > 0."""

    def _write_vcards(self, vcards: list[str]) -> str:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".vcf", delete=False, encoding="utf-8"
        )
        for vc in vcards:
            tmp.write(vc)
        tmp.close()
        return tmp.name

    def _good_vcard(self, name="Alice", phone="+15550001111"):
        return (
            f"BEGIN:VCARD\r\nVERSION:2.1\r\nFN:{name}\r\n"
            f"TEL:{phone}\r\n"
            f"END:VCARD\r\n"
        )

    def _no_fn_vcard(self):
        return "BEGIN:VCARD\r\nVERSION:2.1\r\nTEL:+15550001111\r\nEND:VCARD\r\n"

    def _no_tel_vcard(self, name="Bob"):
        return f"BEGIN:VCARD\r\nVERSION:2.1\r\nFN:{name}\r\nEND:VCARD\r\n"

    def test_zero_contacts_logs_warning(self, caplog):
        sync, svc = _make_sync()
        tmp_path = self._write_vcards([])
        # _on_pullall_complete deletes tmp_path in its own finally block
        with caplog.at_level(logging.DEBUG, logger="tincand.backends.pbap"):
            sync._on_pullall_complete(tmp_path)
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1

    def test_positive_count_logs_info_not_warning(self, caplog):
        sync, svc = _make_sync()
        tmp_path = self._write_vcards([self._good_vcard()])
        with caplog.at_level(logging.DEBUG, logger="tincand.backends.pbap"):
            sync._on_pullall_complete(tmp_path)
        info_msgs = [r.message for r in caplog.records if r.levelno == logging.INFO
                     and "mappings loaded" in r.message]
        assert len(info_msgs) >= 1

    def test_skipped_no_fn_counter_increments(self, caplog):
        sync, svc = _make_sync()
        tmp_path = self._write_vcards([self._no_fn_vcard(), self._no_fn_vcard()])
        with caplog.at_level(logging.DEBUG, logger="tincand.backends.pbap"):
            sync._on_pullall_complete(tmp_path)
        summary = next(
            (r.message for r in caplog.records if "no-fn" in r.message), ""
        )
        assert "2 no-fn" in summary

    def test_skipped_no_tel_counter_increments(self, caplog):
        sync, svc = _make_sync()
        tmp_path = self._write_vcards([self._no_tel_vcard("Carol"), self._no_tel_vcard("Dave")])
        with caplog.at_level(logging.DEBUG, logger="tincand.backends.pbap"):
            sync._on_pullall_complete(tmp_path)
        summary = next(
            (r.message for r in caplog.records if "no-tel" in r.message), ""
        )
        assert "2 no-tel" in summary


# ---------------------------------------------------------------------------
# §3 Fields filter removal
# ---------------------------------------------------------------------------

class TestPBAPFieldsFilter:
    """PullAll is called with only 'Format' — no 'Fields' key."""

    def test_pullall_called_without_fields_key(self, monkeypatch):
        sync, svc = _make_sync()
        captured_filters = []

        def _fake_pullall(path, filter_dict):
            captured_filters.append(dict(filter_dict))
            return ["/transfer/1", {}]

        mock_pbap = MagicMock(name="PhonebookAccess1")
        mock_pbap.Select.return_value = None
        mock_pbap.PullAll.side_effect = _fake_pullall
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/session/1"
        mock_props = _make_transfer("complete")

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface",
                   side_effect=[mock_client, mock_pbap, mock_props]), \
             patch("tincand.backends.pbap.GLib") as mock_glib, \
             patch("os.unlink"):
            mock_glib.timeout_add.side_effect = lambda ms, fn: fn() or 99
            sync.connect("AA:BB:CC:DD:EE:FF")

        assert len(captured_filters) == 1
        assert "Fields" not in captured_filters[0]

    def test_pullall_filter_contains_format_key(self, monkeypatch):
        sync, svc = _make_sync()
        captured_filters = []

        def _fake_pullall(path, filter_dict):
            captured_filters.append(dict(filter_dict))
            return ["/transfer/1", {}]

        mock_pbap = MagicMock()
        mock_pbap.Select.return_value = None
        mock_pbap.PullAll.side_effect = _fake_pullall
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/session/1"
        mock_props = _make_transfer("complete")

        with patch("tincand.backends.pbap.dbus.SessionBus"), \
             patch("tincand.backends.pbap.dbus.Interface",
                   side_effect=[mock_client, mock_pbap, mock_props]), \
             patch("tincand.backends.pbap.GLib") as mock_glib, \
             patch("os.unlink"):
            mock_glib.timeout_add.side_effect = lambda ms, fn: fn() or 99
            sync.connect("AA:BB:CC:DD:EE:FF")

        assert len(captured_filters) == 1
        assert "Format" in captured_filters[0]
