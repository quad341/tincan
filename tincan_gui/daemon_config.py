"""Read/write ~/.config/tincan/config for tincand launch parameters."""
from __future__ import annotations

import configparser
from pathlib import Path

_CONFIG_PATH = Path.home() / ".config" / "tincan" / "config"


class DaemonConfig:
    def __init__(self, backend: str = "map", device: str = "") -> None:
        self.backend = backend
        self.device = device


def load_daemon_config() -> DaemonConfig:
    """Return config from file; returns defaults if file is absent."""
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATH)
    section = cfg["daemon"] if "daemon" in cfg else {}
    return DaemonConfig(
        backend=str(section.get("backend", "map")),
        device=str(section.get("device", "")),
    )


def save_daemon_config(config: DaemonConfig) -> None:
    """Write config to ~/.config/tincan/config, creating dirs as needed."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg["daemon"] = {"backend": config.backend, "device": config.device}
    with _CONFIG_PATH.open("w") as fh:
        cfg.write(fh)
