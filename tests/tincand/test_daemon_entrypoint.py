"""Tests for the tincand daemon entry point argument handling."""
from __future__ import annotations

import sys
from argparse import Namespace

import pytest

from tincand import __main__ as daemon_main
from tincand.backends.mock import MockBackend


def test_mock_shorthand_selects_mock_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["tincand", "--mock"])

    args = daemon_main._parse_args()

    assert args.backend == "mock"
    assert args.mock is True


def test_mock_shorthand_rejects_ancs_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["tincand", "--mock", "--backend", "ancs"])

    with pytest.raises(SystemExit) as excinfo:
        daemon_main._parse_args()

    assert excinfo.value.code == 2


def test_select_backend_uses_mock_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TINCAN_BACKEND", raising=False)

    backend = daemon_main._select_backend(Namespace(backend="mock", device=None))

    assert isinstance(backend, MockBackend)


def test_select_backend_uses_mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TINCAN_BACKEND", "mock")

    backend = daemon_main._select_backend(Namespace(backend=None, device=None))

    assert isinstance(backend, MockBackend)


def test_select_backend_requires_arg_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TINCAN_BACKEND", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        daemon_main._select_backend(Namespace(backend=None, device=None))

    assert "Backend required" in str(excinfo.value)
