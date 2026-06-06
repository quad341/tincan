"""Tests: tincand.__main__ — _select_backend() backend selection logic.
Bead: tincan-spa

Coverage:
  §1 _select_backend() — --backend flag selects correct backend class
  §2 _select_backend() — TINCAN_BACKEND env var selects correct backend class
  §3 _select_backend() — exits when no backend is specified
  §4 _select_backend() — exits when unknown backend name is provided

No hardware or real D-Bus required.
Run with: python -m pytest tests/tincand/test_main.py -v
"""
from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from tincand.__main__ import _select_backend
from tincand.backends.mock import MockBackend


def _args(backend=None, device=None):
    ns = argparse.Namespace()
    ns.backend = backend
    ns.device = device
    return ns


# ---------------------------------------------------------------------------
# §1 --backend flag
# ---------------------------------------------------------------------------

class TestSelectBackendFlag:
    def test_backend_mock_returns_mock_backend(self):
        result = _select_backend(_args(backend="mock"))
        assert isinstance(result, MockBackend)

    def test_backend_ancs_returns_ancs_backend(self):
        from tincand.backends.ancs import ANCSBackend
        result = _select_backend(_args(backend="ancs"))
        assert isinstance(result, ANCSBackend)

    def test_backend_ancs_passes_device_from_flag(self):
        from tincand.backends.ancs import ANCSBackend
        result = _select_backend(_args(backend="ancs", device="AA:BB:CC:DD:EE:FF"))
        assert isinstance(result, ANCSBackend)
        assert result._device_addr == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# §2 TINCAN_BACKEND env var
# ---------------------------------------------------------------------------

class TestSelectBackendEnv:
    def test_env_mock_returns_mock_backend(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "mock")
        result = _select_backend(_args())
        assert isinstance(result, MockBackend)

    def test_env_ancs_returns_ancs_backend(self, monkeypatch):
        from tincand.backends.ancs import ANCSBackend
        monkeypatch.setenv("TINCAN_BACKEND", "ancs")
        result = _select_backend(_args())
        assert isinstance(result, ANCSBackend)

    def test_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "ancs")
        result = _select_backend(_args(backend="mock"))
        assert isinstance(result, MockBackend)


# ---------------------------------------------------------------------------
# §3 No backend → sys.exit
# ---------------------------------------------------------------------------

class TestSelectBackendNoBackend:
    def test_no_backend_calls_sys_exit(self, monkeypatch):
        monkeypatch.delenv("TINCAN_BACKEND", raising=False)
        with pytest.raises(SystemExit):
            _select_backend(_args())

    def test_empty_env_calls_sys_exit(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "")
        with pytest.raises(SystemExit):
            _select_backend(_args())


# ---------------------------------------------------------------------------
# §4 Unknown backend → sys.exit
# ---------------------------------------------------------------------------

class TestSelectBackendUnknown:
    def test_unknown_backend_flag_calls_sys_exit(self):
        with pytest.raises(SystemExit):
            _select_backend(_args(backend="bluez-map"))

    def test_unknown_env_backend_calls_sys_exit(self, monkeypatch):
        monkeypatch.setenv("TINCAN_BACKEND", "unknown_backend")
        with pytest.raises(SystemExit):
            _select_backend(_args())
