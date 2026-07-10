# GATEWAY-PROGRAM — consolidation + wall-clock-optimized build plan

**Status:** PLAN OF RECORD (2026-07-10, rev-2 post red-team). Supersedes the scattered gateway
tickets. **Focus:** finish + polish *how the Charon Gateway decides* — the intelligent-routing layer
(metering, cost-ranking, drain-first, quota-spill, capability-based selection). Core
request/response/failover path already shipped; this layer is the remaining work, almost all parked.
**Convergence:** this layer *is* the admission-control that fixes pool-exhaustion under load.

---

## 1. DECISIONS LOCKED (operator session 2026-07-10)
1. **Retire synthetic benchmark as ranker/seed.** 3 independent Charon reviewers (3 lenses) unanimous
   RETIRE @ high confidence. A non-discriminating seed is *miscalibrated*, not weakly-informative; it
   locks in (low-ranked model → no traffic → no actuals → decay never fires). OOB grading (#26) fixes
   gaming, not discrimination, so it doesn't rescue synthetic.
2. **Ranker = ACTUALS LEDGER** — grade every real sub-session from deterministic byproducts
   (charon-run result, packet-parses, fail-on-revert + gate pass/fail, failover hops, tokens/wall),
   bucketed by `work_class`. **D2: manager accept/reject kept as a LOW-WEIGHT SECONDARY signal,
   tracked separately, re-evaluate after N≈50 samples** (bias risk noted, judged small).
3. **#26 OOB grader kept, repurposed** to grade *real* tasks (reds-replay + actuals). `bench-grader`
   unix substrate (steps 1–4) already stood up — correct foundation.
4. **Capability = MATRIX** `(model × work_class) → grade`, not scalar tier. Promotion/demotion in
   every tier. **D1 (HYBRID): capture the difficulty DATA now, build the ladder MECHANISM later.**
   The bandit runs **flat per work-class now** (no cross-difficulty promotion code). But add a
   `difficulty:` ordinal (1–5) to the ticket schema NOW, **auto-seeded from the existing `tier:`
   field** (economy=1 … frontier=5), enforced by `validate_board.sh`. Rationale: the field is cheap
   now / lossy later (rot: purpose of parked tickets decays), and `tier` is already an ordinal proxy
   so backfill is mechanical. Ladder becomes pure code later with data already present.
5. **Risk-gated exploration** — exploration draws ONLY from the reversible/low-blast-radius pool.
6. **Two exploration channels:** (a) live low-risk real work; (b) **reds-replay** — the safe proxy
   for high-risk classes you can't explore live. This is why reds-replay is kept.
7. **Promotion/demotion confidence-gated, bidirectional, continuous** (Wilson lower-bound / Thompson).
8. **Exploration decays but never zero** (anti-drift).
9. **Open, append-only taxonomy + switchable exploration mode.** Hot path classifies to a *known*
   class or `unknown` (route via safe default + log); offline crystallizer names new classes. Mode
   (`bounded | uniform`) auto-selected by class maturity — **but new/`unknown` classes default to
   HIGH-RISK** (reds-replay/spec-floor only, NO live uniform explore) until the operator attests
   low-risk. *(red-team fix #4: breaks the novel-class × risk-gate deadlock.)*

---

## 2. CONSOLIDATION — clusters, retirements, dedup
**Retire (synthetic-ranker dead work):** BENCH-PROVISIONAL-SCORING, BENCH-AGGREGATE-N,
BENCH-DIFFICULTY-CAL, ASSIGN-DISCRIM-GATE, CAP-PROBE-BACKLOG.
**Fold into ONE CAPABILITY-ENGINE program:** CAPABILITY-ENGINE + COST-RANK-AUTO + DRAIN-ROUTING +
FREE-TIER-QUOTA-SPILL + DRAIN-THEN-PARK + POOLS-SIMPLIFICATION → after the decompose these become
disjoint files under the **`routing_policy/` PACKAGE** (see §4), not competing `gateway.py` writers.
**Keep, repurposed:** BENCH-OOB-GRADING (#26) → grades real tasks.
**Provider-integrity sweep:** PROVIDER-PROBE-FIX → PROVIDER-URL-HELPER (serial, same files) →
CATALOG-SYNC-DRIFT.
**Live-ops, KEEP ACTIVE until POOLS-SIMPLIFICATION ships** *(red-team fix #9 — not "moot"; live drift
exists now)*: GPT5-POOL-REORDER, ZEN-DRIFT-CLEANUP.
**New tickets:** ACTUALS-LEDGER, EXPLORE-PROMOTE, WORKCLASS-TAXONOMY, + DIFFICULTY-SCHEMA (D1 field).

---

## 3. MECHANISM (one line): a **risk-gated contextual bandit over a `(model × work_class)` matrix**,
fed by the actuals ledger (live low-risk work) + reds-replay (high-risk classes), confidence-gated
bidirectional promotion/demotion, decaying-nonzero exploration, open taxonomy where novel classes are
high-risk-by-default until attested. Difficulty data captured now (auto from `tier`), ladder later.

---

## 4. WALL-CLOCK-OPTIMIZED EXECUTION PLAN (rev-2)

**Decompose-first is the unlock,** but *only if it produces a PACKAGE* — **`routing_policy/`**
(`__init__.py`, `cost_rank.py`, `drain.py`, `pools.py`, `spill.py`, `matrix.py`) — one file per
policy. A singular `routing_policy.py` would make Wave-2 4-serial-on-one-file (red-team fix #1). The
decompose lands the package skeleton + interface stubs (abstract policy base, scorecard schema) FIRST;
Wave-2 authors start against the stub, **pipelined — no barrier waiting for full Wave-1 merge**
(red-team fix #8).

**Product-boundary seam (red-team fix #2, CRITICAL):** the rig grader must NOT be a live routing
dependency. Grader writes **versioned, append-only `scorecard.v{n}.json`** via a batch job; the bandit
reads the **latest frozen artifact with last-known-good fallback**. **CI import-guard bans
`import benchmark` / `grader_daemon` on the product hot path.** A rig regression then degrades to
stale-but-safe routing, never silent miscalibration.

**Money-path gate (red-team fix #5):** METER-MODEL-PROVIDER merge precondition is a **metering-
invariant canary** — shadow-run the new meter against a recorded request stream, assert cost-total
delta==0 and credential-shape invariance — BEFORE merge, in addition to 2-tier review. Money-path
items do not get two free attempts at silent mis-pricing.

**Provider capacity (red-team fix #6):** **proactive live-reserve** — reserve provider capacity for
live traffic before allocating build sessions (not reactive ALL-EXHAUSTED). Count the grader's own
model traffic as a consumer. Spread primaries across provider pools.

### WAVE 1 — start now · 4 DISJOINT files · provider-split fixed
| Item | Files (disjoint) | Model | Review gate |
|---|---|---|---|
| GATEWAY-ROUTING-DECOMPOSE → **`routing_policy/` package** + stubs | `gateway.py` → new `routing_policy/*` | deepseek-v4-pro | 🔴 blast-radius, 2-tier N-of-M + coupling check |
| METER-MODEL-PROVIDER | `proxy.py`, `balance.py` | deepseek-v4-pro | 🔴 money-path, **+ metering-invariant canary** |
| BENCH-OOB-GRADING (#26, real-task) | rig `benchmark/*`, `grader-daemon.py` | glm-5.2 | 🔴 isolation + **artifact seam/import-guard** |
| ACTUALS-LEDGER (scaffold + freeze-ring reader) | new `capability/actuals.py`, versioned scorecard | **deepseek-v4-flash** | 🟡 normal |

*Provider-split (fix #6):* pro / pro / glm / flash — no two heavy sessions on one pool; grader traffic
counted. **Pre-Wave-1 check:** verify `gateway.py`↔`proxy.py`/`config.py` import coupling; if coupled,
hard-order meter-then-decompose-rebase instead of parallel (red-team fix, wall-clock item b).

### WAVE 2 — pipelined off decompose stub · wide parallel on package files
CAPABILITY-ENGINE authors `routing_policy/` policies (cost_rank, drain, pools, spill) + `matrix.py`,
consuming meter (cost) + frozen actuals (grades). EXPLORE-PROMOTE (bandit, flat per work-class) +
WORKCLASS-TAXONOMY. **Serialization to respect (red-team #B/#C):** EXPLORE-PROMOTE reads the matrix
schema `matrix.py` defines → order matrix.py first; provider-integrity sweep overlaps CAPABILITY-ENGINE
on `providers.py`/`config.py` → sequence, don't co-write.

### WAVE 3 — DRAIN-THEN-PARK wiring, POOLS live cutover, dashboards.

**Escalation ladder:** a Charon build failing adversarial review **twice** → escalate that item to a
Claude droid tab (operator opens). Default stays Charon.

---

## 5. BOARD ACTIONS
1. Retire the 5 synthetic tickets (append `retired: superseded-by GATEWAY-PROGRAM`).
2. Create ACTUALS-LEDGER, EXPLORE-PROMOTE, WORKCLASS-TAXONOMY, **DIFFICULTY-SCHEMA** (owns/deps/D&S).
3. Repurpose #26 scope → "grade REAL tasks + write versioned frozen scorecard artifacts."
4. **DIFFICULTY-SCHEMA (D1):** add `difficulty:` (1–5) to ticket template; mechanical backfill
   auto-seeded from `tier:`; `validate_board.sh` enforces presence on new tickets.
5. Re-slice the fold set as `routing_policy/` sub-modules under CAPABILITY-ENGINE.
6. Keep GPT5-POOL-REORDER / ZEN-DRIFT-CLEANUP active (live-ops) until POOLS ships.
