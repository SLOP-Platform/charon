---
description: "Q1 RESOLVED (2026-07-09) = A — out-of-band bench grader runs as a dedicated bench-grader unix user on the LOCAL WSL box, answer-keys mode 0700"
metadata: 
name: charon-bench-grader-substrate
node_type: memory
originSessionId: 02f0da30-0dc8-45ce-acbc-4cded96858db
type: project
tags: [benchmark, charon]
last_referenced: 2026-07-13
---
DECISION (operator, 2026-07-09) — Q1 bench-grader substrate = **A**: a dedicated `bench-grader` unix user on the **LOCAL WSL box** (where bench.sh + graders/ live), NOT self-hosted-runner (self-hosted-runner runs only the gateway; the operator's earlier `useradd bench-grader` on self-hosted-runner was the WRONG box — harmless/unused).

**What A means for #26 (OOB-grading) / #25 (reds-replay):**
- Answer-key tree (graders/*.py + baseline fixtures + #25 check_cmds) owned by `bench-grader` at mode **0700** so the graded model's user cannot `cat` it.
- Grader invoked AS that user (e.g. sudo -u bench-grader). Arch: grader-daemon + drop-spool (agent write-only on req/, no read on graders/ or res/); daemon snapshots the worktree read-only, runs grader/check_cmd from the 0700 tree, appends the ledger row. bench.sh keeps DRIVING the agent but LOSES its grading powers.
- 3 invariants: (1) answer key out of subject's reach; (2) grading NOT self-driven (separate scorer); (3) no self-report (scorer is sole ledger writer; agent's pasted score discarded).
- Scope to REDS-REPLAY grading, NOT synthetic S0-S6 (smoke-only, demoted). RIG-ONLY: daemon/spool/keys never referenced by product code ([[product-vs-build-rig-boundary]]).

**Still gated for BUILD:** proper #26/#25 design (from scratch/pivot-implementation-plan.md §3+§Q1+§8) + build-after #20 (BENCH-PROVISIONAL-SCORING, still PARKED — decide unpark-or-drop). BENCH-OOB-GRADING ticket stays `parked: true` until design reviewed + #20 resolved. See [[benchmark-not-a-valid-ranker]].
