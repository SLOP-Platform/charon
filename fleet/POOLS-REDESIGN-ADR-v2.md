# ADR-POOLS-v2 — Collapse ~50 hand-maintained pools into ~4 tier-pools + a benchmark-fed grades table (phased, gated)

- **Status:** Proposed v2 (2026-07-07) — design-only, no code/push. Supersedes `POOLS-REDESIGN-ADR.md` (v1), which was reworked per adversarial review (`POOLS-REDESIGN-REVIEW.md`, verdict REWORK). Feeds the next adversarial review.
- **Deciders:** Rafael (operator) — the CONFIRMED TARGET below is operator-decided and is NOT re-litigated by this rework; only the *path to it* changed.
- **Supersedes:** `docs/adr/0004-routing-gateway-roles-pools-frontend.md` D4 (`role → ordered pool` schema) and its R2 amendment. D1–D3, D5–D8 of ADR-0004 are UNCHANGED.
- **Relates to:** ADR-0005 (gateway-first failover core — UNCHANGED), ADR-0014 ("tier vid" — this ADR makes it a real, seeded set from day one, not benchmark-gated).
- **Grounded by:** same sources as v1 (`pools-analysis.md`, `pools-origin-attribution.md`, `research-litellm-bifrost.md`, `research-opencode-ecosystem.md`, `research-gateway-landscape.md`, `HANDOFF-2026-07-06.md`, `model-scorecard.tsv`) **plus** `POOLS-REDESIGN-REVIEW.md` (this rework's direct input).

---

## Changelog v1 → v2

| # | Review issue | v1 problem | v2 fix |
|---|---|---|---|
| 1 | Sequencing (core fix) | Phases 1–2 built the capability-grades layer as *core*, before it could possibly discriminate | Split into **Phase 1 (structural: ~4 tiers + real cost/health, ships alone)** and **Phase 2 (capability grades, gated, optional)** — see Decision |
| 2 | Coverage / tier bootstrap | Tier required a benchmark composite; ~197/201 routes had no tier at all | Tiers are **seeded manually** from `model_catalog.py` (15 entries) + public reputation for all families on day 1; benchmark-v2 only **refines**, never gates, tier membership |
| 3 | False bridge | Public benchmarks (MMLU/LMArena) implied to map onto S0–S6 grades | Public benchmarks now **only** inform coarse tier *seeding*; per-work-class grades come exclusively from benchmark-v2's own S0–S6 runs |
| 4 | Anti-inert gate gameable | Gate (a) checked field-presence (`!= null`, `!= 1000`) — passable via uniform backfill with zero real differentiation | Replaced with a **decision-differentiation gate**: ships only if the capability-ranked pick differs from the cost/health-only pick for ≥X% of representative requests |
| 5 | Pricing source unlocated | models.dev→`cost_rank` injection assumed to exist | "Locate + wire the real pricing source" is now an explicit **Phase-1 prerequisite task**, not an assumption |
| 6 | Tier count asserted | Committed to exactly 4 before data showed 4 real strata | Keep **~4 as the target label**; note current data (3/4 scored models = Frontier) supports **~3**; final granularity is coverage-determined, not pre-committed |
| 7 | Migration safety | Phase 3 fused reversible routing-flip + destructive schema regen + CRUD migration into one cutover | Split into a **reversible routing-flip sub-phase** and a separate **destructive schema-regen/retirement sub-phase**; gate (c) marked partly unenforceable (opencode mirror is out-of-repo) |
| 8 | Credits | — | Kept verbatim: tier-as-set core idea, dark-launch→shadow phases, SaaS-router rejection, SR-6 discipline; openrouter/auto explicitly retained as optional Frontier-tier passthrough |
| 9 | (coordinator add, post-review) Grades table has a second consumer | v1/v2-draft framed grades as inert until gate (a)-v2 clears | Added "Grades table: two consumers" subsection — fleet ticket-assignment (rig-level, WCI-parked at product level) already has usable per-work-class signal in `model-scorecard.tsv` today and can consume the table from Phase 2a onward, independent of the gateway-routing gate |

---

## CONFIRMED TARGET (operator-approved, not re-litigated)

**~4 tier-pools + a benchmark-fed `model → {tier, per-work-class grades}` table. Pools are derived, never enumerated.** This is unchanged from v1. What changes in v2 is *sequencing*: the tier-pool structure and real cost/health routing ship first and stand alone; the benchmark-fed per-work-class grades layer ships second, behind a gate, and only once it demonstrably changes routing decisions.

---

## Context

Unchanged from v1 — see `POOLS-REDESIGN-ADR.md` §Context for the full sprawl audit (50 pools / 201 routes, 82% boilerplate-template duplication, inert `cost_rank` on ~95% of routes with real priority hidden in `pools.json` array order, 2 fake-failover pools, 3 unlinked curated-list concepts, SR-6's "shipped inert for months" precedent). Nothing in that diagnosis was disputed by the review — it was explicitly credited as first-rate. v2 changes only the design and sequencing built on top of it.

**Constraints** (unchanged, load-bearing): standalone/no new runtime dependency, provider-agnostic/agent-agnostic, free-first, INV-P0 (adding a model is config not code), no hosted-routing dependency.

---

## Decision

**Collapse the ~50 hand-authored pools into a small number of TIER-pools (~4 target, ~3 supported by current data — see Tier count below), each a plain SET of model ids, fed by a `model → {tier, cost, health}` table in Phase 1, extended to `model → {tier, per-work-class grades, cost, health}` in Phase 2.**

The critical change from v1: **this is now explicitly two independently-shippable phases**, not one design with sequential rollout steps that all lead to the same core.

### Phase 1 — Structural tier-collapse + REAL cost/health routing (no benchmark dependency)
Delivers the entire "not 40 pools / elegant" requirement on its own:
- Tiers are a plain SET, not 50 boilerplate arrays.
- `cost_rank` is real (sourced from a located, wired pricing feed — see Pricing source below), not the inert `1000` default.
- A live-health ledger decides "who wins right now" among same-tier candidates.
- List-order-as-hidden-priority is dead: priority is data (real cost + live health), not JSON array position.

**Phase 1 alone already satisfies the operator's confirmed target's structural half** (few pools, not enumerated, no boilerplate, no hidden array-order hack) and does not depend on benchmark-v2 existing, being accurate, or covering the catalog. This is the review's Option A+, adopted as Phase 1 rather than rejected.

### Phase 2 — Benchmark-fed per-work-class grades (gated, additive, optional)
Extends the same table with a `work_class_grades: {S0..S6: score|null}` column, sourced from benchmark-v2's own S0–S6 runs. This layer **ships only if it clears the decision-differentiation gate** (Mechanization, gate (a)-v2 below) — i.e., only once it is proven to actually change routing picks for a meaningful share of requests, not merely populated. Until it clears the gate, Phase 1's cost/health-only routing is the live behavior and is a legitimate, complete terminal state — not a waypoint the system is broken without.

This directly kills the two structural defects `pools-analysis.md` names (82%-boilerplate sprawl, inert-cost/list-order hack) in Phase 1, and adds capability-aware routing in Phase 2 only once it's proven real.

---

## Design detail

### Tier count: ~4 target, not hard-committed
The `Frontier / Strong / Capable / Basic` labels are benchmark-v2's real output bins (`tier_chart.py::composite_v2()`), live-validated on the one real run to date (`gpt-5.4 → FRONTIER, composite 95.8`). But as of this writing only 4 models are scored and 3 of them land in the same top bin (Frontier) — the data does not yet show 4 usefully-distinct strata. **v2 keeps ~4 as the target label** (it's the existing benchmark-v2 output shape and gives room for a real gradient once coverage grows) **but does not pre-commit to exactly 4**: if coverage settles into 3 real strata (matching the existing `model_catalog.tier_hint`'s high/med/low), the tier count follows the data, not the label. This is decided at Phase-1 population time and revisited at Phase 3 cutover, not asserted here.

### Tier assignment: seeded, then refined — never gated on benchmark
**This is the fix for the review's #1 ship-blocker.** A tier must exist for all ~57 model families on day 1, but benchmark-v2 has scored only ~4. So tier assignment is split from grade assignment:
- **Seed** (Phase 1, day 1, covers 100% of the catalog): tier is manually assigned from the existing 15-entry `model_catalog.py` `tier_hint` catalog (already has high/med/low) plus public reputation (rough LMArena/MMLU-class standing, publisher tier, price bracket) for the remaining families. This is a one-time hand-authored mapping — small, auditable, and exactly the kind of judgment call the operator already makes informally.
- **Refine** (ongoing): as benchmark-v2 scores more models, its composite may move a model's tier up or down from its seed. Refinement is additive and reversible; it never *removes* a tier assignment, it corrects one.
- Tier is therefore never null for a covered route, and the routing algorithm's `tier = grades[primary_model].tier` lookup always resolves — closing the review's "tier undefined for 197/201 routes" ship-blocker.

### Kill the false bridge: public benchmarks seed tiers, never grades
**This is the fix for the review's #3.** v1 implied MMLU/LMArena-class public benchmarks could fill `work_class_grades` gaps. The review correctly called this an unvalidated, asserted-not-shown mapping — public benchmarks measure general chat/knowledge/single-file coding, not Charon's agentic S0–S6 work-classes (money-path failover correctness, ci-infra pipefail discipline, anti-dodge test rigor). **v2 draws a hard line:**
- Public benchmarks (LMArena/MMLU/HumanEval-class) may inform **coarse tier seeding only** (a rough "this model is probably Frontier-ish" prior), same role as the `research-gateway-landscape.md` RouterBench survey already gave it in v1's validation-harness role.
- Per-work-class grades come **exclusively** from benchmark-v2's own S0–S6 runs. No public-benchmark number is ever written into a `work_class_grades` cell. A model with no benchmark-v2 run has `work_class_grades: {S0..S6: null}` and Phase 2's ranking falls back to Phase 1's cost/health-only path for that model — never a smuggled-in public-benchmark proxy.

### Pricing source — explicit Phase-1 prerequisite
**This is the fix for the review's #3b.** HANDOFF L53 records that `/data/models.json` has no `cost_input`/`cost_output` and nobody currently knows where the gateway's real per-token pricing lives — the "models.dev import" injection point v1 assumed is unlocated. v2 makes **"locate and wire the real pricing source" an explicit, named Phase-1 task**, not a background assumption folded into "the grades table." Phase 1 cannot claim `cost_rank` is real until this task is done and verified against at least a handful of known-priced routes. This directly blocks the gameable failure mode where `cost_rank` stays `1000`-inert under a new schema, which is the SR-6 precedent this whole ADR exists to avoid repeating.

### The routing algorithm (Phase 1, extended by Phase 2 once gated on)
```
request(primary_model, work_class=None):
  try primary_model
  on failure (429/402/5xx/model-field-mismatch per ADR-0004 D5):
    tier = grades[primary_model].tier          # always resolves — seeded day 1
    candidates = [m for m in grades if m.tier == tier and m.id != exhausted]
    if capability_layer_enabled:                # Phase 2, only post-gate
      wc = resolve_work_class(work_class, primary_model)
      rank candidates by: work_class_grade[wc] desc, then free desc,
                           then cost_rank asc, then live_health desc
    else:                                        # Phase 1 default
      rank candidates by: free desc, then cost_rank asc, then live_health desc
    try best candidate; repeat on failure, excluding tried
  on full-tier exhaustion:
    cascade to next tier down; repeat
  on all-tiers-exhausted: terminal failure (unchanged, ADR-0004 R2)
```
Phase 1 ships the `else` branch only. The `if capability_layer_enabled` branch is dead code, feature-flagged off, until Phase 2's gate passes — this makes the "capability layer is optional and must earn its way in" decision structural, not just documented intent.

### The work-class crux — unchanged from v1, now explicitly Phase-2-only
The three options (client-declared header, Arch-Router local classifier, infer-from-primary) and the recommendation (declared-overrides + Arch-Router fallback + GENERALIST default) are unchanged from v1 — see `POOLS-REDESIGN-ADR.md` §"The work-class crux" for full text. The only change in v2: this entire subsystem is **Phase 2 scope**, evaluated against the decision-differentiation gate before any of it ships live. It is not built or wired in Phase 1.

### Grades table: two consumers (gateway routing + fleet ticket-assignment)
The review's strongest objection was that per-work-class grades are inert on today's data — true for exactly one consumer. The grades table has a **second, independent consumer that already has usable signal today**: fleet ticket-assignment (auto-picking the best-suited agent/model for a ticket/subtask by its work-class), a rig-level concern, not the gateway request-routing path this ADR otherwise centers on.

`model-scorecard.tsv` already carries per-model × per-work-class outcome detail beyond the saturated composite score — merge%/block% and qualitative failure mode per S0–S6 section (e.g. gpt-5.4 clean-merges Frontier work across sections, glm-5.2 blocks/goes inert on specific classes, deepseek confabulates on others). That's exactly the kind of *differentiating* signal the review found missing from the composite-for-routing use case, and it is usable for assignment **right now**, on the existing 4-model coverage, with no benchmark-v2 coverage growth required first.

This means the grades table is not inert-until-Phase-2-gate-clears for *all* purposes — it earns real, immediate value as a fleet ticket-assignment input as soon as it exists, independent of whether the gateway-routing decision-differentiation gate (a)-v2 ever clears. The two consumers share the same underlying schema (work-class taxonomy, model ids) and the same availability/claim substrate (session-bridge), but assignment is deliberately kept **rig-level only** in this ADR — the product-level work-composition-intelligence feature (auto-assignment as a Charon product capability) stays parked per the existing product-vs-build-rig boundary; this subsection scopes fleet-internal ticket-assignment tooling only, not a product commitment.

**Phased-plan implication:** fleet ticket-assignment can start consuming the grades table as soon as Phase 2a (grades table dark-launch, populated from benchmark-v2's own S0–S6 runs) lands — it does not need to wait for gate (a)-v2 to pass, because assignment's bar for usefulness (helps a human/manager pick a plausible agent for a ticket) is lower than and independent of gateway routing's bar (changes an automated failover pick ≥X% of the time). This directly de-risks the "capability layer is inert on today's data" finding: the layer is inert only for the request-routing consumer until gate (a)-v2 clears; it is live-useful for the assignment consumer from Phase 2a onward.

---

## Borrowed patterns

Unchanged from v1 (`POOLS-REDESIGN-ADR.md` §"Borrowed patterns" table) — LiteLLM/Bifrost group-by-capability, RouteLLM cascade validation, Unify's static-grade × live-telemetry split, Arch-Router, Requesty's policy schema, RouterBench, Helicone's externally-maintained metadata catalog. **One addition per review issue #7:** `openrouter/auto` is kept not only as a bare optional passthrough model id (v1's framing) but explicitly as an **optional Frontier-tier passthrough option** — for the "just get me a top model, I don't care which" semantic, a near-free way to cover the Frontier tier's long tail without benchmarking every frontier model. It is never built on top of — the tier engine does not depend on it, matching the no-hosted-routing-dependency constraint.

---

## Options considered

### Option A+ (v1: rejected strawman "Option A"; v2: THIS IS PHASE 1)
v1 steelmanned and rejected a dumb template generator with no real priority signal. The review correctly pointed out the real competitor was never evaluated: template-generated membership + real `cost_rank` + live-health tiebreak + a coarse hand-seeded tier label. **v2 adopts this directly as Phase 1** rather than rejecting a weaker version of it. This resolves review issue #2 by inversion: instead of arguing Option A+ loses to the full design, v2 makes Option A+ *be* the first shipped phase, with the full design as an optional, gated Phase 2 extension on top of the same schema.

### OpenRouter `auto` as foundation — still REJECTED, per v1
Unchanged: closed SaaS meta-model, zero pre-call visibility, would cap routing quality below Charon's existing direct-provider access, violates provider-agnostic mandate as a foundation. Kept only as an optional per-tier passthrough (see Borrowed patterns above).

---

## Blast radius + phased migration

Same consumer list as v1 (`_build_routes_and_pools`/`derived_cost_rank`, `_tier_pools`, global fallback synthesis, the setup API + dashboard, `GatewayProxyServer` cooldown scope, `X-Charon-Provider`/status headers, the incompatible ACP `pools.py` loader, the 3 unlinked curated-list concepts) — see `POOLS-REDESIGN-ADR.md` §"Blast radius" for full detail, unchanged. v2 changes the **phase boundaries** to fix the review's migration-safety issue (#5):

**Phase 1 — Structural tier-collapse + real cost/health, dark launch (no routing change yet).**
Build the `model → {tier, cost, health}` table: seed tiers (100% coverage, manual + catalog + reputation), locate and wire the real pricing source (explicit prerequisite task, see Pricing source above), stand up the live-health ledger. Nothing in the live routing path reads it yet. Provably correct against a shadow-mode comparison against today's pool ordering.

**Phase 1.5 — Routing flip (reversible only).**
Implement and flip the Phase-1 routing algorithm (`else` branch above: tier lookup → free/cost/health rank → cascade) behind a flag. This is a **behavior change but not a schema change** — `pools.json` still exists in its old shape underneath if a rollback is needed; flipping the flag back is a full, instant revert with no data loss. This sub-phase is the entire "not 40 pools" structural win going live.

**Phase 2a — Capability grades, dark launch (gated, optional).**
Only entered if/when benchmark-v2 coverage and the decision-differentiation gate (below) justify it. Build the `work_class_grades` column from benchmark-v2's own S0–S6 runs (never public benchmarks — see Kill the false bridge above). Wire the `if capability_layer_enabled` branch behind its own separate flag, dark (log-only, don't act). **The grades table is live-consumable by fleet ticket-assignment as soon as this sub-phase lands** — see "Grades table: two consumers" above; assignment does not wait for gate (a)-v2, which only gates the gateway-routing consumer.

**Phase 2b — Capability grades flip (reversible, gated).**
Flip the capability-layer flag live only after gate (a)-v2 passes on shadow data. Independently revertible from Phase 1.5 — turning capability routing off falls back cleanly to the Phase-1 cost/health-only path, which is always a valid, complete routing behavior.

**Phase 3 — Schema regeneration + retirement (destructive, separate from the routing flips above).**
This is the review's fix for issue #5: the *destructive* work — regenerating `pools.json`'s 50-entry shape into the final tier-set shape (or retiring it in favor of the grades table directly), migrating the setup API/dashboard CRUD, deleting the old `derived_cost_rank`-on-`1000`-default code path — happens **only after** both routing flips above are already live and stable, as its own phase with its own backup+rollback-verify discipline (`zen-demote-report.md`/`dead-free-go-prune-report.md` pattern). Rolling back a *routing flag* (Phase 1.5/2b) is cheap; rolling back a *schema regeneration* (Phase 3) means restoring a `/data` snapshot while live — genuinely destructive, and this ADR no longer lets that risk hide inside the same phase as a reversible flag flip.

**Phase 4 — Unify the 3 lists.**
`regen-charon-models.sh`'s opencode mirror and `model_catalog.py`'s CLI catalog become generated views off the grades table, closing the 3-lists drift gap — subject to the partial-enforceability caveat in Mechanization gate (c) below.

---

## Mechanization — executable acceptance gates (v2, decision-differentiation gate replaces v1's inert one)

**(a)-v2 Proof-of-effect for the CAPABILITY LAYER — decision-differentiation, not field-presence.**
**This is the fix for the review's #3 (gate is gameable).** v1's gate checked `work_class_grades not all-null AND cost_rank != inert_default` — passable by a uniform backfill that stamps every model the same value, producing zero real differentiation while reading as 90%-populated. v2 replaces it:

> Gate fails unless: over a representative sample of requests (shadow-mode traffic from Phase 2a), the capability-ranked candidate (Phase 2's `work_class_grade[wc]`-first ranking) differs from the cost/health-only candidate (Phase 1's ranking) in **≥X% of cases** (X tuned during Phase 2a population; start at a deliberately low bar like 10-15% since even modest, real differentiation is meaningful — the point is proving non-zero effect, not a high bar).

This directly targets the review's core finding: on today's data (4 models, nearly all scoring 100 on every S0–S6 section), a real decision-differentiation gate would correctly **fail** — because the capability layer genuinely doesn't change any pick yet. That is the gate working as intended, not a flaw: Phase 2 stays gated off until benchmark-v2 coverage and score spread are real enough to move actual routing decisions, which is the only meaningful definition of "the capability layer is not inert."

**(a)-Phase1 Pricing/cost is real, not the inert default.**
A separate, simpler gate scoped to Phase 1 only: `pct_real_cost = count(routes where cost_rank derived from located pricing source) / count(routes) ≥ 90%`. This is the SR-6-style presence check, but applied only to the cheap, already-real Phase-1 cost signal — not smuggled in as proof the capability layer works.

**(b) DRY/anti-boilerplate — unchanged from v1.**
Zero hand-authored per-model pools, structural-duplication detector as in v1. Applies at Phase 3 (schema regeneration), not before.

**(c) The 3 model-lists unify to 1 — partly unenforceable-in-CI, noted honestly (review #5).**
Unchanged assertion (`set(opencode_mirror_ids) ⊆ set(grades_table_ids)`, `set(model_catalog_ids) ⊆ set(grades_table_ids)`, both generated + checksummed). **New in v2:** explicitly documented that the opencode mirror lives at `~/.config/opencode/` on the operator's machine, outside the repo, read only at process start (requires a full `pkill` to pick up regeneration) — a CI job cannot see or enforce that file's freshness. Gate (c) is therefore **CI-enforceable for the in-repo half** (`model_catalog_ids ⊆ grades_table_ids`) and **manual-only for the opencode-mirror half** (a documented regeneration step + operator-run diff, not a blocking CI check). This is stated as a known limitation, not silently assumed solved.

**(d) Commit+SHA-verify + adversarial review as required plan steps — unchanged from v1.**
Every phase (1, 1.5, 2a, 2b, 3, 4) ends with a commit SHA recorded in the phase's report, a before/after `/data` snapshot diff for any phase touching live state, and an adversarial review pass before the next phase starts.

---

## Recommended decision + why it beats the alternatives + honest residual risks

**Recommended: ship Phase 1 (tier-collapse + real cost/health, Option A+) as the first, complete, standalone deliverable. Build the capability-grades layer (Phase 2) only behind the decision-differentiation gate, using benchmark-v2's own S0–S6 runs exclusively — never public-benchmark proxies, never gated on 100% catalog coverage for tier (only for grades).**

**Why this beats v1's original sequencing:** v1 built the least-proven, most-expensive layer as core Phase 1–2, gated on a benchmark (v2) that wasn't built yet and a coverage level that may never arrive, using a gate that couldn't detect its own inertness. v2 ships the same structural win (few pools, no boilerplate, no hidden array-order hack, real cost — the operator's actual confirmed target's structural half) immediately, with zero dependency on benchmark-v2's existence or accuracy, and defers the capability layer to when it can actually be proven to matter.

**Why this still beats doing nothing / Option A (dumb generator):** unchanged from v1 — the sprawl costs real operator time today and worsens linearly with every new model. Phase 1 alone fixes both the authoring-toil symptom (Option A's target) and the structural too-many-objects problem Option A left untouched, plus the inert-cost/hidden-priority problem, which Option A never touched at all.

**Why this still beats a SaaS router:** unchanged from v1 — none are self-hostable with the needed transparency; `openrouter/auto` is retained only as an optional per-tier passthrough, never a foundation.

**Honest residual risks (v2):**
- **Phase 2 may simply never clear its own gate.** If benchmark-v2 coverage stays thin or scores keep clustering near-ties, decision-differentiation may never reach even a low X%. This is now a *feature* of the design (Phase 1 is a legitimate permanent terminal state, not a broken waypoint) but the operator should expect a real possibility that Phase 2 is designed, dark-launched, and never flipped on — that is success, not failure, of the gate doing its job.
- **Tier seeding is a one-time hand-authored judgment call** covering ~57 families from a 15-entry catalog plus reputation — it will contain errors and disagreements with a "real" benchmark-derived tier once one exists. This is accepted as the cost of 100% day-1 coverage; refinement is ongoing and reversible, never gated.
- **The pricing-source location task is unstarted and its difficulty is unknown** — Phase 1 cannot be called done until it's found and verified; if it turns out to require a live API call or an unreliable scrape, the "real cost_rank" half of Phase 1's value is itself at risk and may need its own fallback design.
- **The live-health ledger (unchanged from v1) is new code with no precedent in Charon today** — still the least-specified piece; a second-pass design/ticket for it remains a legitimate outcome of Phase 1.
- **Gate (c)'s CI-unenforceable half (opencode mirror) is a standing manual-process risk** — drift between the repo-side grades table and the operator's live opencode config can still silently occur between manual regeneration runs; this is now documented rather than assumed away, but it is not solved.
- **Migration to the live 4-LOM gateway remains real risk at Phase 3** — splitting the routing flip from the schema regen reduces but does not eliminate this; Phase 3 is still the single highest-blast-radius step in the plan and must not proceed without the established backup+rollback discipline.

---

## Salvaged design ideas (folded in 2026-07-08 from archived docs)

Preserved here before archiving `DTC-tier-abstraction.md` and `PROPOSAL-1-COST-AWARE-ROUTING.md`
(design-work-tracking audit, salvage→POOLS-REDESIGN). Nothing below is new work; it captures the
durable ideas so they survive the source docs' archival.

**From DTC-tier-abstraction.md (the tier-vocabulary consensus; TIER-1..7 shipped the mechanics):**
- **One canonical tier vocabulary as the single truth: `low`/`med`/`high`** (existing `types.Tier`).
  `opus/sonnet/haiku` and `frontier/strong/economy` become **aliases only** — this ends the
  three-vocabulary sprawl and removes the `FixedCap` cap-desync footgun (the editor edits
  members/aliases, never the fixed canonical keys).
- **Keep tier data in a separate `tiers.json`, NOT `pools.json`.** The central correctness fix:
  `pools.load_pools`/`router.from_charon_dir` is a STRICT loader (`_entry_from_registry` requires
  an `agent` field), and web-authored models never write `agent`, so overloading `pools.json`
  crashes the ACP router. A separate `tiers.json` leaves the strict loader untouched → backward
  compatible by construction. This constraint must hold in the pools redesign's schema work.

**From PROPOSAL-1-COST-AWARE-ROUTING.md (cost-aware routing goal; absorbed here + in COST-RANK-AUTO):**
- Route to the **cheapest provider of a specific model without quality loss**, send work to the
  **correct capability tier** for the task class, and switch **silently** on billing caps / rate
  limits / credit exhaustion. This is the north-star statement this ADR + COST-RANK-AUTO
  (cost_rank/cost_class) + DRAIN-ROUTING (balance-aware demotion) implement; no unique unabsorbed
  mechanism remained in the proposal at archival.

**Operator directive (2026-07-08) — multiple members per tier:**
- Each tier MUST carry multiple tested members (no single-point-of-failure); tier membership graded by the real-outcomes signal, not hand-picked (operator directive 2026-07-08).
