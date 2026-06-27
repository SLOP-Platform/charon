## 2026-06-24 — Tier 4 (final): L2 consensus gate + container enforcement; defer parallelism

- **Change under review:** `docs/PLAN-tier4.md` — L2/L3 autonomy + consensus gate
  + parallel units (PERF-4).
- **Reviewers:** three focused adversarial subagents in parallel —
  consensus-gate correctness, parallelism/concurrency-safety, premise/thinness/
  sunset. Independent; strong convergence.

### Convergence + reconciliation (against physics)

1. **BUILD the L2 consensus gate** — the only Tier-4 piece with a real consumer
   (L2 = apply-with-consensus) and durable value. The correctness reviewer
   enumerated 6 implementation gaps; all accepted. **One correction:** its
   proposed predicate (`gate = fence.authorize(consensus=False) AND
   reviewer_passed`) would block L2 *always* (authorize at L2 with
   `consensus=False` is False). The correct wiring supplies the reviewer verdict
   *as* the fence's consensus signal but **named `reviewer_passed` and disclosed
   as automated-not-human** (honoring D-GATE-3's spirit — name + disclose, don't
   silently launder), consulted **once at the completion point before
   `advance_lkg`** (D-GATE-1; lkg advances exactly once per run there, so
   per-checkpoint re-review is moot). Result: L1 unaffected (authorize ignores
   consensus at L1); L2 applies iff the reviewer passes; L2 with no reviewer or a
   reviewer error ⇒ **fail-closed** `blocked-consensus`; L3 applies regardless
   (full-auto) but records any blocking finding. Verdict recorded on the
   checkpoint (INV-1 audit). Per-run breaker, **honestly scoped** (not cross-run
   unless persisted) (D-GATE-5). README: **consensus is not a security boundary**
   (D-GATE-6).
2. **BUILD container-only enforcement for L2+** — all three flagged the latent
   hole: L3 already applies unattended in today's code (`fence.authorize` returns
   True at L3) with no container check, contradicting ADR-0002 §2.3 / INV-B4.
   Fix: `Fence.assert_environment()` refuses L2+ unless `CHARON_CONTAINER_VERIFIED=1`
   (set by the Mode-B image) or an explicit loud `CHARON_ALLOW_UNCONTAINED_AUTONOMY=1`
   opt-out. The in-process fence does not bound a live agent — the container does;
   now enforced in code, not just docs.
3. **DEFER parallelism (PERF-4)** — the concurrency review proved the "thin
   parallel design" **unsafe as drafted**: overlapping `guard_dir`s race the
   escape scan (CONC-1), a shared cumulative budget has a check-then-spend
   overspend race (CONC-2), shared backend subprocesses carry sticky cwd/env
   across units (CONC-3), plus lock-stealing under a shared state dir (CONC-4).
   The premise review independently found it speculative (no throughput consumer,
   frontier-absorbed). **Not built.** CONC-1/2/3/4 recorded as binding directives
   for when a consumer + real concurrency model exist (PLAN-tier4 §3): nest
   worktrees so each unit's `guard_dir` is unique; per-unit budget or an atomic
   reserved counter; per-unit backend instances; unique state dir per unit or a
   PID-liveness lock check.
4. **L3** is retained (full-auto within the fence) but now **gated behind the
   container** (item 2) — no longer undefended. Active cost-aware routing feedback
   is deferred (the attribution data — provider_history + Tier-3 usage spans — is
   already recorded durably; consuming it for bandit routing is frontier-absorbed,
   Tier 5+).

### Built (Tier 4)

L2 consensus gate (MockReviewer PASS/BLOCK/ERROR/FLAKY proof; gate before
`advance_lkg`; fail-closed; `blocked-consensus`; per-run breaker; verdict on the
checkpoint) · `Fence.assert_environment()` container gate for L2+ · honesty:
consensus is not a security boundary, L2/L3 are container-only.

WALK-BACK: none — additive. The only behavior change is that L2 now *functions*
(previously `authorize(consensus=autonomy>=L3)` made L2 silently behave like L0);
this is a fix, recorded here.
