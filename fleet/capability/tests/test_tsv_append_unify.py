"""test_tsv_append_unify.py — fail-on-revert guard for TSV-APPEND-UNIFY.

TOOL-AUDIT-REDUNDANCY finding 6 resolution: model-scorecard.sh cmd_append is
the ONE validate+append implementation; capability/auto_append.py merely
delegates to it.  These tests go RED if either (a) the two paths stop
producing identical rows, (b) the Python wrapper stops surfacing the shell
validator's rejection, or (c) the Python wrapper regrows its own inline
write instead of delegating.

Run: python3 -m pytest fleet/capability/tests/test_tsv_append_unify.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

CAPABILITY_DIR = Path(__file__).resolve().parent.parent
FLEET_DIR = CAPABILITY_DIR.parent
SCORECARD_SH = FLEET_DIR / "model-scorecard.sh"

sys.path.insert(0, str(CAPABILITY_DIR))
import auto_append  # noqa: E402
from auto_append import append_scorecard_row  # noqa: E402

HEADER = (
    "# model-scorecard.tsv — test ledger (hermetic)\n"
    "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
    "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage\n"
)

FIELDS = dict(
    date="2026-07-15",
    source="bench",
    ref="S2",
    work_class="routing",
    tier="2",
    model="unify-test-model",
    verdict="MERGE",
    gate="pass",
    score="97",
    time_s="12.5",
    cost_usd="0.0042",
    corrections="1",
    note="unified append row",
    tokens_in="1500",
    tokens_out="320",
    stage="active",
)


def _rows(p: Path) -> list[str]:
    return [ln for ln in p.read_text().splitlines()
            if ln and not ln.startswith("#")]


def _fresh_tsv(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_text(HEADER)
    return p


def _shell_append(tsv: Path, f: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CHARON_SCORECARD_TSV"] = str(tsv)
    env["CHARON_SCORECARD_TOKENS_IN"] = f["tokens_in"]
    env["CHARON_SCORECARD_TOKENS_OUT"] = f["tokens_out"]
    env["CHARON_SCORECARD_STAGE"] = f["stage"]
    return subprocess.run(
        ["bash", str(SCORECARD_SH), "append",
         f["date"], f["source"], f["ref"], f["work_class"], f["tier"],
         f["model"], f["verdict"], f["gate"], f["score"],
         f["time_s"], f["cost_usd"], f["corrections"], f["note"]],
        env=env, capture_output=True, text=True, timeout=30)


def test_shell_and_python_rows_byte_identical(tmp_path: Path) -> None:
    shell_tsv = _fresh_tsv(tmp_path, "shell.tsv")
    py_tsv = _fresh_tsv(tmp_path, "python.tsv")

    r = _shell_append(shell_tsv, FIELDS)
    assert r.returncode == 0, f"shell append failed: {r.stderr!r}"
    append_scorecard_row(py_tsv, **FIELDS)  # type: ignore[arg-type]

    shell_rows = _rows(shell_tsv)
    py_rows = _rows(py_tsv)
    assert len(shell_rows) == 1
    assert shell_rows == py_rows


def test_env_var_tsv_override_isolates_ledger(tmp_path: Path) -> None:
    tsv = _fresh_tsv(tmp_path, "override.tsv")
    r = _shell_append(tsv, FIELDS)
    assert r.returncode == 0, f"shell append failed: {r.stderr!r}"
    assert len(_rows(tsv)) == 1


def test_python_surfaces_shell_rejection(tmp_path: Path) -> None:
    tsv = _fresh_tsv(tmp_path, "reject.tsv")
    bad = dict(FIELDS, source="synthetic")
    with pytest.raises(ValueError, match="source must be one of"):
        append_scorecard_row(tsv, **bad)  # type: ignore[arg-type]
    assert _rows(tsv) == [], "rejected row must never be written"


def test_python_append_delegates_to_shell(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    tsv = _fresh_tsv(tmp_path, "delegate.tsv")
    stub = tmp_path / "stub-scorecard.sh"
    stub.write_text(
        '#!/usr/bin/env bash\n'
        'printf "SENTINEL-VIA-SHELL\\n" >> "$CHARON_SCORECARD_TSV"\n')
    monkeypatch.setattr(auto_append, "SCORECARD_SH", stub)
    append_scorecard_row(tsv, **FIELDS)  # type: ignore[arg-type]
    assert _rows(tsv) == ["SENTINEL-VIA-SHELL"], (
        "append_scorecard_row must write via model-scorecard.sh, not inline")
