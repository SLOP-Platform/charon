---
description: Manager runs substantive work in sub-sessions to keep the primary session lean for operator communication
metadata: 
name: manager-delegates-to-subsessions
node_type: memory
originSessionId: ebcf9a1e-605b-4f25-ae5c-e6f7580be989
type: feedback
tags: [gate, manager, session, subsession]
last_referenced: 2026-07-13
---
When sane and reasonable, the Charon MANAGER session **delegates its own substantive work to
sub-sessions** (Agent subagents) — investigation, audits, analysis, research, contained
implementation, drafting — keeping the PRIMARY session clear for operator communication and
decisions. The manager still **owns and reviews the result** in the primary session;
sub-sessions are tools, not unsupervised workers.

**Keep it in the PRIMARY session ONLY when it must/should be there:**
- gating DECISIONS + merges (the manager's core judgment, needs my context + operator dialogue)
- pushes (gated `land-push.sh` / the AUTONOMOUS lever)
- direct operator conversation + decisions
- quick inline state checks (status.sh/board.sh) whose result I need immediately to respond
- tightly-sequenced state mutations where handoff overhead / race risk isn't worth it

**Why:** keeps the manager responsive and stops its context filling with implementation detail.

**Run delegated sub-sessions in the BACKGROUND (`run_in_background: true`) by default.** A
FOREGROUND agent or a long `gh ... --watch` blocks the primary and makes the manager appear
unresponsive — the exact failure the operator called out 2026-06-27. Backgrounding does NOT
slow the agent or reduce concurrency; it only keeps the operator able to reach me mid-run. The
primary should never sit blocked on a multi-minute CI watch or review — hand it to a background
watcher that reports back, then I do the quick merge in primary. Default bias: if it takes more
than ~a minute, background it.

**Distinct from [[manager-never-spawns-droids]]:** that rule is about FLEET BUILD-DROIDS that
PR the product — still the operator's job to launch, never the manager's. THIS is the manager
spawning its OWN helpers for its OWN work. Extends the read-only-reviewer rule (manager may
spawn read-only analysis); a delegated implementation sub-session may mutate files, but the
manager reviews/owns the result and the operator stays in the loop.
