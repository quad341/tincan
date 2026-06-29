"""Behavior tests: BackendManager (tincan-2oc1c).

Coverage:
  §1 Instantiation — BackendManager can be constructed without abstract-method crash
     - construct with primary only
     - construct with primary + ancs secondary
     - --with-ancs startup path doesn't raise
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tincand.backend_manager import BackendManager
from tincand.backends.base import BackendInterface


def _mock_backend() -> MagicMock:
    """Return a MagicMock that satisfies BackendInterface."""
    return MagicMock(spec=BackendInterface)


# ---------------------------------------------------------------------------
# §1 Instantiation
# ---------------------------------------------------------------------------

class TestBackendManagerInstantiation:
    """BackendManager must instantiate without crashing on abstract methods."""

    def test_construct_primary_only(self):
        primary = _mock_backend()
        mgr = BackendManager(primary)
        assert mgr is not None

    def test_construct_primary_and_secondary(self):
        primary = _mock_backend()
        secondary = _mock_backend()
        mgr = BackendManager(primary, secondaries=[secondary])
        assert mgr is not None

    def test_is_backend_interface_instance(self):
        mgr = BackendManager(_mock_backend())
        assert isinstance(mgr, BackendInterface)


# ---------------------------------------------------------------------------
# §2 connect resilience — a primary failure must not skip secondaries
# ---------------------------------------------------------------------------

class TestConnectResilience:
    """A primary connect failure (e.g. MAP/OBEX 0x43 Forbidden on a fresh iOS
    pairing) must still start the secondaries so ANCS can solicit — then the
    primary failure is re-raised so the caller's retry path is unchanged."""

    def test_secondary_connects_when_primary_raises(self):
        primary = _mock_backend()
        primary.connect.side_effect = RuntimeError("OBEX Connect failed with 0x43")
        secondary = _mock_backend()
        mgr = BackendManager(primary, secondaries=[secondary])
        with pytest.raises(RuntimeError):
            mgr.connect("AA:BB:CC:DD:EE:FF")
        secondary.connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    def test_primary_exception_is_reraised(self):
        primary = _mock_backend()
        boom = RuntimeError("OBEX Connect failed with 0x43")
        primary.connect.side_effect = boom
        mgr = BackendManager(primary, secondaries=[_mock_backend()])
        with pytest.raises(RuntimeError) as excinfo:
            mgr.connect("AA:BB:CC:DD:EE:FF")
        assert excinfo.value is boom

    def test_all_secondaries_attempted_even_if_one_fails(self):
        primary = _mock_backend()
        failing = _mock_backend()
        failing.connect.side_effect = RuntimeError("ancs boom")
        healthy = _mock_backend()
        mgr = BackendManager(primary, secondaries=[failing, healthy])
        mgr.connect("AA:BB:CC:DD:EE:FF")  # primary ok, first secondary fails
        healthy.connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")
