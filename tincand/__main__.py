"""tincand daemon entry point — python -m tincand."""
from __future__ import annotations

import argparse
import logging
import os
import pathlib
import re
import signal
import sys

_ADAPTER_PATH_RE = re.compile(r"^/org/bluez/hci\d+$")

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


_DEV_MAC_RE = re.compile(r"/dev_([0-9A-Fa-f_]{17})$")


def _mac_from_ofono_path(path: str) -> str:
    """Extract a Bluetooth MAC from an oFono modem path.

    /hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20 → D0:6B:78:33:46:20
    """
    m = _DEV_MAC_RE.search(str(path))
    if not m:
        return ""
    return m.group(1).replace("_", ":").upper()


def _resolve_device_address(args: argparse.Namespace) -> tuple[str, bool]:
    """Return (device_address, device_discovered).

    Priority chain:
      1. args.device (--device CLI flag)
      2. TINCAN_DEVICE env var
      3. DaemonSettings bluetooth/device_address (tincan.ini)
      4. oFono auto-discovery — Online HFP modems → extract MAC
      5. '' (waiting/retry mode)

    device_discovered is True only when the address comes from Step 4.
    """
    # Step 1: --device CLI flag
    if getattr(args, "device", None):
        _log.info("tincand: device address from --device flag (source=cli): %s", args.device)
        return str(args.device), False

    # Step 2: env var
    env_device = os.environ.get("TINCAN_DEVICE")
    if env_device:
        _log.info("tincand: device address from TINCAN_DEVICE env (source=env): %s", env_device)
        return env_device, False

    # Step 3: DaemonSettings bluetooth/device_address
    from tincand.config import DaemonSettings  # noqa: PLC0415

    ini_device = DaemonSettings().value("bluetooth/device_address", "").strip()
    if ini_device:
        _log.info("tincand: device address from tincan.ini (source=config): %s", ini_device)
        return ini_device, False

    # Step 4: oFono auto-discovery
    try:
        import dbus  # noqa: PLC0415

        bus = dbus.SystemBus()
        manager_obj = bus.get_object("org.ofono", "/")
        manager = dbus.Interface(manager_obj, "org.ofono.Manager")
        modems = manager.GetModems()

        candidates = []
        for path, props in modems:
            props = dict(props)
            if str(props.get("Type", "")) == "hfp" and bool(props.get("Online", False)):
                mac = _mac_from_ofono_path(str(path))
                if mac:
                    candidates.append(mac)

        if len(candidates) > 1:
            _log.warning(
                "tincand: multiple Online HFP modems found %s — using %s. "
                "Pin a device with bluetooth/device_address in tincan.ini.",
                candidates,
                candidates[0],
            )
        if candidates:
            _log.info("tincand: device address from oFono discovery (source=ofono): %s", candidates[0])
            return candidates[0], True
    except Exception as exc:  # noqa: BLE001
        _log.debug("tincand: oFono auto-discovery unavailable (%s) — no device address", exc)

    # Step 5: waiting/retry mode
    _log.info("tincand: no device address resolved — will retry")
    return "", False


def _resolve_adapter_path(args: argparse.Namespace) -> tuple[str, str]:
    """Return (resolved_path, adapter_path_requested).

    Priority: --adapter flag → TINCAN_ADAPTER env var → DaemonSettings
    bluetooth/adapter_path → auto-detect first powered adapter → /org/bluez/hci1.

    adapter_path_requested is '' unless the QSettings adapter was absent from
    BlueZ; in that case it holds the requested path so GetStatus() can surface it.
    """
    explicit = getattr(args, "adapter", None) or os.environ.get("TINCAN_ADAPTER")
    if explicit:
        return explicit, ""

    from tincand.config import DaemonSettings  # noqa: PLC0415

    qsettings_raw = DaemonSettings().value("bluetooth/adapter_path", default=None)
    qsettings_path = (
        qsettings_raw if qsettings_raw and _ADAPTER_PATH_RE.match(qsettings_raw) else None
    )

    try:
        import dbus  # noqa: PLC0415

        bus = dbus.SystemBus()
        obj_mgr = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        objects = obj_mgr.GetManagedObjects()

        if (
            qsettings_path
            and qsettings_path in objects
            and "org.bluez.Adapter1" in objects[qsettings_path]
        ):
            _log.info("tincand: using QSettings adapter %s", qsettings_path)
            return str(qsettings_path), ""

        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" not in ifaces:
                continue
            props = ifaces["org.bluez.Adapter1"]
            if props.get("Powered", False):
                _log.info("tincand: auto-detected adapter %s", path)
                return str(path), qsettings_path or ""
    except Exception as exc:  # noqa: BLE001
        _log.debug("tincand: adapter auto-detect failed (%s) — using /org/bluez/hci1", exc)
    return "/org/bluez/hci1", qsettings_path or ""


def _select_backend(args: argparse.Namespace, adapter_path: str = "", device_addr: str = "") -> object:
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

    # Install the GLib D-Bus mainloop BEFORE the first bus connection is created.
    # dbus-python caches the SystemBus/SessionBus singletons, and the first
    # creation decides whether the connection is bound to a mainloop.
    # _resolve_adapter_path() and CallController both open SystemBus(); if the
    # default loop isn't set yet, the cached connection cannot subscribe to
    # signals ("connections must be attached to a main loop") and oFono call
    # control silently goes dark. Order matters — keep this before any bus use.
    import dbus
    import dbus.mainloop.glib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    adapter_path, adapter_path_requested = _resolve_adapter_path(args)
    _device_addr, _device_discovered = _resolve_device_address(args)
    backend = _select_backend(args, adapter_path, device_addr=_device_addr)

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

    service.set_adapter_path(adapter_path)
    service.set_adapter_path_requested(adapter_path_requested)

    from tincand.hfp_capability import is_call_setup_ready
    service.set_capability("call_setup_ready", is_call_setup_ready())

    service.set_device_discovered(_device_discovered)

    from tincand.call_controller import CallController
    call_controller = CallController(
        service,
        service._contact_store,
        device_addr=_device_addr,
        adapter_hci=adapter_path.rsplit("/", 1)[-1] if adapter_path else "",
    )
    service.set_call_controller(call_controller)

    if args.with_ancs and args.backend == "map":
        from tincand.backend_manager import BackendManager
        from tincand.backends.ancs import ANCSBackend

        ancs = ANCSBackend(device_addr=_device_addr, adapter_path=adapter_path)
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

    backend_name = args.backend or os.environ.get("TINCAN_BACKEND", "")
    _log.info("tincand starting with backend=%s device=%s", backend_name, _device_addr)
    try:
        backend.connect(_device_addr)
    except Exception as exc:
        _log.warning(
            "tincand: initial connection to %s failed (%s) — "
            "daemon running, will retry every %ds",
            _device_addr,
            exc,
            10,
        )
        if hasattr(backend, "schedule_reconnect"):
            backend.schedule_reconnect()

    if backend_name == "map" and _device_addr:
        from tincand.backends.pbap import PBAPContactSync
        pbap = PBAPContactSync(service)
        service._pbap = pbap
        GLib.idle_add(lambda: pbap.connect(_device_addr) or False)

    _log.info("tincand started")
    try:
        loop.run()
    finally:
        backend.disconnect()
        _log.info("tincand stopped")


if __name__ == "__main__":
    main()
