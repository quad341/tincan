# Release Gate: add ofono dep + HFP setup docs (tincan-kalmn)

**Deploy bead:** tincan-kalmn
**Source bead:** tincan-pqq3a (Amend tincan.spec: add oFono dependency for phone calls)
**Review bead:** tincan-xrfdr (PASS — tincan/reviewer, 2026-06-10)
**Branch:** fix/hfp-sco-selinux-policy
**Tip commit:** 225f3c1a2a34b1c9bdd409a9388a22b0e1191310
**PR:** https://github.com/quad341/tincan/pull/106
**Gate date:** 2026-06-10

## Commits evaluated (225f3c1 specifically)

| SHA | Message |
|-----|---------|
| 225f3c1 | feat(packaging): add ofono dependency for HFP phone calls (tincan-pqq3a) |

Files changed: `README.md` (+25), `packaging/tincan.spec` (+6). No Python changes.

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan/reviewer PASS verdict on commit 225f3c1 (tincan-xrfdr, 2026-06-10). "README.md + tincan.spec only (no Python). WP 0.5+ SPA-JSON config format correct. All 5 ACs from tincan-pqq3a met. 1682 existing tests green." Single-pass (gemini second-pass disabled). |
| 2 | Acceptance criteria met | **PASS** | See AC evaluation below. |
| 3 | Tests pass | **PASS** | 1695 passed, 6 skipped, 6 xfailed. Run: `pytest tests/ --ignore=tests/tincand/test_mcp_server.py` (mcp module missing: pre-existing infra gap unchanged since main). |
| 4 | No high-severity findings | **PASS** | No HIGH/CRITICAL findings reported by reviewer. Previous round-1 HIGH (missing %build compile) resolved in 22b962d; not reintroduced here. |
| 5 | Final branch is clean | **PASS** | `git status`: no uncommitted changes (untracked .claude/.codex/.gc/.gitkeep are deployer-worktree artifacts, not repo content). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge --no-commit --no-ff origin/main` succeeded: auto-merged `tincand/__main__.py`, no conflicts. Branch is 8 commits ahead, 1 behind main (82d8b05: GUI bugfix batch — disjoint from packaging/docs). |
| 7 | Single feature theme | **PASS** | Two files changed: `packaging/tincan.spec` (Requires: ofono) + `README.md` (HFP setup section). Single cohesive theme: add oFono runtime dependency declaration and document the required WirePlumber backend switch. |

**Overall verdict: PASS**

## Acceptance Criteria Evaluation (tincan-pqq3a)

**AC: Requires: ofono added to tincan.spec**
`packaging/tincan.spec` line 32: `Requires: ofono`. Comment explains the HFP-HF BlueZ5 plugin is compiled statically into ofonod — no plugin subpackage needed. Standard Fedora package (ofono-2.19-2.fc44). **PASS.**

**AC: README.md WirePlumber HFP backend switch documentation**
`README.md`: "Phone calls (HFP) — in progress" section added. Documents `sudo dnf install ofono`, `systemctl enable --now ofono`, and the WirePlumber 0.5+ SPA-JSON conf drop-in at `~/.config/wireplumber/wireplumber.conf.d/50-hfp-ofono.conf` with `bluez5.hfphsp-backend = "ofono"`. Start-order note included (oFono must start/restart after WirePlumber is in oFono mode). **PASS.**

**AC: OQ-1 method reference (spike tincan-xy2sb)**
Commit message and bead notes document method selection: "OQ-1 answered by spike tincan-xy2sb notes: oFono available as standard Fedora dnf package; HFP-HF BlueZ5 plugin compiled statically into ofonod." Reviewer accepted as "All 5 ACs met." **PASS.**

## Open Findings

None. This commit is docs + packaging only. No new ruff findings introduced (no Python changes).
