"""tincand daemon entry point — python -m tincand."""
from __future__ import annotations

import argparse
import logging
import os
import signal

from gi.repository import GLib

_log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tincand — Bluetooth messaging daemon")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock backend (no real Bluetooth hardware required)",
    )
    return parser.parse_args()


def _select_backend(use_mock: bool) -> object:
    if use_mock or os.environ.get("TINCAN_BACKEND") == "mock":
        from tincand.backends.mock import MockBackend

        return MockBackend()
    raise NotImplementedError(
        "No backend selected. Use --mock or set TINCAN_BACKEND=mock to start the daemon."
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    backend = _select_backend(args.mock)

    import dbus.mainloop.glib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    import dbus

    from tincand.dbus_service import TincanService

    bus = dbus.SessionBus()
    service = TincanService(bus)
    backend.register_service(service)

    loop = GLib.MainLoop()

    def _on_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
        _log.info("SIGINT received — shutting down")
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    backend.start()
    _log.info("tincand started")
    try:
        loop.run()
    finally:
        backend.stop()
        _log.info("tincand stopped")


if __name__ == "__main__":
    main()
