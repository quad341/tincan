"""SerialWorker — a single worker thread for blocking OBEX I/O.

The daemon is single-threaded GLib; every blocking OBEX operation (folder
listing, per-message body transfers, transfer-status polling with its
time.sleep backoffs) used to run directly on the main loop, so one stalled
transfer froze ANCS delivery, call control, and all D-Bus dispatch for up to
the transfer timeout (tincan-97mlk.3).

MAP sessions are stateful (SetFolder navigation), so OBEX operations must be
serialized against each other regardless — which makes one dedicated worker
thread the natural shape: the main loop submits jobs, the worker executes
them in order, and completions are marshalled back to the main loop with
GLib.idle_add. Nothing here is MAP-specific; the worker just runs callables.

Thread-safety: dbus.mainloop.glib.threads_init() is called before the worker
thread starts so dbus-python connections may be used from it. Completion
callbacks always run on the GLib main loop, so they may safely touch
TincanService, SQLite stores, and GLib sources.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import dbus.mainloop.glib
from gi.repository import GLib

_log = logging.getLogger(__name__)

# on_done receives (result, exc) — exactly one of them is non-None
# (both None for a job that returned None successfully).
DoneCallback = Callable[[object, BaseException | None], None]


class SerialWorker:
    """Run submitted callables one at a time on a dedicated thread.

    Completions are delivered on the GLib main loop. The thread is a daemon
    thread started lazily on first submit, so constructing a SerialWorker is
    cheap and a worker that is never used never spawns a thread.
    """

    def __init__(self, name: str = "obex-worker") -> None:
        # Must run before the worker thread makes D-Bus calls; idempotent.
        dbus.mainloop.glib.threads_init()
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._started = False
        # Incremented on submit, decremented on main-loop delivery — both on
        # the main thread, so no lock is needed.
        self._pending = 0

    @property
    def busy(self) -> bool:
        """True while any submitted job has not yet delivered its completion."""
        return self._pending > 0

    def submit(self, fn: Callable[[], object], on_done: DoneCallback | None = None) -> None:
        """Queue *fn* for the worker thread.

        on_done(result, exc) is invoked later on the GLib main loop; exc is
        the exception *fn* raised, or None on success.
        """
        if not self._started:
            self._thread.start()
            self._started = True
        self._pending += 1
        self._queue.put((fn, on_done))

    def stop(self) -> None:
        """Ask the worker thread to exit after finishing queued jobs."""
        if self._started:
            self._queue.put(None)

    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            fn, on_done = item
            result: object = None
            exc: BaseException | None = None
            try:
                result = fn()
            except BaseException as e:  # noqa: BLE001 — marshalled to on_done
                exc = e
            GLib.idle_add(self._deliver, on_done, result, exc)

    def _deliver(
        self, on_done: DoneCallback | None, result: object, exc: BaseException | None
    ) -> bool:
        self._pending -= 1
        if on_done is not None:
            try:
                on_done(result, exc)
            except Exception:
                _log.exception("worker completion callback failed")
        elif exc is not None:
            _log.warning("worker job failed with no completion callback: %s", exc)
        return GLib.SOURCE_REMOVE


class InlineWorker:
    """Test double with the SerialWorker interface that runs jobs synchronously.

    Executes *fn* on the caller's thread and invokes on_done immediately, so
    tests exercise the submit → complete flow without threads or a main loop.
    """

    busy = False

    def submit(self, fn: Callable[[], object], on_done: DoneCallback | None = None) -> None:
        result: object = None
        exc: BaseException | None = None
        try:
            result = fn()
        except BaseException as e:  # noqa: BLE001 — mirrors SerialWorker marshalling
            exc = e
        if on_done is not None:
            on_done(result, exc)
        elif exc is not None:
            _log.warning("worker job failed with no completion callback: %s", exc)

    def stop(self) -> None:
        pass
