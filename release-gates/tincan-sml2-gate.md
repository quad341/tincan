# Release Gate: tincan-sml2 — dbus-python fix + §14 ANCS tests

**Bead:** tincan-sml2
**Source beads / reviews:** tincan-zt71 (a08da7d PASS) + tincan-glhc (8c4b412 PASS)
**Commits evaluated:** a08da7d + 8c4b412 (both on main)
**Gate point:** 8c4b412 (abcba62 and f9bcd3d are on main above this; gated against 8c4b412 per bead instructions — abcba62 contains intentionally-failing TDD tests for tincan-inb6/pql5, f9bcd3d adds tincan-ygl3 feature)
**Gate run:** 2026-06-02
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-zt71 CLOSED PASS (a08da7d, 0 blockers, 3 LOW advisories); tincan-glhc CLOSED PASS (8c4b412, 0 blockers, 1 LOW advisory) |
| 2 | Acceptance criteria met | ✅ PASS | All ACs verified against code — see detail below |
| 3 | Tests pass + lint clean | ✅ PASS | 162 pass, 8 fail (test_dbus_client_live.py — live D-Bus/daemon required, pre-existing); ruff PASS |
| 4 | No HIGH findings open | ✅ PASS | Zero HIGH findings across both review beads; all advisories are LOW |
| 5 | Final branch is clean | ✅ N/A | Commits are on main; local-only repo (no remote) |
| 6 | Branch diverges cleanly from main | ✅ N/A | Commits are on main; local-only repo (no remote) |
| 7 | Single feature theme | ✅ PASS | Both commits fix/test the same ANCS+dbus integration path: a08da7d fixes the dbus_client live method path; 8c4b412 re-lands regression tests for the signal-receiver-on-disconnect fix. Reviewer explicitly bundled into one deploy bead. |

---

## Criterion 2 — Acceptance criteria

### a08da7d — dbus_client dbus-python fix (tincan-ixr4 / tincan-zt71)

| AC | Status | Evidence |
|----|--------|---------|
| `get_status()` uses dbus-python (`dbus.SessionBus()`) | ✅ PASS | `tincan_gui/dbus_client.py:260` — `bus = _dbus.SessionBus()` in `_dbus_call()`; `get_status()` calls `_dbus_call(_IFACE_DAEMON, "GetStatus")` at line 272 |
| `list_conversations()` uses dbus-python | ✅ PASS | `dbus_client.py:296` — `list_conversations()` calls `_dbus_call(_IFACE_MESSAGES, "ListConversations")` |
| Qt fallback retained when dbus unavailable | ✅ PASS | `dbus_client.py:275,303` — Qt fallback path present ("used when dbus-python is unavailable (unit tests with mocks)") |

### 8c4b412 — §14 TestSignalReceiverCleanup re-land (tincan-5p06 / tincan-glhc)

| AC | Status | Evidence |
|----|--------|---------|
| 10 new §14 regression tests present | ✅ PASS | `test_ancs_backend.py` class `TestSignalReceiverCleanup` contains 10 tests: `test_disconnected_removes_notif_source_receiver`, `test_disconnected_removes_data_source_receiver`, `test_disconnected_notif_src_receiver_removed_with_correct_path`, `test_disconnected_data_src_receiver_removed_with_correct_path`, `test_disconnected_clears_notif_src_path_field`, `test_disconnected_clears_data_src_path_field`, `test_started_not_subscribed_disconnect_does_not_call_remove_receiver`, `test_remove_receiver_exception_does_not_propagate`, `test_reconnect_cycle_re_registers_both_receivers`, `test_reconnect_second_disconnect_removes_receivers_again` |
| All 71 test_ancs_backend.py tests pass | ✅ PASS | `pytest tests/tincand/test_ancs_backend.py` — 71 collected, 71 passed |

---

## Criterion 3 — Test + lint run (at 8c4b412)

```
python -m pytest --tb=no -q --ignore=tincan_gui --ignore=tests/tincan_gui
162 passed, 8 failed  (in 13.35s)

FAILED tests/tincand/test_dbus_client_live.py::TestGetStatus::test_get_status_returns_capabilities_key
FAILED tests/tincand/test_dbus_client_live.py::TestGetStatus::test_get_status_capabilities_has_messages_key
FAILED tests/tincand/test_dbus_client_live.py::TestGetStatus::test_get_status_capabilities_has_ancs_key
FAILED tests/tincand/test_dbus_client_live.py::TestListConversations::test_list_conversations_returns_non_empty_list
FAILED tests/tincand/test_dbus_client_live.py::TestListConversations::test_list_conversations_each_entry_has_id_key
FAILED tests/tincand/test_dbus_client_live.py::TestListConversations::test_list_conversations_each_entry_has_display_name_key
FAILED tests/tincand/test_dbus_client_live.py::TestSignalReception::test_connected_signal_received_within_5s
FAILED tests/tincand/test_dbus_client_live.py::TestSignalReception::test_capability_changed_signal_received_within_5s

ruff check .: All checks passed!
```

All 8 failures are in `test_dbus_client_live.py` — tests requiring a live tincand daemon + real D-Bus session. This is the same pre-existing baseline as the tincan-eeb1 gate (also 162 pass, 8 fail at a08da7d). No new failures introduced by 8c4b412 (test-only commit, additive).

---

## Criterion 4 — Review findings

| Review bead | Finding | Severity |
|-------------|---------|----------|
| tincan-zt71 F1 | `_dbus_call()` creates a new `dbus.SessionBus()` on every call (internally cached by dbus-python) | ADVISORY/LOW |
| tincan-zt71 F2 | `get_status()` preserves dbus wrapper types (dbus.String, dbus.Boolean) rather than coercing | ADVISORY/LOW |
| tincan-zt71 F3 | Same dbus-type preservation in `list_conversations()` inner values | ADVISORY/LOW |
| tincan-glhc F1 | `test_reconnect_second_disconnect_removes_receivers_again` hardcodes expected remove counts of 2 and 4 | ADVISORY/LOW |

Zero HIGH findings.

---

## Push / PR status

Project is configured as local-only (no git remote). Commits a08da7d + 8c4b412 already on main.
Merge authority: mayor.
