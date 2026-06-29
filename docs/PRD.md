# PRD: Remove Group-Message Surface (tincan-w621v)

**Status:** Draft
**Author:** tincan/planner
**Date:** 2026-06-29
**Source bead:** tincan-w621v
**Type:** Cleanup / Feature removal
**Priority:** P2

---

## Problem Statement

Tincan exposes a group-messaging surface (send + receive) that does not work
over the iPhone's MAP (Message Access Profile). Live testing verified in June
2026 (PR #156, `docs/LIMITATIONS.md`, `spikes/FINDINGS.md` OQ-6):

- **Send:** iOS accepts a multi-recipient MMS push but delivers only to the
  first recipient and creates no group thread on the phone.
- **Receive/reply:** there is no working return path to a group thread.

A group conversation in the UI is therefore a silent dead end: a reply reaches
at most one person, with no warning. Fixing the send-side obexd call signature
bug (2-arg call vs. the required `ssa{sv}` signature) revealed this iOS-level
platform limitation — the feature cannot be made to work without violating
tincan's Bluetooth-profiles-only constraint.

**Who is affected:** All tincan users who encounter multi-recipient inbound
messages. The current experience is misleading; removal improves honesty and
eliminates a crash-prone code path.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Eliminate every group-send/receive API surface | `grep -rE 'send_group_message\|SendMessageToRecipients\|build_bmsg_multi\|_group_participants'` over `tincand/` + `tincan_gui/` returns zero live references |
| G2 | Inbound multi-recipient messages are rendered usefully, not silently dropped | A multi-recipient inbound message creates a 1:1 thread keyed by sender phone, visible in the GUI, with working reply |
| G3 | 1:1 SMS send + receive is completely unaffected | Existing 1:1 messaging tests pass unchanged |
| G4 | Codebase quality maintained | ruff clean + full pytest suite green after removal |

## Non-Goals

- Fixing group messaging to work — iOS MAP does not support it and fixing it
  is out of scope per the Bluetooth-profiles-only constraint.
- Removing the inbound MMS image-attachment parse path (`_parse_mms_content` /
  the `Type=="MMS"` attachment fetch). That is a distinct dead-code cleanup
  (FINDINGS OQ-5); keep it for a separate change unless its removal is
  trivially entangled with this work.
- Any changes to docs (already updated in PR #156; verify they match final
  behavior but no further doc edits expected from this change).
- iMessage support, RCS, or any other messaging mode.

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a user who receives an iMessage or group SMS addressed to multiple people, I want the message to appear in a normal 1:1 thread from the sender, so that I can reply to that sender and have the reply actually reach them. |
| US2 | As a user, I want the GUI to show me only conversation types that work end-to-end, so that I am not misled into a thread where my reply silently fails. |
| US3 | As a developer or MCP agent, I want the D-Bus and MCP APIs to omit group-send methods so that I cannot accidentally invoke a dead code path. |

---

## Functional Requirements

### FR1 — Remove group-send surface (D-Bus, MCP, daemon)

**FR1.1 — BackendInterface ABC.**
`send_group_message` must be removed from `tincand/backends/base.py`.

**FR1.2 — Backend implementations.**
`send_group_message` (and `build_bmsg_multi`) must be removed from:
- `tincand/backends/bluez_map.py`
- `tincand/backends/ancs.py`
- `tincand/backends/fake_map.py`
- `tincand/backends/mock.py`

**FR1.3 — BackendManager.**
`send_group_message` delegate must be removed from `tincand/backend_manager.py`.

**FR1.4 — D-Bus service.**
From `tincand/dbus_service.py`, remove:
- `SendMessageToRecipients` method
- `_group_participants` dict and its population in `upsert_conversation`
- The `SendMessage → send_group_message` routing branch (`to in self._group_participants`)
- `GetConversationParticipants` (if only used for the group surface — verify before removing)
- `is_group` on the `Conversation` dataclass and its D-Bus exposure (if only used for groups — verify before removing)

**FR1.5 — MCP server.**
Remove `send_group_message` from:
- `tincand/mcp/server.py` (tool definition)
- `tincand/mcp/dbus_bridge.py` (bridge method)
- `tincand/mcp/__main__.py` (help line)

**FR1.6 — GUI client.**
From `tincan_gui/dbus_client.py`, remove `send_message_to_recipients` and
`get_conversation_participants` client wrappers.

---

### FR2 — Remove group-receive / group UI surface (GUI)

**FR2.1 — ConversationData model.**
Remove `is_group` from `ConversationData` (and any associated `group_name`
field) in `tincan_gui/` only if it is not also used outside group contexts.
If it is used outside group contexts, keep it and only remove its group-specific
consumers.

**FR2.2 — Group conversation card / GroupAvatarWidget.**
Remove `GroupAvatarWidget` and its rendering from `tincan_gui/main.py`.
Remove the group conversation card path entirely.

**FR2.3 — Thread view group mode.**
Remove `BubbleType.GROUP_UNKNOWN_SENDER`, `set_group_mode`, and the group
rendering branch from the `ThreadView` widget.

**FR2.4 — Compose/new-convo group path.**
Remove the group-mode path from the new-conversation flow and from the compose
widget, including `group_hint` handling.

---

### FR3 — Inbound multi-recipient messages treated as 1:1

**FR3.1 — poll_inbox / `_emit_messages` grouping branch.**
In `tincand/backends/bluez_map.py`, the branch that sets `is_group`, assigns a
SHA1-of-participants conversation key, or tags the message with `group_hint`
must be removed. A multi-recipient inbound message must key its conversation by
**sender phone** (the `Sender` / `SenderAddressing` MAP field) exactly as a 1:1
message does. The resulting thread is indistinguishable from a normal 1:1 thread.

**FR3.2 — Reply path.**
A reply to a thread created from a multi-recipient inbound message must use
`send_message` (1:1) to the sender phone. No group-send call is invoked.

---

### FR4 — Test cleanup

**FR4.1 — Delete test files.**
- `tests/tincand/test_map_group_send.py` — delete entirely
- `tests/tincand/test_dbus_service_group.py` — delete entirely

**FR4.2 — Strip group-specific tests from existing files.**
- `tests/tincand/test_bluez_map_multi.py` — remove `build_bmsg_multi` section; keep `normalize_phone` tests; drop `_parse_participants` tests only if the helper is removed
- `tests/tincand/test_backend_manager.py` — remove `send_group_message` delegation test
- `tests/tincand/test_fake_map_backend.py` — remove group-send tests
- `tests/tincand/test_mcp_server.py` — remove `send_group_message` tests
- `tests/tincand/test_reply_routing.py` — remove group-routing tests; keep 1:1 routing tests
- `tests/tincand/test_dbus_service.py` — remove `_group_participants` population test
- `tests/tincand/test_dbus_contract.py` — remove `SendMessageToRecipients` contract entry

---

## Non-Functional Requirements

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR1 | ruff + black clean | `ruff check .` and `black --check .` return 0 on all changed files |
| NFR2 | Full pytest suite green | `pytest` returns 0 with no new failures |
| NFR3 | grep sentinel passes | `grep -rE 'send_group_message\|SendMessageToRecipients\|build_bmsg_multi\|_group_participants'` over `tincand/` + `tincan_gui/` returns no hits |
| NFR4 | 1:1 messaging unaffected | Tests specifically covering 1:1 send and receive pass unchanged |
| NFR5 | No new external dependencies | stdlib + existing requirements only |

---

## Technical Constraints

*(derived from `docs/PROJECT_MANIFEST.md`)*

- **Python 3.14** — ruff + black must pass.
- **Bluetooth-profiles-only constraint:** No iMessage RE, no non-MAP send paths.
- **Daemon/client API boundary:** The D-Bus interface is the authoritative API;
  GUI and MCP are pure clients. API changes (removing `SendMessageToRecipients`,
  `GetConversationParticipants`, `is_group` D-Bus exposure) must be consistent
  across all clients.
- **Daemon is stateless:** No persistence inside `tincand`. Remove group state
  (`_group_participants`, SHA1 conversation keys) without introducing new state.
- **Capability detection principle:** Removing a feature that never worked is
  not a regression; no capability flag needed for this removal.
- **Branch convention:** `tincan-w621v` feature branch, merge after reviewer gate.

---

## Dependencies

| # | Dependency | Needed For | Status |
|---|------------|-----------|--------|
| D1 | PR #156 (MAP image spike) | Context for OQ-6 finding; docs already updated | Merged or in progress on `cohelper/map-image-spike` — builder should verify docs are in sync |
| D2 | `normalize_phone` utility in `bluez_map.py` | Must be preserved through cleanup | Exists; keep regardless |
| D3 | 1:1 `send_message` path | Reply path after removal (FR3.2) | Exists; unchanged |

---

## Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| OQ1 | Is `is_group` on `Conversation` / `ConversationData` used outside the group-message surface (e.g., the Calls UI dialpad dial-button hide rule `conv_data.is_group`)? If yes, keep the field and only remove the group-message-specific consumers. If no, remove the field entirely. | builder | Before removing `is_group` |
| OQ2 | Is `GetConversationParticipants` D-Bus method used by any consumer other than the group-message surface (e.g., the calls UI bead tincan-8dehj)? If yes, keep it. | builder | Before removing method |
| OQ3 | Are there any remaining references to `_parse_participants_from_bmsg` or `_parse_mms_content` in the MAP backend that are entangled with the group-message removal rather than the separate MMS attachment cleanup? If entangled, include; if separable, leave for the MMS cleanup bead. | builder | During implementation |

---

## Implementation Plan (for builder reference)

The 11-step plan below is derived from the bead notes and is provided as a
starting point. The builder must re-verify all file paths and line numbers
against `origin/main` before editing (the bead notes warn that grepped line
numbers may have drifted).

1. Remove `send_group_message` from BackendInterface ABC, `bluez_map` (+ `build_bmsg_multi`, `_parse_participants`), `ancs`, `fake_map`, `mock`, `backend_manager`.
2. Simplify `_emit_messages` / `poll_inbox`: multi-recipient inbound keys by sender as 1:1 (remove `is_group` logic, SHA1 key, `group_hint`).
3. Remove `is_group` / `group_name` from `Conversation` dataclass + `to_dbus` **after verifying OQ1**.
4. Remove `_group_participants`, `SendMessageToRecipients`, `GetConversationParticipants` from `dbus_service` **after verifying OQ2**.
5. Remove `SendMessage` group branch; clean `register_backend` / `upsert_conversation`.
6. Remove MCP `send_group_message` tool from `server.py`, `bridge.py`, `__main__.py`.
7. GUI: remove `is_group` from `ConversationData`, `GroupAvatarWidget` usage, group rendering, `set_group_mode` on compose / `thread_view`.
8. GUI: remove group branch in new-convo flow, `group_hint` handling.
9. Remove `BubbleType.GROUP_UNKNOWN_SENDER` + `set_group_mode` from `ThreadView`.
10. Remove `send_message_to_recipients` + `get_conversation_participants` from `dbus_client.py`.
11. Tests: delete `test_map_group_send`, `test_dbus_service_group`; strip group tests from the 7 other files per FR4.2.

---

## Handoff Notes for Downstream Agents

This change is a **pure removal** with no new architecture or UI design needed.

**Architect:** Not required. No new D-Bus interfaces, no new domain types,
no new dependencies. The removal plan is fully specified.

**Designer:** Not required. The post-removal behavior (multi-recipient inbound
→ 1:1 thread from sender) uses the existing 1:1 conversation UI without
modification.

**Builder:** Implement steps FR1–FR4 in the order given in the Implementation
Plan above. Resolve OQ1–OQ3 during implementation (the answers are determinable
by reading the current code). Run `ruff`, `black`, and `pytest` before
submitting. Verify the grep sentinel in NFR3 returns zero hits before calling
the work done. The docs (LIMITATIONS.md, PR #156) are already updated — check
that they still match the final behavior but no further doc edits should be
needed.

---

*PRD covers bead: tincan-w621v*
