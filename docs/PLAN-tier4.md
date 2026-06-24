# Charon — Tier 4 build plan (pre-review draft)

> Implements ADR-0001 §9 Tier 4: **autonomy L2/L3 + parallelism (PERF-4)**, and
> folds in the **consensus gate** that Tier 3's review moved here to be paired
> with its only consumer, L2 (REVIEW-LOG 2026-06-24). Final tier; builds on the
> green Tier-1/2/3 core. Pure Charon core, consumer-independent.

## 0. Scope contract

Three things, in dependency order:

1. **Consensus gate + L2 (apply-with-consensus).** Wire the `Reviewer` port into
   the loop so that at **L2** a unit is applied only if a configured reviewer
   passes — carrying the exact security directives the Tier-3 review attached.
2. **L3 (full-auto within the fence).** Apply without requiring consensus, still
   inside the fence (escape scan, scrubbed env, default-deny destructive ops).
3. **Parallel independent units (PERF-4).** Dispatch independent units (separate
   ledgers/worktrees) concurrently, bounded by budget and the fence; serialize
   only true dependencies.

## 1. Consensus gate + L2 — carrying the Tier-3 directives

The Tier-3 adversarial review (REVIEW-LOG 2026-06-24) pre-specified this. The
gate is the thin part Charon owns (predicate + breaker); the reviewer is
integrated, not built (ADR-0001 §2). Directives, all binding:

- **D-GATE-1 (gate before lkg):** the gate verdict is checked **before**
  `advance_lkg` / before the unit is reported `complete` — lkg must never advance
  past *unreviewed* work (INV-2/INV-3). It is a third completion condition
  alongside `remaining == ∅` and `outcome.commit`.
- **D-GATE-2 (L2-only):** the gate binds at **L2+ only**. L0/L1 semantics are
  unchanged (no surprise `blocked-consensus` at L1). With no reviewer configured,
  the gate is a no-op (Tier-1/2/3 behaviour preserved).
- **D-GATE-3 (no conflation):** the reviewer verdict is **not** mapped onto the
  fence's `consensus` boolean as if it were operator/human approval. The fence's
  `consensus` parameter stays "an explicit external approval signal"; the
  reviewer is a *separate* `reviewer_passed` gate that L2 also requires. At L2:
  apply iff `fence.authorize(APPLY_REVERSIBLE, consensus=...)` **and**
  `reviewer_passed`.
- **D-GATE-4 (fail-closed, honest):** reviewer errors/unavailable ⇒ gate verdict
  is cannot-pass (do not apply, do not falsely complete). An explicit operator
  override degrades to **L1 (apply-reversible), never to fail-open**, and is
  recorded loudly in the ledger.
- **D-GATE-5 (breaker scoped honestly):** the breaker bounds reviewer spam/latency
  **within a run**; it is per-process and is **not** claimed as cross-run
  protection unless persisted to the ledger. Trips on exceptions/timeouts only —
  a correct "no" is not an error.
- **D-GATE-6 (not a security boundary):** README/honesty must state plainly that
  an LLM reviewer can be wrong or gamed; consensus is *additive quality
  insurance*, not a security audit.

MockReviewer adapter (PASS / BLOCK / ERROR / FLAKY) is the proof vehicle; the
non-tautological tests assert *cross-cutting* properties: at L2, BLOCK ⇒ not
applied (lkg unchanged); ERROR ⇒ fail-closed; a passing acceptance + BLOCK is
`blocked-consensus` not `complete`; with no reviewer the loop is unchanged.

## 2. L3 — full-auto within the fence

L3 applies without requiring consensus (`fence.authorize` already returns True at
L3). Still fully fenced: scrubbed env, post-run escape scan, destructive ops
(DELETE/DEPLOY) default-denied at every level. L3 is *not* "no fence" — it is "no
consensus gate." The only real boundary for a live agent remains the Mode-B
container (INV-B4); L3 outside the container is honestly disclosed as dangerous.

## 3. Parallel independent units (PERF-4) — the significant new fork

ADR-0001 §5 PERF-4: dispatch independent units concurrently across
backends/worktrees, bounded by budget and the fence; serialize only true
dependencies. Proposed thin design:

- A unit = one task = one ledger = one worktree (already true). "Independent"
  units have **separate ledgers** — so the per-task lock (BR-1) already isolates
  them; there is no shared mutable ledger state across units.
- A `run_parallel(units, ...)` orchestrator above `coordinator.run`: a bounded
  worker pool (`max_parallel`) runs each unit's coordinator loop concurrently;
  each unit keeps its own lock, worktree, lkg. Aggregate cost is bounded by the
  shared `Budget` across units (cumulative, derived from the union of ledgers).
- **No shared worktree** between concurrent units (blast-radius isolation). The
  fence's escape scan runs per-unit.
- Dependencies (unit B needs unit A's output) are **out of scope** for Tier 4 —
  Charon runs *independent* units in parallel; a dependency DAG/scheduler is a
  later concern (or the operator's). Stated as a non-goal.

## 4. Decisions for adversarial review

- **D1 — parallelism safety.** Is "separate ledger + separate worktree + existing
  per-task lock" actually sufficient isolation for concurrent privileged loops,
  or do concurrent agents share dangerous global state (git global config — note
  the scrubbed env already sets `GIT_CONFIG_GLOBAL=/dev/null`; the host FS;
  process env; the shared `.charon` parent)? Where does concurrency reopen a
  blast-radius or ledger-corruption class the single-threaded loop closed?
- **D2 — is L3 + parallelism over-built (sunset/thinness)?** L3 unattended and
  parallel privileged loops are the highest-blast-radius, most
  frontier-absorbable surface. Should Tier 4 ship them now (no production
  consumer), or ship L2+consensus (concrete, gated, valuable) and keep L3/parallel
  minimal or behind explicit opt-in? What is the smallest honest Tier 4?
- **D3 — consensus gate residual holes.** Do the six D-GATE directives fully
  close the Tier-3 findings, or does the implementation reopen one (e.g., the
  L0-propose-only rollback path bypassing the gate, the handoff path, a
  multi-checkpoint run where an earlier checkpoint already advanced lkg)?
- **D4 — budget across parallel units.** A single cumulative `Budget` across
  concurrently-running units is a shared counter read from N ledgers — is that a
  race (two units both pass the cap check, then both spend)? Is per-unit budget
  safer than a shared cap?

## 5. Tests (proven-red)

- L2: reviewer BLOCK ⇒ not applied, lkg unchanged, `blocked-consensus`; PASS ⇒
  applied/complete. ERROR ⇒ fail-closed. No reviewer ⇒ unchanged.
- L3: applies without a reviewer; still rejects an escape (fence intact);
  DELETE/DEPLOY still denied.
- Parallel: N independent units complete concurrently; each keeps its own lkg; a
  failure/escape in one does not corrupt another; aggregate budget cap bounds the
  set.
- Honesty/negative: reviewer gaming is documented; L3-outside-container disclosed.

## 6. Reconciled scope (post-review, 2026-06-24 — REVIEW-LOG)

Three independent reviewers (consensus correctness · concurrency safety ·
premise/thinness) converged. **Built:** the L2 consensus gate + container
enforcement. **Deferred:** parallelism (proved unsafe-as-drafted, no consumer).

**Built (Tier 4):**
1. **L2 consensus gate.** `coordinator.run(..., reviewer=...)`: at completion,
   before `advance_lkg` (D-GATE-1), at L2+ only (D-GATE-2), consult the reviewer.
   The verdict is supplied as the fence's consensus signal but is **named
   `reviewer_passed` and disclosed as an automated check, not human approval and
   not a security boundary** (D-GATE-3/6). L2 PASS ⇒ apply; BLOCK/ERROR/absent ⇒
   **fail-closed** `blocked-consensus`, lkg unchanged (D-GATE-4). L1 never
   consults it (unchanged); L3 applies regardless but records the verdict. The
   verdict is written on the checkpoint (INV-1 audit). No stateful cross-run
   breaker — a reviewer error fails this run closed without retry, honestly
   scoped (D-GATE-5). `MockReviewer` (PASS/BLOCK/ERROR/FLAKY) is the proof.
2. **Container enforcement.** `Fence.assert_environment()` refuses L2+ outside the
   Mode-B container unless `CHARON_CONTAINER_VERIFIED=1` (set by the image) or a
   loud `CHARON_ALLOW_UNCONTAINED_AUTONOMY=1` opt-out. Closes the latent hole
   that L3 already applied unattended with no container check.
3. **L3** retained as full-auto within the fence, now gated behind the container.

**Deferred — parallelism (PERF-4).** Built only when a consumer + real
concurrency model exist. Binding directives carried from the concurrency review
(CONC-1..4) for that work:
- **Per-unit unique `guard_dir`** — nest worktrees as
  `state_dir/sandbox/<task_id>/repo/` so one unit's escape scan can never see a
  sibling's legitimate writes (CONC-1).
- **No shared-budget race** — per-unit budget allocation, or an atomic
  reserve-then-spend counter under a lock; never N units each checking N ledgers
  (CONC-2).
- **Per-unit backend instances** — never share a long-lived ACP subprocess across
  units (sticky cwd/env) (CONC-3).
- **State-dir isolation** — unique state dir per unit, or a PID-liveness lock
  check, to avoid stale-lock reclaim corruption on a shared `.charon` (CONC-4);
  the Mode-B container is the real isolation boundary.

**Deferred — active cost-aware routing feedback.** The attribution *data*
(provider_history + Tier-3 usage spans) is already recorded durably; consuming it
for bandit routing is frontier-absorbable (Tier 5+).
