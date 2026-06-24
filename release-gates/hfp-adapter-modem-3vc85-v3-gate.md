# Release gate: hfp-adapter-modem-3vc85 (v3)

**Branch:** `feat/hfp-adapter-aware-modem-selection-3vc85`
**HEAD:** `32d1114`
**Gate date:** 2026-06-24
**Runner:** builder-1

## Commits in gate

- `9b38c6e` fix(calls): adapter-aware HFP modem selection with deferred Online bind (tincan-3vc85)
- `c1f1f21` fix(calls): proactive SetProperty Powered=true on preferred Offline modem (tincan-odlh9)
- `4014afa` fix(calls): VCM signal leak, re-bind log, log polish (tincan-8o1pj, tincan-5jeeu, tincan-eld4u)
- `baf552b` test(calls): VCM subscription cleanup tests + empty mac guard (tincan-czxfo, tincan-5tojh)
- `471e119` chore: release gate PASS for hfp-adapter-modem-3vc85 (tincan-pqjct)
- `2ad57a7` test(calls): adapter-aware HFP modem selection — 6 NF1 scenarios (tincan-aggkh)
- `ecc8f29` test(calls): T3/T4/FR6 additions — lambda capture, hci10 disambiguation, SetProperty (tincan-8gpmz)
- `32d1114` chore(tests): fix ruff lint in validator-authored test commits

## Test results

```
pytest tests/ --ignore=tests/tincand/test_mcp_server.py
2013 passed, 1 skipped, 6 xfailed
```

## Lint

```
ruff check tincand/call_controller.py tincand/call_audio.py \
    tests/tincand/test_call_controller.py tests/tincand/test_call_audio.py
All checks passed!
```

## Review sign-offs

- tincan-czxfo (VCM tests): CLOSED — PASS
- tincan-awc8g (FR6 SetProperty): CLOSED — PASS (re-review)

## Result: PASS
