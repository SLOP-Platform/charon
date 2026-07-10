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
    """Latest advances on every freeze; LKG advances ONLY on GOOD scorecards.

    F4: previously this test asserted ``lkg_seq() == latest_seq()`` after every
    freeze, which enshrined the F1 bug (LKG always == latest). The CORRECT
    invariant is: LKG tracks the last GOOD seq, which DIVERGES from latest
    when a bad scorecard is frozen.
    """
    store = ScorecardStore(tmp_path / "scorecards")
    for seq in (1, 2, 3):
        store.freeze(ScorecardArtifact(seq=seq, timestamp=float(seq), rows=[]))
    assert store.latest_seq() == 3
    assert store.lkg_seq() == 3

    # Freeze a BAD scorecard (gate failed). Latest advances; LKG does NOT.
    store.freeze(ScorecardArtifact(
        seq=4, timestamp=4.0, rows=[],
        gate_pass=False, fail_on_revert_pass=False,
    ))
    assert store.latest_seq() == 4
    assert store.lkg_seq() == 3, "LKG must stay at the last GOOD seq (3), not 4"

    loaded = store.read_latest()
    assert loaded is not None
    assert loaded.seq == 3, "read_latest must fall back to the GOOD seq 3, not the bad seq 4"


# ── FAIL-ON-REVERT tests ───────────────────────────────────────────────────


def test_fail_on_revert_real_lkg_fallback_bad_scorecard(tmp_path: Path) -> None:
    """FAIL-ON-REVERT (F1): freeze GOOD seq=1, then a BAD seq=2; read_latest
    returns the GOOD seq=1 — NOT the bad seq=2 and NOT None.

    This test MUST go RED if the F1 fix is reverted (i.e. if LKG==latest):
    under the bug, LKG was always set to latest, so read_latest would return
    the bad seq=2 (because the bug never gated on goodness) — or, with the
    goodness check but a fake LKG, would return None (LKG==latest==2, both
    bad), failing the assertion that seq=1 is returned.
    """
    store = ScorecardStore(tmp_path / "scorecards")

    art1 = ScorecardArtifact(
        seq=1, timestamp=100.0,
        rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
        gate_pass=True, fail_on_revert_pass=True,
    )
    store.freeze(art1)

    art2 = ScorecardArtifact(
        seq=2, timestamp=200.0,
        rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
        gate_pass=False, fail_on_revert_pass=False,
    )
    store.freeze(art2)

    assert store.latest_seq() == 2
    assert store.lkg_seq() == 1, "LKG must be the last GOOD seq (1), not latest (2)"

    loaded = store.read_latest()
    assert loaded is not None, "real LKG fallback returned None — RED"
    assert loaded.seq == 1, f"Expected GOOD seq=1, got seq={loaded.seq}"
    assert loaded.rows[0].model == "m1"


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


# ── F2: non-numeric LKG pointer must not crash ──────────────────────────────


def test_scorecard_non_numeric_lkg_pointer_does_not_crash(tmp_path: Path) -> None:
    """F2: a corrupted/non-numeric LKG pointer must NOT raise in read_latest().

    The reader treats an unparseable pointer as "no LKG" (returns None or the
    latest-good, but never raises ValueError).
    """
    store = ScorecardStore(tmp_path / "scorecards")
    # Cold start: no artifacts, but a garbage LKG pointer on disk.
    store.freeze(ScorecardArtifact(
        seq=1, timestamp=1.0, rows=[],
        gate_pass=True, fail_on_revert_pass=True,
    ))
    # Corrupt the LKG pointer into garbage.
    (tmp_path / "scorecards" / "lkg").write_text("GARBAGE-NOT-A-NUMBER\n")

    # Must not raise.
    loaded = store.read_latest()
    # Latest (seq 1) is GOOD, so it is returned — but the garbage LKG did not
    # cause a crash either way.
    assert loaded is not None
    assert loaded.seq == 1

    # lkg_seq() must return None for a non-numeric pointer, not raise.
    assert store.lkg_seq() is None


def test_scorecard_garbage_lkg_pointer_and_bad_latest_returns_none(tmp_path: Path) -> None:
    """F2: bad latest AND garbage LKG -> read_latest returns None, no crash."""
    store = ScorecardStore(tmp_path / "scorecards")
    store.freeze(ScorecardArtifact(
        seq=1, timestamp=1.0, rows=[],
        gate_pass=False, fail_on_revert_pass=False,
    ))
    # Corrupt the LKG pointer to garbage.
    (tmp_path / "scorecards" / "lkg").write_text("xx-not-int\n")
    # Latest is bad (gate failed) -> no fallback path is recoverable.
    result = store.read_latest()
    assert result is None


# ── F3: mid-file corruption must not drop later rows ────────────────────────


def test_actuals_mid_file_corruption_skipped_not_breaking(tmp_path: Path) -> None:
    """F3: a corrupt line in the MIDDLE of the ledger must NOT cause read()
    to drop valid rows written AFTER it. The corrupt line is skipped; reading
    continues.
    """
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    ledger.append(ActualRow("m1", "codegen", "pass", 0, True, True, 0, 100, 100, timestamp=1.0))
    # Inject a corrupt line directly into the middle of the file.
    with open(path, "a") as fh:
        fh.write('{not valid json\n')
    # Now append valid rows AFTER the corrupt line.
    ledger.append(ActualRow("m2", "codegen", "pass", 0, True, True, 0, 200, 200, timestamp=2.0))
    ledger.append(ActualRow("m3", "codegen", "pass", 0, True, True, 0, 300, 300, timestamp=3.0))

    rows = ledger.read()
    # We should get m1, m2, m3 — the corrupt middle line is skipped, not a stop.
    assert len(rows) == 3, f"expected 3 rows (m1,m2,m3), got {len(rows)}"
    assert [r.model for r in rows] == ["m1", "m2", "m3"]
    assert ledger.skipped_corrupt == 1


def test_actuals_torn_trailing_line_still_skipped(tmp_path: Path) -> None:
    """F3 regression guard: the prior torn-trailing-line behavior is preserved
    (a trailing corrupt line is tolerated and does not count as a skip)."""
    path = tmp_path / "actuals.jsonl"
    ledger = ActualsLedger(path)
    ledger.append(ActualRow("m1", "codegen", "pass", 0, True, True, 0, 100, 100, timestamp=1.0))
    with open(path, "a") as fh:
        fh.write('{"model": "m2", "work_class": "codegen", "run_result": "pas')
    rows = ledger.read()
    assert len(rows) == 1
    assert rows[0].model == "m1"
    assert ledger.skipped_corrupt == 0


# ── LKG read path: non-numeric latest pointer also guarded ─────────────────


def test_scorecard_non_numeric_latest_pointer_does_not_crash(tmp_path: Path) -> None:
    """F2 partner: a non-numeric LATEST pointer must also not crash; the reader
    treats it as missing and falls back to LKG if available."""
    store = ScorecardStore(tmp_path / "scorecards")
    store.freeze(ScorecardArtifact(
        seq=1, timestamp=1.0, rows=[],
        gate_pass=True, fail_on_revert_pass=True,
    ))
    store.freeze(ScorecardArtifact(
        seq=2, timestamp=2.0, rows=[],
        gate_pass=True, fail_on_revert_pass=True,
    ))
    # Corrupt the latest pointer to garbage.
    (tmp_path / "scorecards" / "latest").write_text("ZZZ\n")
    # read_latest must not raise; it falls back via LKG (seq 2, GOOD).
    loaded = store.read_latest()
    assert loaded is not None
    assert loaded.seq == 2
    # latest_seq() returns None for non-numeric, not raise.
    assert store.latest_seq() is None


# ── Cold start: no good scorecard -> read_latest returns None ───────────────


def test_scorecard_cold_start_no_good_returns_none(tmp_path: Path) -> None:
    """F1 cold-start: with no GOOD scorecard yet, read_latest returns None
    (not garbage). The LKG pointer is unset for a bad-only history."""
    store = ScorecardStore(tmp_path / "scorecards")
    store.freeze(ScorecardArtifact(
        seq=1, timestamp=1.0, rows=[],
        gate_pass=False, fail_on_revert_pass=False,
    ))
    assert store.lkg_seq() is None
    assert store.read_latest() is None
