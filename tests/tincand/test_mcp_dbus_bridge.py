"""Unit tests for tincand/mcp/dbus_bridge.py — _translate() and _strip_dbus()."""
from __future__ import annotations

import dbus
import dbus.exceptions
import pytest

from tincand.mcp.dbus_bridge import (
    TincandError,
    TincandInvalidArgument,
    TincandNotConnected,
    TincandNotRunning,
    _strip_dbus,
    _translate,
)


def _exc(name: str, msg: str = "test error") -> dbus.exceptions.DBusException:
    return dbus.exceptions.DBusException(msg, name=name)


class TestTranslate:
    def test_service_unknown_raises_not_running(self):
        with pytest.raises(TincandNotRunning):
            _translate(_exc("org.freedesktop.DBus.Error.ServiceUnknown"))

    def test_no_reply_raises_not_running(self):
        with pytest.raises(TincandNotRunning):
            _translate(_exc("org.freedesktop.DBus.Error.NoReply"))

    def test_not_connected_raises_not_connected(self):
        with pytest.raises(TincandNotConnected):
            _translate(_exc("im.tincan.Error.NotConnected"))

    def test_invalid_argument_raises_invalid_argument(self):
        with pytest.raises(TincandInvalidArgument):
            _translate(_exc("im.tincan.Error.InvalidArgument"))

    def test_unknown_name_raises_tincan_error(self):
        with pytest.raises(TincandError) as exc_info:
            _translate(_exc("im.tincan.Error.SomethingElse"))
        assert exc_info.value.dbus_name == "im.tincan.Error.SomethingElse"

    def test_not_running_chained_from_original(self):
        orig = _exc("org.freedesktop.DBus.Error.ServiceUnknown")
        with pytest.raises(TincandNotRunning) as exc_info:
            _translate(orig)
        assert exc_info.value.__cause__ is orig


class TestStripDbus:
    def test_plain_dict_passthrough(self):
        assert _strip_dbus({"a": 1}) == {"a": 1}

    def test_dbus_dictionary(self):
        d = dbus.Dictionary({"key": dbus.String("val")}, signature="sv")
        result = _strip_dbus(d)
        assert result == {"key": "val"}
        assert isinstance(result, dict)
        assert isinstance(result["key"], str)

    def test_nested_dict(self):
        d = dbus.Dictionary(
            {"inner": dbus.Dictionary({"x": dbus.Int32(1)}, signature="sv")},
            signature="sv",
        )
        result = _strip_dbus(d)
        assert result == {"inner": {"x": 1}}

    def test_dbus_array(self):
        arr = dbus.Array([dbus.String("a"), dbus.String("b")], signature="s")
        result = _strip_dbus(arr)
        assert result == ["a", "b"]
        assert all(isinstance(x, str) for x in result)

    def test_nested_array_of_dicts(self):
        arr = dbus.Array(
            [dbus.Dictionary({"n": dbus.String("Alice")}, signature="sv")],
            signature="a{sv}",
        )
        result = _strip_dbus(arr)
        assert result == [{"n": "Alice"}]

    def test_dbus_boolean_true(self):
        result = _strip_dbus(dbus.Boolean(True))
        assert result is True
        assert type(result) is bool

    def test_dbus_boolean_false(self):
        result = _strip_dbus(dbus.Boolean(False))
        assert result is False
        assert type(result) is bool

    def test_dbus_string(self):
        result = _strip_dbus(dbus.String("hello"))
        assert result == "hello"
        assert isinstance(result, str)

    def test_dbus_int32(self):
        result = _strip_dbus(dbus.Int32(42))
        assert result == 42
        assert isinstance(result, int)

    def test_dbus_uint32(self):
        result = _strip_dbus(dbus.UInt32(100))
        assert result == 100
        assert isinstance(result, int)

    def test_dbus_int64(self):
        result = _strip_dbus(dbus.Int64(2**40))
        assert result == 2**40
        assert isinstance(result, int)

    def test_plain_int_passthrough(self):
        assert _strip_dbus(42) == 42

    def test_none_passthrough(self):
        assert _strip_dbus(None) is None

    def test_plain_list_recursed(self):
        result = _strip_dbus([dbus.String("x"), dbus.Int32(1)])
        assert result == ["x", 1]
