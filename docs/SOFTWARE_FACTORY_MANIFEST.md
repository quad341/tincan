# Software Factory Manifest: Tincan

## Factory Overview

Tincan. This factory runs a 6-agent sequential pipeline (Planner → Architect →
Designer → Coder → Reviewer → Deployer) with two human gates, building a Linux
desktop iPhone phone-companion over standard Bluetooth profiles. Tech stack: a
headless Python 3.14 bridge daemon (`tincand`) owning BlueZ/obexd (and later oFono +
PipeWire) over D-Bus, with a PySide6 GUI client and a future `tincan-mcp` MCP client
consuming the same internal API; SMS via MAP, the new-message trigger via ANCS,
contacts via PBAP, calls via HFP in a later phase.

## Pipeline Sequence

1. **Planner**
   - Reads: feature request + PROJECT_MANIFEST.md
   - Writes: work-packages/tincan.md

2. **Architect**
   - Reads: Planner work package + Tech Stack section
   - Writes: docs/adr/NNNN-tincan.md

3. **Designer**
   - Reads: Architect ADR + Domain Model section
   - Writes: design/tincan-spec.md

4. **Coder**
   - Reads: Designer spec + Conventions section
   - Writes: src/ on feature branch tincan-[feature]

5. **Reviewer**
   - Reads: code diff + Review Standards section
   - Writes: review-reports/tincan-review.md

6. **Deployer**
   - Reads: Reviewer report + Release Criteria section
   - Writes: release-gates/tincan-gate.md

## Human Gates

- **Gate 1 — After Architect:** Human approves the ADR before the Designer runs.
- **Gate 2 — After Reviewer:** Human approves the review report before the Deployer runs.

## Per-Agent System Prompt Seeds

**Planner:** "You are the Planner for Tincan. You decompose feature requests (e.g.
ANCS-triggered inbound Message handling) into work packages using the Domain Model
(Message, Conversation, Call, Notification, Contact) and Tech Stack in
PROJECT_MANIFEST.md."

**Architect:** "You are the Architect for Tincan. You write architectural decision
records — especially the load-bearing daemon/client API boundary that carries
Message and Notification events — using the Tech Stack and Constraints in
PROJECT_MANIFEST.md."

**Designer:** "You are the Designer for Tincan. You write interaction and data specs
for how Conversation, Message, Call, and Notification surfaces behave, using the
Domain Model and Conventions in PROJECT_MANIFEST.md, keeping all iOS quirks absorbed
in the daemon."

**Coder:** "You are the Coder for Tincan. You implement features against the tincand
domain model (Message, Conversation, Contact, …) following the Conventions and Task
Inputs in PROJECT_MANIFEST.md."

**Reviewer:** "You are the Reviewer for Tincan. You enforce the Review Standards in
PROJECT_MANIFEST.md against every code diff — including that no raw profile data leaks
past tincand into clients and that Notification/Message normalization stays in the
daemon."

**Deployer:** "You are the Deployer for Tincan. You gate releases against the Release
Criteria in PROJECT_MANIFEST.md, confirming the phase definition-of-done (e.g. holding
a real SMS Conversation end-to-end) before shipping."

## Quality Gates

- **Stage 1 (Planner) passes when:** the work package names the target capability, the
  affected domain entities (Message / Conversation / Call / Notification / Contact),
  and which roadmap phase + risks (R1–R7) it touches.
- **Stage 2 (Architect) passes when:** the ADR respects the Constraints — standard
  profiles only, no iMessage RE in core, no hardcoded iOS-version assumptions — and
  preserves the daemon/client API boundary. *(Gate 1: human approves the ADR.)*
- **Stage 3 (Designer) passes when:** the spec defines domain types and the event
  contract, and specifies that iOS quirks (sent-folder mislabel, group-text
  attribution, "Show Notifications" requirement) are absorbed in the daemon, never the UI.
- **Stage 4 (Coder) passes when:** implementation matches the spec's domain types and
  event contract; no raw profile data leaks past tincand; capability detection +
  graceful degradation present; passes `ruff` + `black` with type hints on the public API.
- **Stage 5 (Reviewer) passes when:** spec-compliance, style, and security standards
  are met — no Apple-ID-risk paths, no sandbox-violating data access, recording (phase 5)
  opt-in — with findings graded on the Low/Medium/High severity scale.
  *(Gate 2: human approves the review report.)*
- **Stage 6 (Deployer) passes when:** all Required release criteria PASS — phase
  definition-of-done met, tests green on a clean checkout (daemon tests run without a
  phone), lint/format clean, no version assumptions added, LIMITATIONS.md updated if
  platform capability changed, onboarding still surfaces the "Show Notifications" + reconnect handling.

## Orchestrator Configuration

- Coordination pattern: sequential pipeline with handoffs
- Failure handling: stop pipeline at failing agent, surface error to human
- Retry policy: no automatic retries (human decides whether to re-run)
- Branch strategy: feature branch per work item, merge after Deployer gate passes

## Conventions Reference

- **File naming:** `snake_case.py` modules; one Bluetooth profile per module under `tincand/bluetooth/`
- **Test files:** `test_*.py` under `tests/`, mirroring package layout; mark on-device tests that need a paired iPhone
- **API routes:** D-Bus interface names `<reverse.dns.domain>.Tincan.*` (placeholder — pick a real reverse-DNS namespace when scaffolding) (or local-socket JSON-RPC methods) — decided in M1.1; methods named after domain actions (`SendMessage`, `ListConversations`), signals for the event stream (`MessageReceived`, `CallStateChanged`)
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `spike:`)
- **Branches:** feature branch per work item — `tincan-<feature>`
