"""test_capture_pipeline.py — hermetic unit tests for the grader-daemon capture handler.

FAIL-ON-REVERT: if the capture handler is removed or the discrepancy computation
is broken, these tests go RED. The handler MUST be imported and called directly
against a scratch ledger — NOT via the live daemon loop.

Run: python3 -m pytest fleet/tests/test_capture_pipeline.py -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_DAEMON_PATH = Path(__file__).resolve().parent.parent / "benchmark" / "grader-daemon.py"
_spec = importlib.util.spec_from_file_location("grader_daemon", str(_DAEMON_PATH))
_gd = importlib.util.module_from_spec(_spec)
sys.modules["grader_daemon"] = _gd
_spec.loader.exec_module(_gd)
gd = _gd  # type: ignore[reportUnknownVariableType]


def _header() -> str:
    return (
        "# test ledger (hermetic)\n"
        "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
        "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage\n"
    )


@pytest.fixture
def scratch_ledger(tmp_path: Path) -> Path:
    p = tmp_path / "model-scorecard.tsv"
    p.write_text(_header())
    return p


@pytest.fixture
def capture_tmpdir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def reset_overrides(capture_tmpdir: Path) -> None:
    """Reset global overrides before each test and set provisional store to tmpdir."""
    gd._LEDGER_PATH_OVERRIDE = None
    gd._PROVISIONAL_STORE_OVERRIDE = Path(capture_tmpdir) / "capture-provisionals"


def _rows(p: Path) -> list[list[str]]:
    return [ln.split("\t") for ln in p.read_text().splitlines()
            if ln and not ln.startswith("#")]


# ── discrepancy computation ──────────────────────────────────────────────────

def test_discrepancy_success_block() -> None:
    assert gd._compute_discrepancy("SUCCESS", "BLOCK", "pass") is True


def test_discrepancy_success_fail_gate() -> None:
    assert gd._compute_discrepancy("SUCCESS", "MERGE", "fail") is True


def test_discrepancy_success_pass() -> None:
    assert gd._compute_discrepancy("SUCCESS", "MERGE", "pass") is False


def test_discrepancy_exhausted_block() -> None:
    assert gd._compute_discrepancy("EXHAUSTED", "BLOCK", "fail") is False


def test_discrepancy_fail_block() -> None:
    assert gd._compute_discrepancy("FAIL", "BLOCK", "fail") is False


# ── capture row append with scratch ledger ───────────────────────────────────

def test_append_capture_row_false_success(scratch_ledger: Path) -> None:
    """FAIL-ON-REVERT: feeds a PROVISIONAL+FINAL(actual=BLOCK,gate=fail) pair
    to the capture handler → appends ONE live row with FALSE-SUCCESS note and
    score≤20 to a scratch ledger."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-run-false-success-001"
    model = "kimi-k2.6-nw"
    ref = "BRIDGE-PUSH"
    wclass = "ci-infra"
    difficulty = "3"
    evidence = "CRITICAL: concurrent thread_post silently DROPS messages"

    # Phase 1: enqueue PROVISIONAL
    prov_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": wclass,
        "ref": ref,
        "difficulty": difficulty,
        "stage": "provisional",
        "evidence": "",
    }
    prov_appended = gd._handle_capture(prov_req)
    # provisional should NOT append a row
    assert prov_appended is False
    assert len(_rows(scratch_ledger)) == 0

    # Phase 2: enqueue FINAL with BLOCK/fail
    final_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": wclass,
        "ref": ref,
        "difficulty": difficulty,
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 15,
        "evidence": evidence,
    }
    final_appended = gd._handle_capture(final_req)
    assert final_appended is True

    rows = _rows(scratch_ledger)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}: {rows}"

    r = rows[0]
    assert r[1] == "live", f"source should be 'live', got {r[1]}"
    assert r[2] == ref, f"ref mismatch: {r[2]}"
    assert r[3] == wclass, f"work_class mismatch: {r[3]}"
    assert r[4] == difficulty, f"difficulty mismatch: {r[4]}"
    assert r[5] == model, f"model mismatch: {r[5]}"
    assert r[6] == "BLOCK", f"verdict mismatch: {r[6]}"
    assert r[7] == "fail", f"gate mismatch: {r[7]}"
    assert int(r[8]) == 15, f"score mismatch: {r[8]}"
    assert int(r[8]) <= 20, f"score {r[8]} should be ≤ 20"
    assert "FALSE-SUCCESS" in r[12], f"note missing FALSE-SUCCESS: {r[12]}"
    assert evidence in r[12], f"note missing evidence: {r[12]}"
    assert r[15] == "active", f"stage should be 'active', got {r[15]}"

    # Clean up override
    gd._LEDGER_PATH_OVERRIDE = None


def test_append_capture_row_no_discrepancy(scratch_ledger: Path) -> None:
    """When claimed_result is NOT SUCCESS, no FALSE-SUCCESS note should appear."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-run-exhausted-001"
    model = "gpt-5.4"
    ref = "some-ticket"
    wclass = "bugfix"
    difficulty = "0"
    evidence = "model exhausted all providers"

    # FINAL (self-contained — no provisional needed)
    final_req = {
        "run_id": run_id,
        "model": model,
        "unit_id": f"CAPTURE-{ref}",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "EXHAUSTED",
        "work_class": wclass,
        "ref": ref,
        "difficulty": difficulty,
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 0,
        "evidence": evidence,
    }
    appended = gd._handle_capture(final_req)
    assert appended is True

    rows = _rows(scratch_ledger)
    assert len(rows) == 1
    r = rows[0]
    assert "FALSE-SUCCESS" not in r[12], f"should not flag false-success for EXHAUSTED: {r[12]}"
    assert r[1] == "live"

    gd._LEDGER_PATH_OVERRIDE = None


def test_final_without_provisional_still_appends(scratch_ledger: Path) -> None:
    """A self-contained FINAL (no prior provisional) should still append a row."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-run-standalone-001"
    final_req = {
        "run_id": run_id,
        "model": "deepseek-v4-pro",
        "unit_id": "CAPTURE-standalone",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "routing",
        "ref": "standalone-ref",
        "difficulty": "2",
        "stage": "active",
        "actual_verdict": "MERGE",
        "actual_gate": "pass",
        "score": 95,
        "evidence": "clean review",
    }
    appended = gd._handle_capture(final_req)
    assert appended is True

    rows = _rows(scratch_ledger)
    assert len(rows) == 1
    r = rows[0]
    assert r[5] == "deepseek-v4-pro"
    assert r[6] == "MERGE"
    assert r[7] == "pass"
    assert int(r[8]) == 95
    assert "FALSE-SUCCESS" not in r[12]

    gd._LEDGER_PATH_OVERRIDE = None


# ── FAIL-ON-REVERT: if _compute_discrepancy is gutted, the row still appears
#    but WITHOUT the FALSE-SUCCESS note. This test proves the discrepancy logic
#    is wired correctly — the note field is the integrity signal.              ──

def test_fail_on_revert_discrepancy_must_detect_false_success(scratch_ledger: Path) -> None:
    """REVERT-GUARD: the discrepancy detector MUST flag a SUCCESS→BLOCK as false."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-revert-guard-001"
    final_req = {
        "run_id": run_id,
        "model": "fake-model",
        "unit_id": "CAPTURE-revert",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "revert-test",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 5,
        "evidence": "revert guard test",
    }
    gd._handle_capture(final_req)

    rows = _rows(scratch_ledger)
    assert len(rows) == 1
    # The INTEGRITY SIGNAL: FALSE-SUCCESS MUST be in the note
    assert "FALSE-SUCCESS" in rows[0][12], \
        "REVERT DETECTED: discrepancy not flagged — FALSE-SUCCESS missing from note"

    gd._LEDGER_PATH_OVERRIDE = None


def test_fail_on_revert_score_bound(scratch_ledger: Path) -> None:
    """REVERT-GUARD: a false-success score MUST be ≤ 20."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-revert-score-001"
    final_req = {
        "run_id": run_id,
        "model": "fake-model",
        "unit_id": "CAPTURE-score",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "score-test",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 15,
        "evidence": "score-bound test",
    }
    gd._handle_capture(final_req)

    rows = _rows(scratch_ledger)
    assert len(rows) == 1
    score_val = int(rows[0][8])
    assert score_val <= 20, \
        f"REVERT DETECTED: false-success score {score_val} > 20"

    gd._LEDGER_PATH_OVERRIDE = None


# ── Schema compliance ────────────────────────────────────────────────────────

def test_capture_row_schema_compliance(scratch_ledger: Path) -> None:
    """Every capture row must have exactly 16 TAB-separated columns."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    final_req = {
        "run_id": "test-schema-001",
        "model": "test-model",
        "unit_id": "CAPTURE-schema",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "routing",
        "ref": "schema-ref",
        "difficulty": "2",
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 12,
        "evidence": "schema compliance test",
    }
    gd._handle_capture(final_req)

    rows = _rows(scratch_ledger)
    assert len(rows) == 1
    assert len(rows[0]) == 16, f"row has {len(rows[0])} cols, expected 16"

    gd._LEDGER_PATH_OVERRIDE = None
