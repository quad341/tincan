"""tincand daemon entry point — python -m tincand."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

from gi.repository import GLib

_log = logging.getLogger(__name__)

_BACKENDS = {"mock", "ancs", "map"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="tincand — Bluetooth messaging daemon")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the mock backend (shorthand for --backend mock).",
    )
    parser.add_argument(
        "--backend",
        choices=sorted(_BACKENDS),
        default=None,
        help=(
            "Backend to use (default: TINCAN_BACKEND env var). "
            "Choices: mock, ancs."
        ),
    )
    parser.add_argument(
        "--device",
        default=None,
        help=(
            "Bluetooth device address for the ancs backend "
            "(default: TINCAN_DEVICE env var)."
        ),
    )
    args = parser.parse_args()
    if args.mock:
        if args.backend and args.backend != "mock":
            parser.error("--mock cannot be combined with --backend ancs")
        args.backend = "mock"
    return args


def _select_backend(args: argparse.Namespace) -> object:
    """Instantiate the backend named by args.backend or TINCAN_BACKEND env var."""
    name = args.backend or os.environ.get("TINCAN_BACKEND")
    if not name:
        choices = ", ".join(sorted(_BACKENDS))
        sys.exit(
            f"Backend required: pass --backend {{{'|'.join(sorted(_BACKENDS))}}} "
            f"or set TINCAN_BACKEND. Choices: {choices}"
        )
    if name == "mock":
        from tincand.backends.mock import MockBackend

        return MockBackend()
    if name == "ancs":
        from tincand.backends.ancs import ANCSBackend

        device_addr = args.device or os.environ.get("TINCAN_DEVICE")
        return ANCSBackend(device_addr=device_addr)
    if name == "map":
        from tincand.backends.bluez_map import MapBackend

        return MapBackend()
    choices = ", ".join(sorted(_BACKENDS))
    sys.exit(f"Unknown backend {name!r}. Must be one of: {choices}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    backend = _select_backend(args)

    import dbus
    import dbus.mainloop.glib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    from tincand.dbus_service import TincanService

    bus = dbus.SessionBus()
    service = TincanService(bus)
    backend.register_service(service)
    service.register_backend(backend)

    loop = GLib.MainLoop()

    def _on_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
        _log.info("SIGINT received — shutting down")
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    device = args.device or os.environ.get("TINCAN_DEVICE", "")
    backend_name = args.backend or os.environ.get("TINCAN_BACKEND", "")
    _log.info("tincand starting with backend=%s device=%s", backend_name, device)
    backend.connect(device)
    _log.info("tincand started")
    try:
        loop.run()
    finally:
        backend.disconnect()
        _log.info("tincand stopped")


if __name__ == "__main__":
    main()
