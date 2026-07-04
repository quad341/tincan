"""Tests: SerialWorker / InlineWorker and MapBackend worker-based polling.
Bead: tincan-97mlk.3

Coverage:
  §1 SerialWorker — jobs run off the calling thread; completions delivered on
     the GLib main context; exceptions marshalled to on_done; jobs execute in
     submit order; busy flag covers submit → delivery.
  §2 InlineWorker — synchronous execution, same (result, exc) contract.
  §3 MapBackend._poll_tick — I/O dispatched via the worker; overlapping ticks
     skipped while a poll is in flight; results processed on completion;
     stale completions (session generation changed) are dropped.

No hardware or real OBEX — D-Bus objects mocked; SerialWorker tests use a real
GLib main context.
Run with: python -m pytest tests/tincand/test_obex_worker.py -v
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import dbus.exceptions
from gi.repository import GLib

from tincand.backends.bluez_map import MapBackend
from tincand.obex_worker import InlineWorker, SerialWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pump_until(predicate, timeout: float = 5.0) -> None:
    """Iterate the default GLib main context until predicate() or timeout."""
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.005)
    assert predicate(), "timed out waiting for main-context delivery"


class _DeferredWorker:
    """Worker double that records submissions and lets tests deliver manually."""

    def __init__(self) -> None:
        self.jobs: list = []  # (fn, on_done)

    @property
    def busy(self) -> bool:
        return bool(self.jobs)

    def submit(self, fn, on_done=None) -> None:
        self.jobs.append((fn, on_done))

    def deliver_next(self) -> None:
        fn, on_done = self.jobs.pop(0)
        result, exc = None, None
        try:
            result = fn()
        except BaseException as e:  # noqa: BLE001 — mirrors worker marshalling
            exc = e
        if on_done is not None:
            on_done(result, exc)

    def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# §1 SerialWorker
# ---------------------------------------------------------------------------


class TestSerialWorker:
    def test_job_runs_off_calling_thread_and_delivers_on_main_context(self):
        worker = SerialWorker(name="test-worker")
        done: list = []
        worker.submit(
            lambda: threading.current_thread().name,
            lambda result, exc: done.append((result, exc)),
        )
        _pump_until(lambda: done)
        worker.stop()
        result, exc = done[0]
        assert exc is None
        assert result == "test-worker"
        assert result != threading.current_thread().name

    def test_exception_is_marshalled_to_on_done(self):
        worker = SerialWorker(name="test-worker")
        done: list = []

        def _boom():
            raise ValueError("kaput")

        worker.submit(_boom, lambda result, exc: done.append((result, exc)))
        _pump_until(lambda: done)
        worker.stop()
        result, exc = done[0]
        assert result is None
        assert isinstance(exc, ValueError)
        assert str(exc) == "kaput"

    def test_jobs_execute_in_submit_order(self):
        worker = SerialWorker(name="test-worker")
        executed: list = []
        done: list = []
        for i in range(5):
            worker.submit(
                lambda i=i: executed.append(i),
                lambda result, exc: done.append(exc),
            )
        _pump_until(lambda: len(done) == 5)
        worker.stop()
        assert executed == [0, 1, 2, 3, 4]
        assert all(exc is None for exc in done)

    def test_busy_true_from_submit_until_delivery(self):
        worker = SerialWorker(name="test-worker")
        release = threading.Event()
        done: list = []
        assert not worker.busy
        worker.submit(release.wait, lambda result, exc: done.append(exc))
        assert worker.busy  # queued/running, completion not yet delivered
        release.set()
        _pump_until(lambda: done)
        assert not worker.busy
        worker.stop()

    def test_never_used_worker_spawns_no_thread(self):
        worker = SerialWorker(name="test-worker-idle")
        assert not worker._thread.is_alive()
        worker.stop()  # must not raise on a never-started worker


# ---------------------------------------------------------------------------
# §2 InlineWorker
# ---------------------------------------------------------------------------


class TestInlineWorker:
    def test_runs_synchronously_and_delivers_result(self):
        done: list = []
        InlineWorker().submit(lambda: 42, lambda result, exc: done.append((result, exc)))
        assert done == [(42, None)]

    def test_delivers_exception(self):
        done: list = []

        def _boom():
            raise RuntimeError("kaput")

        InlineWorker().submit(_boom, lambda result, exc: done.append((result, exc)))
        assert done[0][0] is None
        assert isinstance(done[0][1], RuntimeError)


# ---------------------------------------------------------------------------
# §3 MapBackend._poll_tick via worker
# ---------------------------------------------------------------------------


class TestMapBackendPollViaWorker:
    def _backend(self, worker) -> MapBackend:
        backend = MapBackend(worker=worker)
        backend._msg_access = MagicMock()
        return backend

    def test_poll_tick_processes_results_on_completion(self):
        backend = self._backend(InlineWorker())
        parsed_sentinel = [{"path": "msg1"}]
        backend._poll_fetch = lambda: parsed_sentinel
        processed: list = []
        backend._process_poll_results = lambda parsed: processed.append(parsed)

        result = backend._poll_tick()

        assert processed == [parsed_sentinel]
        assert result == GLib.SOURCE_CONTINUE
        assert backend._poll_in_flight is False

    def test_poll_tick_skips_while_previous_poll_in_flight(self):
        worker = _DeferredWorker()
        backend = self._backend(worker)
        backend._poll_fetch = lambda: []

        backend._poll_tick()
        backend._poll_tick()  # previous poll not delivered yet → must skip

        assert len(worker.jobs) == 1

    def test_poll_tick_resumes_after_completion(self):
        worker = _DeferredWorker()
        backend = self._backend(worker)
        backend._poll_fetch = lambda: []

        backend._poll_tick()
        worker.deliver_next()
        backend._poll_tick()

        assert len(worker.jobs) == 1
        assert backend._poll_in_flight is True

    def test_stale_completion_after_disconnect_is_dropped(self):
        worker = _DeferredWorker()
        backend = self._backend(worker)
        backend._poll_fetch = lambda: [{"path": "stale"}]
        processed: list = []
        backend._process_poll_results = lambda parsed: processed.append(parsed)

        backend._poll_tick()
        backend._session_gen += 1  # session torn down / replaced mid-poll
        backend._poll_in_flight = False
        worker.deliver_next()

        assert processed == []

    def test_dead_session_error_in_completion_triggers_recovery(self):
        backend = self._backend(InlineWorker())

        def _dead():
            raise dbus.exceptions.DBusException(
                name="org.freedesktop.DBus.Error.UnknownObject"
            )

        backend._poll_fetch = _dead
        recovered: list = []
        backend._handle_session_dead = lambda: recovered.append(True)

        result = backend._poll_tick()

        assert recovered == [True]
        assert result == GLib.SOURCE_CONTINUE

    def test_non_dead_session_error_does_not_trigger_recovery(self):
        backend = self._backend(InlineWorker())

        def _flaky():
            raise dbus.exceptions.DBusException(name="org.bluez.obex.Error.Failed")

        backend._poll_fetch = _flaky
        recovered: list = []
        backend._handle_session_dead = lambda: recovered.append(True)

        result = backend._poll_tick()

        assert recovered == []
        assert result == GLib.SOURCE_CONTINUE
        assert backend._poll_in_flight is False  # next tick may poll again

    def test_poll_inbox_remains_synchronous_composition(self):
        """Direct poll_inbox() callers keep the original blocking semantics."""
        backend = MapBackend()
        backend._poll_fetch = lambda: [{"path": "m1"}]
        processed: list = []
        backend._process_poll_results = lambda parsed: processed.append(parsed) or parsed

        result = backend.poll_inbox()

        assert result == [{"path": "m1"}]
        assert processed == [[{"path": "m1"}]]
