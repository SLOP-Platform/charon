# ADR-0015 — Work-Composition Intelligence (reconcile + ordering + advisory layer)

Status: **Proposed** (2026-06-29). Builds on ADR-0010 (native substrate:
`engine/board`, `claim`, `scheduler`), ADR-0008 / 0011 (intake → ticket-plan;
Phase 2 auto-decompose deferred), ADR-0006 (PERF-4 parallel units), ADR-0007
(safe-landing-first; D7 warm pool; D8 liveness). Positions WCI as a **composition
layer** above the existing substrate, not a new engine. Touches the register at
**D020** (static reconcile), **D021** (depth pre-sort), **D022** (on-merge
incremental reconcile hook).

## Context

Charon already runs work concurrently via `PERF-4 run_parallel` + `scheduler.drain`
over `board.claimable`. What it does **not** do is compose work intelligently — it
trusts whatever unit set it is handed. The operator's core direction is to
productize the fleet manager's scheduling doctrine so the engine:

1. Refuses to schedule redundant / duplicate / contradictory / obsoleted work
2. Extracts the maximum safe concurrency the dependency structure allows
3. Chunks dependent work so the truly-dependent sliver is the only thing that blocks

Live evidence the gap is real: even careful manual ticketing created TIER7B
`depends_on HARD1` — a **merge-order** relation mislabeled as a **build
dependency** — exactly the class of mistake the reconciler/chunker should catch.

## Decision

### Three pillars

**Pillar 1 — No redundant / contradictory work (the Reconciler).**
- **Static half** (already exists — a re-port): transitive-dep validity,
  owns-collision, duplicate-branch, orphan-marker, overlap→serialize. Consolidates
  `validate_board.sh` + `board.claimable` + `intake.analyze` into one reusable
  engine function. Deterministic.
- **Semantic half** (genuinely new): dedup / obsolescence / contradiction judgment
  via an LLM. **Advisory only, off the hot path** — emits annotations, never
  mutates `claimable`.

**Pillar 2 — Maximize safe concurrency (Scheduler ordering).**
WCI adds a **critical-path depth pre-sort** to `claimable_units()` ordering only,
with `id` as the final tiebreak. `board.claimable` is **untouched** — the rule
stays injective and deadlock-free. Depth reorders which ready unit a free worker
picks first, never *whether* a unit is claimable.

**Pillar 3 — Dependency-minimizing chunking (gated).**
Deferred behind ADR-0008 Phase 2 (conflict-rate tripwire). WCI's in-scope
contribution: (a) distinguish merge-order from build-dependency edges in intake,
(b) define the §5.1 semantic-independence proof contract. Actual auto-slicing
stays parked.

### R1–R9 resolutions

| ID | Resolution |
|----|-----------|
| **R1** | WCI is a composition layer, not a new engine. Workers remain warm-pool ACP agents driven by `AgentBackend` + `parallel.py` ThreadPool. No `WorkerBackend` port. |
| **R2** | One deterministic `reconcile_static` function; LLM strictly advisory. Semantic pass emits annotations/flags on units, never a mutation of `claimable`. Board stays diffable/replayable. |
| **R3** | Agnostic by construction. Semantic judgment is performed by an agent the engine launches, pointed at Charon's own gateway requesting a tier id. Swap agent/provider freely. |
| **R4** | Product-clean. WCI ships in `src/charon/engine/` only, behind the anti-dilution boundary test. No `tracking.db`, no fleet/, no SLOP. |
| **R5** | Concurrency order is a pre-sort; `claimable` rule untouched. Depth sort key is a **pure deterministic function of board graph state** — no clock/RNG/arrival-order. `id` remains the final tiebreak. Depth is load-bearing on per-drain launch under the sync capacity cap. |
| **R6** | On-merge reconcile hooks `scheduler._advance` (main thread, all board mutations serialized), not `land.py` (layer violation). Incremental — only intersecting units. |
| **R7** | Path-disjointness is necessary, not sufficient. Conservative-serialize default. Any future concurrent split must pass the §5.1 proof. Label flip (`depends_on`→`merge_after`) is never a downgrade — the split is invented by the proof, never by the label. |
| **R8** | Honest MVP scope: Pillar 1 static reconciler (~70% consolidation) + Pillar 2 pre-sort. The only genuinely new intelligence is the semantic dedup pass + gated slice. |
| **R9** | Injection hardening for semantic pass: fenced unit, input wrapped as data, structured advisory-only verdict, schema-validated, non-parsed input. |

### Reshape-fixes (F1–F3)

| Fix | Severity | Resolution |
|-----|----------|-----------|
| **F1** | blocker | `merge_after` may relax the dep-gate ONLY via a positive §5.1 independence certificate or overlapping-owns (no-op). The label itself is never a certificate. Label flip alone never downgrades a build-dep to concurrent. |
| **F2** | medium | Depth sort key MUST be a pure deterministic function of board graph state. Depth is load-bearing on per-drain launch under the sync capacity cap. |
| **F3** | trivial | Bogus `board.py:390` anchor removed; `_advance` lives only at `scheduler.py:390`. |

### Explicit out-of-scope / MVP exclusion

- **WCI-4** (`merge_after` edge): **HELD** until §5.1 is approved (operator decision
  2026-06-27). Label AND its concurrency payoff ship together with §5.1.
- **WCI-5** (semantic advisory spike): deferred beyond MVP.
- **WCI-6** (auto-slice / §5.1 proof): **PARKED** behind §5.1 + ADR-0008 Phase-2
  conflict-rate tripwire.
- Auto-decompose execution, auto-land, AIMD adaptive capacity: gated, not unlocked
  by WCI.

### Product constraint

WCI is **opt-in-orchestrator-only** and **advisory/override for users**. It is
NEVER imposed on gateway-only / single-task fresh installs. Charon ships standalone;
WCI is an orchestrator opt-in, not a default gate.

### MVP build tickets

- **WCI-1** — `engine/reconcile.py::reconcile_static`: consolidate
  `validate_board.sh` + `board.claimable` + `intake.analyze` into one deterministic
  function; wire as a pre-drain preflight.
- **WCI-2** — depth pre-sort in `claimable_units()` ordering with `id` final
  tiebreak; behind a measurement gate.
- **WCI-3** — on-merge incremental reconcile hook at `scheduler._advance`.

## Consequences

- The static reconcile function is ~70% a consolidation of existing checks — its
  new value is continuous (pre-drain + on-merge) execution from one reusable
  function.
- The depth pre-sort is small (rule untouched; reorder only) but load-bearing:
  under the sync per-tier capacity cap, depth determines per-drain launch
  composition.
- Pillar 3 concurrency payoff is gated behind §5.1 — until that proof exists,
  `merge_after` is observationally identical to `depends_on` for disjoint-owns
  pairs.
- The semantic advisory pass is the genuinely-new piece; gate it hardest (fenced
  unit, structured verdict, advisory only).
- WCI is opt-in-orchestrator-only. No overhead for gateway-only / single-task
  installs.

## References

- ADR-0010 (native engine substrate)
- ADR-0008 / ADR-0011 (intake → ticket-plan)
- ADR-0006 (PERF-4 parallel units)
- ADR-0007 (safe-landing-first)
- `DSGN-WCI-reshape.md` (source of truth for R1–R9, F1–F3, out-of-scope)
