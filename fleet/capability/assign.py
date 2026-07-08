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

CLI:
  assign.py --work-class ci-infra
  assign.py --work-class money-path --tier strong
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
    req_tier = resolve_tier_alias(required_tier) if required_tier else None

    ranked: list[Candidate] = []
    for m in models:
        g = grades.grade(m, wc)
        if g is None:
            continue
        tier_hint = get_tier_hint(m)
        avail = availability.status(m)
        excluded = None
        if req_tier and tier_hint is not None and tier_hint != req_tier:
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

    result = assign(work_class, grades, availability, required_tier=required_tier, blockers=blockers)

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
