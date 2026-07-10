"""Tests for the actuals ledger and freeze-ring scorecard.

FAIL-ON-REVERT test: corrupt the latest artifact -> reader returns last-known-good.
The test goes RED if the LKG fallback is removed.
"""
from __future__ import annotations

import time
from pathlib import Path

from charon.capability.actuals import ActualRow, ActualsLedger
from charon.capability.scorecard import ScorecardArtifact, ScorecardRow, ScorecardStore

# ── ActualsLedger tests ────────────────────────────────────────────────────────


def test_actuals_append_and_read(tmp_path: Path) -> None:
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    t0 = 1000.0
    row = ActualRow(
        model="gpt-4",
        work_class="codegen",
        run_result="pass",
        packet_parses=3,
        fail_on_revert_pass=True,
        gate_pass=True,
        failover_hops=0,
        tokens=1500,
        wall_clock_ms=45000,
        timestamp=t0,
    )
    ledger.append(row)
    rows = ledger.read()
    assert len(rows) == 1
    assert rows[0].model == "gpt-4"
    assert rows[0].work_class == "codegen"
    assert rows[0].run_result == "pass"
    assert rows[0].packet_parses == 3
    assert rows[0].fail_on_revert_pass is True
    assert rows[0].gate_pass is True
    assert rows[0].failover_hops == 0
    assert rows[0].tokens == 1500
    assert rows[0].wall_clock_ms == 45000
    assert rows[0].timestamp == t0
    assert rows[0].manager_accept is None


def test_actuals_manager_accept_column(tmp_path: Path) -> None:
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    row = ActualRow(
        model="claude-3",
        work_class="review",
        run_result="pass",
        packet_parses=1,
        fail_on_revert_pass=True,
        gate_pass=True,
        failover_hops=1,
        tokens=800,
        wall_clock_ms=22000,
        manager_accept=True,
    )
    ledger.append(row)
    rows = ledger.read()
    assert len(rows) == 1
    assert rows[0].manager_accept is True

    row2 = ActualRow(
        model="claude-3",
        work_class="review",
        run_result="pass",
        packet_parses=1,
        fail_on_revert_pass=True,
        gate_pass=True,
        failover_hops=1,
        tokens=800,
        wall_clock_ms=22000,
        manager_accept=False,
    )
    ledger.append(row2)
    rows = ledger.read()
    assert len(rows) == 2
    assert rows[1].manager_accept is False


def test_actuals_query_filter(tmp_path: Path) -> None:
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    ledger.append(ActualRow("m1", "codegen", "pass", 0, True, True, 0, 100, 100))
    ledger.append(ActualRow("m1", "review", "pass", 0, True, True, 0, 200, 200))
    ledger.append(ActualRow("m2", "codegen", "fail", 0, False, False, 2, 300, 300))

    assert len(ledger.query(model="m1")) == 2
    assert len(ledger.query(work_class="codegen")) == 2
    assert len(ledger.query(model="m1", work_class="codegen")) == 1
    assert len(ledger.query(model="m2", work_class="review")) == 0


def test_actuals_torn_trailing_line_skipped(tmp_path: Path) -> None:
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    ledger.append(ActualRow("m1", "codegen", "pass", 0, True, True, 0, 100, 100))
    with open(path, "a") as fh:
        fh.write('{"model": "m2", "work_class": "codegen", "run_result": "pas')
    rows = ledger.read()
    assert len(rows) == 1
    assert rows[0].model == "m1"


def test_actuals_empty_path(tmp_path: Path) -> None:
    path = tmp_path / "nope" / "actuals.jsonl"
    ledger = ActualsLedger(path)
    assert ledger.read() == []


# ── ScorecardStore tests ──────────────────────────────────────────────────────


def test_scorecard_freeze_and_read(tmp_path: Path) -> None:
    store = ScorecardStore(tmp_path / "scorecards")
    art = ScorecardArtifact(
        seq=1,
        timestamp=time.time(),
        rows=[
            ScorecardRow(model="gpt-4", work_class="codegen", score=0.92, samples=10),
        ],
    )
    store.freeze(art)
    loaded = store.read_latest()
    assert loaded is not None
    assert loaded.seq == 1
    assert len(loaded.rows) == 1
    assert loaded.rows[0].model == "gpt-4"
    assert loaded.rows[0].score == 0.92


def test_scorecard_latest_seq_is_incrementing(tmp_path: Path) -> None:
    store = ScorecardStore(tmp_path / "scorecards")
    for seq in (1, 2, 3):
        store.freeze(ScorecardArtifact(seq=seq, timestamp=float(seq), rows=[]))
    assert store.latest_seq() == 3
    assert store.lkg_seq() == 3

    loaded = store.read_latest()
    assert loaded is not None
    assert loaded.seq == 3


# ── FAIL-ON-REVERT test ────────────────────────────────────────────────────────


def test_fail_on_revert_corrupt_latest_falls_back_to_lkg(tmp_path: Path) -> None:
    """FAIL-ON-REVERT: corrupt the latest artifact -> reader returns LKG.

    This test MUST go RED if the LKG fallback in read_latest() is removed.
    """
    store = ScorecardStore(tmp_path / "scorecards")

    art1 = ScorecardArtifact(
        seq=1, timestamp=100.0,
        rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
    )
    store.freeze(art1)

    art2 = ScorecardArtifact(
        seq=2, timestamp=200.0,
        rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
    )
    store.freeze(art2)

    loaded_before = store.read_latest()
    assert loaded_before is not None
    assert loaded_before.seq == 2

    # Corrupt the latest artifact file (seq 2).
    art2_path = store._artifact_path("0000002")
    art2_path.write_text("{corrupt json!!!")
    assert art2_path.exists()

    now_loaded = store.read_latest()
    assert now_loaded is not None, "LKG fallback returned None — RED"
    assert now_loaded.seq == 1, f"Expected LKG seq=1, got seq={now_loaded.seq}"
    assert now_loaded.rows[0].model == "m1"


def test_fail_on_revert_corrupt_lkg_still_returns_none_when_both_dead(tmp_path: Path) -> None:
    """When BOTH latest and LKG artifacts are corrupt, read_latest returns None."""
    store = ScorecardStore(tmp_path / "scorecards")

    store.freeze(ScorecardArtifact(
        seq=1, timestamp=100.0,
        rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
    ))
    store.freeze(ScorecardArtifact(
        seq=2, timestamp=200.0,
        rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
    ))

    # Corrupt both artifacts.
    store._artifact_path("0000001").write_text("{bad")
    store._artifact_path("0000002").write_text("{bad")

    result = store.read_latest()
    assert result is None


def test_scorecard_read_at_seq(tmp_path: Path) -> None:
    store = ScorecardStore(tmp_path / "scorecards")
    art = ScorecardArtifact(
        seq=5, timestamp=500.0,
        rows=[ScorecardRow(model="m1", work_class="wg", score=0.7, samples=3)],
    )
    store.freeze(art)
    loaded = store.read_at_seq(5)
    assert loaded is not None
    assert loaded.seq == 5
    assert loaded.rows[0].score == 0.7

    assert store.read_at_seq(99) is None


def test_scorecard_missing_pointer_returns_none(tmp_path: Path) -> None:
    store = ScorecardStore(tmp_path / "empty")
    assert store.read_latest() is None
    assert store.latest_seq() is None
    assert store.lkg_seq() is None


def test_scorecard_corrupt_pointer_file(tmp_path: Path) -> None:
    store = ScorecardStore(tmp_path / "scorecards")
    store.freeze(ScorecardArtifact(seq=1, timestamp=1.0, rows=[]))
    # Corrupt the latest pointer.
    (tmp_path / "scorecards" / "latest").write_text("not-a-number\n")
    # Should still fall back to LKG.
    loaded = store.read_latest()
    assert loaded is not None
    assert loaded.seq == 1
