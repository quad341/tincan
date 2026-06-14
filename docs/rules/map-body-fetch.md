# MAP Body-Retrieval: Live-Hardware Verified on Main

**Rule:** A MAP body-retrieval change **merges on green mock tests** (sections 1
& 2 below). Live-hardware acceptance is **required, but performed on `main`** and
tracked by a `needs-live-test` bead — it is **not** a pre-merge or pre-close
gate.

> **Policy change 2026-06-08.** This rule previously blocked merge/close until
> the operator ran a live test on a feature branch. That held the build queue and
> forced the operator to run arbitrary branches. Per operator decision the live
> test now happens on `main` (test-on-main, file bugs). The verification is still
> mandatory — it simply moves off the PR's critical path to a tracked follow-up.
> First change merged under this policy: PR #92 / `tincan-p74b6`, tracked by
> `tincan-5pjzq`.

**Evidence that established the underlying risk:** PR #46 (bead `tincan-572zo`)
fixed `MessageAccess1.GetMessage → UnknownMethod` and was verified only by mocked
tests that stub `Message1.Get` to succeed. On live hardware (2026-06-07),
`Message1.Get` raised `UnknownObject` for all 16 messages — the body-fetch path
was still broken. Root-cause analysis: `tincan-l8cik` (closed). This is why the
on-main live check remains mandatory even though it no longer blocks merge.

---

## Acceptance requirements

### 1. Regression mock (automated, GATES MERGE — must stay GREEN)
A test that simulates `Message1.Get → UnknownObject` and asserts that
`poll_inbox` falls back to the (possibly truncated) `Subject` field.

File: `tests/tincand/test_repro_fu6xq.py`
Test: `test_BUG_message1_get_unknownobject_truncates_body_to_subject_preview`

This test must remain in the suite and must NOT be deleted or marked xfail.

### 2. Fix mock (automated, GATES MERGE)
A test that simulates `Message1.Get(tmpfile)` returning a transfer path
and asserts that `poll_inbox` returns a body **longer** than the Subject
fallback — i.e., the full body was retrieved, not the preview.

File: `tests/tincand/test_map_get_message_fix.py`
Test: `test_message1_get_tmpfile_fetches_full_body`

### 3. Live-hardware verification (MANDATORY, ON MAIN, tracked — does NOT block merge)
After the change is on `main`, receive a real SMS **longer than 128 characters**
with a long URL on your paired iPhone. Confirm in the tincan GUI
that the full body renders without truncation. Verify in `/tmp/tincand-*.log`
that the daemon shows `Transfer recv` lines — NOT `Get failed UnknownObject`.

If this fails on main, file a bug bead referencing the tracking bead — the fix
did not hold on hardware.

---

## Builder workflow: shipping a MAP body change

1. Ensure the section 1 & 2 mock tests are green — these gate the PR's `test` check.
2. Put an **HW-unverified caveat** in the squash-merge commit body, e.g.
   `⚠️ Merged WITHOUT live-hardware acceptance (test-on-main policy). HW-unverified.`
3. File a `needs-live-test` tracking bead carrying the runbook from section 3,
   assigned to the operator, and reference it from the merge/close.
4. (Optional) FYI the operator:
   ```bash
   gc mail send mayor "needs-live-test: <tracking-bead> — MAP body fetch" \
     "SMS >128 chars with long URL on your paired iPhone. Confirm full body in GUI; no 'Get failed' in daemon log."
   ```
5. Close the implementation bead, noting it merged HW-unverified and citing the
   tracking bead. **Do not** hold the bead/PR open waiting for the live test.

---

## Why live-hardware verification is still required

MAP body-retrieval interacts directly with the BlueZ/obexd D-Bus interface on
a specific iOS device. Mock tests that stub `Message1.Get` to succeed cannot
detect:

- BlueZ version differences in `Message1.Get` argument handling (`targetfile`
  empty vs. real path, `attachment` flag semantics).
- obexd object lifecycle issues (`UnknownObject` on stale transfer paths).
- iOS MAP quirks: `SubjectLength` cap, `sent-folder=0`, multipart SMS
  segment format.

Live-hardware verification is the only check that catches this class of failure —
so it stays mandatory. The 2026-06-08 policy moves *when* it happens (on main,
tracked) but not *whether* it happens.

---

## Where this rule is enforced

- **Here** (`docs/rules/map-body-fetch.md`) — authoritative rule text.
- **Regression test** (`test_repro_fu6xq.py`) — must remain GREEN and not be
  removed (gates merge).
- **Validator review** — reviewer confirms, before approving a MAP body change:
  (a) section 1 & 2 mock tests green, (b) HW-unverified caveat in the merge
  commit, and (c) a `needs-live-test` tracking bead exists. The reviewer no
  longer blocks on live-hardware *evidence* (that now lands on main).
- **Analogous rule:** `docs/rules/validator-dod.md` (general behavioral DoD).
