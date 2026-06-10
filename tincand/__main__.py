"""tincand daemon entry point — python -m tincand."""
from __future__ import annotations

import argparse
import logging
import os
import pathlib
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
    parser.add_argument(
        "--adapter",
        default=None,
        help=(
            "BlueZ adapter path for the ANCS backend, e.g. /org/bluez/hci1 "
            "(default: TINCAN_ADAPTER env var, then auto-detect)."
        ),
    )
    parser.add_argument(
        "--with-ancs",
        action="store_true",
        dest="with_ancs",
        help=(
            "Run the ANCS backend concurrently with the primary backend "
            "(MAP + ANCS in one process)."
        ),
    )
    args = parser.parse_args()
    if args.mock:
        if args.backend and args.backend != "mock":
            parser.error("--mock cannot be combined with --backend ancs")
        args.backend = "mock"
    return args


def _resolve_adapter_path(args: argparse.Namespace) -> str:
    """Return the BlueZ adapter path to use for ANCS.

    Priority: --adapter flag → TINCAN_ADAPTER env var → auto-detect first
    powered adapter → fallback to /org/bluez/hci1 (the USB dongle slot).
    """
    explicit = getattr(args, "adapter", None) or os.environ.get("TINCAN_ADAPTER")
    if explicit:
        return explicit
    try:
        import dbus  # noqa: PLC0415

        bus = dbus.SystemBus()
        obj_mgr = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        objects = obj_mgr.GetManagedObjects()
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" not in ifaces:
                continue
            props = ifaces["org.bluez.Adapter1"]
            if props.get("Powered", False):
                _log.info("tincand: auto-detected adapter %s", path)
                return str(path)
    except Exception as exc:  # noqa: BLE001
        _log.debug("tincand: adapter auto-detect failed (%s) — using /org/bluez/hci1", exc)
    return "/org/bluez/hci1"


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
        adapter_path = _resolve_adapter_path(args)
        return ANCSBackend(device_addr=device_addr, adapter_path=adapter_path)
    if name == "map":
        from tincand.backends.bluez_map import MapBackend
        from tincand.message_store import MessageStore

        db_path = pathlib.Path(
            os.environ.get("TINCAN_DB", "")
            or pathlib.Path.home() / ".local" / "share" / "tincan" / "messages.db"
        )
        store = MessageStore(db_path)
        return MapBackend(message_store=store)
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
    try:
        service = TincanService(bus)
    except dbus.exceptions.NameExistsException:
        # Another tincand already owns the well-known name. Exit cleanly rather
        # than lingering on the session bus (each lingering instance holds a bus
        # connection; enough of them exhaust dbus-broker's FD limit).
        from tincand.dbus_service import BUS_NAME
        _log.error("tincand: another instance already owns %s — exiting", BUS_NAME)
        sys.exit(0)

    from tincand.hfp_capability import is_call_setup_ready
    service.set_capability("call_setup_ready", is_call_setup_ready())

    if args.with_ancs and args.backend == "map":
        from tincand.backend_manager import BackendManager
        from tincand.backends.ancs import ANCSBackend

        device_addr = args.device or os.environ.get("TINCAN_DEVICE", "")
        adapter_path = _resolve_adapter_path(args)
        ancs = ANCSBackend(device_addr=device_addr, adapter_path=adapter_path)
        backend = BackendManager(primary=backend, secondaries=[ancs])
        _log.info("tincand: multi-backend mode — MAP (primary) + ANCS (secondary)")
    elif args.with_ancs:
        _log.warning("--with-ancs is only supported with --backend map; ignoring")

    backend.register_service(service)
    service.register_backend(backend)

    loop = GLib.MainLoop()

    def _on_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        _log.info("%s received — shutting down", signal.Signals(signum).name)
        loop.quit()

    signal.signal(signal.SIGINT, _on_signal)
    # SIGTERM (terminate()/systemctl stop/kill) gets the same clean shutdown as
    # SIGINT, so the daemon runs backend.disconnect() instead of dying abruptly.
    signal.signal(signal.SIGTERM, _on_signal)

    device = args.device or os.environ.get("TINCAN_DEVICE", "")
    backend_name = args.backend or os.environ.get("TINCAN_BACKEND", "")
    _log.info("tincand starting with backend=%s device=%s", backend_name, device)
    try:
        backend.connect(device)
    except Exception as exc:
        _log.warning(
            "tincand: initial connection to %s failed (%s) — "
            "daemon running, will retry every %ds",
            device,
            exc,
            10,
        )
        if hasattr(backend, "schedule_reconnect"):
            backend.schedule_reconnect()

    if backend_name == "map" and device:
        from tincand.backends.pbap import PBAPContactSync
        pbap = PBAPContactSync(service)
        service._pbap = pbap
        GLib.idle_add(lambda: pbap.connect(device) or False)

    _log.info("tincand started")
    try:
        loop.run()
    finally:
        backend.disconnect()
        _log.info("tincand stopped")


if __name__ == "__main__":
    main()
