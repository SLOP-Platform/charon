# Charon — Tier 3 build plan

> **RE-SCOPED post-review (REVIEW-LOG 2026-06-24).** The original draft (the
> consensus gate, preserved below as §0–§6) was re-scoped: two independent
> adversarial reviewers + the orq.ai research converged that the gate's only
> consumer is **L2**, which ships in Tier 4 — so the gate is built **in Tier 4,
> paired with L2** (its security build-directives are recorded there). Tier 3 is
> instead **Ledger-native cost & budget accounting** — durable (git+JSON,
> outlives Charon), sunset-proof, and feeding Tier-4 routing. See §7 for the
> built scope.

## 7. Reconciled scope — Ledger-native cost & budget (BUILT)

The thin part Charon owns; INV-1 (the Ledger is the sole truth) extended to cost.

- **Usage spans.** `Outcome` and `Checkpoint` carry an optional usage span
  (`tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`). Adapters report it; the
  ledger records it append-only. Absent (None) by default so Tier-1/2 stays green.
- **Budget caps.** `Budget` gains `max_cost_usd` and `max_tokens`. The coordinator
  tracks **cumulative** spend across checkpoints and stops with a bounded
  `budget` status *before* exceeding the cap — "always working" never means
  "unbounded cost".
- **Cost is derived truth.** Cumulative spend is re-derived from the ledger spans,
  so a cross-vendor handoff receiver computes the same total (H3-for-cost), not a
  per-session number that resets across vendors.
- **Proof vehicle.** MockBackend reports deterministic usage; tests prove the
  accounting + cap + cross-vendor cost-rehydration contract (proven-red). Live
  token/cost come from real ACP `session/usage`, gated on `charon doctor`.

This feeds Tier 4: cost-per-success attribution tunes routing; a budget cap that
trips becomes a budget-aware **handoff** signal (the orq "retries-exhausted →
handoff" + cost-tracking patterns, adopted natively per docs/research/
orq-comparison.md).

---

## (Original pre-review draft — consensus gate, now Tier 4)

> Kept for the record; built in Tier 4 with L2. Enforces INV-3 / lights up
> autonomy **L2** (apply-with-consensus). The harness owns only the gate
> predicate + breaker; the reviewer is integrated, not built (ADR-0001 §2).

## 0. Scope contract

The `Reviewer` port already exists (`ports/reviewer.py`, `review(unit, outcome)→
Findings`). Tier 1/2 ran with no gate. Tier 3 makes the gate real:

1. A **consensus gate** in the coordinator: when a reviewer is configured, a unit
   may not be reported `complete` — and at L2 may not be **applied** — unless the
   reviewer's `Findings.passes`. INV-3 becomes executable.
2. A **circuit breaker** around the (possibly flaky/remote) reviewer: repeated
   reviewer errors trip the breaker; while tripped the gate **fails closed**
   (cannot obtain consensus ⇒ do not apply / do not falsely complete).
3. A deterministic **MockReviewer** adapter (PASS / BLOCK / ERROR modes) — the
   proof vehicle, mirroring MockBackend. A real cross-model reviewer stays a port
   wired behind the gateway (gated by `SUPPLY-CHAIN.md`, Tier 2.5+), not built
   here.

Out of Tier 3: the real cross-model reviewer's live model calls (needs the gated
gateway), autonomy L3 + parallelism (Tier 4).

## 1. Where the gate sits in the loop

In `coordinator.run`, today, completion is: `not remaining and outcome.commit →
advance_lkg → complete`. Tier 3 inserts the gate **between "acceptance passes"
and "complete/apply"**:

- Acceptance (executable, INV-6) is the *ground truth that the work is done*.
- Consensus is the *second opinion that the work is good* (no regressions a check
  didn't encode). The gate is **additive** to acceptance, never a replacement —
  a unit must pass BOTH `remaining == ∅` AND the gate.
- At **L0/L1** with a reviewer configured: the gate guards the `complete` status
  (a blocked unit reports `blocked-consensus`, lkg does not advance).
- At **L2**: `fence.authorize(APPLY_REVERSIBLE, consensus=<gate passed>)` — the
  gate's verdict *is* the `consensus` boolean the fence already expects. Apply
  happens only on a passing gate. (L3 = full-auto, consensus not required.)
- **Backward compatible:** with **no reviewer configured** (the default through
  Tier 2), the gate is a no-op pass — Tier-1/2 behavior and tests are unchanged.

## 2. Fail-mode — the crux (proposed: FAIL-CLOSED)

A consensus gate that fails *open* is security theater. Proposed default:

- Reviewer returns blocking findings → gate **fails** (unit not complete / not
  applied); findings recorded as a checkpoint. Honest, not an error.
- Reviewer **errors/unavailable** → counts toward the breaker; the gate verdict
  is **cannot-pass** (fail-closed). At L2 this means *do not apply* (you cannot
  prove consensus). At L0/L1 it means report `blocked-consensus` rather than a
  false `complete`. Stranding work unapplied is safe; applying unreviewed work is
  not.
- **Operator override:** `consensus_fail_open=True` is allowed but logs a loud
  warning and is recorded in the ledger checkpoint — never the default.

## 3. Circuit breaker

A thin breaker around `reviewer.review`:

- N consecutive errors (default 3) → **OPEN**: stop calling the reviewer
  (protects a flapping/remote reviewer and bounds latency, PERF), gate verdict =
  fail-closed while open.
- After a cooldown (or on the next run) → **HALF-OPEN**: one trial call; success
  → CLOSED, failure → OPEN again.
- A *blocking finding is not an error* — the breaker trips only on
  exceptions/timeouts, not on the reviewer correctly saying "no".

## 4. Adapter — MockReviewer (proof vehicle)

`adapters/review_mock.py`, deterministic, mirroring MockBackend:
- `PASS` — empty findings (gate passes).
- `BLOCK` — returns blocking findings (gate refuses; proves a unit with
  `remaining == ∅` is still not `complete`).
- `ERROR` — raises (proves the breaker trips and the gate fails closed).
- `FLAKY(k)` — errors k times then passes (proves HALF-OPEN recovery).

## 5. Tests (proven-red)

- Gate blocks completion: acceptance satisfied but reviewer BLOCKs → status
  `blocked-consensus`, lkg unchanged (INV-2/INV-3).
- Gate passes: acceptance satisfied + reviewer PASS → `complete`, lkg advanced.
- L2 apply requires consensus: at L2, BLOCK ⇒ not applied; PASS ⇒ applied.
- Fail-closed on error: reviewer ERROR ⇒ not complete/applied, recorded.
- Breaker opens after N errors and stops calling the reviewer (assert call count
  bounded); HALF-OPEN recovery with FLAKY.
- Backward-compat: no reviewer configured ⇒ all Tier-1/2 tests still green.
- Fail-open override: explicit flag ⇒ completes despite error, with the warning
  recorded.

## 6. Decisions for adversarial review

- **D1 — fail-closed default.** Does fail-closed strand work or deadlock in a way
  that pushes operators to disable the gate (making it pointless)? Is fail-closed
  right at L0/L1 (where autonomy doesn't *require* consensus), or should the gate
  only bind at L2+?
- **D2 — breaker semantics.** Is consecutive-error count + half-open the right
  thin breaker, or over-engineered? Does an open breaker that fails-closed create
  a denial-of-progress an attacker (or a flaky reviewer) can weaponize?
- **D3 — gate vs acceptance.** Is "consensus on top of executable acceptance"
  additive value, or redundant ceremony given acceptance is already machine-
  decidable? What does consensus catch that an executable check cannot — and is
  that worth the complexity now (sunset clause)?
