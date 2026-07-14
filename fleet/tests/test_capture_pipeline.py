"""test_capture_pipeline.py — hermetic unit tests for the grader-daemon capture handler.

FAIL-ON-REVERT: if the capture handler is removed or the discrepancy computation
is broken, these tests go RED. The handler MUST be imported and called directly
against a scratch ledger — NOT via the live daemon loop.

Run: python3 -m pytest fleet/tests/test_capture_pipeline.py -q
"""
from __future__ import annotations

import importlib.util
import os
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
    """Reset global overrides before each test and set provisional store + scorecard dir to tmpdir."""
    gd._LEDGER_PATH_OVERRIDE = None
    gd._PROVISIONAL_STORE_OVERRIDE = Path(capture_tmpdir) / "capture-provisionals"
    gd._SCORECARD_DIR_OVERRIDE = Path(capture_tmpdir) / "scorecard-artifacts"
    # FLAW-3 fix test hook: empty by default -- an unpaired FINAL with no
    # matching state/model-used/<ref> record must be REJECTED (see
    # test_flaw3_* below). Tests exercising a *legitimate* unpaired FINAL
    # (e.g. a hand-closed ticket) must write a matching record here first.
    gd._MODEL_USED_DIR_OVERRIDE = Path(capture_tmpdir) / "model-used"
    # FLAW-1 fix test hook: hermetic req/ dir for _scan_requests tests.
    gd._REQ_DIR_OVERRIDE = Path(capture_tmpdir) / "spool-req"


def _rows(p: Path) -> list[list[str]]:
    return [ln.split("\t") for ln in p.read_text().splitlines()
            if ln and not ln.startswith("#")]


def _write_model_used(capture_tmpdir: Path, ref: str, model: str) -> None:
    """Back a legitimate unpaired FINAL with the provenance anchor charon-run.sh
    would have written at SUCCESS time (state/model-used/<ref> = <model>)."""
    d = Path(capture_tmpdir) / "model-used"
    d.mkdir(parents=True, exist_ok=True)
    (d / ref).write_text(model + "\n")


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


def test_append_capture_row_no_discrepancy(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """When claimed_result is NOT SUCCESS, no FALSE-SUCCESS note should appear."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger

    run_id = "test-run-exhausted-001"
    model = "gpt-5.4"
    ref = "some-ticket"
    wclass = "bugfix"
    difficulty = "0"
    evidence = "model exhausted all providers"
    _write_model_used(capture_tmpdir, ref, model)  # FLAW-3: legit unpaired FINAL needs an anchor

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


def test_final_without_provisional_still_appends(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """A self-contained, PROVENANCE-BACKED FINAL (no prior provisional, but a
    matching state/model-used/<ref> anchor -- e.g. a hand-closed ticket)
    should still append a row (FLAW-3 narrows this to backed rows only)."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "standalone-ref", "deepseek-v4-pro")

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

def test_fail_on_revert_discrepancy_must_detect_false_success(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """REVERT-GUARD: the discrepancy detector MUST flag a SUCCESS→BLOCK as false."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "revert-test", "fake-model")

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


def test_fail_on_revert_score_bound(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """REVERT-GUARD: a false-success score MUST be ≤ 20."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "score-test", "fake-model")

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

def test_capture_row_schema_compliance(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """Every capture row must have exactly 16 TAB-separated columns."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "schema-ref", "test-model")

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


# ── FLAW-3 (adversarial review 2026-07-13): validate enums + pin provenance ──
# for an unpaired FINAL. Direct writes into the 1733 spool bypass
# capture/enqueue-capture.sh's own enum validation entirely, so the daemon
# itself must not trust a request's fields at face value.

def test_flaw3_rejects_invalid_actual_verdict(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """FAIL-ON-REVERT: a forged verdict outside {MERGE,FIXES,BLOCK} must be
    REJECTED -- no row appended, even with a valid model-used anchor."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "forge-verdict-ref", "kimi-k2.6")

    forged = {
        "run_id": "test-flaw3-verdict-001",
        "model": "kimi-k2.6",
        "unit_id": "CAPTURE-forge-verdict-ref",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "forge-verdict-ref",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "SUPER-MERGE",  # not a real verdict
        "actual_gate": "pass",
        "score": 100,
        "evidence": "forged row",
    }
    appended = gd._handle_capture(forged)
    assert appended is False, "REVERT DETECTED: a forged actual_verdict was accepted"
    assert len(_rows(scratch_ledger)) == 0

    gd._LEDGER_PATH_OVERRIDE = None


def test_flaw3_rejects_invalid_actual_gate(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """FAIL-ON-REVERT: a forged gate outside {pass,fail} must be REJECTED."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "forge-gate-ref", "kimi-k2.6")

    forged = {
        "run_id": "test-flaw3-gate-001",
        "model": "kimi-k2.6",
        "unit_id": "CAPTURE-forge-gate-ref",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "forge-gate-ref",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "MERGE",
        "actual_gate": "definitely-passed",  # not a real gate value
        "score": 100,
        "evidence": "forged row",
    }
    appended = gd._handle_capture(forged)
    assert appended is False, "REVERT DETECTED: a forged actual_gate was accepted"
    assert len(_rows(scratch_ledger)) == 0

    gd._LEDGER_PATH_OVERRIDE = None


def test_flaw3_rejects_unbacked_unpaired_final(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """FAIL-ON-REVERT: an unpaired FINAL (no stored provisional) for a model
    with NO matching state/model-used/<ref> record must be REJECTED -- this
    is exactly the shape of a direct forged spool write bypassing
    enqueue-capture.sh's own provisional-then-FINAL lifecycle entirely."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    # deliberately NOT calling _write_model_used — no anchor exists for this ref

    forged = {
        "run_id": "test-flaw3-unbacked-001",
        "model": "some-model-i-want-to-frame",
        "unit_id": "CAPTURE-unbacked-ref",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "unbacked-ref",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "MERGE",
        "actual_gate": "pass",
        "score": 100,
        "evidence": "forged row with no backing model-used record",
    }
    appended = gd._handle_capture(forged)
    assert appended is False, "REVERT DETECTED: an unbacked forged MERGE row was accepted"
    assert len(_rows(scratch_ledger)) == 0

    gd._LEDGER_PATH_OVERRIDE = None


def test_flaw3_rejects_model_mismatch_against_model_used(scratch_ledger: Path, capture_tmpdir: Path) -> None:
    """FAIL-ON-REVERT: an unpaired FINAL naming a DIFFERENT model than the
    one state/model-used/<ref> recorded must be REJECTED (framing another
    model for a ref it did not actually run)."""
    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    _write_model_used(capture_tmpdir, "mismatch-ref", "real-winning-model")

    forged = {
        "run_id": "test-flaw3-mismatch-001",
        "model": "victim-model",  # NOT the model that actually ran per model-used
        "unit_id": "CAPTURE-mismatch-ref",
        "kind": "capture",
        "worktree": "/dev/null",
        "claimed_result": "SUCCESS",
        "work_class": "bugfix",
        "ref": "mismatch-ref",
        "difficulty": "0",
        "stage": "active",
        "actual_verdict": "BLOCK",
        "actual_gate": "fail",
        "score": 0,
        "evidence": "forged BLOCK row to frame victim-model",
    }
    appended = gd._handle_capture(forged)
    assert appended is False, "REVERT DETECTED: a model-mismatched forged row was accepted"
    assert len(_rows(scratch_ledger)) == 0

    gd._LEDGER_PATH_OVERRIDE = None


# ── FLAW-1 (adversarial review 2026-07-13): PROVISIONAL/FINAL filename ──────
# collision. enqueue-capture.sh writes to spool/req/<basename>.json where the
# provisional and FINAL for one lifetime share the SAME run_id (by design,
# for _handle_capture's pairing) but MUST now use DIFFERENT filenames --
# otherwise grader-daemon.py's _scan_requests() `seen`-by-FILENAME dedup
# silently drops the FINAL and the MERGE never reaches the ledger.

def test_flaw1_provisional_then_final_same_run_id_distinct_filenames(
    scratch_ledger: Path, capture_tmpdir: Path
) -> None:
    """FAIL-ON-REVERT: drive the real spool writer (enqueue-capture.sh) for
    ONE lifetime (provisional -> FINAL MERGE, same run_id) and the real
    daemon scan function (_scan_requests) across two poll passes, then hand
    each request straight to _handle_capture the same way _process_request
    does for kind=capture (skipping only _write_result's hardcoded
    /var/lib/bench-grader/spool/res/ write, which this sandbox's `stack`
    user cannot reach -- unrelated to what FLAW-1 touches). Exactly ONE
    promoted source=live MERGE row must land -- proving the FINAL was not
    swallowed by the filename-based `seen` dedup."""
    import subprocess

    gd._LEDGER_PATH_OVERRIDE = scratch_ledger
    req_dir = gd._req_dir()
    req_dir.mkdir(parents=True, exist_ok=True)

    fleet_dir = Path(__file__).resolve().parent.parent
    enqueue = fleet_dir / "capture" / "enqueue-capture.sh"
    model = "kimi-k2.6"
    ref = "FLAW1-LIFETIME"
    run_id = f"capture-{model}-{ref}"
    _write_model_used(capture_tmpdir, ref, model)

    def _process_like_daemon(p: Path) -> None:
        req = gd._read_request(p)
        assert req is not None, f"request file {p} failed to parse"
        gd._handle_capture(req)
        p.unlink()

    # Phase 1: charon-run.sh's provisional enqueue (real script, real run_id).
    subprocess.run(
        [str(enqueue), "--model", model, "--claimed-result", "SUCCESS",
         "--ref", ref, "--stage", "provisional", "--run-id", run_id],
        env={**os.environ, "CAPTURE_SPOOL_DIR": str(req_dir)},
        check=True, capture_output=True,
    )

    # Simulate the daemon's poll loop: scan #1 sees the provisional, marks it seen.
    seen: set = set()
    batch1 = gd._scan_requests(seen)
    assert len(batch1) == 1, f"expected exactly 1 provisional file, got {len(batch1)}"
    for p in batch1:
        seen.add(p.name)
        _process_like_daemon(p)
    assert len(_rows(scratch_ledger)) == 0, "provisional must not append a ledger row"

    # Phase 2: done.sh's FINAL enqueue -- SAME run_id, stage=active, MERGE/pass.
    subprocess.run(
        [str(enqueue), "--model", model, "--claimed-result", "SUCCESS",
         "--ref", ref, "--stage", "active", "--run-id", run_id,
         "--actual-verdict", "MERGE", "--actual-gate", "pass", "--score", "100",
         "--evidence", "done.sh verified close"],
        env={**os.environ, "CAPTURE_SPOOL_DIR": str(req_dir)},
        check=True, capture_output=True,
    )

    # THE REVERT-DETECTOR: if enqueue-capture.sh reverts to writing
    # `$RUN_ID.json` for both phases, this glob returns 0 files (the FINAL
    # write would have collided onto the SAME path phase-1 already deleted),
    # not 1 -- assert the on-disk fix directly before even re-scanning.
    on_disk = sorted(req_dir.glob("*.json"))
    assert len(on_disk) == 1, (
        f"REVERT DETECTED: provisional and FINAL collided onto the same "
        f"filename (expected exactly 1 remaining FINAL file on disk after "
        f"phase-1 processing deleted the provisional's distinct file): "
        f"{[p.name for p in on_disk]}"
    )

    # Scan #2 must find the FINAL as a NEW file (distinct name, not in `seen`).
    batch2 = gd._scan_requests(seen)
    assert len(batch2) == 1, (
        f"REVERT DETECTED: FINAL file was swallowed by filename-based `seen` "
        f"dedup (expected 1 new file for scan #2, got {len(batch2)})"
    )
    for p in batch2:
        seen.add(p.name)
        _process_like_daemon(p)

    rows = _rows(scratch_ledger)
    assert len(rows) == 1, f"expected exactly ONE promoted live MERGE row, got {len(rows)}: {rows}"
    r = rows[0]
    assert r[1] == "live"
    assert r[5] == model
    assert r[6] == "MERGE", f"REVERT DETECTED: FINAL MERGE never landed (verdict={r[6]})"
    assert r[7] == "pass"

    gd._LEDGER_PATH_OVERRIDE = None
