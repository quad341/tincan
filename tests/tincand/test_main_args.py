"""Tests: tincand.__main__ — --with-ancs / --no-ancs default-on argument handling.
Bead: tincan-nbjrp (integration touch-up for PR #154)

Coverage:
  §1 _parse_args() — with_ancs_explicit flag reflects whether the user passed --with-ancs
  §2 main() — no spurious "--with-ancs is only supported" warning on a --mock start
  §3 main() — explicit --with-ancs emits the deprecation hint

Regression: the unconditional `args.with_ancs = not args.no_ancs` clobbered the
flag's default, so the old `elif args.with_ancs:` branch logged a misleading
"--with-ancs is only supported with --backend map; ignoring" on every non-map
start (including --mock) even when nobody passed the flag.

DaemonSettings is mocked so _parse_args never touches real config.
No hardware or real D-Bus required.
Run with: python -m pytest tests/tincand/test_main_args.py -v
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock


def _mock_daemon_settings(monkeypatch, ancs_enabled=True):
    """Patch DaemonSettings so _parse_args reads a controlled ancs/enabled value."""
    monkeypatch.setattr(
        "tincand.config.DaemonSettings",
        lambda *a, **k: MagicMock(value=lambda *a, **k: ancs_enabled),
    )


# ---------------------------------------------------------------------------
# §1 _parse_args — with_ancs_explicit tracks explicit --with-ancs passage
# ---------------------------------------------------------------------------

class TestParseArgsWithAncsExplicit:
    def test_no_flag_is_not_explicit(self, monkeypatch):
        _mock_daemon_settings(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["tincand", "--mock"])
        from tincand.__main__ import _parse_args
        args = _parse_args()
        assert args.with_ancs_explicit is False

    def test_with_ancs_flag_is_explicit(self, monkeypatch):
        _mock_daemon_settings(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["tincand", "--mock", "--with-ancs"])
        from tincand.__main__ import _parse_args
        args = _parse_args()
        assert args.with_ancs_explicit is True


# ---------------------------------------------------------------------------
# §2 / §3 main() — deprecation-hint warning behaviour
# ---------------------------------------------------------------------------

def _neutralise_main(monkeypatch):
    """Stub out everything main() touches so it runs without real D-Bus/Qt/GLib."""
    import dbus
    import dbus.mainloop.glib

    from tincand import __main__ as m

    monkeypatch.setattr(dbus.mainloop.glib, "DBusGMainLoop", lambda set_as_default=False: None)
    monkeypatch.setattr(dbus, "SystemBus", lambda: MagicMock())
    monkeypatch.setattr(dbus, "SessionBus", lambda: MagicMock())
    monkeypatch.delenv("TINCAN_ADAPTER", raising=False)
    monkeypatch.delenv("TINCAN_BACKEND", raising=False)
    monkeypatch.setattr("tincand.dbus_service.TincanService", MagicMock())
    monkeypatch.setattr("tincand.call_controller.CallController", MagicMock())
    monkeypatch.setattr("tincand.hfp_capability.is_call_setup_ready", lambda: False)
    monkeypatch.setattr(m, "_select_backend", lambda *a, **k: MagicMock())
    monkeypatch.setattr(m, "_resolve_adapter_path", lambda args: ("/org/bluez/hci1", ""))
    monkeypatch.setattr(m, "_resolve_device_address", lambda args: ("", False))
    monkeypatch.setattr(m.GLib, "MainLoop", lambda: MagicMock(run=lambda: None))
    monkeypatch.setattr("signal.signal", lambda *a, **k: None)


class TestMainWithAncsWarning:
    """The 'only supported with --backend map' warning must not fire unprompted."""

    def test_mock_start_no_spurious_warning(self, monkeypatch, caplog):
        _mock_daemon_settings(monkeypatch)
        _neutralise_main(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["tincand", "--mock"])

        from tincand import __main__ as m
        with caplog.at_level(logging.WARNING, logger="tincand.__main__"):
            m.main()

        assert "with-ancs" not in caplog.text.lower(), (
            f"spurious --with-ancs warning on a --mock start: {caplog.text!r}"
        )

    def test_explicit_with_ancs_emits_deprecation_hint(self, monkeypatch, caplog):
        _mock_daemon_settings(monkeypatch)
        _neutralise_main(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["tincand", "--mock", "--with-ancs"])

        from tincand import __main__ as m
        with caplog.at_level(logging.WARNING, logger="tincand.__main__"):
            m.main()

        assert "deprecated" in caplog.text.lower(), (
            f"explicit --with-ancs did not emit the deprecation hint: {caplog.text!r}"
        )
