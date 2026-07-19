# ADR-0006 — Parallel independent units + work-decomposition (PERF-4)

Status: **Accepted** (2026-06-26; T1/PERF-4 implementation shipped in PR #9).
Date: 2026-06-26. Supersedes the PERF-4 deferral in PLAN-tier4 §6.
Builds on: ADR-0001 §5 (PERF-4), ADR-0004 D6 (thin DAG runner) / D8 (role
decomposition), PLAN-tier4 §3 + §6 (CONC-1..4 binding directives), ADR-0005
(gateway — the prerequisite that makes N parallel agents sustainable).

## Context

Today Charon runs **one unit** (one goal → one Ledger → one worktree → one lock),
sequentially, with role→cost-ranked-model routing + cross-vendor failover. PERF-4
(ADR-0001 §5) wants independent units dispatched **concurrently** across
backends/worktrees, bounded by budget and the fence. PLAN-tier4 deferred this as
*unsafe-as-drafted with no consumer*; two things changed: (a) the v0.2.0 gateway
now spreads load across providers, making N concurrent agents sustainable, and (b)
the operator will route agent-worker fleets through Charon — a real consumer.

The deferral left **four binding concurrency directives (CONC-1..4)** that any
implementation MUST carry. This ADR also folds in **work-decomposition** (ADR-0004
D8): turning one ticket into a set of units/roles via a thin DAG-of-stages runner
(D6), since that is what *produces* the independent units PERF-4 runs.

## Decisions

### D1 — A unit stays the isolation atom; parallelism is an orchestrator *above* `coordinator.run`
A unit = one task = one Ledger = one worktree = one lock (unchanged — INV-1). A new
`parallel.run_parallel(units, max_parallel, budget)` runs each unit's existing
`coordinator.run` loop in a **bounded worker pool**; the per-unit Ledger/lock/lkg
machinery is reused verbatim. No new isolation primitive inside the loop — we make
the *existing* atom safe to instantiate N times. Threads (not processes) for the
pool — the loop is I/O-bound (subprocess + HTTP); the real isolation boundary is
the worktree + the Mode-B container, not the OS process.

### D2 — Per-unit guard_dir nesting (CONC-1, binding)
Today `guard_dir = worktree.parent` and the sandbox is `state_dir/sandbox/<task_id>`,
so sibling units would share `state_dir/sandbox` as a guard parent — one unit's
escape scan could see a sibling's legitimate writes and false-positive (or worse,
miss its own). **Fix:** nest as `state_dir/sandbox/<task_id>/repo/`, making
`guard_dir = state_dir/sandbox/<task_id>/` **unique per unit**. The escape scan
(`snapshot_outside`/`detect_escape`) then only ever sees one unit's tree. This is a
small change to `_prepare_repo` (api.py) + the guard_dir derivation (coordinator.py).

### D3 — Atomic reserve-then-spend shared budget (CONC-2, binding); resolves Q-D4
A single cumulative `Budget` across concurrent units is a **read-modify-write race**:
two units both pass the cap check, then both spend → overspend. **Fix:** the shared
cap becomes an atomic **reserve-then-spend** counter under one lock — a unit reserves
its projected next-checkpoint cost before dispatch; on return it reconciles to actual.
A unit that cannot reserve stops at `budget` (the existing status). Per-unit sub-caps
are *also* supported (`max_cost_usd` split / unit), but the global cap is the safety
net and must be race-free. Never "N units each summing N ledgers."

### D4 — Per-unit backend + state isolation (CONC-3/4, binding)
- **CONC-3:** each unit gets its **own backend instance** — never share a long-lived
  ACP subprocess across units (sticky cwd/env/model would cross-contaminate). The
  pool constructs (or is handed a factory for) a fresh backend per unit.
- **CONC-4:** each unit already has a unique `task_id` → unique Ledger path + lock;
  the lock gains a **PID-liveness check** so a crashed-unit stale lock on a shared
  `.charon` is not silently reclaimed mid-flight. The Mode-B container remains the
  real isolation boundary; `run_parallel` refuses L2+ outside it (existing
  `Fence.assert_environment`, now asserted once per unit).

### D5 — Decomposition = thin DAG-of-stages over the same atom (D6/D8), NOT a new engine
A `decompose.py` turns a ticket into a typed **DAG of stages** (Triage→Plan→
Implement→Review→Validate→Close per D8) where **each stage is a dispatch unit with a
`role`** (role → cost-ranked pool, already built). Binding constraints from ADR-0004
R4/D6:
- **One Ledger per task**, never one per role/stage — roles/stages are **checkpoint
  metadata** appended to the Ledger (the Ledger IS the checkpointer; reject any
  external graph state — INV-1).
- The runner is native (~250–400 LOC, **zero deps**); reject LangGraph/LangSmith
  (egress + competing checkpointer).
- The L2 reviewer gate generalizes to D6's "interrupt before commit" — already the
  shape of `coordinator.run(..., reviewer=...)`.
- **Independent** units (no inter-unit data dependency) are what `run_parallel`
  fans out; true dependencies serialize as DAG edges. A general dependency
  scheduler beyond the fixed role DAG stays out of scope (PLAN-tier4 §3 non-goal).

### D6 — Smallest honest first cut (resolves Q-D2, over-build)
Ship in this order, each independently valuable and gate-green:
1. **`run_parallel` of N independent units at L0/L1** (propose-only / single-apply)
   with D2–D4 isolation + the shared race-free budget. No decomposition yet — the
   consumer (an agent-worker fleet) supplies the unit list. This is the high-value, lowest-
   blast-radius slice.
2. **`decompose.py` role-DAG** producing units for (1), sequential first.
3. **Parallel + L2 consensus** (decomposed Review stage gates Implement) — only once
   (1)+(2) are proven. **L3 + parallel stays behind explicit opt-in**
   (`CHARON_ALLOW_UNCONTAINED_AUTONOMY` already exists) — it is the highest-blast-
   radius surface and has no consumer demanding it yet.

## Invariants preserved
- INV-1: one Ledger per task, append-only, is the single source of truth (no
  per-role ledgers, no external graph checkpointer).
- Blast-radius: per-unit nested guard_dir; per-unit worktree; no shared worktree;
  escape scan per unit; container-gated L2+.
- Thinness: orchestrator above the existing loop; zero new deps; stdlib-only core.
- Honesty: aggregate budget is a hard race-free cap; L3+parallel disclosed +
  opt-in-gated.

## Risks / honesty register
- **Thread-safety of shared singletons.** Any module-global mutable state read by
  `coordinator.run` (e.g. a process-wide git env, a shared HTTP session) is a latent
  race. Mitigation: audit for globals before (1); the scrubbed env already pins
  `GIT_CONFIG_GLOBAL=/dev/null` (read-only → safe to share).
- **Budget reconciliation drift.** Reserve-vs-actual gap could under/over-count;
  mitigation: reconcile on every return, cap is conservative (reserve high).
- **Decomposition quality** is model-dependent; a bad Triage produces bad units.
  Mitigation: decomposition output is itself a checkpoint (auditable/replayable),
  and stage 1 ships *without* decomposition so the risky part is isolated.
- **Stale-lock reclaim** on a shared `.charon` (CONC-4) — PID-liveness check; the
  container is the real boundary.

## Reconciliation — adversarial self-review, 2026-06-26 (REVIEW-LOG)
Two HIGH clarifications are **binding on T1** (full reconciliation in REVIEW-LOG):
- **Two orthogonal parallelism axes (governs D1/D5).** *Within* one ticket the role
  DAG runs **sequentially** (stages depend on each other — the fixed pipeline, not a
  general dependency scheduler, which stays out of scope). *Across* independent
  tickets/units `run_parallel` fans out. **Parallelism is between units, never
  between stages of one unit.**
- **Budget guarantee is bounded-overshoot (sharpens D3).** The honest property is
  **≤ one in-flight checkpoint per active unit** over the cap — atomic
  check-claim-slot before dispatch + atomic add-actual after, under one lock, NEW
  dispatches halted once running total ≥ cap. NOT "never exceeds to the cent"; the
  `--max-cost-usd` help must say so.
- **Pre-code globals audit (sharpens the risk register):** per-unit/thread-safe L2
  reviewer; no module-level mutable session/counter shared by the loop; **no
  `os.chdir`** in the loop (cwd passed explicitly).

## Build sequence (ticket T1)
ADR (this doc) + adversarial self-review reconciled in REVIEW-LOG **before code**
(done — see REVIEW-LOG 2026-06-26). Then: D2 guard_dir nesting → D3 race-free budget
→ D4 backend/lock isolation → `run_parallel` (D6 step 1) → `decompose.py` (step 2) →
parallel+L2 (step 3). Each step keeps the gate green (pytest/ruff/mypy/boundary/
version). Proven-red tests per PLAN-tier4 §5 (parallel: N units complete; one unit's
failure/escape never corrupts another; aggregate cap bounds the set).
