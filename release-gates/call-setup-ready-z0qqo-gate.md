# Release Gate: unprivileged call_setup_ready detection fix (tincan-rg53h)

**Bead:** tincan-rg53h  
**Source bead:** tincan-ticp8  
**Branch:** fix/call-setup-ready-z0qqo  
**Commits:** 52ee35c6 (fix) + f00a642 (test coverage)  
**PR:** https://github.com/quad341/tincan/pull/130  
**Gate run:** 2026-06-14  

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan--reviewer PASS on PR #130 at commit 52ee35c6. "Two-fallback unprivileged SELinux module detection. install.sh uses set -euo pipefail. POLICY_NAME hardcoded (no injection risk). Low-severity nit (iterdir lacks OSError catch) filed but not blocking." |
| 2 | Acceptance criteria met | ✅ PASS | (a) `tincand/hfp_capability.py`: adds `/var/lib/selinux/<policy>/active/modules/<priority>/<name>/` directory check as world-readable fallback when `semodule -l` fails non-root. (b) `packaging/selinux/install.sh`: copies built `.pp` to `/usr/share/selinux/packages/` marker path after `semodule -i`. (c) POLICY_NAME hardcoded — no shell injection surface. (d) `install.sh` uses `set -euo pipefail`. |
| 3 | Tests pass | ✅ PASS | 1870 passed, 1 skipped, 6 xfailed, 0 failed (test_mcp_server.py excluded — pre-existing missing `mcp` module). 20/20 `test_hfp_capability.py` tests pass, including 2 new `TestCheckModuleLoadedSelinuxStore` cases. Ruff violations in test file and one log line (E501, I001, E402) are style-only; CI runs ruff with `continue-on-error: true` and they do not block. |
| 4 | No high-severity findings open | ✅ PASS | Reviewer noted one low-severity nit: `iterdir()` lacks `OSError` catch (filed as follow-up). No high-severity findings. |
| 5 | Final branch clean | ✅ PASS | `git status` shows working tree clean (no uncommitted changes). |
| 6 | Branch diverges cleanly from main | ✅ PASS | Branches from 8860622 (current origin/main); no merge conflicts. |
| 7 | Single feature theme | ✅ PASS | SELinux unprivileged call_setup_ready detection fix only. One cohesive change. |

## Changed files

```
packaging/selinux/install.sh         — adds marker copy to /usr/share/selinux/packages/
tincand/hfp_capability.py            — adds /var/lib/selinux/ store fallback
tests/tincand/test_hfp_capability.py — 67 lines: 2 new TestCheckModuleLoadedSelinuxStore cases
```

## Open findings (non-blocking)

- **LOW**: `iterdir()` in `_check_module_loaded()` lacks `OSError` catch — follow-up bead filed by reviewer.
- **STYLE**: ruff E501/I001/E402 in test file (line length, import order) — CI non-blocking.

## Verdict: PASS
