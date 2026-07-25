# TIER-CANON — canonical cost-band tier axis (single source of truth)

Ticket: `fleet/board/EVAL-TIER-CANON.md`. Fixes the adversarial review's
F-tier HIGH finding (`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md` §4)
and the cross-ticket drift `HANDOFF-REVIEW-quinlan-vos.md` M2 flags:
"tier" was defined three incompatible ways and `assign.py`'s tier filter
silently no-op'd for every uncatalogued model id (the F-tier/MED gap).

## Decision

ONE canonical tier axis for **routing** = the **COST-BAND tier** — how
expensive a model is to run, defined by an OBJECTIVE $/Mtok rule below.
Cost band is the meaningful routing axis because (a) it is knowable
BEFORE any benchmark run (an INPUT, not a measurement), so it can gate
*which* models a ticket's tier will even consider, and (b) it is what
the gateway pool ordering and the budget taps already key on
(`PROVIDER-BEST-PER-MODEL.md`, `fleet/tier-models.tsv`).

The canonical names are the three already in use across
`fleet/tier-models.tsv` and `src/charon/config/tiers.py`'s
`_LEGACY_ALIASES`:

    CANONICAL_COST_TIERS = economy, strong, frontier

These map 1:1 onto the product router's `low/med/high` via
`config.resolve_tier` (`economy→low`, `strong→med`, `frontier→high` —
see `src/charon/config/tiers.py:13-16`). TIER-CANON.md owns the
cost-band definition; the alias fold is the product's concern and is
unchanged by this ticket.

### The objective cost-band rule ($/Mtok thresholds)

A model's cost-band tier is the **blended $/Mtok** of its
**cheapest-known live provider**, where blended = the simple unweighted
mean of the input $/Mtok and the output $/Mtok that provider charges
(promo rates flagged; re-verify promos before relying — same discipline
`PROVIDER-BEST-PER-MODEL.md` already documents). "Cheapest-known" =
the lowest blended $/Mtok across the providers actually wired in the
live gateway config for that model id (a model reachable only via a
flat-bundle provider is priced at that bundle's effective per-Mtok
rate; a model with no known live provider price is `unknown`, see
below).

The thresholds (the SINGLE SOURCE assign.py reads — do not hardcode in
code; the drift guard in `selftest.py` asserts code and doc agree):

    TIER_COST_THRESHOLDS = (
        (1.50, "frontier"),   # blended $/Mtok >= 1.50  -> frontier
        (0.30, "strong"),     # 0.30 <= blended < 1.50  -> strong
        (0.00, "economy"),    # 0.00 <= blended < 0.30  -> economy
    )

Threshold rationale (derivable, not arbitrary): the cuts fall at the
natural price-band gaps visible in `PROVIDER-BEST-PER-MODEL.md`'s
verified price table. Concretely, the **economy/strong** cut at $0.30
separates the cheap open-weight coders that route onto flat-bundle /
free legs (deepseek-v4-flash $0.14/$0.28 blended ~$0.21; qwen3-coder
~$0.16 blended; glm-4.x-flash sub-$0.30) from the mid-tier workhorses
(glm-5.2 $0.42/$1.32 promo, blended ~$0.87; kimi-k2.6; minimax-m3
~$0.75 blended) that sit in the $0.30–$1.50 band. The
**strong/frontier** cut at $1.50 separates those mid-tier workhorses
from genuine frontier-priced models (claude-opus-4-8, gpt-5.5,
gemini-3.1-pro all blend well above $1.50). A model priced at exactly
a threshold rounds UP to the more expensive band (conservative for
budget-tap purposes — a $0.30 model is `strong`, not `economy`).

### Price input — the `price_per_mtok` map

The $/Mtok figure itself comes from an explicit `price_per_mtok: dict
[str, float]` map keyed by model id — the blended $/Mtok for that id's
cheapest-known live provider. `PROVIDER-BEST-PER-MODEL.md` is the
human-curated source for these numbers (live-verified provider prices,
URLs cited); a machine-readable copy of the table is a separately-owned
downstream concern (not in this ticket's `owns:`). For the live
`assign()` path today, an injected price map is the input seam —
callable callers (the dispatcher in `fleet-droid.sh`, the selftest,
tests) pass the map; ids not present in the map and not in the curated
catalog return `unknown` (fail-closed, surfaced in the rationale, NOT
silently admitted).

### The spill-up cost ceiling — the money-path COST CAP

`fleet/fleet-droid.sh`'s resolver (`resolve_runnable_chain`) SPILLS UP
this axis when a cost band has no runnable model: tier is a capability
FLOOR, so work escalates to a costlier band rather than backlogging on
a band whose whole chain is detained or gateway-capped. That escalation
must be BOUNDED. Without a cap, a run of capped/exhausted cheap legs —
a free-tier window closing, a funding drain parking a provider — walks
work into the most expensive band and KEEPS it there, and nothing in
the loop can say no. The cap is the most expensive band a COST-driven
spill-up may escalate INTO:

    SPILL_UP_COST_CEILING = strong

Read from THIS file by `fleet-droid.sh` (`spill_ceiling_tier`). The
value must be one of the canonical bands above. `strong` means
escalation is allowed up to the mid-band workhorses (blended
< $1.50/Mtok by the threshold table above) and NO further: entering the
`frontier` band (>= $1.50/Mtok) is an operator decision, made by
raising this line, not an automatic consequence of a cheap leg going
dark. A ticket that DECLARES a band at or above the ceiling still runs
in its own declared band — the cap governs ESCALATION, never the band
the operator explicitly asked for.

**FAIL CLOSED.** If this key is missing, blank, malformed, or names a
band that is not on the axis, the dispatcher does NOT fall back to a
default and does NOT run uncapped: cost-driven spill-up is DISABLED
entirely (ceiling := the ticket's own starting band), loudly, with a
`cost-cap-config-invalid` row in the provider-exhaustion ledger. There
is deliberately NO in-code default — an in-code fallback would be a
second source of truth and would turn "config absent" into "silently
uncapped", which is the exact hole this cap closes.

**On a cap hit the work DETAINS, it does not fail and does not
escalate**: the resolver returns 7, the claim loop releases the ticket,
and it stays claimable so it retries when a cheaper leg frees. Each hit
prints a greppable `COST-CAP:` line and writes a `cost-cap-detain` row
to `fleet/provider-exhaustion-ledger.tsv`, and burns one loop-guard
attempt, so a permanently capped ticket is quarantined and surfaced
rather than looping forever.

**One deliberate carve-out.** A band that is unrunnable because its
whole chain is HARD-DETAINED for the ticket's `work_class` (a model
that fabricated on money-path work) escalates ABOVE the ceiling: that
is a SAFETY escalation, and the established semantics are that
money-path detention escalates — "cheap" is never an argument for
running a model proven to fabricate. That hop is loud and is ledgered
as `cost-cap-bypass-detention`, so it is observable, not a silent hole.
Only capped/exhausted (cost) escalation is bounded by the ceiling.

### "tier-appropriate difficulty" — defined concretely

MODEL-PREFLIGHT.md's staged ladder (R0/R1/R2/R3) says "difficulty
scaled to the tier" without ever pinning the mapping — that is the
conflation F-tier flags. TIER-CANON resolves it:

**Rungs and cost-band tiers are the SAME axis, ordered.** A rung IS a
difficulty level, and a tier is a CONTIGUOUS RANGE of rung
difficulties. The ladder has calibrated difficulty levels (an
item-bank quantity owned by EVAL-PIPELINE-CONSOLIDATE, not here); a
cost-band tier says which rung-range a model's preflight draws from:

    economy   -> R0 + R1 only        (cheap models never need to clear R2/R3)
    strong    -> R0 + R1 + R2         (the routing-decision band; needs R2 to
                                       discriminate glm/kimi/mimo/deepseek-flash)
    frontier  -> R0 + R1 + R2 + R3    (only frontier-priced models are asked to
                                       clear the hardest rung; R3 LOCATES the
                                       ceiling — MODEL-PREFLIGHT.md:31)

R0 (the cheap leg canary) is run for EVERY tier — reachability +
throughput + gross-degradation control is tier-agnostic. The "tier-
appropriate difficulty" MODEL-PREFLIGHT.md:27 references is therefore
CONCRETE: a model's cost-band tier selects the set of rungs its
preflight climb is allowed to draw items from. A model priced in the
economy band is never asked to clear R3; a frontier-priced model is
climbed through all four. This makes the ramp's "tier-appropriate"
adjective machine-checkable (a future EVAL-PIPELINE-CONSOLIDATE runner
reads this table to know which rungs to draw for a candidate) instead
of aspirational prose.

The item-bank difficulty levels themselves (the calibrated numeric
difficulty each rung spans) are owned by
EVAL-PIPELINE-CONSOLIDATE/F9 (the adaptive runner), NOT by this
ticket. TIER-CANON fixes the rung→tier MAPPING; the per-rung
calibration is a downstream, separately-owned quantity. This split is
the same one EVAL-TAXONOMY.md makes: own the axis + the mapping, not
the downstream calibration data.

## DISAMBIGUATION — two "tier" meanings that MUST NOT be conflated

The review (`MODEL-TESTING-ADVERSARIAL-REVIEW.md` F9(c), F-tier) and
the handoff drift audit (`HANDOFF-REVIEW-quinlan-vos.md` M2) both flag
that "tier" is used two incompatible ways across two different-owner
tickets. TIER-CANON pins them apart:

| Meaning | Direction | Defined where | Owned by |
|---|---|---|---|
| **COST-BAND tier** (economy/strong/frontier) | **INPUT** — how expensive a model is, knowable before any run | **this file** (`TIER-CANON.md`) | EVAL-TIER-CANON |
| **CEILING-GRADE band** (Frontier/Strong/Capable/Basic/No-Tier) | **OUTPUT** — how capable a model proved, measured by the ramp | `fleet/benchmark/lib/tier_chart.py:23-28` `TIER_LADDER` | EVAL-PIPELINE-CONSOLIDATE (F9) |

These are DIFFERENT axes with DIFFERENT names on purpose. The
cost-band tier is lowercase-cased (`economy/strong/frontier`); the
ceiling-grade band is Title-Cased (`Frontier/Strong/Capable/Basic/No
Tier`) and has FIVE buckets, not three. A `strong` (cost) model can
land a `Frontier` ceiling grade (deepseek-v4-flash priced in the
strong band but near-frontier on SWE-bench — see `model_catalog.py`
note for `gemini-3-flash` "punches above its tier"); a `frontier`
(cost) model can land a `Capable` ceiling (an expensive model that
underperforms). The two are correlated in practice but NOT identical
and NOT derivable from each other.

### How the ceiling-grade OUTPUT maps back onto the cost band

**They are independent — the ceiling grade does NOT redefine the cost
band.** The cost band is an input property of a model (its price) and
is stable across runs. The ceiling grade is a measured property (its
proven capability on the item bank) and can move run-to-run as data
accrues. A model's cost band is whatever TIER-CANON.md's $/Mtok rule
says it is, full stop — regardless of where its ceiling lands. The
ceiling grade FEEDS ASSIGNMENT DECISIONS (a `frontier`-cost model with
a `Basic` ceiling should lose to a `strong`-cost model with a
`Strong` ceiling — that is the rank math `assign.py`/`grades.py`
already do via the real-outcome score), but it never REASSIGNS the
cost-band label.

Concretely for EVAL-PIPELINE-CONSOLIDATE (the downstream owner): the
adaptive runner may treat difficulty-band as a *secondary annotation*
on a candidate (start it near its cost-band's rung range, per the
table above, then search up/down), but the *cost band itself* is read
from this file and is never overwritten by the ramp's output. If a
future ticket wants the ceiling grade to FEED BACK into a model's
routing tier, that is a NEW axis (e.g. "routed-tier" = cost band ×
ceiling grade) and must be declared as a new field, not silently
collapsed into the cost-band column — the exact conflation F-tier
exists to prevent.

## What changed in `fleet/capability/assign.py`

- **Uncatalogued id now resolves its tier from the cost band, not a
  silent pass-through.** Previously `assign.py:117` excluded a
  candidate only when `tier_hint is not None and tier_hint != req_tier`
  — so any id not in `model_catalog.py` (hy3-preview-or, free-mistral-
  code, gemma-4-31b-cb, the deepseek-v4-pro-ds variants the sweep
  uses…) returned `None` from `get_tier_hint()` and SILENTLY passed the
  tier filter regardless of cost. The review calls this out as the
  F-tier/MED gap: `--tier strong` was admitting every uncatalogued id.
  Now `assign.py` calls a new `resolve_cost_tier(blended_per_mtok)`
  (thresholds read from this file) on ids the curated catalog does NOT
  cover, using a caller-injected `price_per_mtok: dict[str, float]` map
  as the price input. This is the load-bearing fix.
- **Fail-closed is OPT-IN via `price_per_mtok`.** Providing a map (even
  an empty `{}`) activates fail-closed cost-band resolution: an id in
  neither the catalog nor the map is `unknown` and EXCLUDED against a
  `--tier` filter (surfaced in the rationale as "tier unknown", NOT
  silently admitted). Omitting the map (`None`, the default) keeps the
  pre-fix pass-through behavior for backward compat — the dispatcher's
  real-outcome ranking path (`fleet-droid.sh`'s `assign_reorder_chain`)
  and tests with synthetic uncatalogued ids see unchanged behavior
  unless they explicitly opt in. This opt-in seam lets the F-tier fix
  land without forcing every existing caller to wire a price map
  simultaneously; the live dispatcher wiring (fleet-droid.sh passing
  its price table) is a separately-owned downstream concern.
- **Thresholds are read from TIER-CANON.md, not hardcoded in
  assign.py.** `load_tier_canon_thresholds()` parses the
  `TIER_COST_THRESHOLDS` block above at runtime (same lockstep +
  drift-guard discipline `EVAL-TAXONOMY.md`/`selftest.py` already use
  for the canonical class set). A revert that hardcodes the
  thresholds in assign.py while the doc drifts is caught by the
  selftest drift guard below.
- **Catalog tier_hint still wins** for the 15 curated ids — the
  curated `model_catalog.py` `tier_hint` field is a human-verified
  cost-band assignment that is allowed to override the $/Mtok rule
  (e.g. a promo-priced frontier model that is temporarily cheap still
  routes as frontier because the operator said so). This keeps
  `catalog_for_tier` / `charon tier resolve` semantics unchanged. The
  cost-band rule only kicks in for ids the catalog does NOT cover.
- **`price_per_mtok` is an injected seam, not a global.** `assign()`
  takes an optional `price_per_mtok: Mapping[str, float] | None`
  parameter (defaults to `None` = pass-through). The CLI exposes
  `--price-map id=price,...` for ad-hoc use; the live dispatcher wiring
  (fleet-droid.sh passing its price table) is a separately-owned
  downstream concern.

## What changed in `fleet/tier-models.tsv`

The header now names TIER-CANON.md as the source of truth for the
three tier names and their cost-band definition, and explicitly flags
that the file's PROVISIONAL status (no workhorse finalized — see
memory: charon-no-workhorse-finalized) is orthogonal to the
cost-band definition: the tiers themselves are stable, the per-tier
failover CHAIN is what is provisional. The chain rows are unchanged
in content (no model-id edits — that is an operator decision, not
this ticket's `owns`).

## Fail-on-revert (`fleet/capability/selftest.py`)

1. **An uncatalogued, economy-priced model resolves `tier=economy`.**
   The test injects a `price_per_mtok` map with a sub-$0.30 blended
   price for an id NOT in `model_catalog.py` and asserts the resolved
   tier is `economy`. Reverting the cost-band fallback (so
   `resolve_model_tier` returns None for uncatalogued ids again) makes
   the test fail: the resolved tier would be `unknown` instead of
   `economy`.
2. **A `--tier strong` query EXCLUDES a frontier-priced model.**
   The test injects a `price_per_mtok` with a >=$1.50 blended price
   for an uncatalogued id and asserts `assign(..., required_tier=
   "strong", price_per_mtok=...)` excludes it with a tier-mismatch
   reason. Reverting the cost-band fallback makes a frontier-priced
   uncatalogued id silently pass the strong-tier filter — the test
   fails because the id appears in the eligible pick set instead of the
   excluded set.
3. **Drift guard: assign.py's threshold source == TIER-CANON.md.**
   `load_tier_canon_thresholds()` parses the thresholds block above
   at runtime. Mutating TIER-CANON.md's threshold values (or
   hardcoding divergent thresholds in assign.py) makes the
   drift-guard assertion fail — the doc is the single source, code
   reads it, neither hardcodes.

## Known, deliberately UNTOUCHED residual (out of this ticket's scope)

- `model_catalog.py`'s curated `tier_hint` is a human-verified
  approximation of the cost band for the 15 cataloged ids; it is NOT
  re-derived from $/Mtok here (re-deriving would touch
  `/home/stack/code/charon/src/charon/model_catalog.py` — the PRODUCT
  repo, not this rig, and not in this ticket's `owns:`). The cost-band
  rule only kicks in for UNCATALOGUED ids; cataloged ids keep their
  curated tier_hint verbatim. A future ticket may reconcile the
  catalog's tier_hint against live $/Mtok data; that is a
  catalog-parity check (memory: always-fix-catalog-mismatches), not a
  TIER-CANON concern.
- The scorecard `tier` column (a 0–4 benchmark difficulty index, per
  `model-scorecard.tsv` header line 4) is a THIRD meaning of "tier"
  that this ticket does NOT touch — it is the per-row difficulty tag
  the benchmark sections use, unrelated to the cost band. Renaming it
  to `difficulty` would touch `model-scorecard.sh`/`enqueue-capture.sh`
  (neither owned here) and is tracked separately. TIER-CANON.md names
  it to disambiguate, not to redefine it.
- The `fleet/tier-models.tsv` per-tier failover CHAIN contents (which
  model ids sit in which tier's failover list) remain PROVISIONAL and
  operator-gated — this ticket defines what the tier names MEAN, not
  which models populate them. Reordering the chains is an operator
  decision gated on real benchmark data the ramp
  (EVAL-PIPELINE-CONSOLIDATE) will produce.
