---
description: "The version actually used last few sessions = fleet rig (no mailbox, tabs+timer+retries, WSL bash launch); exact files to ground/reimplement it"
metadata: 
name: fleet-rig-grounding-docs
node_type: memory
originSessionId: 8f3bca2a-1eeb-45ff-8265-fbde61400eb5
type: reference
tags: [build-rig, fleet]
last_referenced: 2026-07-13
---
The droid Team-mode version used in the last few sessions is the **fleet rig** at `/build-rig/fleet/` — NOT the mediastack mailbox harness. Distinguishing traits: NO mailbox, ephemeral per-ticket tabs each with a TIMER + RETRY count, launched by a bash command from WSL (not from inside a Claude Code prompt).

**Launcher (implementation):** `/build-rig/fleet/fleet-droid.sh` — `fleet-droid.sh <tier> [--wait <min>] [--retries <n>]`; one command per tab. `--wait`=sleep between empty claim checks (default 3 min), `--retries`=max empty checks before stand-down (default 6). Live command: `fleet-droid.sh <tier> --wait 3 --retries 10` (see [[droid-launch-with-wait-retry-flags]]).

**Grounding docs (all in same dir):**
- `WORKFLOW.md` — AUTHORITATIVE end-to-end spec (state machine, droid job, manager job, hard rules, WCI)
- `JOIN-PROMPT.md` — per-session droid rules (worktree isolation, ownership, gate-on-commit, no PR push/merge)
- `README.md` — operator overview + launch model
- `START-SESSION.md` — manager/operator role split + gating loop
- `RUNBOOK.md` — launch sequence, --wait/--retries, concurrency
- `HANDOFF.md` — live state + exact launch command
- `OPTIMIZATION-PASS.md` — latest backlog/wave analysis

**Minimal set to fully ground + reimplement:** `fleet-droid.sh` + `WORKFLOW.md` + `JOIN-PROMPT.md` + `RUNBOOK.md`.

Self-contained: does NOT depend on the droid-harness archive docs. It is a trimmed adaptation of the audited mediastack harness with two deliberate changes: propose-default landing (PR, never auto-merge) and ephemeral-per-ticket (one session per ticket, launcher relaunches — no warden/reaper). See [[droid-robot-mode-harness]], [[charon-build-via-fleet]], [[fleet-rig-absolute-path]].
