#!/usr/bin/env python3
"""auto_append.py — mechanized scorecard row append (F17).

Mirrors model-scorecard.sh's cmd_append validation and 16-column TSV format
exactly, so every row produced by this helper is indistinguishable from one
produced by the shell ledger.  Designed for Python call-sites (benchmark
graders, review hooks, ticket-close automation) that want to append without
shelling out or hand-editing the TSV.

Validation is FAIL-CLOSED: any invalid field raises ValueError immediately,
so a bad row is NEVER written to the append-only ledger.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# These sets must stay in lockstep with model-scorecard.sh lines ~20-21.
VALID_SOURCE = {"live", "bench", "bench2"}
VALID_CLASS = {
    "money-path", "routing", "ci-infra", "refactor", "bugfix",
    "tests", "greenfield-feature", "docs", "frontend",
}
VALID_VERDICT = {"MERGE", "FIXES", "BLOCK"}
VALID_GATE = {"pass", "fail", "-"}
VALID_STAGE = {"provisional", "active"}


def _validate_date(date: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must be YYYY-MM-DD")


def _validate_non_negative_int(value: str, name: str) -> None:
    if value == "-":
        return
    if not value.isdigit():
        raise ValueError(f"{name} must be a non-negative integer or '-'")


def _validate_non_negative_number(value: str, name: str) -> None:
    if value == "-":
        return
    try:
        if float(value) < 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"{name} must be a non-negative number or '-'")


def _validate_score(value: str) -> None:
    if value == "-":
        return
    if not value.isdigit():
        raise ValueError("score must be 0-100 or '-'")
    v = int(value)
    if v < 0 or v > 100:
        raise ValueError("score must be 0-100")


def _validate_tier(value: str) -> None:
    if value not in ("0", "1", "2", "3", "4", "-"):
        raise ValueError("tier must be 0-4 or '-'")


def append_scorecard_row(
    tsv_path: Path | str,
    *,
    date: str | None = None,
    source: str,
    ref: str,
    work_class: str,
    tier: str,
    model: str,
    verdict: str,
    gate: str,
    score: str,
    time_s: str,
    cost_usd: str,
    corrections: str,
    note: str = "-",
    tokens_in: str = "-",
    tokens_out: str = "-",
    stage: str = "active",
) -> None:
    """Append a validated row to *tsv_path*.

    Every field is validated exactly as model-scorecard.sh cmd_append does.
    The TSV must already exist (fail-closed: this helper will NOT seed a new
    ledger; that is the operator's responsibility).

    Parameters default to the same conventions as cmd_append:
      - date defaults to today UTC if omitted.
      - note defaults to "-".
      - tokens_in/tokens_out default to "-".
      - stage defaults to "active".
    """
    tsv_path = Path(tsv_path)
    if not tsv_path.exists():
        raise FileNotFoundError(f"ledger not found: {tsv_path}")

    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    _validate_date(date)
    if source not in VALID_SOURCE:
        raise ValueError(f"source must be one of: {sorted(VALID_SOURCE)}")
    if work_class not in VALID_CLASS:
        raise ValueError(f"work_class must be one of: {sorted(VALID_CLASS)}")
    if verdict not in VALID_VERDICT:
        raise ValueError(f"verdict must be one of: {sorted(VALID_VERDICT)}")
    if gate not in VALID_GATE:
        raise ValueError(f"gate must be one of: {sorted(VALID_GATE)}")
    _validate_tier(tier)
    _validate_score(score)
    _validate_non_negative_number(time_s, "time_s")
    _validate_non_negative_number(cost_usd, "cost_usd")
    _validate_non_negative_int(corrections, "corrections")
    if "\t" in note:
        raise ValueError("note must not contain tabs")
    _validate_non_negative_int(tokens_in, "tokens_in")
    _validate_non_negative_int(tokens_out, "tokens_out")
    if stage not in VALID_STAGE:
        raise ValueError(f"stage must be one of: {sorted(VALID_STAGE)}")

    row = [
        date, source, ref, work_class, tier, model, verdict, gate,
        score, time_s, cost_usd, corrections, note,
        tokens_in, tokens_out, stage,
    ]
    line = "\t".join(row) + "\n"
    with open(tsv_path, "a") as fh:
        fh.write(line)


def main(argv: list[str] | None = None) -> int:
    """Minimal CLI for non-Python call-sites.

    Run: python3 auto_append.py --tsv <path> --source <s> --ref <r> ...
    """
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tsv", required=True, help="path to model-scorecard.tsv")
    ap.add_argument("--date", default=None)
    ap.add_argument("--source", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--work-class", required=True)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--score", required=True)
    ap.add_argument("--time-s", required=True)
    ap.add_argument("--cost-usd", required=True)
    ap.add_argument("--corrections", default="-")
    ap.add_argument("--note", default="-")
    ap.add_argument("--tokens-in", default="-")
    ap.add_argument("--tokens-out", default="-")
    ap.add_argument("--stage", default="active")
    args = ap.parse_args(argv)
    try:
        append_scorecard_row(
            args.tsv,
            date=args.date,
            source=args.source,
            ref=args.ref,
            work_class=args.work_class,
            tier=args.tier,
            model=args.model,
            verdict=args.verdict,
            gate=args.gate,
            score=args.score,
            time_s=args.time_s,
            cost_usd=args.cost_usd,
            corrections=args.corrections,
            note=args.note,
            tokens_in=args.tokens_in,
            tokens_out=args.tokens_out,
            stage=args.stage,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
