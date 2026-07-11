"""test_auto_append.py — hermetic unit tests for fleet/capability/auto_append.py.

Fail-on-revert: corrupt validation or remove the helper -> these tests go RED.
Run: python3 -m pytest fleet/tests/test_auto_append.py -q
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "capability"))
from auto_append import append_scorecard_row


def _header() -> str:
    return (
        "# model-scorecard.tsv — test ledger (hermetic)\n"
        "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
        "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage\n"
    )


@pytest.fixture
def tmp_tsv(tmp_path: Path) -> Path:
    p = tmp_path / "model-scorecard.tsv"
    p.write_text(_header())
    return p


def _rows(p: Path) -> list[list[str]]:
    return [ln.split("\t") for ln in p.read_text().splitlines()
            if ln and not ln.startswith("#")]


# ── basic append ──

def test_full_valid_row(tmp_tsv: Path) -> None:
    append_scorecard_row(
        tmp_tsv,
        date="2026-07-11",
        source="bench",
        ref="S2",
        work_class="routing",
        tier="2",
        model="kimi-k2.6",
        verdict="MERGE",
        gate="pass",
        score="100",
        time_s="42.5",
        cost_usd="0.03",
        corrections="1",
        note="clean fix",
        tokens_in="4000",
        tokens_out="800",
        stage="active",
    )
    rows = _rows(tmp_tsv)
    assert len(rows) == 1
    r = rows[0]
    assert r[0] == "2026-07-11"
    assert r[1] == "bench"
    assert r[2] == "S2"
    assert r[3] == "routing"
    assert r[4] == "2"
    assert r[5] == "kimi-k2.6"
    assert r[6] == "MERGE"
    assert r[7] == "pass"
    assert r[8] == "100"
    assert r[9] == "42.5"
    assert r[10] == "0.03"
    assert r[11] == "1"
    assert r[12] == "clean fix"
    assert r[13] == "4000"
    assert r[14] == "800"
    assert r[15] == "active"


def test_default_date(tmp_tsv: Path) -> None:
    append_scorecard_row(
        tmp_tsv,
        source="live",
        ref="#42",
        work_class="bugfix",
        tier="-",
        model="gpt-5",
        verdict="FIXES",
        gate="fail",
        score="-",
        time_s="-",
        cost_usd="-",
        corrections="-",
    )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = _rows(tmp_tsv)
    assert rows[0][0] == today


def test_multiple_rows(tmp_tsv: Path) -> None:
    for i in range(3):
        append_scorecard_row(
            tmp_tsv,
            date="2026-07-11",
            source="bench",
            ref=f"S{i}",
            work_class="bugfix",
            tier="0",
            model="deepseek-v4-pro",
            verdict="MERGE",
            gate="pass",
            score="100",
            time_s="10",
            cost_usd="0",
            corrections="0",
        )
    assert len(_rows(tmp_tsv)) == 3


# ── validation guards ──

def test_missing_tsv_raises() -> None:
    with pytest.raises(FileNotFoundError):
        append_scorecard_row("/nonexistent.tsv", source="bench", ref="S0",
                             work_class="bugfix", tier="0", model="m",
                             verdict="MERGE", gate="pass", score="100",
                             time_s="10", cost_usd="0", corrections="0")


@pytest.mark.parametrize("bad_date", ["2026-7-11", "11-07-2026", "2026/07/11", ""])
def test_invalid_date(bad_date: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="date"):
        append_scorecard_row(
            tmp_tsv, date=bad_date, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0")


def test_invalid_source(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="source"):
        append_scorecard_row(
            tmp_tsv, source="synthetic", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0")


def test_invalid_work_class(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="work_class"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="magic", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0")


def test_invalid_verdict(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="verdict"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MAYBE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0")


def test_invalid_gate(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="gate"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="maybe", score="100",
            time_s="10", cost_usd="0", corrections="0")


@pytest.mark.parametrize("bad_tier", ["5", "A", ""])
def test_invalid_tier(bad_tier: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="tier"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier=bad_tier, model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0")


@pytest.mark.parametrize("bad_score", ["-1", "101", "abc", ""])
def test_invalid_score(bad_score: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="score"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score=bad_score,
            time_s="10", cost_usd="0", corrections="0")


@pytest.mark.parametrize("bad_time", ["-1", "abc", ""])
def test_invalid_time_s(bad_time: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="time_s"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s=bad_time, cost_usd="0", corrections="0")


@pytest.mark.parametrize("bad_cost", ["-0.01", "abc", ""])
def test_invalid_cost_usd(bad_cost: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="cost_usd"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd=bad_cost, corrections="0")


@pytest.mark.parametrize("bad_corr", ["-1", "abc", ""])
def test_invalid_corrections(bad_corr: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="corrections"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections=bad_corr)


def test_note_must_not_have_tabs(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="tabs"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0",
            note="a\tb")


@pytest.mark.parametrize("bad_tok", ["abc", "-1", ""])
def test_invalid_tokens_in(bad_tok: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="tokens_in"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0",
            tokens_in=bad_tok)


@pytest.mark.parametrize("bad_tok", ["abc", "-1", ""])
def test_invalid_tokens_out(bad_tok: str, tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="tokens_out"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0",
            tokens_out=bad_tok)


def test_invalid_stage(tmp_tsv: Path) -> None:
    with pytest.raises(ValueError, match="stage"):
        append_scorecard_row(
            tmp_tsv, source="bench", ref="S0",
            work_class="bugfix", tier="0", model="m",
            verdict="MERGE", gate="pass", score="100",
            time_s="10", cost_usd="0", corrections="0",
            stage="draft")


# ── CLI ──

SCRIPT = Path(__file__).resolve().parent.parent / "capability" / "auto_append.py"


def test_cli_ok(tmp_tsv: Path) -> None:
    rc = subprocess.call([
        sys.executable, str(SCRIPT),
        "--tsv", str(tmp_tsv),
        "--date", "2026-07-11",
        "--source", "bench", "--ref", "S1",
        "--work-class", "money-path", "--tier", "1",
        "--model", "gpt-5", "--verdict", "MERGE",
        "--gate", "pass", "--score", "100",
        "--time-s", "12.3", "--cost-usd", "0.01",
    ])
    assert rc == 0
    assert len(_rows(tmp_tsv)) == 1


def test_cli_bad_source(tmp_tsv: Path) -> None:
    rc = subprocess.call([
        sys.executable, str(SCRIPT),
        "--tsv", str(tmp_tsv),
        "--source", "bad", "--ref", "S1",
        "--work-class", "bugfix", "--tier", "0",
        "--model", "m", "--verdict", "MERGE",
        "--gate", "pass", "--score", "100",
        "--time-s", "10", "--cost-usd", "0",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert rc == 1
