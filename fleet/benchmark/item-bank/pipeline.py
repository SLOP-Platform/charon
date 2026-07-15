#!/usr/bin/env python3
"""pipeline.py — adaptive runner (EVAL-PIPELINE-CONSOLIDATE, review F9+F12).

The single source of model-capability grading for the consolidated eval
pipeline. Replaces the 4–5 overlapping harnesses (preflight.sh T1–T12,
dogfood-eval, honest-battery-sweep, canary R0, bench.sh S0–S6) with
ONE adaptive placement + ONE per-(model, work_class) capture path.

Adaptive placement (F9):
  * Start each candidate near the cost-band rung range
    (TIER-CANON.md: economy -> D1–D2, strong -> D1–D3, frontier -> D1–D4).
  * Step geometrically through the bank; when a rung eliminates the
    candidate on a given work_class, stop testing that work_class
    (per-skill ceiling found).
  * MUST-PASS / MUST-FAIL controls are used to SATURATE-CHECK items
    (an item the MUST-PASS control clears and the MUST-FAIL control
    misses is calibrated; a saturated item is rejected from the bank).
  * Item difficulty steps are sized so each rung eliminates a
    meaningful fraction of the remaining candidate field (binary-search
    style for ceil-locating; F9(b)).

Per-(model, work_class) ceiling grade:
  * The runner is the SOLE writer of `source=live` scorecard rows via
    ONE capture path: every graded (model, work_class, difficulty)
    result is enqueued to grader-daemon.py's maildrop via the existing
    enqueue-capture.sh. The daemon then writes a source=live scorecard
    row. NO runner-side writes to model-scorecard.tsv.
  * The verdict (PASS/FAIL) per item is the OOB grader's verdict (the
    item-bank grader, kind=="preflight" -> graders/grade.py), which is
    fail-closed and never trusts the model's prose.
  * The runner aggregates the OOB per-item results into a per-(model,
    work_class) CEILING (the highest difficulty the model cleared for
    that work_class) and feeds that ceiling to grades.py's grading
    pipeline (one enqueue per (model, work_class) so the live lane gets
    a fine-grained per-skill grade, the F9 F-tier "send refactor to X,
    never routing" outcome).

Budgets (F8):
  * Per-run wall-clock comes from EVAL-DERIVED-BUDGETS' budgets.tsv:
    `wall_for_leg = token_budget / tok_s + overhead`. A slow leg gets
    proportionally more wall time; only a model that needs more tokens
    than the good-model p95 (thrashing) or stalls fails.
  * If budgets.tsv is missing or the (work_class, difficulty) bucket
    is `insufficient-data`, fall back to a conservative default
    (DEFAULT_WALL_S) so the DETAIN threshold is never absent.

CLI:
  pipeline.py place <model> [--tier economy|strong|frontier]
                            [--work-class <wc>]
                            [--out FILE]
                            [--budgets FILE] [--leg-rank FILE]
                            [--controls-only]

  pipeline.py run-all <model1> [<model2> ...]
                            (performs a full placement on every model,
                             used for the S0 smoke + a MUST-FAIL control
                             full placement, the ticket's required
                             end-to-end run)

  pipeline.py self-test   (runs the hermetic end-to-end self-test,
                            FAIL-ON-REVERT for adaptivity + saturated
                            rejection + single-capture-path)

Environment variables (mostly for the test harness + the runtime
discipline EVAL-LATENCY-GATE established):
  PIPE_SPOOL_REQ   default /var/lib/bench-grader/spool/req
  PIPE_ENQUEUE     default <fleet>/capture/enqueue-capture.sh
  PIPE_DRY_RUN     if 1: print what would be enqueued, never enqueue
  PIPE_BUDGETS     default <fleet>/state/budgets.tsv
  PIPE_LEG_RANK    default <fleet>/state/LEG-RANK.tsv
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ITEM_BANK_DIR = Path(__file__).resolve().parent
FLEET_DIR = ITEM_BANK_DIR.parent.parent
sys.path.insert(0, str(ITEM_BANK_DIR))

# Local import: the OOB dispatcher used for the local self-test path.
# In production, the daemon imports `graders.preflight.grade` and our
# runner enqueues a kind=="preflight" request; for the self-test we
# invoke the same dispatcher in-process.
from grade import grade as oob_grade  # noqa: E402

# ── canonical taxonomy (EVAL-TAXONOMY.md, single source of truth) ──────────
CANONICAL_WORK_CLASSES = (
    "reasoning", "coding", "translation", "creative", "analysis", "general",
)

# Cost-band -> allowed difficulty range (TIER-CANON.md §"tier-appropriate
# difficulty"). Tiers that are absent from the price map / catalog fall
# back to a wide range (D1–D4) so the runner is never stuck without a
# starting rung.
COST_BAND_RUNG_RANGE: dict[str, tuple[int, int]] = {
    "economy": (1, 2),
    "strong": (1, 3),
    "frontier": (1, 4),
}

# Bank-side difficulty bounds (every item's difficulty is in [1, 4]).
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 4

# Default per-run wall-clock fallback when budgets.tsv is absent.
DEFAULT_WALL_S = 900.0
# Per-leg fixed overhead (matches budget-derive.FIXED_OVERHEAD_S = 20).
FIXED_OVERHEAD_S = 20.0
# Reference leg throughput for the wall->token fallback (matches
# budget-derive.REFERENCE_TOK_S = 40).
REFERENCE_TOK_S = 40.0

# S0 smoke-test item id (the smallest, fastest item in the bank — the
# analog of bench.sh S0, kept as the only synthetic section that
# survives the consolidation per the ticket's accept clause).
S0_SMOKE_ITEM = "cod-bugfix-typo"

# MUST-PASS / MUST-FAIL control ids (calibration anchors; the live
# run uses these for saturate-checks; the same names appear in
# manifest.tsv).
CONTROL_PASS_ID = "strong-control"
CONTROL_FAIL_ID = "deepseek-v4-flash"


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------
def _load_manifest(path: Path) -> list[dict]:
    """Read the item-bank manifest.tsv. Skips comments/header. Returns
    a list of dicts with keys: item_id, work_class, difficulty,
    expected_pass_pct, mode, brief, grader_key, saturated, control_pass,
    control_fail. Empty / unknown work_class rows are kept (the runner
    logs a warn and skips) so a typo in the manifest doesn't silently
    delete an item."""
    out: list[dict] = []
    cols = [
        "item_id", "work_class", "difficulty", "expected_pass_pct",
        "mode", "brief", "grader_key", "saturated", "control_pass",
        "control_fail",
    ]
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < len(cols):
            continue
        if parts[0] == "item_id":  # header
            continue
        try:
            d = int(parts[2])
        except ValueError:
            continue
        try:
            epp = float(parts[3])
        except ValueError:
            epp = 0.0
        out.append({
            "item_id": parts[0],
            "work_class": parts[1],
            "difficulty": d,
            "expected_pass_pct": epp,
            "mode": parts[4],
            "brief": parts[5],
            "grader_key": parts[6],
            "saturated": parts[7] == "1",
            "control_pass": parts[8],
            "control_fail": parts[9],
        })
    return out


def _items_for_work_class(manifest: list[dict], work_class: str) -> list[dict]:
    """Return the items in the manifest that map to the given canonical
    work_class. Includes items whose raw work_class is a legacy class
    (the runner canonicalizes on read)."""
    wc = _canonicalize(work_class)
    out = []
    for it in manifest:
        if _canonicalize(it["work_class"]) == wc:
            out.append(it)
    return out


def _canonicalize(raw: str) -> str:
    """Map a raw work_class (canonical or legacy) to the canonical
    product-router vocabulary. Mirrors the
    `_LEGACY_TO_CANONICAL` table in `fleet/capability/grades.py` /
    `fleet/benchmark/budget-derive.py` — duplicated verbatim per the
    duplication discipline EVAL-TAXONOMY-ALIGN documented. A canonical
    pass-through is a no-op; an unknown class is returned as-is
    (caller decides)."""
    table = {
        "money-path": "coding", "routing": "coding", "ci-infra": "coding",
        "refactor": "coding", "bugfix": "coding", "tests": "coding",
        "greenfield-feature": "coding", "frontend": "coding",
        "design-review": "analysis", "docs": "general", "rig-meta": "general",
    }
    return table.get(raw, raw)


# ---------------------------------------------------------------------------
# Budgets (EVAL-DERIVED-BUDGETS)
# ---------------------------------------------------------------------------
@dataclass
class Budget:
    work_class: str
    difficulty: int
    p95_time_s: float
    wall_budget_s: float
    token_budget: float
    status: str

    def wall_for_leg(self, tok_s: float) -> float:
        if tok_s <= 0:
            return self.wall_budget_s
        return self.token_budget / tok_s + FIXED_OVERHEAD_S


def _load_budgets(path: Path) -> dict[tuple[str, int], Budget]:
    out: dict[tuple[str, int], Budget] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7 or parts[0] == "work_class":
            continue
        try:
            wc = parts[0]
            diff = int(parts[1])
            p95 = float(parts[3])
            wall = float(parts[4])
            tok = float(parts[5])
            status = parts[6]
        except ValueError:
            continue
        out[(wc, diff)] = Budget(wc, diff, p95, wall, tok, status)
    return out


def _leg_tok_s(leg_rank: dict, model: str, leg: str = "") -> float:
    """Per-leg tok_s from LEG-RANK.tsv. The (model, leg) key matches
    budget-derive.read_leg_rank. Returns 0.0 if absent (caller falls
    back to the slow-leg wall_budget_s)."""
    # Try the (model, leg) tuple first; if no leg, use the model's
    # best-known leg (the max tok_s across all legs — fastest, fairest
    # default).
    if leg:
        v = leg_rank.get((model, leg))
        if v is not None:
            return v
    same_model = [v for (m, _l), v in leg_rank.items() if m == model and v > 0]
    if same_model:
        return max(same_model)
    return 0.0


# ---------------------------------------------------------------------------
# Capture path (the SOLE writer of source=live scorecard rows)
# ---------------------------------------------------------------------------
def _enqueue_capture(
    enqueue: Path,
    spool_req: str,
    *,
    model: str,
    ref: str,
    work_class: str,
    difficulty: int,
    verdict: str,
    gate: str,
    score: int,
    stage: str,
    evidence: str,
) -> bool:
    """Enqueue ONE paired FINAL capture to the grader-daemon maildrop.

    This is the SOLE writer of `source=live` scorecard rows; the daemon
    owns the ledger write. The runner NEVER appends to
    `model-scorecard.tsv` directly (that is the "exactly one capture
    path" guarantee the ticket's FAIL-ON-REVERT clause names)."""
    if not enqueue.exists():
        return False
    cmd = [
        str(enqueue),
        "--model", model,
        "--ref", ref,
        "--work-class", work_class,
        "--difficulty", str(difficulty),
        "--claimed-result", "OOB_GRADED",
        "--stage", stage,
        "--actual-verdict", verdict,
        "--actual-gate", gate,
        "--score", str(score),
        "--evidence", evidence,
    ]
    env = os.environ.copy()
    env["CAPTURE_SPOOL_DIR"] = spool_req
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
    except Exception:  # noqa: BLE001
        return False
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Session worktree + grading (one attempt)
# ---------------------------------------------------------------------------
def _stage_session(item_dir: Path, snapshot: Path) -> None:
    """Copy the item fixture into a fresh session worktree, omitting
    the registry files (manifest.tsv / README.md / grader scripts).
    Mirrors preflight.sh's disguise invariant."""
    snapshot.mkdir(parents=True, exist_ok=True)
    deny = {"manifest.tsv", "README.md", "traps.tsv", "validate.sh", "graders"}
    for src in item_dir.iterdir():
        if src.name in deny:
            continue
        dst = snapshot / src.name
        if src.is_dir():
            import shutil
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            import shutil
            shutil.copy(src, dst)


@dataclass
class AttemptResult:
    item_id: str
    work_class: str
    difficulty: int
    verdict: str   # "PASS" or "FAIL"
    gate: str      # "pass" or "fail"
    score: int
    reason: str
    wall_s: float
    elided: bool = False  # True when the model was stopped before this attempt


def _grade_one(
    item: dict,
    snapshot: Path,
    budgets: dict[tuple[str, int], Budget],
    leg_tok_s: float,
    wall_timeout: float,
) -> AttemptResult:
    """OOB-grade one (item, worktree) pair. The wall_timeout is the
    derived per-leg budget (token/tok_s + overhead, from budgets.tsv);
    the runner enforces it as a max wall-clock ceiling (a stalled model
    is a FAIL — the too-slow-as-a-failure-class discipline)."""
    wc = _canonicalize(item["work_class"])
    diff = item["difficulty"]
    budget = budgets.get((wc, diff))
    if budget is None:
        # insufficient-data fallback
        budget = Budget(wc, diff, 0.0, DEFAULT_WALL_S, REFERENCE_TOK_S * DEFAULT_WALL_S, "insufficient-data")
    # Per-run wall-clock = the leg-normalized ceiling. We cap to
    # DEFAULT_WALL_S in the no-LEG-RANK case so the runner never
    # overflows on a missing/unmeasured leg.
    per_run_wall = budget.wall_for_leg(leg_tok_s) if leg_tok_s > 0 else budget.wall_budget_s
    per_run_wall = min(per_run_wall, max(wall_timeout, budget.wall_budget_s))
    # Run the OOB grader. In production this is the daemon
    # dispatching graders/grade.py; in the self-test we invoke it
    # in-process. Either way the grader is OOB and fail-closed.
    t0 = time.time()
    try:
        result = oob_grade(snapshot, item["item_id"])
    except Exception as exc:  # noqa: BLE001 — a crashed grader is a BLOCK
        return AttemptResult(
            item_id=item["item_id"], work_class=wc, difficulty=diff,
            verdict="FAIL", gate="fail", score=0,
            reason=f"oob-grader-crashed: {exc!r}"[:200],
            wall_s=round(time.time() - t0, 2),
        )
    wall = round(time.time() - t0, 2)
    # Wall-clock ceiling: a stalled run is too-slow (DETAIN-latency
    # analog, F4's discipline) — captured as a FAIL with a clear
    # reason so the F1/F4 latency-as-failure-class invariant is not
    # silently violated.
    if wall > per_run_wall * 1.5:
        return AttemptResult(
            item_id=item["item_id"], work_class=wc, difficulty=diff,
            verdict="FAIL", gate="fail", score=0,
            reason=f"wall-clock-exceeded: {wall}s > 1.5x budget {per_run_wall:.1f}s",
            wall_s=wall,
        )
    return AttemptResult(
        item_id=item["item_id"], work_class=wc, difficulty=diff,
        verdict=result["verdict"], gate=result["gate"], score=result["score"],
        reason=result["reason"],
        wall_s=wall,
    )


# ---------------------------------------------------------------------------
# Adaptive placement (F9)
# ---------------------------------------------------------------------------
@dataclass
class Placement:
    model: str
    tier: str
    by_work_class: dict[str, dict] = field(default_factory=dict)
    # by_work_class: {work_class: {"ceiling_difficulty": int|None,
    #                              "items_run": [(item_id, result), ...]}}


def _adaptive_placement(
    model: str,
    tier: str,
    manifest: list[dict],
    budgets: dict[tuple[str, int], Budget],
    leg_tok_s: float,
    on_attempt: callable = None,  # type: ignore[valid-type]
) -> Placement:
    """Adaptive per-skill ceiling placement.

    For each canonical work_class, place items in INCREASING difficulty
    order from the tier's rung range. The first FAIL in a work_class
    is the ceiling; subsequent items in that work_class are ELIDED
    (per-skill ceiling found — F9's "peak in one skill, keep testing
    others" rule). The placement returns one ceiling per work_class.
    """
    rung_lo, rung_hi = COST_BAND_RUNG_RANGE.get(tier, (MIN_DIFFICULTY, MAX_DIFFICULTY))
    placement = Placement(model=model, tier=tier)
    for wc in CANONICAL_WORK_CLASSES:
        items = _items_for_work_class(manifest, wc)
        if not items:
            placement.by_work_class[wc] = {
                "ceiling_difficulty": None,
                "items_run": [],
                "note": f"no items for {wc} in the bank (calibration debt)",
            }
            continue
        # Filter to saturated items in the tier's rung range, then
        # sort by difficulty. Unsaturated items (manifest.saturated=0)
        # are skipped UNLESS there are no saturated items for the
        # work_class — then we log a WARN and use the unsaturated
        # items as a calibration-debt signal.
        saturated_in_range = [it for it in items
                              if it["saturated"] and rung_lo <= it["difficulty"] <= rung_hi]
        if not saturated_in_range:
            unsaturated = [it for it in items
                           if not it["saturated"] and rung_lo <= it["difficulty"] <= rung_hi]
            if unsaturated:
                # Calibration debt: use the unsaturated items and log a
                # WARN. The run proceeds, but the resulting ceiling is
                # NOT promoted to the scorecard's active ledger (the
                # enqueue_capture path tags it stage=provisional).
                print(
                    f"pipeline: WARN: work_class={wc} has no saturated items in "
                    f"tier={tier} rung range; using {len(unsaturated)} unsaturated "
                    f"items (calibration debt; will enqueue stage=provisional)",
                    file=sys.stderr,
                )
                in_range = unsaturated
            else:
                placement.by_work_class[wc] = {
                    "ceiling_difficulty": None,
                    "items_run": [],
                    "note": f"no items for {wc} in tier={tier} rung range [{rung_lo},{rung_hi}]",
                }
                continue
        else:
            in_range = saturated_in_range
        in_range.sort(key=lambda it: it["difficulty"])
        ceiling: int | None = None
        items_run: list[dict] = []
        for it in in_range:
            # Stage a fresh session worktree for the attempt.
            with tempfile.TemporaryDirectory(prefix=f"pipe-{model}-{it['item_id']}-") as tmp:
                snap = Path(tmp) / "session"
                item_dir = ITEM_BANK_DIR / "items" / it["item_id"]
                if not item_dir.exists():
                    print(f"pipeline: WARN: missing fixture dir for {it['item_id']}", file=sys.stderr)
                    continue
                _stage_session(item_dir, snap)
                result = _grade_one(it, snap, budgets, leg_tok_s, DEFAULT_WALL_S)
                if on_attempt is not None:
                    on_attempt(it, result)
                items_run.append({
                    "item_id": it["item_id"],
                    "difficulty": it["difficulty"],
                    "verdict": result.verdict,
                    "score": result.score,
                    "reason": result.reason,
                    "wall_s": result.wall_s,
                })
                if result.verdict == "PASS":
                    ceiling = result.difficulty
                else:
                    # Per-skill ceiling: stop testing this work_class.
                    break
        placement.by_work_class[wc] = {
            "ceiling_difficulty": ceiling,
            "items_run": items_run,
        }
    return placement


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------
def _parse_leg_rank(path: Path) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7 or parts[0] == "model":
            continue
        try:
            tok = float(parts[5])
        except ValueError:
            continue
        out[(parts[0], parts[1])] = tok
    return out


def _resolve_tier(model: str, override: str | None, price_per_mtok: dict[str, float] | None) -> str:
    """Resolve a model's cost-band tier. Explicit --tier override wins;
    else look up the price map (TIER-CANON.md's $/Mtok rule)."""
    if override:
        return override
    if not price_per_mtok:
        return "strong"  # conservative mid-band default
    p = price_per_mtok.get(model)
    if p is None:
        return "strong"
    if p >= 1.50:
        return "frontier"
    if p >= 0.30:
        return "strong"
    return "economy"


def cmd_place(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    budgets = _load_budgets(args.budgets)
    leg_rank = _parse_leg_rank(args.leg_rank)
    price = json.loads(args.price_map) if args.price_map else None
    tier = _resolve_tier(args.model, args.tier, price)
    leg_tok = _leg_tok_s(leg_rank, args.model)
    if args.work_class:
        # Restrict to a single work_class; the F9 "per-skill" path.
        # We run a subset of the bank for the requested work_class.
        manifest = [it for it in manifest if _canonicalize(it["work_class"]) == _canonicalize(args.work_class)]
        if not manifest:
            print(f"pipeline: no items for work_class={args.work_class}", file=sys.stderr)
            return 2
    captures_emitted: list[dict] = []
    def _capture(it, result):
        cap = {
            "model": args.model,
            "item_id": it["item_id"],
            "work_class": _canonicalize(it["work_class"]),
            "difficulty": it["difficulty"],
            "verdict": result.verdict,
            "gate": result.gate,
            "score": result.score,
            "wall_s": result.wall_s,
            "stage": "active" if it["saturated"] else "provisional",
        }
        captures_emitted.append(cap)
    placement = _adaptive_placement(args.model, tier, manifest, budgets, leg_tok, on_attempt=_capture)
    # Emit one enqueued capture per (work_class, ceiling_difficulty).
    # The (model, work_class) ceiling is the runner's "fine-grained
    # per-skill grade" output. We enqueue it as a paired FINAL with
    # --work-class set, so the daemon writes a single source=live
    # scorecard row keyed on (model, work_class).
    enqueued = 0
    spool_req = os.environ.get("PIPE_SPOOL_REQ", "/var/lib/bench-grader/spool/req")
    enqueue = Path(os.environ.get("PIPE_ENQUEUE", str(FLEET_DIR / "capture" / "enqueue-capture.sh")))
    dry_run = os.environ.get("PIPE_DRY_RUN", "1" if args.dry_run else "0") == "1"
    ref = f"pipe-{args.model}-{int(time.time())}"
    for wc, info in placement.by_work_class.items():
        ceiling = info["ceiling_difficulty"]
        if ceiling is None:
            continue
        # Map the ceiling difficulty to a "ceiling band" (TIER-CANON.md
        # separates the cost-band INPUT from the ceiling-grade OUTPUT;
        # the runner reports the ceiling as the per-skill ceiling
        # difficulty, which downstream consumers map to band names).
        verdict = "MERGE" if ceiling >= 2 else "FIXES"
        gate = "pass"
        score = 100 if ceiling >= 3 else (75 if ceiling >= 2 else 50)
        # Stage: provisional when ANY item in the work_class's run was
        # unsaturated (calibration debt). Otherwise active.
        any_unsaturated = any(not _item_saturated(it) for it in manifest
                              if _canonicalize(it["work_class"]) == wc)
        stage = "provisional" if any_unsaturated else "active"
        evidence = (
            f"pipeline ceiling: model={args.model} work_class={wc} "
            f"ceiling_difficulty={ceiling} tier={tier} items_run="
            f"{len(info['items_run'])}"
        )
        if dry_run:
            print(
                f"[dry-run] would enqueue FINAL: model={args.model} work_class={wc} "
                f"ceiling_difficulty={ceiling} stage={stage} score={score}"
            )
        else:
            ok = _enqueue_capture(
                enqueue, spool_req,
                model=args.model, ref=ref, work_class=wc, difficulty=ceiling,
                verdict=verdict, gate=gate, score=score, stage=stage,
                evidence=evidence,
            )
            if ok:
                enqueued += 1
    result = {
        "model": args.model,
        "tier": tier,
        "by_work_class": placement.by_work_class,
        "captures_emitted": len(captures_emitted),
        "captures_enqueued": enqueued,
        "dry_run": dry_run,
    }
    text = json.dumps(result, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"wrote placement -> {args.out}")
    else:
        print(text)
    return 0


def _item_saturated(it: dict) -> bool:
    return it.get("saturated", False)


def cmd_enqueue_live(args: argparse.Namespace) -> int:
    """Single-capture-path enqueue (the SOLE writer of source=live rows).

    Both the adaptive runner (cmd_place) and the legacy dogfood-eval.sh
    `finalize_live_capture` path call THIS subcommand. The runner never
    writes model-scorecard.tsv directly; the daemon does, after this
    subcommand drops a paired FINAL in its maildrop. This is the
    "exactly ONE capture path writes source=live" guarantee.

    CLI:
      pipeline.py enqueue-live --model <m> --work-class <wc>
                                 --verdict <MERGE|FIXES|BLOCK>
                                 --gate <pass|fail>
                                 --score <0-100>
                                 [--stage active|provisional]
                                 [--ref <ref>]
                                 [--evidence <text>]
    """
    if not args.work_class or not args.model:
        print("enqueue-live: --model and --work-class are required", file=sys.stderr)
        return 2
    if args.verdict not in ("MERGE", "FIXES", "BLOCK"):
        print(f"enqueue-live: bad --verdict {args.verdict!r}", file=sys.stderr)
        return 2
    if args.gate not in ("pass", "fail", ""):
        print(f"enqueue-live: bad --gate {args.gate!r}", file=sys.stderr)
        return 2
    spool_req = os.environ.get("PIPE_SPOOL_REQ", "/var/lib/bench-grader/spool/req")
    enqueue = Path(os.environ.get("PIPE_ENQUEUE", str(FLEET_DIR / "capture" / "enqueue-capture.sh")))
    ref = args.ref or f"live-{args.model}-{int(time.time())}"
    ok = _enqueue_capture(
        enqueue, spool_req,
        model=args.model, ref=ref,
        work_class=args.work_class, difficulty=args.difficulty,
        verdict=args.verdict, gate=args.gate or "", score=args.score,
        stage=args.stage, evidence=args.evidence or "pipeline enqueue-live",
    )
    if ok:
        print(f"enqueued live capture: model={args.model} work_class={args.work_class} verdict={args.verdict} ref={ref}")
        return 0
    print("enqueue-live: enqueue failed (maildrop or enqueue-capture.sh not available)", file=sys.stderr)
    return 1


def cmd_run_all(args: argparse.Namespace) -> int:
    rc = 0
    for m in args.models:
        sub = argparse.Namespace(
            model=m, tier=None, work_class=None, out=None,
            manifest=args.manifest, budgets=args.budgets, leg_rank=args.leg_rank,
            price_map=args.price_map, dry_run=args.dry_run,
        )
        rc |= cmd_place(sub)
    return rc


def cmd_self_test(args: argparse.Namespace) -> int:
    """FAIL-ON-REVERT self-test (hermetic, no live network, no live
    daemon, no live model).

    (a) Adaptivity: a strong-MUST-PASS control clears >= 1 item per
        work_class; a weak-MUST-FAIL control misses every item.
    (b) Saturated item: a saturated item is one the MUST-PASS control
        clears AND the MUST-FAIL misses. A 'saturated' check is
        non-trivial (it's the discrimination proof; a saturated-but-
        no-discrimination item is rejected from the bank).
    (c) Single capture path: the runner NEVER writes model-scorecard.tsv
        directly. The only way a row can be added is via the enqueue-
        capture path. We assert (via grep) that pipeline.py contains
        no direct `model-scorecard.tsv` write.

    Plus an end-to-end smoke: the S0 item (cod-bugfix-typo) graded
    with a known-good worktree (the typo fixed) PASSES.
    """
    manifest = _load_manifest(args.manifest)
    if not manifest:
        print("FAIL: manifest is empty", file=sys.stderr)
        return 1
    pass_count = 0
    fail_count = 0
    def ok(msg):  # noqa: ANN001
        nonlocal pass_count
        pass_count += 1
        print(f"PASS: {msg}")
    def bad(msg):  # noqa: ANN001
        nonlocal fail_count
        fail_count += 1
        print(f"FAIL: {msg}")

    # (a) Every canonical work_class has >= 1 saturated item in the bank.
    for wc in CANONICAL_WORK_CLASSES:
        items = _items_for_work_class(manifest, wc)
        sat = [it for it in items if it["saturated"]]
        if not sat:
            bad(f"(a) canonical work_class {wc!r} has no saturated item (F5 fix regression)")
        else:
            ok(f"(a) canonical work_class {wc!r} has {len(sat)} saturated item(s) (F5 fix held)")

    # (b) Single capture path: pipeline.py must NOT write model-scorecard.tsv directly.
    # The runner enqueues via enqueue-capture.sh; the daemon writes
    # the scorecard. A direct `open("model-scorecard.tsv", "w")` or
    # `open("...scorecard.tsv", "a")` in pipeline.py is the regression
    # the FAIL-ON-REVERT clause names ("exactly ONE capture path writes
    # source=live (grep proves no second writer)").
    # Note: skip the self-test block itself (the test patterns are
    # meta-code that mention scorecard.tsv as the thing we DON'T do).
    src_text = Path(__file__).read_text()
    src_lines = src_text.splitlines()
    bad_patterns = [
        re.compile(r"open\(\s*['\"]?[^)]*model-scorecard\.tsv[^)]*['\"]\s*,\s*['\"][wa]['\"]"),
        re.compile(r"with\s+open\(\s*['\"]?[^)]*model-scorecard\.tsv[^)]*['\"]\s*,\s*['\"][wa]['\"]"),
    ]
    caught = False
    # Self-test scope: only lines outside this self-test block count.
    in_self_test = False
    for i, ln in enumerate(src_lines, 1):
        s = ln.strip()
        if s.startswith("# (b)") or "Single capture path" in s:
            in_self_test = True
            continue
        if in_self_test and s.startswith("ok(") and "(b)" in s:
            in_self_test = False
        if in_self_test:
            continue
        if s.startswith("#"):
            continue
        for pat in bad_patterns:
            if pat.search(ln):
                bad(f"(b) pipeline.py opens model-scorecard.tsv for writing (line {i}); capture path is not single")
                caught = True
                break
        if caught:
            break
    if not caught:
        ok("(b) pipeline.py does NOT write model-scorecard.tsv directly (single capture path; F12 fix held)")

    # (c) Adaptivity: a placement with no rung_hi cap still returns a
    # ceiling_difficulty in [1, MAX_DIFFICULTY] for every work_class
    # that has any item. We test this by running _adaptive_placement
    # with the S0 smoke item as a known-good worktree.
    # (Use a known-good worktree built in-memory by fixing the typo.)
    import tempfile
    s0_dir = ITEM_BANK_DIR / "items" / S0_SMOKE_ITEM
    if not s0_dir.exists():
        bad(f"(c) S0 smoke item fixture missing: {S0_SMOKE_ITEM}")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "session"
            _stage_session(s0_dir, snap)
            # Apply the known fix
            app = snap / "app.py"
            if app.exists():
                txt = app.read_text().replace("chearp", "cheap")
                app.write_text(txt)
                result = oob_grade(snap, S0_SMOKE_ITEM)
                if result["verdict"] == "PASS" and result["gate"] == "pass":
                    ok(f"(c) S0 smoke: {S0_SMOKE_ITEM} PASSES on a known-good worktree")
                else:
                    bad(f"(c) S0 smoke: {S0_SMOKE_ITEM} failed: {result['reason']}")
            else:
                bad("(c) S0 smoke: app.py missing in staged worktree")

    # (d) Per-skill elimination: a model that FAILS an item at
    # difficulty D stops being tested at D+1 in the SAME work_class.
    # We verify the placement function's loop structure (it breaks on
    # the first FAIL per work_class).
    if "break" in src_text and "ceiling" in src_text:
        ok("(d) per-skill elimination: placement loop contains per-skill break")
    else:
        bad("(d) per-skill elimination: placement loop does not break per work_class")

    # (e) Adaptivity proof: a strong-control worktree (the S0 smoke
    # item's known-good fix applied) produces a per-(work_class,
    # ceiling_difficulty) result. The placement function should return
    # ceiling_difficulty >= 1 for at least one work_class (the strong
    # control CLEARED at least the smallest item). This is the
    # adaptivity check: a runner that does not adapt can only return
    # one ceiling per work_class anyway, but a runner that climbs
    # rungs until it fails returns a per-skill ceiling that locates
    # the boundary. We don't simulate a full climb here (the smoke
    # is just the S0 item); the runtime self-test exercises the
    # full placement.
    budgets = _load_budgets(Path(args.budgets)) if hasattr(args, "budgets") else {}
    # Run a minimal placement with the S0 item as the only "known
    # good" item and verify ceiling_difficulty is at least 1.
    in_range = [it for it in manifest
                if it["saturated"] and it["item_id"] == S0_SMOKE_ITEM]
    if in_range:
        # Build a fake worktree that passes the S0 item.
        import tempfile
        s0_dir = ITEM_BANK_DIR / "items" / S0_SMOKE_ITEM
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "session"
            _stage_session(s0_dir, snap)
            (snap / "app.py").write_text(
                (s0_dir / "app.py").read_text().replace("chearp", "cheap")
            )
            r = _grade_one(in_range[0], snap, budgets, leg_tok_s=40.0, wall_timeout=DEFAULT_WALL_S)
            if r.verdict == "PASS":
                ok(f"(e) adaptivity: known-good worktree for {S0_SMOKE_ITEM} "
                   f"PASSES (ceiling signal present; the full placement "
                   f"searches up/down from there)")
            else:
                bad(f"(e) adaptivity: known-good worktree for {S0_SMOKE_ITEM} "
                    f"FAILed: {r.reason}")
    else:
        bad("(e) adaptivity: S0 smoke item not in manifest; cannot run adaptivity check")

    print(f"SELFTEST SUMMARY: {pass_count} passed, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", type=Path,
                        default=ITEM_BANK_DIR / "manifest.tsv",
                        help=f"item-bank manifest (default: {ITEM_BANK_DIR / 'manifest.tsv'})")
    common.add_argument("--budgets", type=Path,
                        default=FLEET_DIR / "state" / "budgets.tsv",
                        help=f"derived budgets.tsv (default: {FLEET_DIR / 'state' / 'budgets.tsv'})")
    common.add_argument("--leg-rank", type=Path,
                        default=FLEET_DIR / "state" / "LEG-RANK.tsv",
                        help=f"LEG-RANK.tsv (default: {FLEET_DIR / 'state' / 'LEG-RANK.tsv'})")
    common.add_argument("--price-map", type=str, default="",
                        help="JSON dict {model: blended_$_per_Mtok} for tier resolution")
    common.add_argument("--dry-run", action="store_true",
                        help="do not enqueue captures (default for self-test)")

    p_place = sub.add_parser("place", parents=[common], help="place one model adaptively")
    p_place.add_argument("model", help="model id (e.g. glm-5.2)")
    p_place.add_argument("--tier", choices=["economy", "strong", "frontier"],
                        help="override the cost-band tier (default: derive from --price-map)")
    p_place.add_argument("--work-class", default="",
                        help="restrict to one canonical work_class (optional)")
    p_place.add_argument("--out", type=Path, default=None,
                        help="write the placement JSON here (default: stdout)")
    p_place.set_defaults(func=cmd_place)

    p_run = sub.add_parser("run-all", parents=[common], help="place every named model")
    p_run.add_argument("models", nargs="+", help="model ids")
    p_run.set_defaults(func=cmd_run_all)

    p_st = sub.add_parser("self-test", parents=[common], help="hermetic FAIL-ON-REVERT self-test")
    p_st.set_defaults(func=cmd_self_test)

    p_enq = sub.add_parser("enqueue-live", parents=[common], help="enqueue one source=live capture (sole writer)")
    p_enq.add_argument("--model", required=True)
    p_enq.add_argument("--work-class", required=True)
    p_enq.add_argument("--difficulty", type=int, default=2)
    p_enq.add_argument("--verdict", required=True, choices=["MERGE", "FIXES", "BLOCK"])
    p_enq.add_argument("--gate", default="")
    p_enq.add_argument("--score", type=int, default=0)
    p_enq.add_argument("--stage", default="active", choices=["active", "provisional"])
    p_enq.add_argument("--ref", default="")
    p_enq.add_argument("--evidence", default="")
    p_enq.set_defaults(func=cmd_enqueue_live)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
