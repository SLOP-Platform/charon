# WCI-MVP — WCI-1 static reconciler + WCI-2 depth pre-sort

The adversarial-blessed MVP of Work-Composition Intelligence. **Two pieces ONLY** — WCI-1 and
WCI-2. Design source of truth: `docs/adr/0015-work-composition-intelligence.md` (landed first;
this ticket `depends_on: ADR-0015` precisely so you build against a SIGNED design, never an
unsigned one). The fuller reshape rationale lives in the build rig's `DSGN-WCI-reshape.md` —
read for context, but the ADR is the contract.

## Scope (exactly this — nothing more)

**WCI-1 — static reconciler** (`src/charon/engine/reconcile.py::reconcile_static`):
Consolidate / re-port the EXISTING redundancy / contradiction / overlap checks that today live
across `validate_board.sh`, `board.claimable`, and `intake.analyze` into ONE deterministic
function, wired as a **pre-drain preflight**. This is a re-port (per R8 / M1) — **no new
intelligence**, no new heuristics. Same invariants, one home, deterministic.

**WCI-2 — critical-path depth pre-sort** (in `board.claimable_units()` ordering):
Pre-sort the READY set by critical-path depth so the longest dependency chain drains first, with
`id` kept as the FINAL injective tiebreak. The claimability / serialization **rule is untouched**
(per R5 / B2) — this is a pre-sort of an already-correct ready set, never a change to what is
claimable.

## Hard EXCLUSIONS (do NOT build these — they are WCI-FOLLOWON)
- **WCI-4** — the `merge_after` edge type. Do NOT introduce the `merge_after` schema field.
- **WCI-6** — auto-slice / semantic-independence (§5.1) proof. Parked behind §5.1 + the
  ADR-0008 Phase-2 conflict-rate tripwire.
- **WCI-5** — the semantic advisory spike (separately gated).

## Hard PRODUCT constraint
WCI is **opt-in-orchestrator-only** and **advisory / override for users**. It must NEVER be
imposed on a gateway-only or single-task fresh install. A fresh `pipx install` user who only
wants the failover gateway must see ZERO WCI behaviour unless they opt into orchestration.
Charon ships standalone (stdlib core); WCI adds no required dependency.

## Notes on owns
`owns:` is provisional but authoritative for you: `reconcile.py` is the design-named NEW module
(reshape §6); `board.py` carries the WCI-2 pre-sort; `scheduler.py` is included for the wiring;
`tests/test_reconcile.py` is your test home. New behaviour ships with its test in the same commit.

## CONSTRAINTS
Own ONLY the files in your board `owns:` line:
`src/charon/engine/reconcile.py`, `src/charon/engine/scheduler.py`, `src/charon/engine/board.py`,
`tests/test_reconcile.py` (plus your own `docs/review-log/WCI.md` fragment). Create/edit nothing
else. Privileged core stays stdlib-only; keep the gate GREEN on every commit. If the work
genuinely needs a file outside `owns:`, STOP (`release.sh`) and report — do not create it.
