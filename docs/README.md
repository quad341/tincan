# Tincan

A Linux desktop "phone companion" for the iPhone — like Microsoft Phone Link,
but open and for Linux. Tincan connects to an iPhone over **standard Bluetooth
profiles** (no jailbreak, no Apple-ID risk) and lets you **send/receive SMS,
place/answer calls, see notifications, and browse contacts** from a desktop GUI.

It is architected so a future **"secretary" AI agent** (Claude) can drive the
same capabilities programmatically — read/send messages, transcribe calls, and
eventually speak on a call.

The name: a tin-can telephone — a humble, honest string between two endpoints.

## Status

**Scoping complete; pre-implementation.** No code yet. This `docs/` folder
holds the plan and the research it's built on.

- Reference target: **iPhone 15 Pro, iOS 26.5** (treated as one data point, not a
  spec — see version-resilience principle in the plan).
- Reference host: **Fedora 44**, BlueZ 5.86, PipeWire 1.6.4, Python 3.14.
- Chosen v1: **SMS first**. Stack: **Python + Qt (PySide6)**.

## Documents

| File | What's in it |
|------|--------------|
| [PLAN.md](PLAN.md) | The plan: vision, design principles, architecture, phased milestones, risk register, open questions, prerequisites. **Start here.** |
| [PROTOCOLS.md](PROTOCOLS.md) | Technical reference for the Bluetooth profiles we depend on (ANCS, MAP, HFP, PBAP) and how iOS actually behaves, with sources. |
| [LIMITATIONS.md](LIMITATIONS.md) | The honest "what this can and cannot do" list. Read before promising anyone anything. |

## The one-line existence proof

Microsoft Phone Link for iPhone (shipped April 2023, Windows 11) already does
calls + SMS + notifications + contacts over **Bluetooth alone**. Nobody has
assembled the same stack on Linux. That gap is what Tincan fills.
