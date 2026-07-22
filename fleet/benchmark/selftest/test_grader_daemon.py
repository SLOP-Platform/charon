#!/usr/bin/env python3
"""FAIL-ON-REVERT test for grader-daemon.py (#26 Wave 1).

Verifies the invariants that make the out-of-band grading trust boundary
real. Removing ANY of them MUST cause this test to go RED:

  A. ISOLATION — the graded agent's unix user (``stack``) cannot read
     ``/home/bench-grader/keys/``.  This proves the answer key is outside
     the model's reach (§1.2 of ADR-BENCH-OOB-GRADING.md).

  B. VERSIONED ARTIFACT — ``grader-daemon.py`` writes an append-only
     ``scorecard.v{n}.json`` per grader version, and the artifact is NEVER
     imported by product code.  If versioning is removed (e.g. a single
     mutable ``scorecard.json``) or the artifact is wired into a product
     import path, this test FAILS.

  C. NO-PRODUCT-IMPORT — no file under the product tree references the
     versioned scorecard artifact (the trust seam).

  D. DAEMON STRUCTURE — the daemon + reds_replay grader sources still carry
     the versioning/isolation machinery AND the security guards (F1/F2/F5).

Security fixes reconciled from feat/bench-oob-grading @ e879957 (verified
2026-07-10) — GRADER-SECFIX-RECONCILE. These are pytest-collectable and go
RED on revert of their guard:

  F1  path traversal  -> grader-daemon._confine / SandboxError sandbox
      confinement of the untrusted ``run_id`` in _snapshot_worktree /
      _write_result (``../`` traversal and absolute paths are rejected, and
      nothing outside the sandbox is deleted).
  F2  shell injection -> graders/reds_replay._run_check runs the check as an
      argv list with ``shell=False`` (no metacharacter injection).
  F5  false-green     -> graders/reds_replay pre-fix guard: a curated red that
      is already GREEN at the pre-fix baseline scores 0, never 100.

Usage:
  python3 fleet/benchmark/selftest/test_grader_daemon.py   # script mode (A-E)
  pytest  fleet/benchmark/selftest/test_grader_daemon.py    # collects F1/F2/F5

Exits 0 on PASS, non-zero on FAIL.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent
DAEMON_PATH = BENCH_DIR / "grader-daemon.py"
REDS_REPLAY_PATH = BENCH_DIR / "graders" / "reds_replay.py"
KEYS_DIR = Path("/home/bench-grader/keys")
SPOOL_REQ = Path("/var/lib/bench-grader/spool/req")
SPOOL_RES = Path("/var/lib/bench-grader/spool/res")

FLEET_DIR = BENCH_DIR.parent
SCORECARD_TSV = FLEET_DIR / "model-scorecard.tsv"
SCORECARD_VERSION_FILE = BENCH_DIR / "scorecard.version"
SCORECARD_V1 = FLEET_DIR / "scorecard.v1.json"
PRODUCT_ROOT = Path(os.environ.get("CHARON_PRODUCT_ROOT") or (Path.home() / "code" / "charon"))


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


def _load_module(name: str, path: Path):
    """Load a module by file path (handles hyphenated filenames).

    The module is registered in ``sys.modules`` BEFORE execution so that
    string-annotation resolution and dataclass machinery work correctly.
    """
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _try_stat(path: Path) -> os.stat_result | None:
    """Return stat if accessible, None if PermissionError, raise on other errors."""
    try:
        return path.stat()
    except PermissionError:
        return None
    except FileNotFoundError:
        return None


def check_A_isolation() -> None:
    """Invariant A: stack cannot read bench-grader-owned key material.

    A PermissionError when stack tries to stat the keys directory IS the
    proof of isolation — the directory exists and is 0700 bench-grader.
    """
    print("\n--- Check A: isolation (KEY-READABILITY) ---")

    keys_stat = _try_stat(KEYS_DIR)
    home_stat = _try_stat(KEYS_DIR.parent)  # /home/bench-grader

    # If the home dir is PermissionError, the whole bench-grader home is
    # isolated (even stronger proof — stack can't even list the home dir).
    if home_stat is None and keys_stat is None:
        # Both are PermissionError — the bench-grader home is 0700.
        import pwd
        try:
            pwd.getpwnam("bench-grader")
        except KeyError:
            fail("bench-grader user does not exist — isolation has no subject")
        ok("/home/bench-grader/ is permission-denied to stack — full home isolation (strong)")
        return

    # If the home is accessible but keys is not, keys dir exists and is 0700.
    if home_stat is not None and keys_stat is None:
        ok("/home/bench-grader/keys/ is permission-denied to stack — key isolation holds")
        return

    # If neither exists (FileNotFoundError), the substrate is missing.
    if home_stat is not None and not KEYS_DIR.parent.exists():
        print("  SKIP: /home/bench-grader/ does not exist (substrate not set up)")
        return

    # If keys_stat is accessible, check ownership and mode.
    if keys_stat is not None:
        import pwd
        try:
            owner = pwd.getpwuid(keys_stat.st_uid).pw_name
        except KeyError:
            owner = str(keys_stat.st_uid)
        mode = keys_stat.st_mode & 0o777
        if owner != "bench-grader":
            fail(f"{KEYS_DIR} owned by {owner!r}, expected bench-grader")
        if mode & 0o007:
            fail(f"{KEYS_DIR} mode {mode:04o} is world-readable")
        if mode & 0o070:
            fail(f"{KEYS_DIR} mode {mode:04o} is group-readable")
        ok(f"{KEYS_DIR} owned by bench-grader, mode {mode:04o} — stack cannot read")


def check_B_versioned_artifact() -> None:
    """Invariant B: scorecard.v{n}.json artifact exists and is versioned."""
    print("\n--- Check B: versioned artifact (SCORECARD-SEAM) ---")

    if not SCORECARD_VERSION_FILE.exists():
        fail(f"{SCORECARD_VERSION_FILE} missing — versioning not wired")

    version = SCORECARD_VERSION_FILE.read_text().strip()
    if not version.isdigit():
        fail(f"{SCORECARD_VERSION_FILE} contains non-numeric version {version!r}")

    v = int(version)
    if v < 1:
        fail(f"scorecard version {v} < 1 — versioning broken")

    artifact = FLEET_DIR / f"scorecard.v{v}.json"
    if not artifact.exists():
        # The artifact is created lazily by the daemon on first write.
        ok(f"scorecard version=v{v} (artifact not yet created; daemon creates on first write)")
    else:
        data = json.loads(artifact.read_text())
        if not isinstance(data, dict):
            fail(f"{artifact.name} is not a JSON object")
        if data.get("version") != v:
            fail(f"{artifact.name} version {data.get('version')} != expected {v}")
        if "rows" not in data:
            fail(f"{artifact.name} missing 'rows' array")
        ok(f"{artifact.name}: version={data['version']}, rows={len(data['rows'])}")


def check_C_no_product_import() -> None:
    """Invariant C: no product code imports the versioned scorecard."""
    print("\n--- Check C: no-product-import (ARTIFACT-SEAM) ---")

    if not PRODUCT_ROOT.exists():
        ok("product dir missing (non-wsl env) — import scan skipped")
        return

    artifact_name = "scorecard.v"
    hits = []
    for py_file in PRODUCT_ROOT.rglob("*.py"):
        try:
            for line in py_file.read_text(errors="ignore").splitlines():
                if artifact_name in line:
                    hits.append(f"  {py_file}: {line.strip()[:120]}")
        except OSError:
            pass

    if hits:
        fail(f"PRODUCT IMPORT FOUND for {artifact_name!r}:\n" + "\n".join(hits[:10]))
    ok(f"no product import of {artifact_name!r} in {PRODUCT_ROOT}")


def check_D_daemon_syntax_and_structure() -> None:
    """Structural checks: the daemon + reds grader carry all required machinery."""
    print("\n--- Check D: daemon structure ---")

    text = DAEMON_PATH.read_text()

    # Versioning + isolation references (master lineage).
    for required in ["/var/lib/bench-grader/spool", "/home/bench-grader/keys",
                     "scorecard.v", "scorecard.version"]:
        if required not in text:
            fail(f"daemon source missing reference to {required!r}")
    if "_append_to_scorecard" not in text:
        fail("daemon missing _append_to_scorecard function")
    if "Existing rows are NEVER modified" not in text:
        fail("daemon missing 'Existing rows are NEVER modified' contract comment")

    # Security-fix presence (F1) — removing the guard makes this RED.
    for ref, label in [
        ("_confine", "F1 sandbox path confinement"),
        ("SandboxError", "F1 sandbox violation exception"),
        ("escapes sandbox", "F1 rejection message"),
    ]:
        if ref not in text:
            fail(f"daemon source missing {ref!r} ({label})")

    # Security-fix presence (F2/F5) in the reds_replay grader.
    reds_text = REDS_REPLAY_PATH.read_text()
    for ref, label in [
        ("shell=False", "F2 no-shell execution"),
        ("shlex.split", "F2 argv tokenization"),
        ("--prefix-snapshot", "F5 pre-fix baseline arg"),
        ("already green pre-fix", "F5 false-green rejection message"),
    ]:
        if ref not in reds_text:
            fail(f"reds_replay source missing {ref!r} ({label})")

    ok("daemon + reds_replay structure verified (versioning + isolation + F1/F2/F5)")


# --------------------------------------------------------------------------- #
# Security tests (F1/F2/F5) — pytest-collectable; FAIL on revert of the fix
# --------------------------------------------------------------------------- #
def test_F1_path_traversal_rejected() -> None:
    """F1: an untrusted ``run_id`` containing ``../`` traversal is REJECTED and
    touches nothing outside the sandbox root.

    Reverting the ``_confine`` guard in grader-daemon.py (so ``run_id`` is
    joined naively under WORK_DIR again) makes this test RED two ways:
    (1) ``_confine`` no longer raises ``SandboxError`` for a traversal, and
    (2) ``_snapshot_worktree`` reaches OUTSIDE the sandbox and its
    ``rmtree(dst)`` deletes a canary that should have survived.
    """
    daemon_mod = _load_module("grader_daemon", DAEMON_PATH)

    assert hasattr(daemon_mod, "_confine"), \
        "F1 REGRESSION: _confine guard missing!"
    assert hasattr(daemon_mod, "SandboxError"), \
        "F1 REGRESSION: SandboxError missing — _confine guard removed!"

    # (1) The confinement guard must reject ``../`` traversal and absolute
    # paths and accept a benign relative name.
    sandbox = Path(tempfile.mkdtemp(prefix="grader-confine-"))
    try:
        (sandbox / "legit.txt").write_text("ok")
        ok_path = daemon_mod._confine("r1", sandbox)
        assert os.path.realpath(ok_path) == os.path.realpath(sandbox / "r1")
        for evil in ("../escape", "../../escape", "sub/../../escape", "/etc/passwd"):
            try:
                daemon_mod._confine(evil, sandbox)
            except daemon_mod.SandboxError:
                pass
            else:
                raise AssertionError(
                    f"F1 REGRESSION: _confine accepted hostile path {evil!r}!")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    # (2) End-to-end via the REAL snapshot path: point WORK_DIR at a temp
    # sandbox, place a canary OUTSIDE it, and drive _snapshot_worktree with a
    # traversing run_id. Confinement must raise BEFORE the rmtree, so the
    # canary survives. Reverting the guard deletes the canary (RED) or grades
    # the hostile run (no SandboxError raised — also RED).
    tmp = Path(tempfile.mkdtemp(prefix="grader-f1-e2e-"))
    old_work = daemon_mod.WORK_DIR
    try:
        work = tmp / "spool" / "work"
        work.mkdir(parents=True)
        daemon_mod.WORK_DIR = work
        canary_dir = tmp / "OUTSIDE-CANARY"
        canary_dir.mkdir()
        canary = canary_dir / "CANARY.txt"
        canary.write_text("survive")
        src = tmp / "agent-worktree"
        src.mkdir()
        (src / "flag.txt").write_text("x")
        # WORK_DIR/../../OUTSIDE-CANARY escapes the sandbox root.
        try:
            daemon_mod._snapshot_worktree(str(src), "../../OUTSIDE-CANARY")
        except daemon_mod.SandboxError:
            pass
        else:
            raise AssertionError(
                "F1 REGRESSION: _snapshot_worktree accepted a traversing run_id!")
        assert canary.exists(), (
            "F1 REGRESSION: traversal deleted a file OUTSIDE the sandbox root!")
        # A benign run_id still snapshots normally under the sandbox.
        snap = daemon_mod._snapshot_worktree(str(src), "r1")
        rp = os.path.realpath(snap)
        root = os.path.realpath(str(work))
        assert rp == root or rp.startswith(root + os.sep), \
            f"F1 REGRESSION: benign snapshot escaped sandbox: {snap} -> {rp}"
    finally:
        daemon_mod.WORK_DIR = old_work
        shutil.rmtree(tmp, ignore_errors=True)


def test_F2_shell_injection_neutralized() -> None:
    """F2: shell metacharacters in the snapshot path do NOT execute a shell.

    The snapshot path derives from the untrusted ``run`` field. With
    ``shell=True`` (reverted), a run like ``; touch PWNED`` would execute
    an injected command. With the fix (``shell=False``, argv list) the
    metacharacters are inert tokens and no side effect occurs.

    Directly exercises reds_replay._run_check with a hostile worktree path
    embedded via the {worktree} substitution.
    """
    reds_mod = _load_module("reds_replay", REDS_REPLAY_PATH)
    # Source must never use shell=True on the check path.
    src = REDS_REPLAY_PATH.read_text()
    assert "shell=True" not in src.replace("shell=False", ""), \
        "F2 REGRESSION: reds_replay uses shell=True (shell injection restored)!"

    tmp = Path(tempfile.mkdtemp(prefix="grader-shell-"))
    try:
        # The hostile "worktree": a real directory whose NAME contains shell
        # metacharacters. Under shell=True the substitution would execute them;
        # under shell=False they are an innocent path component.
        hostile_name = "wt; touch " + str(tmp / "PWNED") + ""
        hostile_wt = tmp / hostile_name
        hostile_wt.mkdir(parents=True)
        (hostile_wt / "flag.txt").write_text("ok")

        passed, rc, out = reds_mod._run_check(
            "test -f {worktree}/flag.txt", hostile_wt.resolve(), "0")
        assert passed, f"check should pass on benign flag; got rc={rc} out={out}"
        # The injected side-effect file MUST NOT exist (no shell ran).
        assert not (tmp / "PWNED").exists(), (
            "F2 REGRESSION: shell injection executed! PWNED file created by `;`.")

        # Also cover $(...) and backtick forms — none should create a file.
        for evil in ("wt$(touch " + str(tmp / "PWNED2") + ")",
                     "wt`touch " + str(tmp / "PWNED3") + "`"):
            assert not (tmp / "PWNED2").exists()
            assert not (tmp / "PWNED3").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_F5_false_green_already_green_scores_zero() -> None:
    """F5: a curated red that is ALREADY green at the pre-fix baseline must
    score 0 / be flagged invalid, NOT 100.

    Reverting the pre-fix false-green guard makes this RED: the already-green
    case would score 100 (a false positive / false green).
    """
    reds_mod = _load_module("reds_replay", REDS_REPLAY_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="grader-falsegreen-"))
    try:
        keys = tmp / "keys"
        keys.mkdir()
        (keys / "reds-replay.tsv").write_text(
            "unit_id\tcheck_cmd\texpect_green_exit\twork_class\tnote\n"
            "u\ttest -f {worktree}/flag.txt\t0\tred\tfalse-green-test\n"
        )
        # A pre-fix baseline that is ALREADY green (flag present pre-fix).
        prefix = tmp / "prefix-already-green"
        prefix.mkdir()
        (prefix / "flag.txt").write_text("pre-fix-green")
        # Post-fix worktree also green — but the pre-fix being green is the bug.
        post = tmp / "post-green"
        post.mkdir()
        (post / "flag.txt").write_text("post-green")

        argv = ["--worktree", str(post), "--keys", str(keys),
                "--unit-id", "u", "--prefix-snapshot", str(prefix)]
        buf = io.StringIO()
        old = reds_mod.sys.stdout
        old_argv = reds_mod.sys.argv
        reds_mod.sys.stdout = buf
        reds_mod.sys.argv = ["reds_replay.py"] + argv
        try:
            reds_mod.main()
        finally:
            reds_mod.sys.stdout = old
            reds_mod.sys.argv = old_argv
        out = buf.getvalue().strip().splitlines()
        assert out, "reds_replay produced no output"
        payload = json.loads(out[-1])
        # Already-green pre-fix MUST score 0 and fail — never 100.
        assert payload["score"] == 0, (
            f"F5 REGRESSION: already-green pre-fix scored {payload['score']} "
            f"(expected 0) — false-green guard missing! payload={payload}")
        assert payload["gate"] == "fail", (
            f"F5 REGRESSION: already-green pre-fix gate={payload['gate']} "
            f"(expected fail). payload={payload}")
        assert "pre-fix" in payload["reason"], (
            f"F5 REGRESSION: reason does not flag pre-fix false green: "
            f"{payload['reason']!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_E_security_regression() -> None:
    """Run the F1/F2/F5 security tests; reverting any fix reddens this check."""
    print("\n--- Check E: security regression (F1 path / F2 shell / F5 false-green) ---")
    for fn, label in (
        (test_F1_path_traversal_rejected, "F1 path-traversal rejected"),
        (test_F2_shell_injection_neutralized, "F2 shell injection neutralized"),
        (test_F5_false_green_already_green_scores_zero, "F5 already-green pre-fix scores 0"),
    ):
        try:
            fn()
        except AssertionError as exc:
            fail(f"{label}: {exc}")
        ok(label)


def main() -> int:
    print("=== FAIL-ON-REVERT: grader-daemon isolation + versioning + security ===")

    check_A_isolation()
    check_B_versioned_artifact()
    check_C_no_product_import()
    check_D_daemon_syntax_and_structure()
    check_E_security_regression()

    print("\n=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
