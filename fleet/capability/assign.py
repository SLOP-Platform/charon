#!/usr/bin/env python3
"""assign() — ticket -> best agent/model, with a human-readable rationale.

Build #14 (ticket->best-agent AUTO-ASSIGNMENT, rig-level WCI). First consumer
of the shared capability brain (capability/grades.py's GradesProvider +
capability/availability.py's AvailabilityProvider) that the gateway routing
path will later reuse — see fleet/POOLS-REDESIGN-ADR-v2.md, "Grades table:
two consumers".

Ranking, deterministic and explainable:
  1. D&S gate: a ticket with unmet depends_on is REFUSED, never assigned.
  2. Grade every candidate model at the ticket's work_class (generalist
     fallback if the model has no direct data for that class).
  3. Filter by cost-tier (if the ticket declares one) and by availability
     (session-bridge: exclude only models resolved as 'busy'; 'unknown'
     passes through — see availability.py's documented gap).
  4. Sort eligible candidates by score desc, then mean_bench_score desc,
     then mean_cost_usd asc, then mean_time_s asc, then model id (stable).
  5. Pick #1; the rationale names the runner-up and any top-ranked-but-
     excluded candidate so the recommendation is auditable, not a black box.

EVAL-TIER-CANON (review F-tier fix): step 3's cost-tier filter used to
silently no-op for any id not in `model_catalog.py` — `get_tier_hint()`
returned None for uncatalogued ids (hy3-preview-or, the -ds/-together
sweep variants, every benchmark-only id) and the filter admitted them
regardless of the requested `--tier`. Now an uncatalogued id resolves
its tier from the COST BAND via a caller-injected `price_per_mtok` map
($/Mtok thresholds parsed from fleet/state/TIER-CANON.md, never
hardcoded here). Catalog `tier_hint` still wins for the 15 curated ids;
with no price map and no catalog entry an id is `unknown`, surfaced in
the rationale and treated fail-CLOSED against a `--tier` filter (excluded
with "tier unknown", not silently admitted). See TIER-CANON.md for the
canonical tier axis definition + the rung/tier disambiguation.

CLI:
  assign.py --work-class ci-infra
  assign.py --work-class money-path --tier strong
  assign.py --work-class money-path --tier strong --price-map glm-5.2=0.87,hy3-preview-or=2.10
  assign.py TICKET-ID                    # reads board/<ID>.md's tier/depends_on
  assign.py TICKET-ID --work-class routing   # override/declare work_class
  assign.py TICKET-ID --claim SESSION_ID     # after recommending, claim via bridge
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grades import (  # noqa: E402
    GENERALIST, WORK_CLASSES, GradesProvider, ScorecardGradesProvider,
    get_tier_hint, resolve_tier_alias,
)
from availability import (  # noqa: E402
    AvailabilityProvider, SessionBridgeAvailability, StaticAvailability,
)

FLEET_DIR = Path(__file__).resolve().parent.parent
BOARD_DIR = FLEET_DIR / "board"
DONE_DIR = FLEET_DIR / "state" / "done"

# ---------------------------------------------------------------------------
# EVAL-TIER-CANON (review F-tier fix): canonical cost-band tier resolution.
# fleet/state/TIER-CANON.md is the SINGLE SOURCE OF TRUTH for the cost-band
# tier axis (economy/strong/frontier by $/Mtok thresholds). assign.py reads
# TIER-CANON.md's threshold block at runtime — never hardcodes the numbers —
# so a doc edit takes effect immediately (same lockstep + drift-guard
# discipline EVAL-TAXONOMY.md/grades.py already use for the canonical
# work-class set). See TIER-CANON.md for the full axis definition, the
# rung<->tier mapping, and the disambiguation between the cost-band INPUT
# (defined here) and the CEILING-GRADE OUTPUT (defined in
# fleet/benchmark/lib/tier_chart.py:23-28 TIER_LADDER, owned by
# EVAL-PIPELINE-CONSOLIDATE).
# ---------------------------------------------------------------------------
TIER_CANON_MD = FLEET_DIR / "state" / "TIER-CANON.md"

# Canonical cost-band tier names (lowercase — distinct from the Title-Case
# ceiling-grade band in tier_chart.py on purpose; see TIER-CANON.md's
# disambiguation table). These fold to the product router's low/med/high via
# resolve_tier_alias() (frontier->high, strong->med, economy->low).
CANONICAL_COST_TIERS: tuple[str, ...] = ("economy", "strong", "frontier")

# Reverse of grades.py's _ALIASES: low/med/high (the catalog's tier_hint
# vocabulary, and what resolve_tier_alias() folds legacy synonyms to) ->
# canonical cost-band names (economy/strong/frontier). Kept here, not in
# grades.py, because the cost-band axis is TIER-CANON.md's definition
# (grades.py owns only the alias fold, not the cost-band rule). Used in
# assign() to normalize BOTH the required tier and the model's resolved
# tier into the SAME namespace before comparing.
_LMH_TO_COSTTIER: dict[str, str] = {"low": "economy", "med": "strong", "high": "frontier"}

_tier_canon_thresholds: list[tuple[float, str]] | None = None


def load_tier_canon_thresholds(canon_md: Path = TIER_CANON_MD) -> list[tuple[float, str]]:
    """Parse the `TIER_COST_THRESHOLDS = (...)` block from TIER-CANON.md.

    Returns a list of (threshold_usd_per_mtok, tier_name) tuples, ordered
    HIGH-threshold-first (so a caller can walk down: blended >= first
    threshold -> first tier; else >= second -> second tier; etc.). The doc
    is the single source — code never hardcodes these numbers, and the
    selftest drift-guard asserts the parsed values match what the doc says.

    Format expected in TIER-CANON.md (one tuple per line, threshold first,
    then a comma, then the tier name in double quotes, optional trailing
    comment after `#`):

        TIER_COST_THRESHOLDS = (
            (1.50, "frontier"),   # blended $/Mtok >= 1.50  -> frontier
            (0.30, "strong"),     # 0.30 <= blended < 1.50  -> strong
            (0.00, "economy"),    # 0.00 <= blended < 0.30  -> economy
        )

    Tolerates whitespace variations. Raises ValueError if the block is
    missing or malformed (fail-loud at call time, not a silent default —
    a drifted TIER-CANON.md must surface, not fall back to a stale copy).
    """
    global _tier_canon_thresholds
    if _tier_canon_thresholds is not None:
        return _tier_canon_thresholds
    text = canon_md.read_text() if canon_md.exists() else ""
    # Match `TIER_COST_THRESHOLDS = ( ... )` — the outermost paren block,
    # which contains inner `(float, "tier")` tuples. A non-greedy `.*?`
    # with DOTALL plus the closing `)` on its own line (4-space indent by
    # doc convention) isolates the block without false-stopping on the
    # tuple-internal closing parens like `[^)]*` would.
    m = re.search(
        r"TIER_COST_THRESHOLDS\s*=\s*\((.*?)\)\s*\n",
        text, re.DOTALL,
    )
    if not m:
        raise ValueError(
            f"TIER-CANON.md ({canon_md}) is missing the TIER_COST_THRESHOLDS block — "
            f"cannot resolve cost-band tiers. Restore the block per fleet/state/TIER-CANON.md."
        )
    out: list[tuple[float, str]] = []
    # Within the captured block, find every `(float, "tiername")` tuple.
    # This is robust to the tuples being on one line each (the doc
    # convention) or comma-separated on one line, and to inline `#`
    # comments (they cannot contain a `)` so they don't break the match).
    for tm in re.finditer(
        r"\(\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*\"([a-z]+)\"\s*\)",
        m.group(1),
    ):
        out.append((float(tm.group(1)), tm.group(2)))
    if not out:
        raise ValueError(
            f"TIER-CANON.md ({canon_md}): TIER_COST_THRESHOLDS block has no "
            f"(threshold, \"tier\") tuples — needs at least one row."
        )
    # Order HIGH-threshold-first so callers walk down. The doc conventionally
    # lists them high->low already (frontier/strong/economy); sort defensively
    # so a doc reorder doesn't change the resolution semantics.
    out.sort(key=lambda t: -t[0])
    _tier_canon_thresholds = out
    return out


def resolve_cost_tier(blended_per_mtok: float,
                      thresholds: list[tuple[float, str]] | None = None) -> str:
    """Resolve a blended $/Mtok to its canonical cost-band tier using
    TIER-CANON.md's thresholds. A price at exactly a threshold rounds UP
    to the more expensive band (>= test, conservative for budget-tap
    purposes — a $0.30 model is `strong`, not `economy`)."""
    th = thresholds if thresholds is not None else load_tier_canon_thresholds()
    for threshold, tier in th:  # already high-first
        if blended_per_mtok >= threshold:
            return tier
    # Below every threshold's floor — the last (lowest-threshold) tier is the
    # floor band. With the conventional doc block, $0.00 is the economy floor,
    # so a non-negative price always resolves (a negative price would be a
    # data error; treat it as the floor band rather than crash).
    return th[-1][1] if th else "economy"


def resolve_model_tier(model: str,
                       price_per_mtok: Mapping[str, float] | None = None) -> str | None:
    """Resolve a model id to its canonical cost-band tier (economy/strong/
    frontier), or None if it cannot be resolved.

    Two paths, in priority order (see TIER-CANON.md "What changed in
    assign.py"):

      1. Curated catalog `tier_hint` WINS for the 15 cataloged ids
         (operator-verified cost-band assignment; keeps `catalog_for_tier`/
         `charon tier resolve` semantics unchanged). The catalog returns
         low/med/high — folded to the canonical cost-band names via
         `_LMH_TO_COSTTIER` below.
      2. COST-BAND fallback for UNCATALOGUED ids: when a `price_per_mtok`
         map is provided, look the id up in it; if present, apply
         `resolve_cost_tier()` to the blended $/Mtok. This is the
         F-tier/MED fix — previously these ids returned None and silently
         passed the tier filter.
      3. Neither path resolves -> None. The caller (assign()) decides
         whether None means fail-closed-exclude or pass-through, based on
         whether cost-band resolution was opted into (map provided) or
         not (None) — see assign()'s `fail_closed_on_unknown` docstring.

    `price_per_mtok` defaults to None (pass-through for uncatalogued ids,
    preserving pre-EVAL-TIER-CANON backward compat). Providing a map —
    even an empty `{}` — opts into fail-closed resolution in assign().
    """
    # Path 1: curated catalog (low/med/high -> economy/strong/frontier).
    hint = get_tier_hint(model)
    if hint is not None:
        return _LMH_TO_COSTTIER.get(hint)
    # Path 2: cost-band fallback for uncatalogued ids (only when a
    # non-empty price map is provided).
    if price_per_mtok:
        price = price_per_mtok.get(model)
        if price is not None:
            return resolve_cost_tier(float(price))
    # Path 3: unresolved -> None. assign() decides fail-closed vs pass-through.
    return None


@dataclass
class Candidate:
    model: str
    grade: object          # grades.Grade
    tier_hint: str | None
    availability: str
    excluded_reason: str | None = None


@dataclass
class AssignResult:
    work_class: str
    picked: str | None
    rationale: str
    ranked: list = field(default_factory=list)
    refused: bool = False
    refuse_reason: str | None = None


def _sort_key(c: Candidate):
    g = c.grade
    return (
        # Should-fix #3 (#14 review, Q1 tail): a generalist-fallback grade
        # (no direct work_class evidence) is NOT ranked head-to-head as an
        # equal peer to a direct-work_class grade, even if its raw score is
        # higher — direct evidence, however thin, is preferred over an
        # aggregate borrowed from unrelated work_classes. False (direct)
        # sorts before True (fallback).
        g.fallback_used,
        -g.score,
        -(g.mean_bench_score if g.mean_bench_score is not None else 0.0),
        g.mean_cost_usd if g.mean_cost_usd is not None else float("inf"),
        g.mean_time_s if g.mean_time_s is not None else float("inf"),
        c.model,
    )


def assign(
    work_class: str,
    grades: GradesProvider,
    availability: AvailabilityProvider,
    required_tier: str | None = None,
    blockers: list[str] | None = None,
    candidate_models: list[str] | None = None,
    price_per_mtok: Mapping[str, float] | None = None,
) -> AssignResult:
    blockers = blockers or []
    if blockers:
        return AssignResult(
            work_class=work_class, picked=None,
            rationale=f"REFUSED — blocked on: {', '.join(blockers)} "
                      f"(D&S standing rule: never assign a blocked ticket)",
            refused=True, refuse_reason="blocked",
        )

    wc = work_class if work_class in WORK_CLASSES or work_class == GENERALIST else GENERALIST
    models = candidate_models if candidate_models is not None else grades.all_models()
    # EVAL-TIER-CANON: normalize the required tier into the canonical cost-band
    # namespace (economy/strong/frontier). resolve_tier_alias() folds legacy
    # synonyms (high/opus, med/sonnet, low/haiku) to low/med/high; we then map
    # those to the cost-band names via _LMH_TO_COSTTIER so the comparison is
    # in ONE namespace. A user passing --tier frontier directly is already in
    # the cost-band namespace (resolve_tier_alias folds it to high) — round-
    # tripped to "frontier" here. This is the single normalization point.
    req_alias = resolve_tier_alias(required_tier) if required_tier else None
    req_tier = _LMH_TO_COSTTIER.get(req_alias) if req_alias else None

    # EVAL-TIER-CANON: when the caller provides a price_per_mtok map, the
    # tier filter is fail-CLOSED for uncatalogued ids — an id in neither the
    # catalog nor the map is `unknown` and EXCLUDED (the F-tier/MED fix:
    # "make an uncatalogued id resolve its tier from the cost band, not
    # silently pass"). When NO price map is provided, uncatalogued ids keep
    # their pre-fix pass-through behavior (tier_hint=None -> not excluded)
    # so callers that don't opt into cost-band resolution see unchanged
    # behavior (the dispatcher's real-outcome ranking path, tests with
    # synthetic uncatalogued ids). The fail-closed path is OPT-IN via the
    # price_per_mtok parameter: providing a map (even an empty one {})
    # activates fail-closed; omitting it (None) keeps pass-through.
    fail_closed_on_unknown = price_per_mtok is not None

    ranked: list[Candidate] = []
    for m in models:
        g = grades.grade(m, wc)
        if g is None:
            continue
        # EVAL-TIER-CANON: resolve the model's cost-band tier. Catalog
        # tier_hint wins for cataloged ids; uncatalogued ids fall back to
        # the cost-band rule via the caller-injected price_per_mtok map;
        # neither resolves -> tier_hint stays None (handled below).
        tier_hint = resolve_model_tier(m, price_per_mtok)
        avail = availability.status(m)
        excluded = None
        if req_tier and tier_hint is None and fail_closed_on_unknown:
            # An uncatalogued id with no price data, AGAINST a --tier filter,
            # with cost-band resolution opted in: fail-CLOSED (exclude with a
            # surfaced reason). Pre-EVAL-TIER-CANON this case silently passed.
            excluded = (f"tier unknown (uncatalogued, no price data; "
                        f"ticket requires {req_tier})")
        elif req_tier and tier_hint is not None and tier_hint != req_tier:
            excluded = f"tier mismatch (model={tier_hint}, ticket requires {req_tier})"
        elif avail == "busy":
            excluded = "unavailable (session-bridge: busy)"
        ranked.append(Candidate(m, g, tier_hint, avail, excluded))

    ranked.sort(key=_sort_key)
    eligible = [c for c in ranked if c.excluded_reason is None]

    if not eligible:
        return AssignResult(
            work_class=wc, picked=None,
            rationale="REFUSED — no eligible candidate (all excluded by tier/availability, "
                      "or no scorecard data for any candidate at this work_class)",
            ranked=ranked, refused=True, refuse_reason="no-eligible",
        )

    picked = eligible[0]
    rationale = _rationale(picked, wc, eligible, ranked)
    return AssignResult(work_class=wc, picked=picked.model, rationale=rationale, ranked=ranked)


def _rationale(picked: Candidate, wc: str, eligible: list[Candidate], ranked: list[Candidate]) -> str:
    lines = [f"PICK: {picked.model}  (work_class={wc})", f"  {picked.grade.summary()}"]
    if picked.tier_hint:
        lines.append(f"  tier={picked.tier_hint}")
    lines.append(f"  availability={picked.availability}")

    runner_up = eligible[1] if len(eligible) > 1 else None
    if runner_up:
        lines.append(f"  runner-up: {runner_up.grade.summary()}")

    # Surface anyone who out-scored the pick but got excluded — this is the
    # anti-black-box check: a reader can see WHY the top-graded model wasn't chosen.
    for c in ranked:
        if c.excluded_reason and c is not picked:
            if c.grade.score >= picked.grade.score:
                lines.append(f"  NOTE: {c.model} scored >= pick but was EXCLUDED: {c.excluded_reason}")

    # Same anti-black-box principle for the fallback de-prioritization
    # (should-fix #3): if a generalist-fallback candidate out-scored the
    # (direct-evidence) pick, say so — it wasn't dropped silently, it was
    # deliberately ranked behind direct work_class evidence.
    if not picked.grade.fallback_used:
        for c in eligible:
            if c is not picked and c.grade.fallback_used and c.grade.score > picked.grade.score:
                lines.append(f"  NOTE: {c.model} scored higher via generalist fallback "
                             f"(no direct {wc} evidence) — ranked below the direct-evidence pick")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ticket board-file meta reading (mirrors fleet/board.sh's `meta()` awk
# pattern: first line starting "key: " wins; continuation lines ignored —
# sufficient for tier/depends_on/work_class, which are always single-line).
# ---------------------------------------------------------------------------
_META_RE = re.compile(r"^([a-zA-Z_-]+):\s?(.*)$")


def read_ticket_meta(ticket_id: str) -> dict[str, str] | None:
    # case-insensitive match against board/*.md basenames, like _lib.sh's canon()
    match = None
    for f in BOARD_DIR.glob("*.md"):
        if f.stem.lower() == ticket_id.lower():
            match = f
            break
    if match is None:
        return None
    meta: dict[str, str] = {}
    for line in match.read_text().splitlines():
        m = _META_RE.match(line)
        if m and m.group(1) not in meta:
            meta[m.group(1)] = m.group(2).strip()
    meta["_id"] = match.stem
    return meta


def unmet_deps(depends_on: str) -> list[str]:
    if not depends_on:
        return []
    unmet = []
    for raw in depends_on.split(","):
        dep_id = raw.strip()
        if not dep_id:
            continue
        canon = next((f.stem for f in BOARD_DIR.glob("*.md") if f.stem.lower() == dep_id.lower()), dep_id)
        if not (DONE_DIR / canon).exists():
            unmet.append(canon)
    return unmet


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket", nargs="?", help="board ticket id (e.g. SR-13); optional")
    ap.add_argument("--work-class", choices=list(WORK_CLASSES) + [GENERALIST],
                     help="declare/override work_class (required if no ticket, or ticket has none declared)")
    ap.add_argument("--tier", help="required cost tier (frontier/strong/economy, or low/med/high)")
    ap.add_argument("--claim", metavar="SESSION_ID",
                     help="after recommending, claim the ticket on session-bridge as SESSION_ID (requires a ticket id)")
    ap.add_argument("--tsv", default=None, help="override model-scorecard.tsv path (mainly for tests)")
    ap.add_argument("--live-availability", action="store_true",
                     help="query the live session-bridge for availability (default: unknown for all, since MVP has no live model-tagged sessions to differentiate on — see build report)")
    # S4 (Gap A rig facet): fleet-droid.sh's tier dispatcher consumer seam. It already owns a
    # vetted, gateway-proven model set per tier (fleet/tier-models.tsv); it must never let a
    # real-outcome recommendation introduce a DIFFERENT, unlisted model id into a gateway call.
    # --candidates restricts ranking to exactly that set (threads straight into assign()'s
    # existing candidate_models param); --print-model gives a plain, script-friendly single
    # line (the picked model id, nothing else) instead of the human rationale, so a caller can
    # do `model="$(assign.py ... --print-model)"` and treat a non-zero exit as "no real-outcome
    # recommendation available — fall back to your own static ordering."
    ap.add_argument("--candidates", metavar="M1,M2,...",
                     help="restrict ranking to this comma-separated candidate model-id set")
    ap.add_argument("--print-model", action="store_true",
                     help="print ONLY the picked model id to stdout (nothing if refused); "
                          "suppresses the human rationale. Exit 0 on a pick, 1 on refusal.")
    # EVAL-TIER-CANON: the cost-band tier resolver for UNCATALOGUED ids (ids
    # not in model_catalog.py). Format: id=blended_$/Mtok,id=price,... e.g.
    # `--price-map hy3-preview-or=2.10,free-mistral-code=0.18`. Cataloged ids
    # ignore this (their curated tier_hint wins); an id in neither the catalog
    # nor this map is `unknown` and fail-CLOSED against a --tier filter (excluded,
    # surfaced in the rationale — the F-tier/MED fix that replaced the prior
    # silent pass-through). The live dispatcher wiring (fleet-droid.sh passing
    # its price table) is a separately-owned downstream concern; this CLI flag
    # is the ad-hoc/test seam.
    ap.add_argument("--price-map", default=None,
                     help="blended $/Mtok per model id for uncatalogued-id cost-tier resolution "
                          "(format: id=price,id=price,...); see fleet/state/TIER-CANON.md")
    args = ap.parse_args(argv)

    work_class = args.work_class
    required_tier = args.tier
    blockers: list[str] = []
    ticket_id = None

    if args.ticket:
        meta = read_ticket_meta(args.ticket)
        if meta is None:
            print(f"error: no board ticket matching '{args.ticket}'", file=sys.stderr)
            return 2
        ticket_id = meta["_id"]
        work_class = work_class or meta.get("work_class")
        required_tier = required_tier or meta.get("tier")
        blockers = unmet_deps(meta.get("depends_on", ""))
        if work_class is None:
            print(f"NOTE: ticket {ticket_id} declares no work_class meta key — "
                  f"using generalist default. Pass --work-class to be specific.", file=sys.stderr)
            work_class = GENERALIST

    if work_class is None:
        ap.error("--work-class is required when no ticket is given (or the ticket declares none)")

    grades = ScorecardGradesProvider(args.tsv) if args.tsv else ScorecardGradesProvider()
    availability: AvailabilityProvider
    availability = SessionBridgeAvailability() if args.live_availability else StaticAvailability()

    candidate_models = None
    if args.candidates:
        candidate_models = [m.strip() for m in args.candidates.split(",") if m.strip()]

    # EVAL-TIER-CANON: parse the optional price map (id=price pairs). None
    # when not provided -> uncatalogued ids keep their pre-fix pass-through
    # behavior (the dispatcher's real-outcome path, tests with synthetic
    # uncatalogued ids see unchanged behavior). A map (even empty {}) opts
    # INTO fail-closed cost-band resolution.
    price_per_mtok: dict[str, float] | None = None
    if args.price_map:
        price_per_mtok = {}
        for pair in args.price_map.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            mid, _, pstr = pair.partition("=")
            mid = mid.strip()
            pstr = pstr.strip()
            if not mid:
                continue
            try:
                price_per_mtok[mid] = float(pstr)
            except ValueError:
                ap.error(f"--price-map: {pair!r} has a non-numeric price {pstr!r}")

    result = assign(work_class, grades, availability, required_tier=required_tier, blockers=blockers,
                     candidate_models=candidate_models,
                     price_per_mtok=price_per_mtok)

    if args.print_model:
        # Machine-readable mode ONLY — no rationale, no claim side-effect. A dispatcher-side
        # caller (fleet-droid.sh's assign_reorder_chain) wants exactly one thing: is there a
        # real-outcome pick, yes/no, and if so which model id.
        if result.picked:
            print(result.picked)
            return 0
        return 1

    if ticket_id:
        print(f"TICKET: {ticket_id}")
    print(result.rationale)
    if availability.note():
        print(f"  (availability source: {availability.note()})")

    if result.refused:
        return 1

    if args.claim:
        if not ticket_id:
            print("error: --claim requires a ticket id (positional arg)", file=sys.stderr)
            return 2
        import json
        import subprocess
        from availability import PROXY_PATH
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "claim", "arguments": {"session_id": args.claim, "ticket": ticket_id}}}
        try:
            p = subprocess.run(["python3", PROXY_PATH], input=json.dumps(req) + "\n",
                                capture_output=True, text=True, timeout=10)
            print(f"CLAIM: {p.stdout.strip().splitlines()[-1] if p.stdout.strip() else '(no response)'}")
        except Exception as e:
            print(f"CLAIM FAILED: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
