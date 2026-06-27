## 2026-06-24 — Tier 3 RE-SCOPE: consensus gate → Ledger-native cost/budget

- **Change under review:** `docs/PLAN-tier3.md` — build the consensus gate +
  circuit breaker (ADR-0001 §9 Tier 3).
- **Reviewers:** two focused adversarial subagents in parallel — lens A =
  security/fail-mode, lens B = premise/thinness. Independent.
- **Outcome: the plan is re-scoped, not built as written.** Both reviewers, plus
  the orq.ai research, converged on the same physics.

### The convergence (why re-scope, reconciled against physics)

1. **The gate's only consumer is L2, which ships in Tier 4 (CONS-4 / T3-L0L1).**
   L0 applies nothing; L1 applies *without* consensus (the fence ignores the
   `consensus` arg at L1); L3 is full-auto. Only **L2 = apply-with-consensus**
   consumes a gate verdict. Building the gate in Tier 3, before L2 exists, makes
   it untestable end-to-end — the *exact* mistake Tier 2b caught (don't ship
   ahead of the consumer). **Decision: the gate is built in Tier 4, paired with
   L2.**
2. **Cost/budget is the durable, sunset-proof, routing-feeding alternative
   (CONS-7 + orq research).** A reviewer is frontier-absorbed (self-review,
   multi-model critique are landing natively; orq flagged consensus SKIP/WATCH).
   Ledger-native `{tokens_in/out, cost, latency}` spans + a fence **budget cap**
   + end-of-run cost attribution are permanent (git+JSON), survive Charon's
   sunset, and *feed* Tier-4 routing (cost-per-success, budget-aware handoff —
   the orq "retries-exhausted → handoff" + cost patterns). **Decision: Tier 3 =
   cost/budget accounting.**
3. **The security findings are deferred WITH the gate, recorded as Tier-4
   build-directives** so they cannot be lost: gate verdict checked **before**
   `advance_lkg` (T3-INV2-BYPASS); the gate binds **only at L2+** (T3-L0L1);
   reviewer-verdict is **not** mapped onto the fence `consensus` boolean — they
   are separate signals (T3-CONSENSUS-CONFLATION); breaker is per-*loop* latency
   bounding only, never claimed as cross-run protection unless persisted to the
   ledger (T3-BREAKER-EPHEMERAL); fail-closed is honest DoS, disclosed, with an
   operator override that degrades to L1 not fail-open (T3-FAIL-CLOSED-DOS);
   README must state **consensus is not a security boundary** — an LLM reviewer
   can be gamed (T3-REVIEWER-GAMING).

### Reconciled Tier 3 scope (built now)

Ledger-native cost & budget (the thin part Charon owns; INV-1 extended to costs):
1. `Outcome` + `Checkpoint` carry an optional **usage span**
   (`tokens_in/out`, `cost_usd`, `latency_ms`); adapters report it, the ledger
   records it (append-only, INV-1).
2. `Budget` gains `max_cost_usd` / `max_tokens`; the coordinator enforces the
   **cumulative** cap and stops (bounded `budget` status) before exceeding it —
   "always working" can never mean "unbounded cost" (PERF / fence).
3. **Cost is derived truth, like progress:** cumulative spend is re-derived from
   the ledger spans, so a handoff receiver sees the same total (H3-for-cost), not
   a per-session number that resets across vendors.
4. MockBackend reports deterministic usage → the accounting **contract** is
   proven-red; live token/cost come from real ACP `session/usage`, gated on
   `charon doctor` (honesty).

### Verdict on the security findings raised against the *unbuilt* gate

All ACCEPTED but carried to Tier 4 (where the gate lands), not discarded — see
the Tier-4 plan's "consensus build-directives". CONS-1 (is consensus redundant
with executable acceptance?) is answered: it is *additive insurance*, justified
only at L2 and only if measured to catch real regressions — so it is built where
it can be measured (with L2), not speculatively now.

WALK-BACK: none — Tier 3's consensus code was never written; this is a plan
re-scope before code, the cheapest possible place to change direction.
