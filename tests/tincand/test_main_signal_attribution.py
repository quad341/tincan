"""Tests: tincand.__main__ — SIGTERM/SIGINT in-process attribution + shutdown.
Bead: tincan-97mlk.6.1 (tests for tincan-97mlk.6)

Coverage:
  §1 _block_shutdown_signals() — SIGINT/SIGTERM land in the thread's signal mask
  §2 _proc_cmdline() / _proc_ppid() — real pid, missing pid, malformed /proc content
  §3 _describe_signal_sender() — chain format, max_depth=4 cutoff, 1000-char cap,
     cycle guard, non-positive-pid fallback
  §4 _signal_waiter() — logs INFO then WARNING then quits, in that order; WARNING
     carries sender pid/uid/chain; loop.quit() called exactly once
  §5 _start_signal_waiter() — spawns a named daemon thread that runs the waiter

Regression context: an earlier version of this code (max_depth=8, no per-cmdline
or overall truncation) filled the daemon's piped stderr while attributing a
SIGTERM sender, blocking the signal-waiter thread inside the logging call and
hanging shutdown (tincan-97mlk.6). §3's bound tests pin the fix.

No hardware or real D-Bus required.
Run with: python -m pytest tests/tincand/test_main_signal_attribution.py -v
"""
from __future__ import annotations

import os
import pathlib
import signal
import types
from unittest.mock import Mock

import pytest

from tincand import __main__ as main

_TRUNCATION_MARKER = "…(truncated)"


def _unused_pid() -> int:
    """A pid that (almost certainly) does not exist right now.

    Computed rather than hardcoded since pid_max varies by system/container.
    """
    candidate = 999_999
    while pathlib.Path(f"/proc/{candidate}").exists():
        candidate += 1
    return candidate


def _fake_siginfo(*, signo=signal.SIGTERM, pid=4242, uid=1000):
    return types.SimpleNamespace(si_signo=signo, si_pid=pid, si_uid=uid)


# ---------------------------------------------------------------------------
# §1 _block_shutdown_signals — process/thread signal mask
# ---------------------------------------------------------------------------


class TestBlockShutdownSignals:
    def test_blocks_sigint_and_sigterm_in_current_thread_mask(self):
        prior_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        try:
            main._block_shutdown_signals()
            new_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
            assert signal.SIGINT in new_mask
            assert signal.SIGTERM in new_mask
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask)


# ---------------------------------------------------------------------------
# §2 _proc_cmdline / _proc_ppid
# ---------------------------------------------------------------------------


class TestProcCmdline:
    def test_real_pid_returns_actual_cmdline(self):
        result = main._proc_cmdline(os.getpid())
        assert result != "<unavailable>"
        assert result

    def test_missing_pid_returns_unavailable(self):
        assert main._proc_cmdline(_unused_pid()) == "<unavailable>"

    def test_long_cmdline_is_truncated_with_marker(self, monkeypatch):
        raw = ("x" * 300).encode() + b"\0"
        monkeypatch.setattr(pathlib.Path, "read_bytes", lambda self: raw)
        result = main._proc_cmdline(12345)
        assert result == "x" * 200 + _TRUNCATION_MARKER

    def test_empty_cmdline_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr(pathlib.Path, "read_bytes", lambda self: b"")
        assert main._proc_cmdline(12345) == "<unavailable>"


class TestProcPpid:
    def test_real_pid_returns_int(self):
        assert isinstance(main._proc_ppid(os.getpid()), int)

    def test_missing_pid_returns_none(self):
        assert main._proc_ppid(_unused_pid()) is None

    def test_status_without_ppid_line_returns_none(self, monkeypatch):
        monkeypatch.setattr(pathlib.Path, "read_text", lambda self: "Name:\tfoo\n")
        assert main._proc_ppid(12345) is None

    def test_malformed_ppid_value_returns_none(self, monkeypatch):
        monkeypatch.setattr(pathlib.Path, "read_text", lambda self: "PPid:\tnotanumber\n")
        assert main._proc_ppid(12345) is None


# ---------------------------------------------------------------------------
# §3 _describe_signal_sender
# ---------------------------------------------------------------------------


class TestDescribeSignalSender:
    def test_chain_format_and_order(self, monkeypatch):
        ppid_map = {100: 50, 50: 10, 10: None}
        cmdline_map = {100: "child", 50: "mid", 10: "init"}
        monkeypatch.setattr(main, "_proc_cmdline", lambda pid: cmdline_map[pid])
        monkeypatch.setattr(main, "_proc_ppid", lambda pid: ppid_map[pid])

        result = main._describe_signal_sender(100)

        assert result == (
            "pid=100 cmdline='child' <- pid=50 cmdline='mid' <- pid=10 cmdline='init'"
        )

    def test_stops_at_max_depth_4_not_8(self, monkeypatch):
        # 6-deep chain: only the nearest 4 ancestors should appear.
        ppid_map = {106: 105, 105: 104, 104: 103, 103: 102, 102: 101, 101: None}
        monkeypatch.setattr(main, "_proc_cmdline", lambda pid: f"proc{pid}")
        monkeypatch.setattr(main, "_proc_ppid", lambda pid: ppid_map[pid])

        result = main._describe_signal_sender(106)

        for pid in (106, 105, 104, 103):
            assert f"pid={pid}" in result
        for pid in (102, 101):
            assert f"pid={pid}" not in result

    def test_overall_length_capped_at_1000(self, monkeypatch):
        ppid_map = {200: 199, 199: 198, 198: 197, 197: None}
        monkeypatch.setattr(main, "_proc_cmdline", lambda pid: "y" * 300)
        monkeypatch.setattr(main, "_proc_ppid", lambda pid: ppid_map[pid])

        result = main._describe_signal_sender(200)

        assert len(result) == 1000 + len(_TRUNCATION_MARKER)
        assert result.endswith(_TRUNCATION_MARKER)

    def test_non_positive_pid_falls_back_to_unavailable(self):
        assert main._describe_signal_sender(0) == "pid=0 <unavailable>"

    def test_cyclic_parent_chain_terminates(self, monkeypatch):
        # 5 -> 6 -> 5 -> ... would loop forever without the `seen` guard.
        ppid_map = {5: 6, 6: 5}
        monkeypatch.setattr(main, "_proc_cmdline", lambda pid: f"proc{pid}")
        monkeypatch.setattr(main, "_proc_ppid", lambda pid: ppid_map[pid])

        result = main._describe_signal_sender(5)

        assert result.count("pid=5") == 1
        assert result.count("pid=6") == 1


# ---------------------------------------------------------------------------
# §4 _signal_waiter
# ---------------------------------------------------------------------------


class TestSignalWaiter:
    def test_logs_then_quits_in_order_with_expected_content(self, monkeypatch):
        siginfo = _fake_siginfo(pid=4242, uid=1000)
        monkeypatch.setattr(main.signal, "sigwaitinfo", lambda sigs: siginfo)
        monkeypatch.setattr(
            main, "_describe_signal_sender", lambda pid: "pid=1 cmdline='initd'"
        )

        calls = []
        monkeypatch.setattr(main._log, "info", lambda *a: calls.append(("info", a)))
        monkeypatch.setattr(main._log, "warning", lambda *a: calls.append(("warning", a)))
        loop = Mock()
        loop.quit.side_effect = lambda: calls.append(("quit", ()))

        main._signal_waiter(loop)

        assert [c[0] for c in calls] == ["info", "warning", "quit"]

        info_fmt, info_signame = calls[0][1]
        assert info_fmt == "%s received — shutting down"
        assert info_signame == "SIGTERM"

        warning_fmt, signame, pid, uid, chain = calls[1][1]
        assert warning_fmt == "%s sent by pid=%d uid=%d chain=%s"
        assert (signame, pid, uid, chain) == ("SIGTERM", 4242, 1000, "pid=1 cmdline='initd'")

        loop.quit.assert_called_once()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Acceptance criteria for tincan-97mlk.6.1 says quit 'must not depend on "
            "the WARNING log succeeding'; current _signal_waiter calls loop.quit() "
            "unconditionally AFTER _log.warning(...) with no try/except, so an "
            "exception there skips quit() and shutdown hangs -- the exact failure "
            "class tincan-97mlk.6 exists to prevent. Confirm intent with reviewer "
            "(tincan-97mlk.6.2); fix by wrapping the warning call or moving "
            "loop.quit() into a finally, then remove this xfail."
        ),
    )
    def test_quit_still_called_if_warning_log_raises(self, monkeypatch):
        siginfo = _fake_siginfo()
        monkeypatch.setattr(main.signal, "sigwaitinfo", lambda sigs: siginfo)
        monkeypatch.setattr(main._log, "warning", Mock(side_effect=RuntimeError("boom")))
        loop = Mock()

        try:
            main._signal_waiter(loop)
        except RuntimeError:
            pass

        assert loop.quit.call_count == 1


# ---------------------------------------------------------------------------
# §5 _start_signal_waiter
# ---------------------------------------------------------------------------


class TestStartSignalWaiter:
    def test_starts_named_daemon_thread_that_runs_the_waiter(self, monkeypatch):
        siginfo = _fake_siginfo()
        monkeypatch.setattr(main.signal, "sigwaitinfo", lambda sigs: siginfo)
        monkeypatch.setattr(main, "_describe_signal_sender", lambda pid: "")
        loop = Mock()

        thread = main._start_signal_waiter(loop)
        thread.join(timeout=2)

        assert thread.name == "tincand-signal-waiter"
        assert thread.daemon is True
        assert not thread.is_alive()
        loop.quit.assert_called_once()
