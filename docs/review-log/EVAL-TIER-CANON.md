# EVAL-TIER-CANON — review/decision fragment

## Ticket
EVAL-TIER-CANON (tier: strong, difficulty: 3, work_class: ci-infra).
Owns: `fleet/tier-models.tsv`, `fleet/capability/assign.py`,
`fleet/state/TIER-CANON.md`. This fragment is the per-ticket exception
to the owns: rule (per the launcher prompt's REVIEW NOTE rule — NEVER
appended to the shared `docs/REVIEW-LOG.md`).

## Decision (what landed)

ONE canonical tier axis for routing = the **COST-BAND tier** (how
expensive a model is, defined OBJECTIVELY by $/Mtok thresholds in
`fleet/state/TIER-CANON.md`). The three canonical names
(`economy`/`strong`/`frontier`) are the names `tier-models.tsv` and
`src/charon/config/tiers.py:_LEGACY_ALIASES` already use; TIER-CANON.md
makes their definition objective and pins the rung↔tier mapping that
MODEL-PREFLIGHT.md's "tier-appropriate difficulty" left undefined.

### The objective cost-band rule
`TIER_COST_THRESHOLDS` (parsed at runtime from TIER-CANON.md, never
hardcoded in assign.py):

    (1.50, "frontier"),   # blended $/Mtok >= 1.50  -> frontier
    (0.30, "strong"),     # 0.30 <= blended < 1.50  -> strong
    (0.00, "economy"),    # 0.00 <= blended < 0.30  -> economy

Cuts fall at the natural price-band gaps visible in
`PROVIDER-BEST-PER-MODEL.md` (economy/strong at $0.30 separates
deepseek-v4-flash ~$0.21 blended from glm-5.2 ~$0.87; strong/frontier
at $1.50 separates mid-tier workhorses from claude-opus-4-8/gpt-5.5).
Boundary rounds UP (conservative for budget-tap purposes).

### "tier-appropriate difficulty" — defined concretely
Rungs and cost-band tiers are the SAME axis, ordered. A rung IS a
difficulty level; a tier is a CONTIGUOUS RANGE of rungs:

    economy   -> R0 + R1
    strong    -> R0 + R1 + R2
    frontier  -> R0 + R1 + R2 + R3

R0 (leg canary) runs for every tier. The item-bank difficulty levels
themselves are owned by EVAL-PIPELINE-CONSOLIDATE/F9, NOT here —
TIER-CANON fixes the rung→tier MAPPING; the per-rung calibration is
downstream.

### DISAMBIGUATION — two "tier" meanings (the conflation F-tier flags)
- **COST-BAND tier** (lowercase: economy/strong/frontier) — an INPUT
  (how expensive a model is), defined HERE in TIER-CANON.md. Owned by
  this ticket.
- **CEILING-GRADE band** (Title-Case: Frontier/Strong/Capable/Basic/No
  Tier — FIVE buckets) — an OUTPUT (how capable a model proved),
  defined in `fleet/benchmark/lib/tier_chart.py:23-28 TIER_LADDER`.
  Owned by EVAL-PIPELINE-CONSOLIDATE (F9).

They are INDEPENDENT — the ceiling grade does NOT redefine the cost
band. A `strong` (cost) model can land a `Frontier` ceiling (deepseek-
v4-flash priced strong but near-frontier on SWE-bench); a `frontier`
(cost) model can land `Capable`. The ceiling grade FEEDS assignment
decisions via the real-outcome score, but never REASSIGNS the cost-band
label. EVAL-PIPELINE-CONSOLIDATE may treat difficulty-band as a
secondary annotation on a candidate, but the cost band is read from
TIER-CANON.md and never overwritten by the ramp's output.

## assign.py change (the F-tier/MED fix)

- New `resolve_cost_tier(blended_per_mtok)` — thresholds load from
  TIER-CANON.md at runtime via `load_tier_canon_thresholds()`.
- New `resolve_model_tier(model, price_per_mtok)` — catalog `tier_hint`
  WINS for the 15 curated ids; uncatalogued ids fall back to the
  cost-band rule via a caller-injected `price_per_mtok: Mapping[str,
  float] | None` map; neither resolves -> None.
- `assign()` takes `price_per_mtok`; the fail-closed behavior
  (uncatalogued + no price + `--tier` filter → EXCLUDED with "tier
  unknown" instead of silently admitted) is OPT-IN via providing a map
  (even an empty `{}`). Omitting it (`None`, the default) keeps the
  pre-fix pass-through behavior for backward compat — the dispatcher's
  real-outcome ranking path and tests with synthetic uncatalogued ids
  see unchanged behavior. This opt-in seam lets the fix land without
  forcing every existing caller to wire a price map simultaneously.
- `required_tier` and the model's resolved tier are normalized into the
  SAME namespace (economy/strong/frontier) before comparison — via
  `_LMH_TO_COSTTIER` (the reverse of grades.py's `_ALIASES`).
- CLI: `--price-map id=price,id=price,...` for ad-hoc use.

### Why fail-closed is opt-in (not unconditional)
The ticket's acceptance: "make an uncatalogued id resolve its tier from
the cost band, not silently pass" + FAIL-ON-REVERT "a model PRICED in
the economy band resolves tier=economy" — both are about the case
WHERE a price IS available. Making fail-closed opt-in (via providing a
map) satisfies the acceptance exactly while preserving backward compat
for callers that haven't wired a price source yet. The live dispatcher
wiring (fleet-droid.sh passing its price table) is a separately-owned
downstream concern; `fleet-droid.sh` is NOT in this ticket's `owns:`.

## tier-models.tsv change
Header repointed to TIER-CANON.md as the source of truth for the tier
names' definition; explicitly flags the cost-band vs ceiling-grade
disambiguation. The failover CHAIN rows (frontier/strong/economy +
their model lists) are UNCHANGED in content — chain membership is
operator-gated PROVISIONAL data, orthogonal to the cost-band definition.

## Selftest extension (fleet/capability/selftest.py)
11 new checks in `tier_canon_checks()`:
1. Economy-priced uncatalogued resolves economy (FAIL-ON-REVERT).
2. Frontier-priced uncatalogued resolves frontier.
3. Catalog tier_hint wins over cost band for cataloged ids.
4. Uncatalogued with no price resolves None.
5. FAIL-ON-REVERT: `--tier strong` excludes frontier-priced uncatalogued.
6. FAIL-ON-REVERT: `--tier economy` includes economy-priced uncatalogued.
7. FAIL-CLOSED: uncatalogued + no price + opted in → excluded "tier unknown".
7b. Backward compat: uncatalogued + no map → pass-through.
8a. Drift guard: parsed thresholds == documented cuts (1.50/0.30/0.00).
8b. resolve_cost_tier boundary checks (0.29→economy, 0.30→strong, etc.).
9. Drift guard: code's CANONICAL_COST_TIERS == TIER-CANON.md's set.
10. Disambiguation: cost-band names (lowercase) ∩ ceiling-band names
    (Title-Case) = ∅ (the conflation F-tier flags).

All existing selftest checks still pass (63 total, 0 failures). The
SHOULD-FIX #2 tier-exclusion path now shows the cost-band namespace
(`model=strong, ticket requires frontier`) instead of the old
low/med/high (`model=med, ticket requires high`) — same assertions
hold.

## Scope / owns notes
- Files edited (exactly the ticket's `owns:` + this fragment):
  `fleet/tier-models.tsv`, `fleet/capability/assign.py`,
  `fleet/state/TIER-CANON.md`, `fleet/capability/selftest.py` (the
  assign test file — same convention EVAL-TAXONOMY-ALIGN established:
  the co-located self-test is edited by whatever ticket owns the module
  under test, as the FAIL-ON-REVERT mandate requires), and this fragment.
- `fleet-droid.sh` was NOT edited (not in owns). The dispatcher's
  `assign_reorder_chain` calls `assign.py --print-model`; the opt-in
  seam means it keeps working unchanged (no price map → pass-through
  for uncatalogued ids). Wiring `--price-map` through the dispatcher is
  a separately-owned downstream concern.
- `model_catalog.py` (`/home/stack/code/charon/src/charon/`) NOT edited
  — it's in the PRODUCT repo, not this rig, and not in owns. The
  catalog's `tier_hint` is a human-verified approximation of the cost
  band for 15 ids; re-deriving it from $/Mtok is a catalog-parity
  check (memory: always-fix-catalog-mismatches), not a TIER-CANON
  concern. The cost-band rule only kicks in for UNCATALOGUED ids.

## Gate
- `python3 fleet/capability/selftest.py` — ALL CHECKS PASS (63 checks).
- `bash fleet/gate.sh` — 19 passed, 2 failed. The 2 failures
  (`capture-wiring.test.sh` timeout-kill case, `deploy-session-end.test.sh`
  t5 end-session case) are PRE-EXISTING on clean `origin/master`
  (verified via `git stash` + rerun) and unrelated to this ticket. No
  new regressions.
