# Validator Definition-of-Done: Demonstrated Behavior Required

**Rule:** A feature or bug bead may NOT be closed on passing unit tests alone.
Behavioral acceptance — user-visible, end-to-end — must be demonstrated before
the bead closes.

**Evidence that established this rule:** `message_cache.py` + `test_message_cache.py`
passed 100% of unit tests. Beads `tincan-skxe`, `tincan-4vg0`, and `tincan-drj4`
were CLOSED as a result. At the 2026-06-06 deploy, caching, sent-history, and
contact-name display were all broken in the live app. The unit tests were green
because they only exercised individual functions — not user-visible flows through
the full daemon → GUI pipeline.

---

## What counts as behavioral acceptance

### Preferred: integration or contract test
A test that exercises the behavior end-to-end (or at the major boundary) without
real hardware. Examples:

- A `dbus-run-session` integration test that starts tincand, connects a fake backend,
  and asserts that `MessageReceived` signals propagate to a D-Bus subscriber.
- A contract test that introspects tincand's D-Bus interface and asserts the GUI
  subscribes to exactly the signals the daemon exports (not just that unit-test mocks
  return the right values).
- A fake MAP backend test that exercises `MapBackend.poll_inbox()` with iOS-realistic
  data and asserts the correct conversations appear in the service — including that
  `sent-folder=0` causes sent messages to come from local cache only.

At minimum, every bead that adds or changes a user-visible flow **must** have at
least one integration-level or contract-level test covering that flow.

### Acceptable when hardware is required: documented manual smoke
For flows that inherently require real Bluetooth hardware (e.g., verifying that
ANCS actually delivers a notification from a real iPhone over BLE), a documented
manual smoke test is acceptable. The smoke test must:

1. List the exact steps.
2. List the exact observable result (what appears in the GUI, what D-Bus signal
   fires, etc.).
3. Record that it was run, by whom, and on what device.
4. Live either in the bead's notes or in a file committed to the branch.

Hardware-gated smokes are NOT acceptable for flows that can be exercised with
a fake backend, a dbus-run-session, or a contract test.

---

## Validator gate checklist — post-build review

When reviewing a builder's implementation (bead status: `ready-to-review`):

| # | Criterion | Required |
|---|-----------|----------|
| 1 | All new/changed unit tests pass | ✅ required |
| 2 | Lint clean (`ruff check .`) | ✅ required |
| 3 | **Behavioral acceptance demonstrated** (integration test OR documented smoke) | ✅ required — do NOT waive |
| 4 | Acceptance criteria met (all ACs verifiable from the behavioral test or smoke) | ✅ required |
| 5 | No regressions in existing tests | ✅ required |

The validator must fail criterion 3 for ANY bead that only has unit tests and no
integration/contract/smoke evidence. Write an explicit note in the bead explaining
what behavioral evidence is missing, and return it to the builder.

---

## Why this rule exists

Unit tests verify function-level correctness in isolation. They do not verify that
the **pipeline** (daemon → D-Bus signals → GUI subscriptions → slot routing →
UI update) actually works end-to-end. The pipeline has several failure modes that
are invisible to unit tests:

- A D-Bus signal handler missing `@Slot` causes the connection to silently fail
  at runtime — no error, no log entry. Unit tests that call the handler directly
  never detect this.
- A signal with a mismatched type signature is silently dropped by Qt's signal
  routing. Unit tests that mock the signal emission don't hit this path.
- A method call to a D-Bus path that does nothing returns without error — the GUI
  just fails to update. Unit tests that mock the D-Bus call at the Python level
  never see this.
- Local cache semantics (e.g., sent-history stored client-side because iOS MAP
  doesn't expose sent) are only observable in a flow that actually exercises the
  cache and the daemon's response together.

Integration tests, contract tests, and live smokes catch exactly this class of
failure.

---

## Where this rule is enforced

- **Here** (`docs/rules/validator-dod.md`) — the authoritative rule text.
- **Release gates** (`release-gates/`) — criterion 3 must appear in every gate
  checklist with a PASS/FAIL verdict and evidence pointer.
- **Validator agent guidance** (`docs/SOFTWARE_FACTORY_MANIFEST.md` Quality Gates
  section) — references this document.
- **Beads** — the validator adds a note to any bead returned for missing behavioral
  evidence, citing this rule.
