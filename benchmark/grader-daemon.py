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
from datetime import UTC, datetime
from pathlib import Path

# ── F1: sandbox path confinement ────────────────────────────────────────────
#
# GRADER-SECFIX-RECONCILE: fold in the VERIFIED path-traversal hardening from
# feat/bench-oob-grading @ e879957 (independently verified 2026-07-10). Every
# filesystem path derived from an attacker-controlled request field — most
# importantly ``run_id``, which flows into the work-snapshot dir (deletable via
# ``rmtree``) and into ``res/<run_id>.json`` — must be confined under its
# sandbox root so a ``../`` traversal or absolute path cannot reach, or delete,
# anything outside the bench-grader spool. Reverting this guard reddens
# selftest/test_grader_daemon.py::test_F1_path_traversal_rejected.

class SandboxError(Exception):
    """Trust-boundary violation: untrusted input escaped the sandbox root.

    Raised when an attacker-controlled request field (e.g. ``run_id``) is used
    in a path that resolves outside the daemon's sandbox root via ``../``
    traversal or an absolute path. Per F1 this is a HARD error — the request is
    rejected and NOTHING outside the sandbox is written or deleted.
    """


def _confine(untrusted: str, sandbox_root: Path) -> Path:
    """Resolve ``untrusted`` (attacker-controlled) under ``sandbox_root``.

    F1 hardening: every path derived from a request's untrusted fields must be
    confined so ``../`` traversal or absolute paths cannot reach a target
    outside the sandbox. The path is resolved with ``os.path.realpath`` and
    REJECTED (raising :class:`SandboxError`) if it does not stay within
    ``sandbox_root``. The returned path is absolute and normalized; it is NOT
    created — callers create/use it after confinement passes.

    ``untrusted`` may be a bare name (``r1``) or a relative path (``sub/r1``);
    both resolve under the sandbox. An absolute untrusted path, or one whose
    realpath escapes the sandbox, raises.
    """
    root_real = os.path.realpath(sandbox_root)
    # Join under the sandbox first so a bare name or relative path is anchored;
    # os.path.join with an absolute ``untrusted`` would DISCARD the root, so
    # reject absolute inputs explicitly before joining.
    if os.path.isabs(untrusted):
        raise SandboxError(
            f"refusing absolute path from untrusted input: {untrusted!r} "
            f"(must be relative under sandbox {root_real})"
        )
    candidate = os.path.realpath(os.path.join(root_real, untrusted))
    # The confined path must equal the root or live beneath it.
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise SandboxError(
            f"untrusted path escapes sandbox: {untrusted!r} -> {candidate} "
            f"is not under {root_real}"
        )
    return Path(candidate)


# ── configuration ──────────────────────────────────────────────────────────

KEYS_DIR           = Path("/home/bench-grader/keys")
KEYS_REDS_REPLAY   = KEYS_DIR / "reds-replay.tsv"
KEYS_SNAPSHOTS     = KEYS_DIR / "prefix-snapshots"

SPOOL_DIR          = Path("/var/lib/bench-grader/spool")
REQ_DIR            = SPOOL_DIR / "req"
RES_DIR            = SPOOL_DIR / "res"
WORK_DIR           = SPOOL_DIR / "work"

def _resolve_fleet_dir() -> Path:
    """Resolve the fleet/ dir from env or the daemon's own location.

    REACHABILITY CONTRACT (fleet/board/REACHABILITY-GATE.md): a cross-boundary
    path (this daemon runs as the bench-grader unix user, not stack) must NEVER
    be a hardcoded dev-box absolute. Prefer CHARON_FLEET if the deploying
    process sets it (e.g. a future non-WSL/production layout); otherwise derive
    it relative to this file's own location, which is portable across users,
    hosts, and worktrees. KEYS_DIR/SPOOL_DIR stay hardcoded intentionally —
    those are bench-grader-owned absolutes, not a stack-only dev-box path.
    """
    env_override = os.environ.get("CHARON_FLEET")
    if env_override:
        return Path(env_override).resolve()
    return Path(__file__).resolve().parents[1]


FLEET_DIR          = _resolve_fleet_dir()
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
_MODEL_USED_DIR_OVERRIDE: Path | None = None  # FLAW-3 fix test hook
_REQ_DIR_OVERRIDE: Path | None = None  # FLAW-1 fix test hook (hermetic _scan_requests)


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


def _model_used_dir() -> Path:
    """Return the active state/model-used/ dir (real or test-overridden)."""
    if _MODEL_USED_DIR_OVERRIDE is not None:
        return _MODEL_USED_DIR_OVERRIDE
    return FLEET_DIR / "state" / "model-used"


def _req_dir() -> Path:
    """Return the active spool req/ dir (real or test-overridden)."""
    if _REQ_DIR_OVERRIDE is not None:
        return _REQ_DIR_OVERRIDE
    return REQ_DIR

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
            "created": datetime.now(UTC).isoformat(),
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

    ROOT-CAUSE (b) FIX, part 2 (review F2 / EVAL-GRADER-PROVISION): the daemon
    runs as a DIFFERENT unix user (bench-grader) than the agent whose worktree
    it snapshots. A tool cache the agent's test run created — most commonly
    ``.hypothesis`` (property-test example database, often written with
    restrictive perms) — can contain files bench-grader cannot read even after
    the session root/dir itself is made traversable (preflight.sh:243/282).
    ``shutil.copytree`` raised on the FIRST such unreadable file, aborting the
    ENTIRE snapshot (and therefore the grade) over one irrelevant cache
    artifact — the confirmed mechanism behind a uniform fail-closed BLOCK
    verdict that is independent of what the model actually did
    (state/preflight-results/CONTROLS-STATUS.md, attempt 2). Fixed two ways:
    (i) known cache dirs are excluded by NAME so the daemon never even
    attempts to read into them; (ii) any OTHER individual file that still
    can't be read is skipped-and-logged rather than aborting the whole
    snapshot — the destination tree already has everything copytree managed
    to copy before it hit the unreadable straggler.
    """
    src = Path(worktree_path)
    # F1 — confine the snapshot dir under WORK_DIR. ``run_id`` is
    # attacker-controlled and flows straight into the ``rmtree(dst)`` below, so
    # a ``../`` traversal (or an absolute run_id) could delete a path OUTSIDE
    # the spool. ``_confine`` rejects that (raising SandboxError) BEFORE
    # anything is removed; the caller turns it into a rejection result.
    dst = _confine(run_id, WORK_DIR)
    if dst.exists():
        shutil.rmtree(dst)
    try:
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns(
                "__pycache__", ".pytest_cache", ".mypy_cache", ".hypothesis", "node_modules"
            ),
            symlinks=False,
            copy_function=shutil.copy,  # do NOT copy metadata / ownership
        )
    except shutil.Error as exc:
        # exc.args[0] is a list of (src, dst, why) tuples shutil accumulated —
        # everything else in the tree was already copied; only these stragglers
        # failed. Log each and continue: a handful of unreadable cache files
        # must never fail-closed a grade over an environment artifact.
        for item in exc.args[0]:
            bad_src = item[0] if item else "?"
            why = item[-1] if item else str(exc)
            log(f"snapshot {run_id}: SKIPPED unreadable file (non-fatal): {bad_src}: {why}")
        if not dst.exists():
            raise
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


# STAGE-DEMUX (2026-07-16): the spool's `stage` field is OVERLOADED — it
# means two different things in two subsystems (PHASE = write-now vs hold,
# vs TRUST = may-this-row-steer-a-live-number). The PHASE flag is derived
# from `actual_verdict` presence (the two-phase spool protocol), not from
# any on-the-wire field; the TRUST axis is the new 16th column on the
# ledger. To keep the on-the-wire name (currently `stage`, written by
# capture/enqueue-capture.sh) and the ledger column (also `stage`,
# consumed by grades.py / budget-derive.py) from colliding in this
# daemon, the daemon now reads a new explicit field ``trust_stage`` for
# the ledger column. ``stage`` is still accepted as a legacy alias so
# the existing enqueue-capture.sh writer continues to work without
# modification; the fail-closed STAGE-FAILCLOSED follow-up will switch
# enqueue-capture.sh to the new name and flip the default. See
# fleet/session-notes/2026-07-16-evidence/bench-provisional-deepdive.md §6.
_VALID_TRUST_STAGES = ("active", "provisional")
_DEFAULT_TRUST_STAGE = "active"


def _resolve_trust_stage(req: dict) -> str:
    """Return the requested ledger column-16 trust value for *req*.

    Accepts the canonical ``trust_stage`` field (going forward) and the
    legacy ``stage`` field (what capture/enqueue-capture.sh currently
    writes). Invalid values are clamped to the default rather than
    rejected — the request may have other valid content, and a malformed
    trust tag must not break the FINAL path entirely. The fail-closed
    flip (``STAGE-FAILCLOSED``) is a separate ticket; this one only
    makes the trust axis EXPRESSIBLE end-to-end.
    """
    raw = req.get("trust_stage")
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        raw = req.get("stage")
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return _DEFAULT_TRUST_STAGE
    raw = str(raw).strip()
    if raw not in _VALID_TRUST_STAGES:
        return _DEFAULT_TRUST_STAGE
    return raw


def _append_capture_row(model: str, ref: str, work_class: str, difficulty: str,
                        claimed_result: str, actual_verdict: str, actual_gate: str,
                        score: int, evidence: str, ledger_path: Path,
                        trust_stage: str = "active") -> None:
    """Append a source=live capture row to the ledger.

    STAGE-DEMUX (2026-07-16): the 16th column is the TRUST axis
    (provisional/active). Pre-demux the daemon hardcoded the literal
    ``"active"`` here, which made the trust axis inert in production
    (live row 45/45 = active, zero provisional ever). Now the value
    comes from the request's ``trust_stage`` (or legacy ``stage``)
    field; see ``_resolve_trust_stage`` for the precedence rules.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    discrepancy = _compute_discrepancy(claimed_result, actual_verdict, actual_gate)

    note_parts = [f"ref={ref}", f"evidence={evidence}"]
    if discrepancy:
        note_parts.append("FALSE-SUCCESS claimed=SUCCESS")
    note = "; ".join(note_parts).replace("\t", " ")

    row = [
        today, "live", ref, work_class, difficulty, model,
        actual_verdict, actual_gate, str(score),
        "-", "-", "-", note, "-", "-", trust_stage,
    ]
    line = "\t".join(row) + "\n"

    with open(ledger_path, "a") as fh:
        fh.write(line)

    tag = "FALSE-SUCCESS " if discrepancy else ""
    log(f"capture: appended {tag}live row: {model} / {ref} / {actual_verdict} score={score} trust_stage={trust_stage}")  # noqa: E501


# FLAW-3 fix (adversarial review 2026-07-13) -- GRADER-SECFIX-RECONCILE: fold
# this in. _read_request only checked FIELD PRESENCE, so a direct write into
# the 1733 spool (the `stack` user CAN write there, bypassing
# capture/enqueue-capture.sh's own enum validation entirely) could forge a
# `source=live` row with a bogus verdict/gate for ANY model -> instant HARD
# detain. This is a narrow, defensive addition (enum validation + a
# provenance anchor for unpaired FINALs) -- NOT a rewrite of the daemon; the
# owning ticket should reconcile/fold this into whatever broader request
# validation it lands.
_VALID_CAPTURE_VERDICTS = {"MERGE", "FIXES", "BLOCK"}
_VALID_CAPTURE_GATES = {"pass", "fail"}


def _model_used_matches(ref: str, model: str) -> bool:
    """Cross-check that *model* matches state/model-used/<ref>.

    charon-run.sh writes this file the instant a model's run succeeds
    (fleet/state/model-used/<ref>) -- BEFORE any capture row is even
    enqueued, and outside the bench-grader-owned spool a forger writes to.
    It is the only independent provenance anchor available for an UNPAIRED
    FINAL (no stored provisional to pair against): exactly the shape a
    forged direct-spool write takes, since it skips charon-run.sh's own
    provisional-then-FINAL lifecycle entirely.
    """
    try:
        p = _model_used_dir() / ref
        return p.is_file() and p.read_text().strip() == model
    except OSError:
        return False


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

    # ── FLAW-3: validate enums before trusting either phase ──────────────
    has_verdict = actual_verdict is not None and not (isinstance(actual_verdict, str) and actual_verdict.strip() == "")  # noqa: E501
    if has_verdict and str(actual_verdict) not in _VALID_CAPTURE_VERDICTS:
        log(f"capture: REJECTED {run_id} -- invalid actual_verdict {actual_verdict!r} (valid: {sorted(_VALID_CAPTURE_VERDICTS)})")  # noqa: E501
        return False
    if actual_gate and str(actual_gate) not in _VALID_CAPTURE_GATES:
        log(f"capture: REJECTED {run_id} -- invalid actual_gate {actual_gate!r} (valid: {sorted(_VALID_CAPTURE_GATES)})")  # noqa: E501
        return False

    # ── PROVISIONAL: store and wait ──────────────────────────────────────
    if not has_verdict:
        data = _load_provisionals()
        data[run_id] = {
            "model": model,
            "ref": ref,
            "work_class": work_class,
            "difficulty": difficulty,
            "claimed_result": claimed_result,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _save_provisionals(data)
        log(f"capture: stored provisional {run_id} (model={model}, ref={ref})")
        return False

    # ── FINAL: compute discrepancy and append ────────────────────────────
    prov_data = {}
    provs = _load_provisionals()
    paired = run_id in provs
    if paired:
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

    # ── FLAW-3: pin model provenance for an UNPAIRED FINAL ───────────────
    # A paired FINAL is trustworthy (the provisional was itself written by a
    # real charon-run.sh SUCCESS earlier in this same lifetime). An UNPAIRED
    # one has no such anchor, so require state/model-used/<ref> to confirm
    # this model really is the one that ran -- reject a forged/unbacked row.
    if not paired and not _model_used_matches(stored_ref, stored_model):
        log(f"capture: REJECTED unpaired FINAL {run_id} -- model {stored_model!r} not confirmed by state/model-used/{stored_ref} (unbacked/forged row)")  # noqa: E501
        return False

    if score is None:
        score = 0
    score_int = int(score)

    # ── STAGE-DEMUX (2026-07-16): the 16th column is the trust axis ──────
    # Pre-demux, the daemon hardcoded the literal "active" into every row
    # and never read req["stage"], so no code path could emit
    # source=live/stage=provisional — 45/45 live rows were active, zero
    # provisional ever (bench-provisional-deepdive.md §1). Now the value
    # is resolved from the request's trust_stage (canonical) or stage
    # (legacy alias) field; invalid values fall back to "active". This
    # makes the trust axis EXPRESSIBLE end-to-end. The fail-closed flip
    # (default active -> provisional) is STAGE-FAILCLOSED's job, not
    # this ticket's.
    trust_stage = _resolve_trust_stage(req)

    _append_capture_row(
        model=stored_model, ref=stored_ref, work_class=stored_wclass,
        difficulty=stored_diff, claimed_result=stored_claimed,
        actual_verdict=str(actual_verdict), actual_gate=str(actual_gate),
        score=score_int, evidence=evidence, ledger_path=ledger,
        trust_stage=trust_stage,
    )

    # Also append to versioned scorecard artifact
    version = _read_scorecard_version()
    _ensure_scorecard(version)
    discrepancy = _compute_discrepancy(stored_claimed, str(actual_verdict), str(actual_gate))
    note = f"ref={stored_ref};evidence={evidence}"
    if discrepancy:
        note += ";FALSE-SUCCESS claimed=SUCCESS"
    scorecard_row = {
        "timestamp": datetime.now(UTC).isoformat(),
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
    if score >= 90: return "MERGE"  # noqa: E701
    if score >= 50: return "FIXES"  # noqa: E701
    return "BLOCK"


def _append_to_ledger(model: str, unit_id: str, kind: str, score: int,
                      gate: str, reason: str, record: dict) -> None:
    """Append a row to model-scorecard.tsv.

    Uses the same column layout as model-scorecard.sh (16 columns):
    date, source, ref, work_class, tier, model, verdict, gate, score,
    time_s, cost_usd, corrections, note, tokens_in, tokens_out, stage.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
    run_id = req["run_id"]
    # F1 — confine the result path under RES_DIR. ``run_id`` is
    # attacker-controlled; reject any ``../`` traversal or absolute path before
    # touching the filesystem, so a hostile run_id can never write outside the
    # result spool.
    try:
        base = _confine(run_id, RES_DIR)
    except SandboxError as exc:
        log(f"REJECTED sandbox escape in result run_id={run_id!r}: {exc}")
        return
    result = {
        "run_id": run_id,
        "model": req["model"],
        "unit_id": req["unit_id"],
        "kind": req.get("kind", "section"),
        "success": success,
    }
    result.update(grade)
    result["record"] = record

    p = RES_DIR / f"{base.name}.json"
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
            "timestamp": datetime.now(UTC).isoformat(),
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

    except SandboxError as exc:
        # F1 — the untrusted run_id tried to escape the sandbox (path
        # traversal). Nothing outside the spool was written or deleted:
        # _confine raises before the snapshot rmtree. Record it as a hard
        # rejection (ERROR/error), not a graded verdict.
        log(f"REJECTED sandbox escape processing {run_id!r}: {exc}")
        _write_result(req, {
            "run_id": run_id,
            "model": req.get("model", "?"),
            "unit_id": req.get("unit_id", "?"),
            "kind": req.get("kind", "section"),
            "success": False,
            "score": 0,
            "verdict": "ERROR",
            "gate": "error",
            "reason": f"sandbox violation (rejected path traversal): {exc}",
            "record": {},
        }, {}, False)

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
    """Return new (not yet seen) request files sorted by mtime.

    Dedup key is the FILENAME (`seen` stores names, not run_ids) -- this is
    why FLAW-1 (2026-07-13 adversarial review) required the spool WRITER
    (capture/enqueue-capture.sh) to give the PROVISIONAL and FINAL phases of
    one run_id distinct on-disk filenames: pairing itself is keyed on the
    run_id FIELD inside the JSON (_handle_capture), never on this filename.
    """
    new = []
    try:
        for entry in sorted(_req_dir().iterdir(), key=lambda p: p.stat().st_mtime):
            if entry.is_file() and entry.suffix == ".json" and entry.name not in seen:
                new.append(entry)
    except OSError:
        pass
    return new


def log(msg: str) -> None:
    """Timestamped log line to stderr."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
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
    log(f"watching {_req_dir()}")

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
