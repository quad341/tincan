# Plan: Formalize MAP Body-Fetch Live-HW Acceptance Rule

_PM: tincan/pm · 2026-06-07_

---

## Background

PR #46 was merged with only mock-based test coverage for the MAP body-retrieval
path. The live path was broken: `Message1.Get("", False)` raised
`UnknownObject` for all 16 messages in conv 898287. Bodies fell back to the
128-char Subject preview, clipping URLs. Root cause documented in tincan-l8cik.

The incident established that mock-only verification is insufficient for MAP
body-retrieval changes — the mock path and the live BlueZ path can diverge
silently.

---

## Goal

Create `docs/rules/map-body-fetch.md` to formalize the rule that MAP
body-retrieval changes require live-hardware acceptance before closure.

---

## Child Beads

| Bead | Title | Routing | Label |
|------|-------|---------|-------|
| tincan-k35oj | Write docs/rules/map-body-fetch.md: MAP body-retrieval live-HW acceptance rule | builder | ready-to-build |

---

## Rule Summary (for builder reference)

The rule document must specify:

1. **Regression mock** (automated): simulate `Message1.Get → UnknownObject`,
   assert body falls back to truncated Subject. Must remain GREEN.
2. **Fix mock** (automated): simulate `Message1.Get(tmpfile)` returning a
   transfer path, assert full body > Subject length.
3. **Live-HW acceptance** (MANDATORY before close): receive a real SMS >128
   chars on Malala (D0:6B:78:33:46:20); confirm full body renders in tincan;
   `/tmp/tincand-*.log` shows `Transfer recv` lines, not `Get failed`.

**Builder workflow gate:** when code is ready for live test, add `needs-live-test`
to the bead and mail mayor with the bead ID and what to test. Do not close
without operator confirmation.

---

## Acceptance

- `docs/rules/map-body-fetch.md` committed to main
- Three-step rule clearly stated with Malala device spec
- Builder workflow (needs-live-test + mail operator) documented
- Evidence section cites PR #46 / tincan-l8cik
- Format mirrors `docs/rules/validator-dod.md`
