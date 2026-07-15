#!/usr/bin/env python3
"""budget-derive.py — DERIVED latency/wall-clock budgets for the eval pipeline
(EVAL-DERIVED-BUDGETS, review F8).

Replaces the arbitrary rung/latency budgets (3/6/10 min, 480/900s) documented
in fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md §F8 with budgets DERIVED
from the OBSERVED completion-time distribution of KNOWN-GOOD models, then
NORMALIZED per-leg via token / measured tok_s so a fast leg and a slow leg on
the SAME task get fair, different wall-clocks instead of one flat number.

Design of record: fleet/state/PREFLIGHT-DESIGN-V2.md §LATENCY-BUDGET.
Taxonomy source: fleet/state/EVAL-TAXONOMY.md (canonical work_class).

TWO-PART RULE (F8):
  (a) budget  = p95(good_model_completion_times) + margin
               where margin = 0.5 * p95  (i.e. total = 1.5 * p95)
  (b) wall(leg) = token_budget / measured_tok_s(leg) + fixed_overhead

  (a) is the per-(work_class × difficulty) ceiling; (b) is the per-run,
  per-leg normalization that makes "too-slow" mean "too much work" (a model
  that needs more tokens than the good-model p95 — thrashing/looping — or
  stalls), NOT "unlucky low-throughput leg" (F8 finding (c)).

INPUTS (all read-only; this tool NEVER writes the live scorecard):
  - model-scorecard.tsv (model-scorecard.sh ledger): col layout
        date source ref work_class tier model verdict gate score
        time_s cost_usd corrections note tokens_in tokens_out stage
    KNOWN-GOOD row = source in {live, bench, bench2} AND verdict == MERGE
    AND stage == active (a provisional MERGE is not yet trustworthy).
    time_s (col 10) is the wall-clock seconds the runner itself bracketed.
    tokens_out (col 15, may be "-") is the good-model OUTPUT token count.
  - dogfood-eval result-card SUMMARY.md (dogfood-eval.sh writes one per
    ticket-run): a markdown table with columns
        | model | verdict | attribution | wall_s | budget_s | gate | ...
    KNOWN-GOOD row = verdict starts with "REVIEW-READY" (dogfood-to-scorecard.sh
    maps REVIEW-READY -> MERGE, so this is the same known-good definition as
    the scorecard's, captured before the finalize step folds it).
  - LEG-RANK.tsv (leg-preflight.sh writes it): tab-separated
        model leg reachable canary_score latency_s tok_s verdict date
    tok_s (col 6) is the per-leg throughput measured by the canary.

OUTPUT: a small budgets.tsv keyed (canonical_work_class, difficulty) with:
    work_class  difficulty  n_good  p95_time_s  wall_budget_s  token_budget  status
  - wall_budget_s = p95_time_s * 1.5  (the SLOW-LEG reference ceiling)
  - token_budget  = p95(good tokens_out)  (or derived from wall*ref tok_s)
  - status = "derived" | "insufficient-data" (zero good rows -> safe default)

A caller with no LEG-RANK.tsv uses wall_budget_s directly (graceful degrade);
a caller with it divides token_budget by the leg's tok_s and adds the
fixed_overhead for the fair per-run ceiling (the F8(b) win).

Canonical work_class join: scorecard/result-card rows tagged in the fleet
ticket-shape vocabulary (bugfix, ci-infra, routing, refactor, tests, ...) are
resolved to the product-router canonical vocabulary via _LEGACY_TO_CANONICAL
(the SAME table EVAL-TAXONOMY-ALIGN placed in grades.py — duplicated verbatim
per that file's duplication discipline; both are literal copies of the SSOT
table in fleet/state/EVAL-TAXONOMY.md). A budget keyed on a fleet class the
router never queries would be useless to the router — this is the
EVAL-TAXONOMY-ALIGN dependency made load-bearing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable

BENCH_DIR = Path(__file__).resolve().parent
FLEET_DIR = BENCH_DIR.parent
DEFAULT_SCORECARD = FLEET_DIR / "model-scorecard.tsv"
DEFAULT_LEG_RANK = FLEET_DIR / "state" / "LEG-RANK.tsv"
DEFAULT_RESULTS_DIR = FLEET_DIR / "state" / "dogfood-eval" / "results"
DEFAULT_OUT = FLEET_DIR / "state" / "budgets.tsv"

# ── F8 rule constants ──────────────────────────────────────────────────────
# margin = 0.5 * p95  =>  total budget = 1.5 * p95  (F8: "p95 + margin, e.g. 1.5x")
MARGIN_FACTOR = 0.5
# fixed overhead in the wall = tokens/tok_s + overhead formula. Covers worktree
# setup, gate fork, mtime settle — NOT a second latency budget. 20s matches
# BENCH_MTIME_STABLE_SEC and the leg-preflight probe order of magnitude.
FIXED_OVERHEAD_S = 20.0
# reference leg throughput for the wall->token fallback (when tokens_out is "-"
# across the board). Picked as a conservative midrange of observed canary tok_s
# so the derived token budget is finite and sane, never 0.
REFERENCE_TOK_S = 40.0
# Safe-default ceiling when a (work_class, difficulty) bucket has ZERO
# known-good rows. NOT presented as derived (status=insufficient-data) — this
# is the highest of the old arbitrary numbers, used as a ceiling-not-cliff so
# the DETAIN threshold (F1/F4) is never absent on an uncalibrated class.
DEFAULT_WALL_S = 900.0
DEFAULT_TOKEN_BUDGET = 12000.0
# KNOWN-GOOD verdict filters.
SCORECARD_GOOD_VERDICT = "MERGE"          # source=live/bench/bench2 + stage=active
RESULTCARD_GOOD_VERDICT_PREFIX = "REVIEW-READY"   # dogfood-eval overall verdict

# ── canonical taxonomy (EVAL-TAXONOMY.md, single source of truth) ──────────
# Verbatim copy of the _LEGACY_TO_CANONICAL table in grades.py (per that
# file's duplication discipline). An import-time assertion below cross-checks
# the canonical set against EVAL-TAXONOMY.md's documented line.
CANONICAL_WORK_CLASSES = (
    "reasoning", "coding", "translation", "creative", "analysis", "general",
)
_LEGACY_TO_CANONICAL: dict[str, str] = {
    "money-path": "coding",
    "routing": "coding",
    "ci-infra": "coding",
    "refactor": "coding",
    "bugfix": "coding",
    "tests": "coding",
    "greenfield-feature": "coding",
    "frontend": "coding",
    "design-review": "analysis",
    "docs": "general",
    "rig-meta": "general",
    # canonical-native pass-through (a row already tagged `coding` stays `coding`).
    "reasoning": "reasoning",
    "translation": "translation",
    "creative": "creative",
    "analysis": "analysis",
    "general": "general",
}


def _canonical_of(raw: str) -> str | None:
    """Resolve either vocabulary to a canonical bucket. Returns None for an
    unknown class (caller skips rather than silently bucketing as 'general')."""
    if raw in CANONICAL_WORK_CLASSES:
        return raw
    return _LEGACY_TO_CANONICAL.get(raw)


def _assert_canonical_set_matches_taxonomy(doc: Path) -> None:
    """Drift guard: the CANONICAL_WORK_CLASSES tuple above must equal the
    canonical class set documented in EVAL-TAXONOMY.md. Best-effort — if the
    doc is absent or the line moved, this is a warning, not a crash (the
    tuple itself is still the operative SSOT for this module)."""
    if not doc.exists():
        print(
            f"budget-derive: WARN: {doc} not found — canonical-set drift check "
            f"skipped (CANONICAL_WORK_CLASSES tuple is still operative).",
            file=sys.stderr,
        )
        return
    needle = "CANONICAL_CLASSES = "
    for line in doc.read_text().splitlines():
        s = line.strip()
        if s.startswith(needle):
            tail = s[len(needle):].strip()
            # tolerate trailing comment / whitespace
            tail = tail.split("#", 1)[0].strip().rstrip(",")
            documented = tuple(tail.split(", "))
            documented = tuple(x for x in documented if x)
            if set(documented) != set(CANONICAL_WORK_CLASSES):
                print(
                    f"budget-derive: WARN: {doc} canonical set {documented} != "
                    f"code tuple {CANONICAL_WORK_CLASSES} — drift; code wins.",
                    file=sys.stderr,
                )
            return


_ASSERT_DOC = FLEET_DIR / "state" / "EVAL-TAXONOMY.md"
_assert_canonical_set_matches_taxonomy(_ASSERT_DOC)


# ---------------------------------------------------------------------------
# p95 + margin derivation (F8 part a)
# ---------------------------------------------------------------------------
def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile. pct in [0,100]. Empty -> 0.0.

    Uses the same nearest-rank-ish interpolation as numpy's default
    ('linear'): for a sorted sample, p95 lands between the 95th-percentile
    fence posts. This is intentionally pure-stdlib (numpy is NOT available in
    the privileged core; promote.py precedent).
    """
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return s[lo]
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def derive_budget(good_times: list[float]) -> tuple[float, str]:
    """F8(a): budget = p95(good_times) + margin, margin = 0.5 * p95.

    Returns (wall_budget_s, status). status is 'derived' when there is data,
    'insufficient-data' when good_times is empty (caller gets a safe default
    — see DEFAULT_WALL_S — NOT a silently-zero budget that would DETAIN every
    model on an uncalibrated class).
    """
    if not good_times:
        return DEFAULT_WALL_S, "insufficient-data"
    p95 = percentile(good_times, 95.0)
    if p95 <= 0:
        return DEFAULT_WALL_S, "insufficient-data"
    return p95 * (1.0 + MARGIN_FACTOR), "derived"


def derive_token_budget(
    good_tokens_out: list[float], good_times: list[float]
) -> float:
    """F8(b): token_budget = p95(good tokens_out). Falls back to
    p95(good wall_s) * REFERENCE_TOK_S when no token data exists (the common
    case today — tokens_in/out were added later and many rows are '-')."""
    if good_tokens_out:
        tb = percentile(good_tokens_out, 95.0)
        if tb > 0:
            return tb
    if good_times:
        return percentile(good_times, 95.0) * REFERENCE_TOK_S
    return DEFAULT_TOKEN_BUDGET


def wall_for_leg(token_budget: float, tok_s: float) -> float:
    """F8(b) per-leg normalized wall-clock ceiling:
        wall(leg) = token_budget / tok_s + fixed_overhead

    A leg with 2x tok_s gets ~1/2 the streaming wall for the SAME token
    budget (the FAIL-ON-REVERT invariant). tok_s <= 0 (an unreachable/unmeasured
    leg) falls back to DEFAULT_WALL_S so the caller still has a number for
    F1/F4's DETAIN threshold."""
    if tok_s <= 0:
        return DEFAULT_WALL_S
    return token_budget / tok_s + FIXED_OVERHEAD_S


# ---------------------------------------------------------------------------
# scorecard.tsv reader (model-scorecard.sh ledger)
# ---------------------------------------------------------------------------
# column indices (1-based in the header comment of model-scorecard.sh; 0-based here)
_SC_DATE, _SC_SOURCE, _SC_REF, _SC_WCLASS = 0, 1, 2, 3
_SC_TIER, _SC_MODEL, _SC_VERDICT, _SC_GATE = 4, 5, 6, 7
_SC_SCORE, _SC_TIME_S, _SC_COST, _SC_CORR = 8, 9, 10, 11
_SC_NOTE, _SC_TOK_IN, _SC_TOK_OUT, _SC_STAGE = 12, 13, 14, 15
_REAL_OUTCOME_SOURCES = {"live", "bench", "bench2"}


def _is_good_scorecard_row(cols: list[str]) -> bool:
    """KNOWN-GOOD scorecard row = real-outcome source + verdict MERGE + active
    stage. A provisional MERGE is not yet trustworthy; a FIXES/BLOCK/DETAIN
    row is exactly the too-slow tail we must NOT let raise the p95."""
    if len(cols) <= _SC_VERDICT:
        return False
    if cols[_SC_SOURCE] not in _REAL_OUTCOME_SOURCES:
        return False
    if cols[_SC_VERDICT] != SCORECARD_GOOD_VERDICT:
        return False
    stage = cols[_SC_STAGE] if len(cols) > _SC_STAGE and cols[_SC_STAGE] else "active"
    return stage == "active"


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s or s == "-":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v >= 0 else None


def read_scorecard(
    path: Path | str = DEFAULT_SCORECARD,
) -> list[dict]:
    """Parse model-scorecard.tsv -> list of good-row dicts with keys:
    work_class_raw, time_s, tokens_out. Only KNOWN-GOOD rows are returned
    (the budget is over the GOOD-model distribution; bad rows are irrelevant)."""
    path = Path(path)
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if not _is_good_scorecard_row(cols):
            continue
        wc_raw = cols[_SC_WCLASS] if len(cols) > _SC_WCLASS else ""
        time_s = _parse_float(cols[_SC_TIME_S]) if len(cols) > _SC_TIME_S else None
        tok_out = _parse_float(cols[_SC_TOK_OUT]) if len(cols) > _SC_TOK_OUT else None
        rows.append({"work_class_raw": wc_raw, "time_s": time_s, "tokens_out": tok_out})
    return rows


# ---------------------------------------------------------------------------
# dogfood-eval result-card SUMMARY.md reader (wall_s)
# ---------------------------------------------------------------------------
def _parse_md_table_row(line: str) -> list[str] | None:
    """Parse a markdown table data row `| a | b | c |` -> ['a','b','c'].
    Returns None for separators, headers, or non-table lines."""
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|"):
        return None
    inner = s[1:-1]
    cells = [c.strip() for c in inner.split("|")]
    # separator row like |---|---|
    if cells and all(set(c) <= set("-: ") and c for c in cells):
        return None
    return cells


def read_result_cards(results_dir: Path | str = DEFAULT_RESULTS_DIR) -> list[dict]:
    """Parse every *-SUMMARY.md under results_dir -> good-row dicts with keys:
    work_class_raw, time_s (from wall_s), tokens_out (None — result cards don't
    carry output tokens; the scorecard is the token source).

    The result card's `verdict` column holds dogfood-eval's overall verdict;
    REVIEW-READY is the known-good definition (dogfood-to-scorecard.sh maps it
    to MERGE). DETAIN(latency)/RETRY/BLOCKED/FIXES-NEEDED rows are excluded."""
    results_dir = Path(results_dir)
    rows: list[dict] = []
    if not results_dir.exists():
        return rows
    for card in sorted(results_dir.glob("*-SUMMARY.md")):
        # work_class_raw: derive from the filename prefix (ticket label) only
        # if the table itself doesn't carry it. The result-card table does NOT
        # tag work_class per row, so a summary is attributable to the TICKET's
        # work_class at run-time; since we don't have that here, we leave
        # work_class_raw="" and let the canonical resolver skip it (the
        # scorecard is the primary source; result cards are supplementary).
        _consume_summary(card, rows)
    return rows


def _consume_summary(card: Path, rows: list[dict]) -> None:
    """Read one SUMMARY.md, appending good wall_s rows to `rows`."""
    try:
        text = card.read_text()
    except OSError:
        return
    header_idx: dict[str, int] | None = None
    for line in text.splitlines():
        cells = _parse_md_table_row(line)
        if cells is None:
            continue
        if header_idx is None:
            # first table row is the header
            lowered = [c.lower() for c in cells]
            if "model" in lowered and "verdict" in lowered and "wall_s" in lowered:
                header_idx = lower_to_index(lowered)
            continue
        # separator row is skipped by _parse_md_table_row already
        if len(cells) <= max(header_idx.values()):
            continue
        verdict = cells[header_idx["verdict"]]
        if not verdict.startswith(RESULTCARD_GOOD_VERDICT_PREFIX):
            continue
        wall = _parse_float(cells[header_idx["wall_s"]])
        if wall is None:
            continue
        rows.append({
            "work_class_raw": "",
            "time_s": wall,
            "tokens_out": None,   # result cards don't carry output tokens
        })


def lower_to_index(lowered: list[str]) -> dict[str, int]:
    """Build a {column-name: index} map from a lowered header row."""
    idx: dict[str, int] = {}
    for i, name in enumerate(lowered):
        if name not in idx:
            idx[name] = i
    return idx


# ---------------------------------------------------------------------------
# LEG-RANK.tsv reader (per-leg tok_s)
# ---------------------------------------------------------------------------
# columns: model leg reachable canary_score latency_s tok_s verdict date
_LR_MODEL, _LR_LEG, _LR_REACH, _LR_SCORE, _LR_LAT, _LR_TOKS, _LR_VR = 0, 1, 2, 3, 4, 5, 6


def read_leg_rank(path: Path | str = DEFAULT_LEG_RANK) -> dict[tuple[str, str], float]:
    """Parse LEG-RANK.tsv -> {(model, leg): tok_s}. The file is append-only;
    later rows are newer, so the LAST row per (model, leg) wins (matches
    leg-preflight.sh --gate's own 'latest row' semantics)."""
    path = Path(path)
    out: dict[tuple[str, str], float] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) <= _LR_TOKS:
            continue
        if cols[_LR_MODEL] == "model":
            continue
        model, leg = cols[_LR_MODEL], cols[_LR_LEG]
        toks = _parse_float(cols[_LR_TOKS])
        if toks is None:
            continue
        out[(model, leg)] = toks
    return out


# ---------------------------------------------------------------------------
# per-bucket derivation
# ---------------------------------------------------------------------------
def _bucket_key(work_class_raw: str, difficulty: int) -> tuple[str, int] | None:
    """Resolve a raw work_class to canonical and pair with difficulty. Returns
    None if the class is unknown (the row is skipped — never silently bucketed
    as 'general', which would dilute the general bucket with mislabeled data)."""
    canon = _canonical_of(work_class_raw)
    if canon is None:
        return None
    return (canon, difficulty)


def derive_all(
    scorecard_rows: list[dict],
    resultcard_rows: list[dict],
    difficulty: int,
) -> list[dict]:
    """Derive a budget row per (canonical_work_class, difficulty) present in the
    union of scorecard + result-card good rows. Returns a list of dicts with
    keys: work_class, difficulty, n_good, p95_time_s, wall_budget_s,
    token_budget, status. Buckets with zero good rows are emitted with
    status='insufficient-data' IF they're in the canonical set (so a caller
    sees every canonical class even before it has data)."""
    times: dict[tuple[str, int], list[float]] = {}
    toks: dict[tuple[str, int], list[float]] = {}
    # union both sources; result-card rows have work_class_raw="" so they only
    # contribute to buckets they can be attributed to (they can't, here — they
    # get skipped, which is correct: a result card without a work_class can't
    # raise a per-class budget. They DO feed the global fallback if needed.)
    for r in scorecard_rows + resultcard_rows:
        key = _bucket_key(r.get("work_class_raw", ""), difficulty)
        if key is None:
            continue
        t = r.get("time_s")
        if t is not None:
            times.setdefault(key, []).append(t)
        tk = r.get("tokens_out")
        if tk is not None:
            toks.setdefault(key, []).append(tk)

    out: list[dict] = []
    # always emit every canonical class so a caller sees the full surface
    for wc in CANONICAL_WORK_CLASSES:
        key = (wc, difficulty)
        gt = times.get(key, [])
        gk = toks.get(key, [])
        wall, status = derive_budget(gt)
        p95 = percentile(gt, 95.0) if gt else 0.0
        tb = derive_token_budget(gk, gt)
        out.append({
            "work_class": wc,
            "difficulty": difficulty,
            "n_good": len(gt),
            "p95_time_s": round(p95, 1),
            "wall_budget_s": round(wall, 1),
            "token_budget": round(tb, 1),
            "status": status,
        })
    return out


def write_budgets_tsv(budgets: Iterable[dict], path: Path | str) -> None:
    """Write the budgets.tsv table. Tab-separated; header + one row per
    (work_class, difficulty). A leading comment block documents the rule so a
    human reading the file sees the derivation, not just the numbers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# DERIVED eval budgets (EVAL-DERIVED-BUDGETS, review F8).",
        "# Rule: budget = p95(good_model_completion) + margin, margin = 0.5*p95 (total 1.5x).",
        "# Per-leg wall = token_budget / measured_tok_s(leg) + fixed_overhead_s(20).",
        "# Source: model-scorecard.tsv time_s + dogfood-eval result-card wall_s (KNOWN-GOOD only).",
        "# status=insufficient-data -> safe default (not derived); calibrate before trusting.",
    ]
    lines.append(
        "work_class\tdifficulty\tn_good\tp95_time_s\twall_budget_s\ttoken_budget\tstatus"
    )
    for b in budgets:
        lines.append(
            f"{b['work_class']}\t{b['difficulty']}\t{b['n_good']}\t"
            f"{b['p95_time_s']}\t{b['wall_budget_s']}\t{b['token_budget']}\t{b['status']}"
        )
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="budget-derive.py",
        description=(
            "Derive eval budgets (p95+margin, token/tok_s-normalized) from "
            "observed known-good model completion times. See "
            "fleet/state/PREFLIGHT-DESIGN-V2.md §LATENCY-BUDGET."
        ),
    )
    p.add_argument(
        "--scorecard", type=Path, default=DEFAULT_SCORECARD,
        help=f"model-scorecard.tsv path (default: {DEFAULT_SCORECARD})",
    )
    p.add_argument(
        "--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
        help=f"dogfood-eval results dir (default: {DEFAULT_RESULTS_DIR})",
    )
    p.add_argument(
        "--leg-rank", type=Path, default=DEFAULT_LEG_RANK,
        help=f"LEG-RANK.tsv path (default: {DEFAULT_LEG_RANK})",
    )
    p.add_argument(
        "--difficulty", type=int, default=2,
        help="difficulty tier on the rung ladder (default: 2 = mid)",
    )
    p.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"output budgets.tsv path (default: {DEFAULT_OUT})",
    )
    p.add_argument(
        "--json", action="store_true",
        help="emit JSON to stdout instead of writing budgets.tsv",
    )
    p.add_argument(
        "--wall-for-leg", type=str, default="",
        help="compute the per-run wall-clock for a specific leg id "
             "(format: model/tok_s or model,tok_s or just tok_s). "
             "Requires --token-budget or a derived budget for the class.",
    )
    p.add_argument(
        "--token-budget", type=float, default=0.0,
        help="token budget to use with --wall-for-leg (overrides derived).",
    )
    p.add_argument(
        "--work-class", type=str, default="coding",
        help="canonical work_class for --wall-for-leg budget lookup "
             "(default: coding).",
    )
    return p


def _parse_leg_spec(spec: str) -> tuple[str, float]:
    """Parse 'model/tok_s', 'model,tok_s', or just 'tok_s' into
    (model, tok_s). An empty model is fine (the caller only needs tok_s)."""
    s = spec.replace(",", "/")
    parts = [p.strip() for p in s.split("/") if p.strip()]
    if len(parts) == 1:
        return "", float(parts[0])
    if len(parts) == 2:
        return parts[0], float(parts[1])
    raise SystemExit(f"bad --wall-for-leg spec '{spec}' (use model/tok_s or tok_s)")


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    sc_rows = read_scorecard(args.scorecard)
    rc_rows = read_result_cards(args.results_dir)

    # --wall-for-leg: one-off per-run ceiling (the F8(b) normalization)
    if args.wall_for_leg:
        model, tok_s = _parse_leg_spec(args.wall_for_leg)
        token_budget = args.token_budget
        if token_budget <= 0:
            # look up the derived token_budget for (work_class, difficulty)
            budgets = derive_all(sc_rows, rc_rows, args.difficulty)
            for b in budgets:
                if b["work_class"] == args.work_class:
                    token_budget = b["token_budget"]
                    break
        if token_budget <= 0:
            token_budget = DEFAULT_TOKEN_BUDGET
        wall = wall_for_leg(token_budget, tok_s)
        print(json.dumps({
            "model": model or "(unspecified)",
            "tok_s": tok_s,
            "token_budget": token_budget,
            "fixed_overhead_s": FIXED_OVERHEAD_S,
            "wall_budget_s": round(wall, 1),
            "rule": "token_budget / tok_s + fixed_overhead_s",
        }))
        return 0

    budgets = derive_all(sc_rows, rc_rows, args.difficulty)
    if args.json:
        print(json.dumps({
            "rule": {
                "budget": "p95(good) * 1.5",
                "wall_for_leg": "token_budget / tok_s + fixed_overhead_s",
                "margin_factor": MARGIN_FACTOR,
                "fixed_overhead_s": FIXED_OVERHEAD_S,
            },
            "budgets": budgets,
        }, indent=2))
        return 0

    write_budgets_tsv(budgets, args.out)
    print(f"derived {len(budgets)} budget rows -> {args.out}")
    for b in budgets:
        flag = "" if b["status"] == "derived" else "  <-- needs calibration data"
        print(
            f"  {b['work_class']:12s} D{b['difficulty']} "
            f"n_good={b['n_good']:3d}  p95={b['p95_time_s']:7.1f}s  "
            f"wall={b['wall_budget_s']:7.1f}s  tokens={b['token_budget']:8.1f}"
            f"  [{b['status']}]{flag}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
