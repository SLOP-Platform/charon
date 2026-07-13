#!/usr/bin/env python3
"""grader-daemon.py — Out-of-band benchmark grading daemon (#26 Wave 1).

Runs as the dedicated ``bench-grader`` unix user. Watches
``/var/lib/bench-grader/spool/req/`` for incoming grading requests, grades
against private answer keys (``/home/bench-grader/keys/``), writes results to
``spool/res/``, appends scored rows to both the central
``model-scorecard.tsv`` ledger and a VERSIONED, APPEND-ONLY
``scorecard.v{n}.json`` artifact.

Architecture: fleet/ADR-BENCH-OOB-GRADING.md §1.6

RED-TEAM FIX #2 (artifact seam):
    The daemon writes versioned, append-only ``scorecard.v{n}.json`` artifacts
    that are NEVER imported by product code. Consumers read frozen artifacts only.
    Removing the versioning or making the artifact product-importable would
    collapse the trust boundary — the FAIL-ON-REVERT test proves this.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── configuration ──────────────────────────────────────────────────────────

KEYS_DIR           = Path("/home/bench-grader/keys")
KEYS_REDS_REPLAY   = KEYS_DIR / "reds-replay.tsv"
KEYS_SNAPSHOTS     = KEYS_DIR / "prefix-snapshots"

SPOOL_DIR          = Path("/var/lib/bench-grader/spool")
REQ_DIR            = SPOOL_DIR / "req"
RES_DIR            = SPOOL_DIR / "res"
WORK_DIR           = SPOOL_DIR / "work"

FLEET_DIR          = Path("/home/stack/charon-private/fleet")
BENCH_DIR          = FLEET_DIR / "benchmark"
SCORECARD_TSV      = FLEET_DIR / "model-scorecard.tsv"
UNITS_TSV          = BENCH_DIR / "units.tsv"
GRADERS_DIR        = BENCH_DIR / "graders"
STATE_PY           = BENCH_DIR / "lib" / "grade_state.py"
GRADERS_LIB_DIR    = BENCH_DIR / "lib"
SECTIONS_GRADERS   = BENCH_DIR / "graders"

SCORECARD_VERSION_FILE = BENCH_DIR / "scorecard.version"
SCORECARD_ARTIFACT_DIR = FLEET_DIR   # bench-grader-owned, same as SCORECARD_TSV

PROVISIONAL_STORE  = WORK_DIR / "capture"   # provisional capture pairing

POLL_INTERVAL_S    = 2          # seconds between req/ directory scans
GRADER_TIMEOUT_S   = 300        # max seconds a grader subprocess may run

# ── test hook: override ledger path for hermetic unit tests ──────────────────
_LEDGER_PATH_OVERRIDE: Path | None = None
_PROVISIONAL_STORE_OVERRIDE: Path | None = None
_SCORECARD_DIR_OVERRIDE: Path | None = None


def _ledger_path() -> Path:
    """Return the active ledger path (real or test-overridden)."""
    if _LEDGER_PATH_OVERRIDE is not None:
        return _LEDGER_PATH_OVERRIDE
    return SCORECARD_TSV


def _provisional_dir() -> Path:
    """Return the active provisional store dir (real or test-overridden)."""
    if _PROVISIONAL_STORE_OVERRIDE is not None:
        return _PROVISIONAL_STORE_OVERRIDE
    return PROVISIONAL_STORE


def _scorecard_dir() -> Path:
    """Return the active scorecard artifact dir (real or test-overridden)."""
    if _SCORECARD_DIR_OVERRIDE is not None:
        return _SCORECARD_DIR_OVERRIDE
    return SCORECARD_ARTIFACT_DIR

# ── section metadata (mirrored from lib/sections.sh) ───────────────────────

ALL_SECTIONS = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]

SECTION_INFO = {
    "S0": {"tier": 0, "work_class": "bugfix",             "fixture": "fixtures/sections/s0"},
    "S1": {"tier": 1, "work_class": "money-path",         "fixture": "fixtures/sections/s1"},
    "S2": {"tier": 2, "work_class": "routing",            "fixture": "fixtures/sections/s2"},
    "S3": {"tier": 2, "work_class": "ci-infra",           "fixture": "fixtures/sections/s3"},
    "S4": {"tier": 3, "work_class": "refactor",           "fixture": "fixtures/sections/s4"},
    "S5": {"tier": 4, "work_class": "greenfield-feature", "fixture": "fixtures/sections/s5"},
    "S6": {"tier": 3, "work_class": "frontend",           "fixture": "fixtures-fe"},
}


def section_grader_cmd(section: str) -> list[str]:
    if section == "S6":
        return ["node", str(SECTIONS_GRADERS / "s6.js")]
    name = section.lower()
    return [sys.executable, str(SECTIONS_GRADERS / f"{name}.py")]


def section_baseline(section: str) -> Path:
    return BENCH_DIR / SECTION_INFO[section]["fixture"]


def section_work_class(section: str) -> str:
    return SECTION_INFO[section]["work_class"]


def section_tier(section: str) -> int:
    return SECTION_INFO[section]["tier"]


# ── versioned scorecard ────────────────────────────────────────────────────

def _read_scorecard_version() -> int:
    try:
        vf = SCORECARD_VERSION_FILE
        return int(vf.read_text().strip())
    except (OSError, ValueError):
        return 1


def _scorecard_path(version: int) -> Path:
    return _scorecard_dir() / f"scorecard.v{version}.json"


def _ensure_scorecard(version: int) -> Path:
    """Create the scorecard file if it does not exist. Returns its Path."""
    p = _scorecard_path(version)
    if not p.exists():
        initial = {
            "version": version,
            "created": datetime.now(timezone.utc).isoformat(),
            "rows": [],
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(initial, indent=2) + "\n")
    return p


def _append_to_scorecard(version: int, row: dict) -> None:
    """Append a scored row to the versioned scorecard artifact.

    The artifact is a JSON object ``{"version": N, "created": "...", "rows":
    [...]}``.  Row appending reads-then-rewrites atomically via a temp file
    so no partial write is ever visible.  Existing rows are NEVER modified.
    """
    p = _scorecard_path(version)
    data = json.loads(p.read_text())
    data["rows"].append(row)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(p)


# ── request handling ───────────────────────────────────────────────────────

_REQUIRED_REQUEST_FIELDS = {"run_id", "model", "unit_id", "kind", "worktree"}


def _read_request(req_path: Path) -> dict | None:
    try:
        data = json.loads(req_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log(f"bad request {req_path.name}: {exc}")
        return None
    missing = _REQUIRED_REQUEST_FIELDS - set(data)
    if missing:
        log(f"bad request {req_path.name}: missing fields {missing}")
        return None
    return data


def _snapshot_worktree(worktree_path: str, run_id: str) -> Path:
    """Copy the agent's worktree into a read-only daemon snapshot.

    Strips ownership so the agent (who owns the source worktree) does not
    leak read-permissions into the daemon-private snapshot dir.
    Returns the snapshot directory path.
    """
    src = Path(worktree_path)
    dst = WORK_DIR / run_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"),
        symlinks=False,
        copy_function=shutil.copy,  # do NOT copy metadata / ownership
    )
    # Make snapshot read-only to the daemon too — the daemon grades against
    # it but should never mutate it.
    for f in dst.rglob("*"):
        if f.is_file():
            f.chmod(0o444)
        elif f.is_dir():
            f.chmod(0o555)
    return dst


def _wait_worktree_stable(worktree: Path, stable_sec: int = 20, max_wait: int = 60) -> None:
    """Block until no file in *worktree* has been written in *stable_sec* seconds.

    Mirrors ``wait_for_worktree_stable`` from lib/sections.sh.
    """
    waited = 0
    while waited < max_wait:
        newest = 0.0
        for f in worktree.rglob("*"):
            if f.is_file():
                try:
                    mtime = f.stat().st_mtime
                    if mtime > newest:
                        newest = mtime
                except OSError:
                    pass
        if newest == 0.0:
            return
        age = time.time() - newest
        if age >= stable_sec:
            return
        remaining = max(stable_sec - age, 1.0)
        time.sleep(remaining)
        waited += remaining
    log("worktree mtime still fresh after max wait — grading anyway")


# ── grading ─────────────────────────────────────────────────────────────────

def _grade_section(snapshot: Path, unit_id: str) -> dict:
    """Run the synthetic section grader against the snapshot worktree.

    Returns the grader's JSON output dict: ``{score, verdict, gate, reason}``.
    """
    baseline = section_baseline(unit_id)
    cmd = section_grader_cmd(unit_id) + [
        "--worktree", str(snapshot),
        "--baseline", str(baseline),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=GRADER_TIMEOUT_S,
            cwd=str(BENCH_DIR),
        )
    except subprocess.TimeoutExpired:
        return {"score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"grader timed out after {GRADER_TIMEOUT_S}s"}

    if proc.returncode != 0:
        return {"score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"grader crashed: {proc.stderr.strip() or proc.stdout.strip()}"}

    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except json.JSONDecodeError:
        return {"score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"grader produced non-JSON output: {proc.stdout[:200]}"}


def _grade(snapshot: Path, req: dict) -> dict:
    """Dispatch grading to the correct grader based on request kind."""
    kind = req.get("kind", "section")
    unit_id = req["unit_id"]

    if kind == "red":
        from graders.real import grade as grade_real
        result = grade_real(snapshot, unit_id)
        if result is not None:
            return result
        return {"score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"reds-replay: unit {unit_id!r} not found in reds-replay.tsv"}

    if kind == "preflight":
        # PREFLIGHT-CHUNK0 dispatch seam: route MODEL-PREFLIGHT battery tasks to
        # their LOAD-BEARING out-of-band graders in $KEYS/preflight/ (0700). The
        # grader ALWAYS returns a dict — it fails CLOSED (BLOCK) when no grader
        # is deployed, so an ungraded preflight task can never silently pass a
        # model into tier-models.tsv. The graders themselves are CHUNK-B.
        from graders.preflight import grade as grade_preflight
        return grade_preflight(snapshot, unit_id)

    # kind == "section" (or unknown — fall back to section grader)
    if unit_id.startswith("S") and unit_id in SECTION_INFO:
        return _grade_section(snapshot, unit_id)

    return {"score": 0, "verdict": "BLOCK", "gate": "fail",
            "reason": f"unknown unit {unit_id!r} — no grader available"}


# ── capture handler (kind=capture) ───────────────────────────────────────────

def _load_provisionals() -> dict:
    """Load the provisional capture store. Returns {run_id: data}."""
    store_dir = _provisional_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    pf = store_dir / "provisionals.json"
    if not pf.exists():
        return {}
    try:
        return json.loads(pf.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_provisionals(data: dict) -> None:
    store_dir = _provisional_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    pf = store_dir / "provisionals.json"
    tmp = pf.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(pf)


def _compute_discrepancy(claimed: str, actual_verdict: str, actual_gate: str) -> bool:
    """True when the model claimed SUCCESS but independent review found a failure."""
    if claimed != "SUCCESS":
        return False
    if actual_verdict == "BLOCK":
        return True
    if actual_gate == "fail":
        return True
    return False


def _append_capture_row(model: str, ref: str, work_class: str, difficulty: str,
                        claimed_result: str, actual_verdict: str, actual_gate: str,
                        score: int, evidence: str, ledger_path: Path) -> None:
    """Append a source=live capture row to the ledger."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    discrepancy = _compute_discrepancy(claimed_result, actual_verdict, actual_gate)

    note_parts = [f"ref={ref}", f"evidence={evidence}"]
    if discrepancy:
        note_parts.append("FALSE-SUCCESS claimed=SUCCESS")
    note = "; ".join(note_parts).replace("\t", " ")

    row = [
        today, "live", ref, work_class, difficulty, model,
        actual_verdict, actual_gate, str(score),
        "-", "-", "-", note, "-", "-", "active",
    ]
    line = "\t".join(row) + "\n"

    with open(ledger_path, "a") as fh:
        fh.write(line)

    tag = "FALSE-SUCCESS " if discrepancy else ""
    log(f"capture: appended {tag}live row: {model} / {ref} / {actual_verdict} score={score}")


def _handle_capture(req: dict, ledger_override: Path | None = None) -> bool:
    """Handle a capture-kind request.

    Two-phase protocol:
    - PROVISIONAL (actual_verdict absent/null): store for later pairing.
    - FINAL (actual_verdict present): pair with stored provisional, compute
      discrepancy, append a ``source=live`` row to the ledger.

    Returns True if a row was appended to the ledger.
    """
    actual_verdict = req.get("actual_verdict")
    actual_gate = req.get("actual_gate", "")
    score = req.get("score")

    ledger = ledger_override if ledger_override is not None else _ledger_path()

    run_id = req.get("run_id", "?")
    model = req.get("model", "?")
    ref = req.get("ref", "?")
    work_class = req.get("work_class", "ci-infra")
    difficulty = req.get("difficulty", "-")
    claimed_result = req.get("claimed_result", "?")
    evidence = req.get("evidence", "")

    # ── PROVISIONAL: store and wait ──────────────────────────────────────
    if actual_verdict is None or (isinstance(actual_verdict, str) and actual_verdict.strip() == ""):
        data = _load_provisionals()
        data[run_id] = {
            "model": model,
            "ref": ref,
            "work_class": work_class,
            "difficulty": difficulty,
            "claimed_result": claimed_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _save_provisionals(data)
        log(f"capture: stored provisional {run_id} (model={model}, ref={ref})")
        return False

    # ── FINAL: compute discrepancy and append ────────────────────────────
    prov_data = {}
    provs = _load_provisionals()
    if run_id in provs:
        prov_data = provs.pop(run_id)
        _save_provisionals(provs)
        log(f"capture: paired FINAL with provisional {run_id}")
    else:
        log(f"capture: FINAL {run_id} with no stored provisional — using request fields directly")

    stored_claimed = prov_data.get("claimed_result", claimed_result)
    stored_model = prov_data.get("model", model)
    stored_ref = prov_data.get("ref", ref)
    stored_wclass = prov_data.get("work_class", work_class)
    stored_diff = prov_data.get("difficulty", difficulty)

    if score is None:
        score = 0
    score_int = int(score)

    _append_capture_row(
        model=stored_model, ref=stored_ref, work_class=stored_wclass,
        difficulty=stored_diff, claimed_result=stored_claimed,
        actual_verdict=str(actual_verdict), actual_gate=str(actual_gate),
        score=score_int, evidence=evidence, ledger_path=ledger,
    )

    # Also append to versioned scorecard artifact
    version = _read_scorecard_version()
    _ensure_scorecard(version)
    discrepancy = _compute_discrepancy(stored_claimed, str(actual_verdict), str(actual_gate))
    note = f"ref={stored_ref};evidence={evidence}"
    if discrepancy:
        note += ";FALSE-SUCCESS claimed=SUCCESS"
    scorecard_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "model": stored_model,
        "unit_id": f"CAPTURE-{stored_ref}",
        "kind": "capture",
        "score": score_int,
        "verdict": str(actual_verdict),
        "gate": str(actual_gate),
        "reason": note,
        "time_s": -1,
        "cost_usd": "-",
        "corrections": -1,
        "finalize": False,
    }
    _append_to_scorecard(version, scorecard_row)

    return True

def _record_grade_state(model: str, unit_id: str, score: int, gate: str) -> dict:
    """Call grade_state.py record. Returns the record JSON as a dict.

    If grade_state.py refuses (stale state, missing init, etc.), the dict
    contains ``{"error": "...", "stale": bool}`` — callers handle it.
    """
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(GRADERS_LIB_DIR))
    cmd = [sys.executable, str(STATE_PY), "record", model, unit_id, str(score), gate]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                              cwd=str(BENCH_DIR), env=env)
    except subprocess.TimeoutExpired:
        return {"error": "grade_state.py record timed out"}
    try:
        return json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"error": f"grade_state.py produced non-JSON: {proc.stdout[:200]}"}


# ── scorecard ledger append ─────────────────────────────────────────────────

def _unit_stage(unit_id: str) -> str:
    """Look up unit stage from units.tsv (provisional / active). default=active."""
    if not UNITS_TSV.exists():
        return "active"
    for line in UNITS_TSV.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if cols[0] == "unit_id":
            continue
        if cols[0] == unit_id and len(cols) >= 3:
            return cols[2]
    return "active"


def _verdict_from_score(score: int) -> str:
    if score >= 90: return "MERGE"
    if score >= 50: return "FIXES"
    return "BLOCK"


def _append_to_ledger(model: str, unit_id: str, kind: str, score: int,
                      gate: str, reason: str, record: dict) -> None:
    """Append a row to model-scorecard.tsv.

    Uses the same column layout as model-scorecard.sh (16 columns):
    date, source, ref, work_class, tier, model, verdict, gate, score,
    time_s, cost_usd, corrections, note, tokens_in, tokens_out, stage.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    verdict = _verdict_from_score(score)

    if kind == "section" and unit_id in SECTION_INFO:
        wclass = section_work_class(unit_id)
        if unit_id == "S6":
            tier = "3" if score >= 90 else "2"
        else:
            tier = str(section_tier(unit_id))
    else:
        wclass = "ci-infra"   # default for reds-replay tasks
        tier = "-"

    time_s = record.get("time_s", "-")
    cost_usd = record.get("cost_usd", "-")
    corrections = record.get("corrections", "-")
    timed_out = record.get("timed_out", False)
    note = f"timeout ({reason})" if timed_out and reason else reason
    tokens_in = record.get("tokens_in", "-")
    tokens_out = record.get("tokens_out", "-")
    stage = _unit_stage(unit_id)

    row = [
        today, "bench", unit_id, wclass, tier, model, verdict, gate,
        str(score), str(time_s), str(cost_usd), str(corrections),
        note.replace("\t", " "), str(tokens_in), str(tokens_out), stage,
    ]
    line = "\t".join(row) + "\n"

    with open(SCORECARD_TSV, "a") as fh:
        fh.write(line)

    log(f"appended ledger row: {model} / {unit_id} / {verdict} score={score}")


# ── result writing ──────────────────────────────────────────────────────────

def _write_result(req: dict, grade: dict, record: dict, success: bool) -> None:
    """Atomically write the result to res/<run_id>.json."""
    result = {
        "run_id": req["run_id"],
        "model": req["model"],
        "unit_id": req["unit_id"],
        "kind": req.get("kind", "section"),
        "success": success,
    }
    result.update(grade)
    result["record"] = record

    p = RES_DIR / f"{req['run_id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    tmp.chmod(0o644)
    tmp.rename(p)


# ── main loop ───────────────────────────────────────────────────────────────

def _process_request(req_path: Path) -> None:
    """Process a single request file from req/."""
    req = _read_request(req_path)
    if req is None:
        _delete_req_safe(req_path)
        return

    run_id = req["run_id"]
    log(f"processing: {run_id}  model={req['model']}  unit={req['unit_id']}")

    # ── capture requests skip snapshot/grade ─────────────────────────────
    if req.get("kind") == "capture":
        try:
            appended = _handle_capture(req)
            success = True
            result_data = {
                "run_id": run_id,
                "model": req.get("model", "?"),
                "unit_id": req.get("unit_id", "?"),
                "kind": "capture",
                "success": True,
                "appended": appended,
            }
            _write_result(req, result_data, {}, True)
        except Exception:
            log(f"capture handler error for {run_id}:\n{traceback.format_exc()}")
            _write_result(req, {
                "run_id": run_id,
                "model": req.get("model", "?"),
                "unit_id": req.get("unit_id", "?"),
                "kind": "capture",
                "success": False,
                "score": 0,
                "verdict": "BLOCK",
                "gate": "fail",
                "reason": f"capture handler error: {traceback.format_exc()[:500]}",
            }, {}, False)
        _delete_req_safe(req_path)
        return

    try:
        # 1. snapshot the agent's worktree
        snapshot = _snapshot_worktree(req["worktree"], run_id)

        # 2. wait for snapshot to settle
        _wait_worktree_stable(snapshot)

        # 3. grade
        grade = _grade(snapshot, req)
        score = int(grade.get("score", 0))
        gate = grade.get("gate", "fail")

        # 4. record in grade_state
        record = _record_grade_state(req["model"], req["unit_id"], score, gate)

        # 5. if grade_state completed (even with errors), append to ledger
        if "finalize" in record and record.get("finalize"):
            final_score = record.get("final_score", score)
            _append_to_ledger(req["model"], req["unit_id"], req.get("kind", "section"),
                              final_score, gate, grade.get("reason", ""), record)

        # 6. append to versioned scorecard artifact
        version = _read_scorecard_version()
        _ensure_scorecard(version)
        scorecard_row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "model": req["model"],
            "unit_id": req["unit_id"],
            "kind": req.get("kind", "section"),
            "score": record.get("final_score", score),
            "verdict": _verdict_from_score(record.get("final_score", score)),
            "gate": gate,
            "reason": grade.get("reason", ""),
            "time_s": record.get("time_s", -1),
            "cost_usd": record.get("cost_usd", "-"),
            "corrections": record.get("corrections", -1),
            "finalize": record.get("finalize", False),
        }
        _append_to_scorecard(version, scorecard_row)

        # 7. write result
        _write_result(req, grade, record, True)

    except Exception:
        log(f"unhandled exception processing {run_id}:\n{traceback.format_exc()}")
        error_result = {
            "run_id": run_id,
            "model": req.get("model", "?"),
            "unit_id": req.get("unit_id", "?"),
            "kind": req.get("kind", "section"),
            "success": False,
            "score": 0,
            "verdict": "BLOCK",
            "gate": "fail",
            "reason": f"daemon internal error: {traceback.format_exc()[:500]}",
            "record": {},
        }
        _write_result(req, error_result, {}, False)

    # Always clean up the request file
    _delete_req_safe(req_path)


def _delete_req_safe(path: Path) -> None:
    """Try to delete a request file; never crash on failure.

    In a maildrop (mode 1733) dir, only the file's creator can unlink it.
    If the daemon can't unlink (different uid created it), that's fine —
    the daemon skips already-processed files by tracking run_id.
    """
    try:
        path.unlink()
    except OSError:
        pass


def _scan_requests(seen: set) -> list[Path]:
    """Return new (not yet seen) request files sorted by mtime."""
    new = []
    try:
        for entry in sorted(REQ_DIR.iterdir(), key=lambda p: p.stat().st_mtime):
            if entry.is_file() and entry.suffix == ".json" and entry.name not in seen:
                new.append(entry)
    except OSError:
        pass
    return new


def log(msg: str) -> None:
    """Timestamped log line to stderr."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def _ensure_dirs() -> None:
    """Ensure the daemon's output directories exist."""
    for d in (RES_DIR, WORK_DIR):
        d.mkdir(parents=True, exist_ok=True)


def main() -> None:
    _ensure_dirs()

    version = _read_scorecard_version()
    _ensure_scorecard(version)

    log(f"grader-daemon started (pid={os.getpid()}, scorecard=v{version})")
    log(f"watching {REQ_DIR}")

    seen: set[str] = set()

    while True:
        try:
            for req_path in _scan_requests(seen):
                seen.add(req_path.name)
                _process_request(req_path)
        except Exception:
            log(f"scan loop error: {traceback.format_exc()}")
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
