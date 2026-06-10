# Release Gate: HFP call audio — SELinux policy, readiness detection, RPM auto-load

**Deploy bead:** tincan-5b40m (round 2; supersedes tincan-fm436)
**Source beads:** tincan-jekiq (SELinux policy + docs), tincan-r41sx (capability detection + RPM), tincan-arvln (tests), tincan-nwb41 (round-2 review)
**Branch:** fix/hfp-sco-selinux-policy
**Tip commit:** 22b962d293326f382c5bc0bca95574f536bfde5c
**PR:** https://github.com/quad341/tincan/pull/106
**Gate date:** 2026-06-10

## Commits on branch (vs origin/main)

| SHA | Message |
|-----|---------|
| 277c3b3 | fix(selinux): add HFP/SCO policy module for dbus-broker fd receive (tincan-jekiq) |
| a1e2ba4 | docs: SELinux HFP/SCO call-audio root-cause writeup (tincan-jekiq) |
| 675cdc9 | feat(calls): detect HFP call readiness + sudo-free RPM setup (tincan-r41sx) |
| 6c5f9e4 | chore: release gate PASS for hfp-sco-selinux-policy (round-1, superseded) |
| 1939380 | test(hfp): unit tests for hfp_capability probe and dbus_service integration (tincan-arvln) |
| 22b962d | fix(packaging): compile SELinux policy in %build so rpmbuild -ba succeeds |

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Round-1 review bead tincan-e03u5: PASS (tincan/reviewer, Claude Sonnet 4.6, 675cdc9). Round-2 review bead tincan-nwb41: PASS (tincan/reviewer, Claude Sonnet 4.6, 22b962d) — HIGH blocker from round-1 resolved. Single-pass (gemini second-pass disabled). |
| 2 | Acceptance criteria met | **PASS** | See below. |
| 3 | Tests pass | **PASS** | 1695 passed, 6 skipped, 6 xfailed (excluding test_mcp_server: pre-existing missing-dep infra failure unchanged since main). test_dbus_client_live: pre-existing D-Bus timeout excluded. ruff: 3 LOW style findings in test file (see below), no errors in production code paths. |
| 4 | No high-severity findings | **PASS** | Round-1 HIGH (missing %build compile of tincan_hfp_sco.pp) resolved in 22b962d. No remaining HIGH/CRITICAL open findings. |
| 5 | Final branch is clean | **PASS** | git status: no uncommitted changes. |
| 6 | Branch diverges cleanly from main | **PASS** | PR #106 state: OPEN, MERGEABLE. No conflicts with origin/main. |
| 7 | Single feature theme | **PASS** | All commits address one coupled feature: HFP/SCO call audio (SELinux policy + docs + capability detection + RPM packaging + unit tests). Components are mutually dependent — detection is useless without the loaded policy; policy is worthless without RPM auto-load. |

**Overall verdict: PASS**

## Acceptance Criteria Evaluation

**AC1: Unprivileged capability probe reports call-readiness accurately**
`tincand/hfp_capability.py` implements probe via `getenforce` (no root) + `semodule -l` (unprivileged on Fedora). Returns `CALLS_READY`, `CALLS_NEED_SELINUX_MODULE`, `SELINUX_NOT_ENFORCING`, `CALLS_STATUS_UNKNOWN`. Wired into `dbus_service.py` as `call_setup_ready` capability. 18 unit tests in `tests/tincand/test_hfp_capability.py` cover all branches (1939380, tincan-arvln). Round-2 reviewer-verified: "correct unprivileged probe; sound error handling/timeouts; 18 unit tests cover all branches." **PASS.**

**AC2: Documented setup path enables calls without manual semodule**
`packaging/tincan.spec`: `BuildRequires: checkpolicy` + `policycoreutils`; `checkmodule` + `semodule_package` in `%build` compile `tincan_hfp_sco.te` → `.pp` at build time; `%install` copies `.pp` to `/usr/share/selinux/packages/`; `%post` runs `semodule -i` (guarded by `selinuxenabled`); `%postun` removes module. RPM install automatically loads the module — no user sudo needed. `docs/hfp-sco-selinux-rootcause.md` documents root cause. Round-2 reviewer-verified: "HIGH blocker resolved; BuildRequires correct; standard Fedora pattern." **PASS.**

## Open Findings (all LOW — non-blocking)

**LOW-1 (round-1, status: RESOLVED in 22b962d):** `packaging/selinux/.gitignore` excluded `*.pp`; `%install` referenced uncompiled binary. Fixed by adding `checkmodule` + `semodule_package` to `%build` and `BuildRequires: checkpolicy policycoreutils`. ✓ Closed.

**LOW-2:** `hfp_capability.py:50-53`: file-presence fallback for `semodule -l` unavailability returns `CALLS_READY` when .pp file exists but module may not be loaded. No security impact; `semodule -l` works unprivileged on all Fedora targets.

**LOW-3:** `packaging/tincan.spec` `%postun` removes SELinux module on upgrade and uninstall (should check `$1 -eq 0`). Creates brief module-absent window during upgrades. Follow-up packaging fix.

**LOW-4 (new):** `tests/tincand/test_hfp_capability.py` has 3 ruff style issues (E501 ×2: lines 7/140 exceed 99 chars; I001: unsorted imports). Test-only, no production impact.
