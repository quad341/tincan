# MAP Body-Retrieval: Live-Hardware Acceptance Required

**Rule:** A MAP body-retrieval change may NOT be closed on mock-only test
success. Live-hardware acceptance is mandatory before closing.

**Evidence that established this rule:** PR #46 (bead `tincan-572zo`) fixed
`MessageAccess1.GetMessage → UnknownMethod` and was verified only by mocked
tests that stub `Message1.Get` to succeed. On live hardware (2026-06-07),
`Message1.Get` raised `UnknownObject` for all 16 messages — the body-fetch
path was still broken. Root-cause analysis: `tincan-l8cik` (closed).

---

## Three-step acceptance requirement

Every MAP body-retrieval change requires all three steps before the bead closes:

### 1. Regression mock (automated, must stay GREEN)
A test that simulates `Message1.Get → UnknownObject` and asserts that
`poll_inbox` falls back to the (possibly truncated) `Subject` field.

File: `tests/tincand/test_repro_fu6xq.py`
Test: `test_BUG_message1_get_unknownobject_truncates_body_to_subject_preview`

This test must remain in the suite and must NOT be deleted or marked xfail.

### 2. Fix mock (automated)
A test that simulates `Message1.Get(tmpfile)` returning a transfer path
and asserts that `poll_inbox` returns a body **longer** than the Subject
fallback — i.e., the full body was retrieved, not the preview.

File: `tests/tincand/test_map_get_message_fix.py`
Test: `test_message1_get_tmpfile_fetches_full_body`

### 3. Live-hardware acceptance (MANDATORY before closing)
Receive a real SMS **longer than 128 characters** with a long URL on device
Malala (`D0:6B:78:33:46:20`). Confirm in the tincan GUI that the full body
renders without truncation. Verify in `/tmp/tincand-*.log` that the daemon
shows `Transfer recv` lines — NOT `Get failed UnknownObject`.

---

## Builder workflow: when live test has not run

When code is ready for live-hardware acceptance but the operator test has not
yet run, the builder must:

1. Add the label `needs-live-test` to the bead.
2. Mail the operator with bead ID and what to test:
   ```bash
   gc mail send mayor "needs-live-test: <bead-id> — MAP body fetch" \
     "SMS >128 chars with long URL on Malala. Confirm full body in GUI; no 'Get failed' in daemon log."
   ```
3. Do NOT close the bead until the operator confirms the live test passed.

---

## Why this rule exists

MAP body-retrieval interacts directly with the BlueZ/obexd D-Bus interface on
a specific iOS device. Mock tests that stub `Message1.Get` to succeed cannot
detect:

- BlueZ version differences in `Message1.Get` argument handling (`targetfile`
  empty vs. real path, `attachment` flag semantics).
- obexd object lifecycle issues (`UnknownObject` on stale transfer paths).
- iOS MAP quirks: `SubjectLength` cap, `sent-folder=0`, multipart SMS
  segment format.

Live-hardware acceptance is the only gate that catches this class of failure.

---

## Where this rule is enforced

- **Here** (`docs/rules/map-body-fetch.md`) — authoritative rule text.
- **Regression test** (`test_repro_fu6xq.py`) — must remain GREEN and not be
  removed.
- **Validator review** — reviewer must confirm live-hardware evidence in bead
  notes before approving a MAP body-retrieval bead.
- **Analogous rule:** `docs/rules/validator-dod.md` (general behavioral DoD).
