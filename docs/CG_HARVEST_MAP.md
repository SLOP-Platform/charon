---
doc: CG_HARVEST_MAP
version: 2
date: 2026-08-07
supersedes: 1
aligns_with:
  - CG_PLAN_v2.md §6 (this file is its companion; §6.1 is the harvest map it points to)
  - CG_MISSION.md (adopt before build, compose before extend, delete after adopt)
changelog:
  - "v2 (2026-08-07): correct the consolidation-warning rationale — closing #216 is about product_grades.py duplicating the third grade store, NOT about litellm.Router (D-019 ADOPTS the Router as substrate, it does not delete it); the v1 rationale was itself an instance of MANAGER_PLAYBOOK §8 failure-shape #1"
  - "v1 (2026-08-06): initial harvest map — companion to CG_PLAN_v2 §6 (published in PR #246 with the §8-misread rationale, corrected here)"
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
on `event_ledger` and close #216 — not because it touches `litellm.Router` (D-019 deletes the
bespoke `litellm_plane`, but adopts the Router as its substrate, so attaching to the Router is the
adoption path, not a delete target — this is §8 failure-shape #1), but because its
`product_grades.py` (+485) builds a third store duplicating the product-side grading
`event_ledger` already ships. Its `grade_order.py` (+692) is adoption glue and is kept. This is
the disposition executed as `GRADE-ORDER-LEDGER-REPOINT`.
