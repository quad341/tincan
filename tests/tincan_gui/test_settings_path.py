"""Regression: app_settings() resolves its path from /etc/passwd, not $HOME.

Bead: tincan-3s41m (OQ1 hardening).
A rig shell that overrides HOME must not redirect the settings file.
"""
from __future__ import annotations


def test_app_settings_ignores_overridden_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "bogus"))
    from tincan_gui._settings import app_settings
    fn = app_settings().fileName()
    assert str(tmp_path / "bogus") not in fn
    assert fn.endswith("/.config/tincan/tincan.ini")
