# Release Gate: call_link_ready wired into dial/call button state

**Deploy bead:** tincan-k5q7c
**Source beads:** tincan-wcqn2 (review), tincan-uuia9 (impl)
**Branch:** gc-builder-1-f41fb9344627
**Reviewed/tip commit:** d7b2fe6c7344aa50b684635ad0f97da02441d210
**Base:** origin/main @ 7f34ad6 (same tip the routed bead itself cites)
**Merge-base:** 336c2460b5d35487cfda7fbdcf43737715b5e3b4
**Gate date:** 2026-07-13

## Gate Result: FAIL

Criteria 1-5 all PASS — the reviewed change itself (`d7b2fe6c`) is sound. But
criterion 6 fails: `git merge-tree` against the exact `origin/main` tip the
bead cites shows **real, marker-level conflicts in 7 files, including both
reviewed application files** (`tincan_gui/main.py`, `tincan_gui/thread_view.py`).
This directly contradicts the bead's own note ("a dry-run merge-tree shows no
conflicts in the changed application files"). Criterion 7 fails as a direct
consequence — a PR from this branch as-is would bundle 25 files / +1158/-184
lines spanning at least three unrelated beads, not a single feature theme.

Routed back to the builder rather than resolved here — resolving these
requires reconciling feature intent on both sides, which the deployer seat is
not positioned to safely improvise (see Guardrails: never resolve conflicts
from the deployer seat).

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-wcqn2 closed, reason: pass. Full AC-by-AC verdict recorded in its notes. |
| 2 | Acceptance criteria met | **PASS** | All 7 ACs (tincan-uuia9) independently spot-checked against the diff at d7b2fe6c — line numbers and logic match reviewer's verdict. |
| 3 | Tests pass | **PASS** | Full suite independently re-run at d7b2fe6c (detached HEAD): 2132 passed, 2 skipped, 10 xfailed, 0 failed. ruff clean except 1 pre-existing E501, confirmed via `git blame` to predate this commit. |
| 4 | No high-severity findings open | **PASS** | 0 HIGH. One minor non-blocking finding carried over from review (stale comment at main.py:1035 mischaracterizing call_link_ready as "SCO/audio link state") — confirmed still present, doc-only, non-blocking. |
| 5 | Final branch is clean | **PASS** | `git status` at d7b2fe6c: nothing to commit, working tree clean. |
| 6 | Branch diverges cleanly from main | **FAIL** | See detail below. Real conflicts in 7 files, not a clean fast-forward/no-conflict merge. |
| 7 | Single feature theme | **FAIL** | Consequence of #6: branch carries 9 additional commits beyond the reviewed tip that are not ancestors of origin/main, covering 3+ unrelated beads (tincan-nbjrp, tincan-pyefu, plus this one) and doc/release-gate artifacts. `git diff --stat` vs origin/main: 25 files, +1158/-184. |

---

## Criterion 6 Detail — Merge Conflicts

**Method:** `git merge-tree <merge-base> origin/main gc-builder-1-f41fb9344627`
(non-destructive 3-way analysis; working tree untouched). Merge-base
(`336c2460`) is **27 commits behind** the current `origin/main` tip (`7f34ad6`)
— the identical tip the routed bead's own note cites when it claims "no
conflicts in the changed application files." Re-running the check against
that same tip surfaces real conflicts, so this is a discrepancy in the
original dry-run methodology, not a race against a moving target.

Of the 10 commits the feature branch carries since the merge-base, only the
tip (`d7b2fe6c`, the actually-reviewed change) is genuinely net-new relative
to `origin/main`. The other 9 predate it on the branch and are not ancestors
of main:

```
d7b2fe6 feat(gui): wire call_link_ready into dial/call button state (tincan-uuia9)   <- reviewed
9fc7a44 docs(plans): decompose tincan-bhij3 into build+test children
7af630d docs: bring status docs up to reality; burn in AEC as a hard requirement
097dfc2 feat(ancs): add ANCS_EXT_ADV_BUG + ANCS_EXPERIMENTAL_REQUIRED failure reasons and dispatch
38e55de feat(gui): Calls UI — DialpadDialog, TitleBar Dial, ThreadHeader Call, _sync_call_state (tincan-pyefu)
fdb7873 fix(ancs): silence spurious --with-ancs warning; honest toggle copy (tincan-nbjrp)
5bcce52 style(gui): wrap StateCBanner docstring under line limit
d6c2b08 Merge remote-tracking branch 'origin/main' into builder/tincan-nbjrp
87dbab6 chore: release gate PASS for ancs-default-on-nbjrp (tincan-nbjrp)
bddce79 feat(ancs): honest state model, default-on, heal delegation (tincan-nbjrp)
```

**Files with real conflict markers (7):** `tincan_gui/main.py`,
`tincan_gui/thread_view.py`, `tincand/backends/ancs.py`, `tincand/pairing.py`,
`tests/tincand/test_main_args.py`, `tests/tincan_gui/test_main_daemon.py`,
`spikes/FINDINGS.md`.

**Two confirmed root causes** (verified by direct content inspection of both
tips, not just diff inference):

1. **`tincand/pairing.py` / `tincand/backends/ancs.py` — genuine duplicate
   feature, incompatible values.** Both `origin/main` and this branch (via its
   own commit `097dfc2`) independently added the same two `FailureReason`
   constants, with **different string values**:
   - `origin/main`: `ANCS_EXT_ADV_BUG = "ancs_ext_adv_bug"`,
     `ANCS_EXPERIMENTAL_REQUIRED = "ancs_experimental_required"` (lowercase),
     dispatched via a retained `_classify_adv_error` static method; pairing.py
     also still carries `_ADAPTER_IFACE`/`_PROPS_IFACE`/`computer_name` alias
     lookup.
   - This branch: `ANCS_EXT_ADV_BUG = "ANCS_EXT_ADV_BUG"`,
     `ANCS_EXPERIMENTAL_REQUIRED = "ANCS_EXPERIMENTAL_REQUIRED"` (uppercase,
     self-referential), dispatched via a new `self._adv_failure_reason` field;
     pairing.py drops the alias-lookup code entirely.
   This is not just a textual collision — a naive conflict resolution that
   picks the wrong side changes the literal value any caller/test/telemetry
   matches on. Needs a deliberate reconciliation choice, not a rebase
   autoresolve.

2. **`tincan_gui/main.py` — textual collision with main's existing
   group-conversation plumbing, not a duplicate of the reviewed feature
   itself.** Confirmed via direct grep of both tips: `origin/main` does
   **not** have `call_link_ready` anywhere (the reviewed feature is genuinely
   net-new) — but `origin/main` **already has** group-mode support
   (`_current_is_group`, `_current_contact_name`, `set_group_mode` calls)
   that this branch also carries in a differently-shaped form. The two
   diverge inside the exact same functions the reviewed commit touches
   (`_sync_call_state`, `_apply_capabilities`, the conversation-open handler),
   so git can't auto-merge the `call_link_ready` 3-way gating logic on top of
   `main`'s current group-mode code shape. `tincan_gui/thread_view.py` has one
   smaller instance of the same pattern: the branch is missing a
   `setAccessibleDescription` pairing that `origin/main`'s current version
   already carries at that spot.

**Remaining 3 files** (`test_main_args.py`, `test_main_daemon.py`,
`spikes/FINDINGS.md`) show the same "stale branch vs. moved-on main" pattern
— test scaffolding and doc content drift. Lower individual risk, but they
still block a clean merge and need resolution.

**Recommendation to builder:** don't rebase the whole branch. Cherry-pick only
the reviewed tip (`d7b2fe6c`) onto a fresh branch cut from current
`origin/main`, and manually reconcile the `call_link_ready` insertion against
main's current group-mode code shape in `_sync_call_state` /
`_apply_capabilities` / the conversation-open handler (re-adding the missing
`thread_view.py` a11y pairing if it's still absent post-cherry-pick). Leave
the `ancs.py`/`pairing.py` `FailureReason` question alone entirely — that
feature already shipped independently via `origin/main`; the branch's own
`097dfc2` should not be part of this deploy's diff at all. Since the
reconciled diff will have a different shape than what tincan-wcqn2 reviewed,
a fresh review pass is advisable before re-routing to deploy.

---

## Project Manifest Release Criteria

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Phase definition-of-done | N/A | Incremental UX gating fix, not the Phase 1 E2E milestone |
| 2 | All tests pass | PASS | 2132/2/10, 0 failed, at the reviewed commit in isolation |
| 3 | Lint/format clean | PASS* | Zero new violations; 1 pre-existing E501 predates this commit |
| 4 | No hardcoded iOS/iPhone-model assumptions | PASS | None in the reviewed diff |
| 5 | LIMITATIONS.md updated | N/A | No platform-capability change, only GUI gating on an existing daemon-exposed flag |
| 6 | Onboarding requirements surfaced | PASS | Onboarding paths untouched by the reviewed diff |

*Manifest criteria above evaluate the reviewed commit in isolation and do not
themselves fail — the blocking issue is entirely the branch-history conflict
in criterion 6/7 above.
