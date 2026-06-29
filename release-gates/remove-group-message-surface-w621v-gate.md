# Release Gate: remove-group-message-surface-w621v

**Bead:** tincan-fyrkb (deploy) / tincan-w621v (feature) / tincan-1droe (review)  
**Branch:** builder/tincan-w621v @ d9172fbb  
**Date:** 2026-06-29  
**Gate result:** PASS

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-1droe: "REVIEW VERDICT: PASS" (reviewer-gm-t2m7q, 2026-06-29) |
| 2 | Acceptance criteria met | ✅ PASS | All 12 ACs verified — see below |
| 3 | Tests pass | ✅ PASS | 2214 passed, 1 skipped, 9 xfailed (test_mcp_server.py excluded — pre-existing `mcp` absence) |
| 4 | No high-severity review findings | ✅ PASS | 0 HIGH findings; 2 LOW non-blocking (stale arch doc, cosmetic comment) |
| 5 | Final branch is clean | ✅ PASS | `git status`: nothing to commit, working tree clean |
| 6 | Branch diverges cleanly from main | ✅ PASS | `merge-base --is-ancestor origin/main HEAD` = true; no conflicts |
| 7 | Single feature theme | ✅ PASS | All commits remove group-message surface — one coherent cleanup |

---

## Note on SHA

The review bead (tincan-1droe) references `62d0b10` as the reviewed tip. The current branch tip is `d9172fb`. The builder rebased the 3 feature commits onto the current `origin/main` (`9b5eb99`, the Calls UI PR) after the review passed. Commit messages and content are identical pre/post-rebase; tests re-verified at the current tip and pass identically.

---

## Acceptance criteria

| AC | Status | Verification |
|----|--------|-------------|
| `send_group_message` removed from all backends, BackendInterface, BackendManager | ✅ | grep 0 hits in tincand/ |
| `build_bmsg_multi` / `_parse_participants_from_bmsg` removed from bluez_map.py | ✅ | grep 0 hits |
| `SendMessageToRecipients` / `GetConversationParticipants` D-Bus methods removed | ✅ | grep 0 hits |
| `is_group` / `group_name` removed from Conversation and to_dbus() | ✅ | grep 0 hits |
| `_group_participants` dict removed from TincanService | ✅ | grep 0 hits |
| `GroupAvatarWidget` removed from avatar.py | ✅ | grep 0 hits |
| `BubbleType.GROUP_UNKNOWN_SENDER` removed from thread_view.py | ✅ | grep 0 hits |
| `set_group_mode` removed from ThreadView and ComposePanel | ✅ | grep 0 hits |
| `set_group_info` removed from ThreadHeader | ✅ | grep 0 hits |
| MCP `send_group_message` tool removed | ✅ | grep 0 hits in tincand/mcp/ |
| 3 test files deleted; group tests stripped from 8 others | ✅ | confirmed in diff |
| Multi-recipient inbound threads by sender as 1:1 | ✅ | code inspection + tests green |

---

## Test run

```
platform linux -- Python 3.14.6, pytest-9.0.3
2214 passed, 1 skipped, 9 xfailed in 61.75s
(test_mcp_server.py excluded — pre-existing mcp package absence, same exclusion as reviewer)
```

## Lint

`ruff check .` — 2 pre-existing errors in `docs/mgmt_ext_adv.py` (not touched by this branch). All changed files clean.
