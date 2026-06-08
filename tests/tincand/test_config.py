"""Unit tests for tincand/config.py DaemonSettings."""
from __future__ import annotations

import stat

import pytest

from tincand.config import DaemonSettings


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return DaemonSettings()


class TestBoolCoercion:
    def test_bool_true_round_trips(self, tmp_settings):
        tmp_settings.setValue("x/flag", True)
        tmp_settings.sync()
        assert tmp_settings.value("x/flag", type=bool) is True

    def test_bool_false_round_trips(self, tmp_settings):
        tmp_settings.setValue("x/flag", False)
        tmp_settings.sync()
        assert tmp_settings.value("x/flag", type=bool) is False

    @pytest.mark.parametrize("raw", ["true", "1", "yes"])
    def test_truthy_string_coerces(self, tmp_settings, raw):
        tmp_settings.setValue("x/flag", raw)
        tmp_settings.sync()
        assert tmp_settings.value("x/flag", type=bool) is True

    @pytest.mark.parametrize("raw", ["false", "0", "no"])
    def test_falsy_string_coerces(self, tmp_settings, raw):
        tmp_settings.setValue("x/flag", raw)
        tmp_settings.sync()
        assert tmp_settings.value("x/flag", type=bool) is False


class TestStrPassthrough:
    def test_str_round_trips(self, tmp_settings):
        tmp_settings.setValue("General/name", "hello world")
        tmp_settings.sync()
        assert tmp_settings.value("General/name") == "hello world"

    def test_missing_key_returns_default(self, tmp_settings):
        assert tmp_settings.value("General/missing", default="fallback") == "fallback"

    def test_missing_key_returns_none_by_default(self, tmp_settings):
        assert tmp_settings.value("General/missing") is None


class TestGroupRoundTrip:
    def test_beginGroup_childKeys_endGroup(self, tmp_settings):
        tmp_settings.beginGroup("notifications")
        tmp_settings.setValue("com.apple.mobilesms", "allow")
        tmp_settings.setValue("com.apple.mail", "deny")
        tmp_settings.endGroup()
        tmp_settings.sync()

        tmp_settings.beginGroup("notifications")
        keys = tmp_settings.childKeys()
        tmp_settings.endGroup()
        assert set(keys) == {"com.apple.mobilesms", "com.apple.mail"}

    def test_endGroup_no_op_on_empty_stack(self, tmp_settings):
        tmp_settings.endGroup()  # must not raise

    def test_childKeys_empty_for_missing_section(self, tmp_settings):
        tmp_settings.beginGroup("nonexistent")
        assert tmp_settings.childKeys() == []
        tmp_settings.endGroup()

    def test_nested_key_path(self, tmp_settings):
        tmp_settings.setValue("notifications/app_filter/bundle.id", "allow")
        tmp_settings.sync()
        assert tmp_settings.value("notifications/app_filter/bundle.id") == "allow"


class TestAtomicWrite:
    def test_xdg_config_home_override(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
        s = DaemonSettings()
        s.setValue("General/key", "value")
        s.sync()
        assert (custom / "tincan" / "tincan.ini").exists()

    def test_parent_dirs_created(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b" / "c"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(deep))
        s = DaemonSettings()
        s.setValue("General/x", "y")
        s.sync()
        assert (deep / "tincan" / "tincan.ini").exists()

    def test_file_mode_is_0o600(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        s = DaemonSettings()
        s.setValue("General/key", "val")
        s.sync()
        ini = tmp_path / "tincan" / "tincan.ini"
        assert stat.S_IMODE(ini.stat().st_mode) == 0o600
