#!/usr/bin/env python3
"""benchmark-v2 season close (BENCHMARK-V2-DESIGN.md §4.2).

Reproducibility is the load-bearing property this module exists for: a
`bench2` row's `section_total` must be computed ONCE, against the FULL
season cohort (never a live/growing field, never a partial one), and then
NEVER change value again. Mechanics (§4.2):

  1. While a season is OPEN, `bench2` rows carry only `raw` (grader score)
     and raw usage metrics (tokens/time/cost) - no `section_total`/
     `modifier` yet. Nothing in this module runs yet; rows are
     "provisional" simply because no closed-season file exists for their
     season id (see `is_closed`/`load_closed`).
  2. At season CLOSE (`close_season()` below - triggered by an operator
     action, not by this module reading the wall clock: see the module
     docstring note on why `season_id` is always an explicit input here),
     this runs EXACTLY ONCE per season: read every `bench2` row tagged
     with that season, group by section, compute the cohort `C(S,season)`
     per section (§4.3b), call `lib/efficiency.py` once per cohort, and
     write the result to one immutable JSON file.
  3. After close, the season is IMMUTABLE - `close_season()` refuses to
     recompute over an existing closed-season file unless the caller
     explicitly passes `force=True` (an explicit, deliberate override,
     never automatic). No later event (a new season opening, a model
     joining a DIFFERENT season, a re-render) ever touches a closed file.

WALL-CLOCK NOTE: this module never calls `time.time()`/`date.today()` to
DECIDE which season is "current" or "over" - `season_id` is always an
explicit argument (bench.sh's `season close <season_id>` operator command,
or a caller/test that already knows which season it means). `closed_ts`
(when a season was closed) is the one place a timestamp is recorded, and
that's provenance metadata, not a decision input.

SEASON ID: ISO calendar week of a row's `date` column (e.g. "2026-W28"),
reusing exactly the id §7 already defines for section-set sampling - see
`season_id_for_date()`.
"""
from __future__ import annotations

import json
import time
from datetime import date as _date
from pathlib import Path

import efficiency

BENCH_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TSV = BENCH_DIR.parent / "model-scorecard.tsv"
DEFAULT_SEASONS_DIR = BENCH_DIR / "state" / "seasons"

# CORRECTIONS_CAP mirrors grade_state.py's constant of the same name -
# not imported directly (grade_state.py is a script module, not meant to
# be imported for its constant alone) but kept in lockstep by convention;
# not actually needed for the capped_while_failing derivation below, which
# works off `gate`/`note` instead (see docstring on `bench2_rows_from_tsv`).


def season_id_for_date(date_str: str) -> str:
    """ISO calendar week id, e.g. "2026-W28" for 2026-07-06 - the same
    season-key SHAPE §7 already defines for section-set sampling. Reused
    here (§4.2) as the identical partition key for the efficiency field:
    one season, one section-set, one efficiency field, by construction."""
    y, w, _weekday = _date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def _num(value: str, cast):
    if value in (None, "-", ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def bench2_rows_from_tsv(tsv_path=DEFAULT_TSV) -> list[dict]:
    """Parse `model-scorecard.tsv`-shaped rows, returning ONLY
    `source == "bench2"` rows (a `source == "bench"`/`live` row can never
    enter a bench2 cohort - §4.6b's hard partition, enforced here at the
    read boundary, not just downstream) as the row-dicts
    `lib/efficiency.compute_section_cohort` expects:
    {"model", "section", "season", "raw", "capped_while_failing",
     "tokens", "time_s", "cost_usd"}.

    KNOWN APPROXIMATION (flagged, not silently papered over): `raw` here
    is the TSV `score` column, i.e. the value `grade_state.py::cmd_record`
    already finalized - which, for a row that hit CORRECTIONS_CAP while
    still failing, is `min(true_raw, 89)`, NOT the grader's true pre-cap
    number (that number is not persisted anywhere upstream today - closing
    this gap fully is the `grade.json` work described in
    BENCHMARK-V2-DESIGN.md §5, out of scope for this scoring-only pass).
    This is harmless for the ANTI-CHEAT invariant specifically (§4.5's
    final `min(adjusted, 89)` re-application still holds the ceiling at
    89 regardless of what `raw` was going in), but means a capped-while-
    failing row's `section_total` is computed from an already-capped `raw`
    rather than the true one - documented explicitly in
    v2-scoring-build-report.md, not hidden here.

    `capped_while_failing` is derived (not read off a column that doesn't
    exist yet) from the existing columns: `bench.sh::do_grade` appends
    `gate` verbatim from the grader's FINAL round, and prefixes `note`
    with `"timeout ("` only on the timeout finalize path (see bench.sh's
    `do_grade`). A row that finalized via `gate == "pass"` is a clean
    pass; a row that finalized via timeout scores `raw == 0` regardless of
    `gate` (and is recognizable by the `"timeout ("` note prefix); the
    ONLY remaining way a row finalizes with `gate == "fail"` and no
    timeout prefix is grade_state.py's `min(score, 89)` cap-while-failing
    branch. So `capped_while_failing = (gate == "fail") and not
    note.startswith("timeout (")`.

    `tokens` = `tokens_in + tokens_out` (cols 14/15) when BOTH are
    present and numeric, else `None` (metric unavailable for that model -
    never partially summed, never guessed).
    """
    rows: list[dict] = []
    path = Path(tsv_path)
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 13:
            continue
        date, source = cols[0], cols[1]
        if source != "bench2":
            continue
        ref, _wclass, _tier, model, _verdict, gate, score, time_s, cost_usd, _corr, note = cols[2:13]
        tokens_in_raw = cols[13] if len(cols) > 13 else "-"
        tokens_out_raw = cols[14] if len(cols) > 14 else "-"
        if score == "-":
            continue
        capped_while_failing = (gate == "fail") and not note.startswith("timeout (")
        tokens_in = _num(tokens_in_raw, int)
        tokens_out = _num(tokens_out_raw, int)
        tokens = tokens_in + tokens_out if tokens_in is not None and tokens_out is not None else None
        rows.append({
            "model": model,
            "section": ref,
            "season": season_id_for_date(date),
            "raw": int(score),
            "capped_while_failing": capped_while_failing,
            "tokens": tokens,
            "time_s": _num(time_s, float),
            "cost_usd": _num(cost_usd, float),
        })
    return rows


def season_path(season_id: str, seasons_dir=DEFAULT_SEASONS_DIR) -> Path:
    return Path(seasons_dir) / f"{season_id}.json"


def is_closed(season_id: str, seasons_dir=DEFAULT_SEASONS_DIR) -> bool:
    return season_path(season_id, seasons_dir).exists()


def load_closed(season_id: str, seasons_dir=DEFAULT_SEASONS_DIR) -> dict | None:
    p = season_path(season_id, seasons_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def close_season(season_id: str, tsv_path=DEFAULT_TSV, seasons_dir=DEFAULT_SEASONS_DIR,
                  force: bool = False) -> dict:
    """§4.2 batch job. Computes `EFF_PCT`/`modifier`/`section_total` for
    EVERY model in EVERY section's cohort for `season_id`, in one shot,
    and writes the result to `<seasons_dir>/<season_id>.json` (atomic
    write: build in a `.tmp` file, then `rename()` over the final path).

    Raises RuntimeError if this season is already closed and `force` is
    not explicitly set - closed seasons are IMMUTABLE (§4.2 mechanic 3):
    there is no code path anywhere else in this subsystem that recomputes
    or overwrites a closed season's file.
    """
    p = season_path(season_id, seasons_dir)
    if p.exists() and not force:
        raise RuntimeError(
            f"season {season_id!r} is already CLOSED ({p}) - closed seasons are "
            f"immutable (BENCHMARK-V2-DESIGN.md §4.2 mechanic 3). Refusing to "
            f"recompute. Pass force=True only for a deliberate, explicit override "
            f"(e.g. correcting a genuine data-entry bug before anyone has acted on "
            f"the closed numbers) - never as a routine path.")

    all_rows = bench2_rows_from_tsv(tsv_path)
    season_rows = [r for r in all_rows if r["season"] == season_id]

    by_section: dict[str, list[dict]] = {}
    for row in season_rows:
        by_section.setdefault(row["section"], []).append(row)

    sections_out = {}
    for section, rows in by_section.items():
        cohort_models = sorted({r["model"] for r in rows})
        sections_out[section] = {
            "cohort_models": cohort_models,
            "cohort_size": len(cohort_models),
            "models": efficiency.compute_section_cohort(rows),
        }

    payload = {
        "season": season_id,
        "closed_ts": time.time(),
        "status": "final",
        "sections": sections_out,
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(p)  # atomic on POSIX - never a half-written closed-season file
    return payload


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    cmd = sys.argv[1]
    if cmd == "close":
        if len(sys.argv) < 3:
            print("usage: close_season.py close <season_id> [--force]", file=sys.stderr)
            raise SystemExit(2)
        season_id = sys.argv[2]
        force = "--force" in sys.argv[3:]
        payload = close_season(season_id, force=force)
        print(json.dumps({"season": season_id, "sections": sorted(payload["sections"])}))
    elif cmd == "status":
        if len(sys.argv) < 3:
            print("usage: close_season.py status <season_id>", file=sys.stderr)
            raise SystemExit(2)
        season_id = sys.argv[2]
        print(json.dumps({"season": season_id, "closed": is_closed(season_id)}))
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
