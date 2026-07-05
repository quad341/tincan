"""tincand/setup_preflight.py — system preflight checks for calls setup (tincan-lqj89)."""
from __future__ import annotations

import logging
import pathlib
import subprocess

_log = logging.getLogger(__name__)

_OFONO_BUS_NAME = "org.ofono"
_WIREPLUMBER_BUS_NAME = "org.freedesktop.ReserveDevice1.Audio0"


def _check_ofono_available() -> bool:
    """Return True when oFono D-Bus service is reachable on the system bus."""
    try:
        import dbus  # noqa: PLC0415
        bus = dbus.SystemBus()
        obj = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
        iface = dbus.Interface(obj, "org.freedesktop.DBus")
        names = [str(n) for n in iface.ListNames()]
        return _OFONO_BUS_NAME in names
    except Exception as exc:
        _log.debug("ofono_available check failed: %s", exc)
        return False


def _check_wireplumber_ofono_backend() -> bool:
    """Return True when WirePlumber's oFono backend is active.

    Checks for the ofono-sink-watcher or ofono-source-watcher object in
    PipeWire's WirePlumber session via the wireplumber D-Bus API. Falls back
    to checking the WirePlumber config file known to enable the oFono backend.
    """
    try:
        import dbus  # noqa: PLC0415
        bus = dbus.SessionBus()
        obj = bus.get_object("org.freedesktop.WirePlumber", "/org/freedesktop/WirePlumber")
        iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        # WirePlumber exposes its loaded components; the oFono backend registers nodes.
        props = iface.GetAll("org.freedesktop.WirePlumber")
        active = bool(props.get("Active", False))
        if not active:
            return False
    except Exception:
        pass

    # Fallback: check if operator's WirePlumber config has the oFono backend enabled.
    # The file is at /home/jaword/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf
    # (operator config is at /home/jaword, not ~/. — see ENV TRAP in bd memories).
    import os  # noqa: PLC0415
    operator_home = pathlib.Path(
        os.environ.get("ACTUAL_HOME", "/home/jaword")
    )
    config_path = (
        operator_home / ".config" / "wireplumber" / "wireplumber.conf.d" / "50-bluez-ofono.conf"
    )
    system_config = pathlib.Path("/usr/share/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf")
    if config_path.exists() or system_config.exists():
        return True

    # Check if wireplumber is running with ofono support via pw-dump
    try:
        result = subprocess.run(
            ["pw-dump"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return "ofono" in result.stdout.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _check_selinux_hfp_module() -> "bool | str":
    """Return True, False, or 'permissive' for the tincan_hfp_sco SELinux module.

    - True: Enforcing mode + tincan_hfp_sco module loaded → calls ready
    - False: Enforcing mode + module absent → install needed
    - 'permissive': SELinux is Permissive/Disabled → module not required
    """
    from tincand.hfp_capability import (  # noqa: PLC0415
        _MODULE_NAME,
        _check_module_loaded,
        _get_enforce_mode,
    )
    mode = _get_enforce_mode()
    if mode in ("Permissive", "Disabled", ""):
        return "permissive"
    loaded = _check_module_loaded(_MODULE_NAME)
    if loaded is True:
        return True
    if loaded is False:
        return False
    return False  # unknown → treat as absent for safety


def _check_usb_autosuspend_disabled() -> bool:
    """Return True when USB autosuspend is disabled for all BT USB devices.

    Checks /sys/bus/usb/devices/*/power/autosuspend_delay_ms == -1 (or
    autosuspend == -1 on older kernels) for devices with the Bluetooth class.
    Returns True if no BT USB devices are found (non-USB adapters are fine).
    """
    usb_root = pathlib.Path("/sys/bus/usb/devices")
    if not usb_root.exists():
        return True

    bt_devices_found = 0
    autosuspend_ok = 0

    for dev in usb_root.iterdir():
        bclass_path = dev / "bDeviceClass"
        if not bclass_path.exists():
            continue
        try:
            bclass = bclass_path.read_text().strip()
        except OSError:
            continue
        # Bluetooth devices have bDeviceClass "e0" (224) or use an interface class
        # Some BT adapters have class "ff" (vendor-specific); also check bInterfaceClass
        iclass_path = dev / "bInterfaceClass"
        is_bt = bclass in ("e0", "E0")
        if not is_bt and iclass_path.exists():
            try:
                is_bt = iclass_path.read_text().strip().lower() in ("e0",)
            except OSError:
                pass
        if not is_bt:
            continue

        bt_devices_found += 1
        # Check autosuspend_delay_ms first (modern kernels), fall back to autosuspend
        as_ms = dev / "power" / "autosuspend_delay_ms"
        as_old = dev / "power" / "autosuspend"
        for path in (as_ms, as_old):
            if path.exists():
                try:
                    val = int(path.read_text().strip())
                    if val < 0:
                        autosuspend_ok += 1
                    break
                except (OSError, ValueError):
                    pass

    if bt_devices_found == 0:
        return True
    return autosuspend_ok >= bt_devices_found


def _get_adapter_vid_pid(adapter_path: str = "/org/bluez/hci0") -> str:
    """Return 'VVVV:PPPP' for the BT adapter at adapter_path, or '' if unknown.

    Resolves hci0 → /sys/class/bluetooth/hci0/device → USB device VID:PID.
    """
    hci_name = adapter_path.rstrip("/").split("/")[-1]  # e.g. 'hci0'
    sysfs_bt = pathlib.Path(f"/sys/class/bluetooth/{hci_name}/device")
    if not sysfs_bt.exists():
        _log.debug("_get_adapter_vid_pid: %s not found in sysfs", sysfs_bt)
        return ""

    # Walk up the symlink to find the USB device directory with idVendor/idProduct
    try:
        resolved = sysfs_bt.resolve()
    except OSError:
        return ""

    # Traverse up until we find idVendor
    candidate = resolved
    for _ in range(5):
        vid_path = candidate / "idVendor"
        pid_path = candidate / "idProduct"
        if vid_path.exists() and pid_path.exists():
            try:
                vid = vid_path.read_text().strip().lower()
                pid = pid_path.read_text().strip().lower()
                return f"{vid}:{pid}"
            except OSError:
                return ""
        candidate = candidate.parent

    return ""


class SetupPreflightChecker:
    """Run calls-setup preflight checks and return a result dict.

    All checks are synchronous and fast (< 1 s each). The result dict is
    safe to return via D-Bus; string values are used where booleans are ambiguous
    (e.g., selinux_hfp_module = 'permissive' when SELinux is not enforcing).
    """

    def check_calls(self, adapter_path: str = "/org/bluez/hci0") -> dict:
        """Run all calls-setup preflight checks.

        Returns dict with keys:
          ofono_available: bool
          wireplumber_ofono_backend: bool
          selinux_hfp_module: bool | str  ('permissive' when SELinux not enforcing)
          usb_autosuspend_disabled: bool
          adapter_vid_pid: str
        """
        return {
            "ofono_available": _check_ofono_available(),
            "wireplumber_ofono_backend": _check_wireplumber_ofono_backend(),
            "selinux_hfp_module": _check_selinux_hfp_module(),
            "usb_autosuspend_disabled": _check_usb_autosuspend_disabled(),
            "adapter_vid_pid": _get_adapter_vid_pid(adapter_path),
        }
