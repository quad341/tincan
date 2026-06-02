"""tincand daemon entry point — python -m tincand."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

from gi.repository import GLib

_log = logging.getLogger(__name__)

_BACKENDS = {"mock", "bluez-map"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tincand — Bluetooth messaging daemon")
    parser.add_argument(
        "--backend",
        choices=sorted(_BACKENDS),
        default=None,
        help="Backend to use (default: mock)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Shorthand for --backend mock",
    )
    parser.add_argument(
        "--device",
        default="AA:BB:CC:DD:EE:FF",
        help="Bluetooth device address to connect to",
    )
    return parser.parse_args()


def _resolve_backend_name(args: argparse.Namespace) -> str:
    if args.mock:
        return "mock"
    if args.backend is not None:
        return args.backend
    env = os.environ.get("TINCAN_BACKEND")
    if env is not None:
        if env not in _BACKENDS:
            choices = ", ".join(sorted(_BACKENDS))
            sys.exit(f"Unknown backend in TINCAN_BACKEND: {env!r}. Must be one of: {choices}")
        return env
    return "mock"


def _select_backend(name: str) -> object:
    if name == "mock":
        from tincand.backends.mock import MockBackend
        return MockBackend()
    if name == "bluez-map":
        from tincand.backends.bluez_map import MapBackend
        return MapBackend()
    sys.exit(f"Unknown backend: {name!r}. Must be one of: {', '.join(sorted(_BACKENDS))}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    backend_name = _resolve_backend_name(args)
    backend = _select_backend(backend_name)

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

    _log.info("tincand starting with backend=%s device=%s", backend_name, args.device)
    backend.connect(args.device)
    _log.info("tincand started")
    try:
        loop.run()
    finally:
        backend.disconnect()
        _log.info("tincand stopped")


if __name__ == "__main__":
    main()
