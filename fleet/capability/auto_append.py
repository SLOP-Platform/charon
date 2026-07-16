#!/usr/bin/env python3
"""auto_append.py — Python entry point for scorecard row append (F17).

TSV-APPEND-UNIFY (fleet/state/TOOL-AUDIT-REDUNDANCY.md finding 6): this
module used to be a full second implementation of model-scorecard.sh's
cmd_append, kept in lockstep only by comment discipline.  It is now a THIN
DELEGATOR: validation and the 16-column TSV write live ONLY in
fleet/model-scorecard.sh `cmd_append` (one implementation, two callers).
This wrapper builds the argv/env for the shell appender, points it at the
caller's ledger via CHARON_SCORECARD_TSV, and maps a rejection back to
ValueError so Python call-sites (benchmark graders, review hooks,
ticket-close automation) keep a native API.

Fail-closed as before: the shell validator rejects any invalid field and
exits non-zero BEFORE writing, so a bad row is NEVER appended; that
rejection surfaces here as ValueError with the shell's own message.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCORECARD_SH = Path(__file__).resolve().parent.parent / "model-scorecard.sh"


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
    """Append a validated row to *tsv_path* via model-scorecard.sh `append`.

    Every field is validated by cmd_append itself (the single source of
    truth); an invalid field raises ValueError carrying the shell's error
    message.  The TSV must already exist (fail-closed: this helper will NOT
    seed a new ledger; that is the operator's responsibility).

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

    # Transport guard, NOT field validation (that lives in cmd_append):
    # these three ride the CHARON_SCORECARD_* env-var channel, whose
    # `${VAR:-default}` expansion cannot distinguish "" from unset — an
    # empty string would silently become the default instead of being
    # rejected. Refuse it here so the fail-closed contract holds.
    for env_name, env_value in (
        ("tokens_in", tokens_in),
        ("tokens_out", tokens_out),
        ("stage", stage),
    ):
        if env_value == "":
            raise ValueError(
                f"{env_name} must not be empty "
                "(env-var channel cannot carry '')"
            )

    env = os.environ.copy()
    env["CHARON_SCORECARD_TSV"] = str(tsv_path)
    env["CHARON_SCORECARD_TOKENS_IN"] = tokens_in
    env["CHARON_SCORECARD_TOKENS_OUT"] = tokens_out
    env["CHARON_SCORECARD_STAGE"] = stage
    proc = subprocess.run(
        [
            "bash", str(SCORECARD_SH), "append",
            date, source, ref, work_class, tier, model, verdict, gate,
            score, time_s, cost_usd, corrections, note,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip()
        if msg.startswith("error: "):
            msg = msg[len("error: "):]
        raise ValueError(
            msg or f"model-scorecard.sh append failed (rc={proc.returncode})"
        )


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
