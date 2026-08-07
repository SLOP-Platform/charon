---
doc: CG_HARVEST_MAP
version: 1
date: 2026-08-06
supersedes: none — initial version
aligns_with:
  - CG_PLAN_v2.md §6 (this file is its companion; §6.1 is the harvest map it points to)
  - CG_MISSION.md (adopt before build, compose before extend, delete after adopt)
changelog:
  - v1 (2026-08-06) — initial version. Body unchanged from the authoritative
    2026-08-05 branch-and-code audit; this revision adds version frontmatter only.
---
# CG Harvest Map

Companion to `CG_PLAN_v2.md` §6. **Before building any Block-B item, check here first — most gaps
are unwired, not absent.** A branch-and-code audit found the ledger / grading / cost spine was
already designed and partly built several times, scattered and unwired. This maps what exists to
the plan so nothing gets rebuilt from scratch.

**Rule: harvest the *mechanism*, re-decide the *decisions*.** Existing code is a source to reuse,
never an authority to obey — much of it embodies old-lens (dual-identity gateway) assumptions.
Reuse the working machinery; re-validate every decision it encodes against the current thin-glue
mission (`CG_MISSION.md`).

| Plan item | Already exists as | Action |
|---|---|---|
| §3 cost record | `ledger.py` `Checkpoint.usage.cost_usd` (authoritative spend) | **extend** with `model` + `fingerprint` |
| §1/§2 cost-per-task | ADR on branch `feat/cost-per-task-replay` — `cost_per_accepted_task(work_class, tier, model, provider)`, provider-as-identity, fail-on-revert | design done — **align fields** |
| §19 benchmark seed | `grades_import.py` (master) — decaying prior, replaced by real outcomes | **wire**, don't rebuild |
| §16 grade store | `CapabilityMatrix` (master) — present, unwired | **wire** |
| §16 / §7b anti-gaming grader | `feat/bench-oob-grading` (PR #193) — out-of-band grader daemon; answer keys out of the subject's reach | **harvest** for the grading unit |
| §1 cost cross-check | `metering.py` (master) — litellm verify-only | **reuse** |
| §4b difficulty routing | `decompose_effort` scores difficulty, then drops it before routing | **wire** the existing signal into tier selection |

**Consolidation warning — three grade stores exist or are proposed:** `grades.py`, the merged
`event_ledger.py`, and `product_grades.py` proposed by #216. The plan names **one**. Consolidate
on `event_ledger`; close #216 (it builds a third *and* attaches to `litellm.Router`, which D-019
deletes).
