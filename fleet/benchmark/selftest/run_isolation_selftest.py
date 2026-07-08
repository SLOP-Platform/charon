#!/usr/bin/env python3
"""bench-run-collision / bench-premature-grade self-test (fleet/reds.tsv, P1
+ P2).

Proves, entirely against SCRATCH copies (a temp dir standing in for
benchmark/lib + benchmark/runs) - NEVER the real benchmark/runs/ tree or a
live opencode session:

  1. `grade_state.py init` always stamps a FRESH `start_ts`/`round_start_ts`
     - never inherited from any other run's state.
  2. `is_active` correctly distinguishes a genuinely in-flight section
     (within its current round's timebox) from a STALE/abandoned one (past
     it) - this is the actual fix for the incident (a ~25h-old start_ts
     silently poisoning a new run via naive "does meta.json exist" resume
     logic).
  3. `record`'s TIMEOUT decision resets per correction round
     (`round_start_ts`) rather than accumulating against the section's
     original `start_ts` - a model spread across 2 legitimate correction
     rounds, each individually within timebox, is NOT false-zeroed just
     because their sum exceeds one round's budget.
  4. `BENCH_GUARD_ACTIVE_RUN=1` makes `init` refuse to clobber a genuinely
     ACTIVE section, but still allows re-init over a STALE one - the exact
     behavior bench.sh relies on.
  5. The per-(model,section) `flock` makes a concurrent `init` fail fast
     with a clear message while another process holds it.
  6. `lib/sections.sh`'s `wait_for_worktree_stable` (the bench-premature-
     grade mtime-stability gate) returns promptly once a worktree's mtime
     is old enough, and respects its BENCH_MTIME_MAX_WAIT_SEC cap instead of
     hanging forever against a continuously-touched directory.

Usage: python3 selftest/run_isolation_selftest.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH_DIR = HERE.parent
LIB_DIR = BENCH_DIR / "lib"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def _make_scratch_lib(tmp: Path) -> Path:
    """Copy grade_state.py + charon_cost.py into <tmp>/lib/ so
    Path(__file__).resolve().parent.parent / "runs" (grade_state.RUNS)
    resolves to <tmp>/runs - never the real benchmark/runs/ tree."""
    lib = tmp / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    shutil.copy(LIB_DIR / "grade_state.py", lib / "grade_state.py")
    shutil.copy(LIB_DIR / "charon_cost.py", lib / "charon_cost.py")
    return lib


def _run(lib: Path, *args, env_extra=None, check_rc=None):
    env = os.environ.copy()
    # no gateway configured - charon_cost.snapshot_usage() returns None
    # gracefully (never raises), exactly like a real run with no Charon
    # gateway reachable.
    for var in ("CHARON_BENCH_STATUS_URL", "CHARON_BENCH_STATUS_TOKEN", "CHARON_BENCH_SESSION_ID"):
        env.pop(var, None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(lib / "grade_state.py"), *args],
        capture_output=True, text=True, env=env, timeout=30)
    if check_rc is not None:
        check(proc.returncode == check_rc,
              f"grade_state.py {' '.join(args)}: expected rc={check_rc}, got {proc.returncode} "
              f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    return proc


def _meta_path(tmp: Path, model: str, section: str) -> Path:
    return tmp / "runs" / model / section / "meta.json"


def part1_fresh_timestamps_and_staleness() -> None:
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-") as td:
        tmp = Path(td)
        lib = _make_scratch_lib(tmp)
        model, section = "fresh-model", "S1"

        proc = _run(lib, "init", model, section, "5", check_rc=0)
        worktree = proc.stdout.strip()
        check(bool(worktree), "init printed no worktree path")

        meta = json.loads(_meta_path(tmp, model, section).read_text())
        now = time.time()
        check("start_ts" in meta and "round_start_ts" in meta,
              f"init meta missing start_ts/round_start_ts: {meta}")
        check(abs(now - meta["start_ts"]) < 5, f"start_ts not fresh: {meta.get('start_ts')} vs now {now}")
        check(meta["start_ts"] == meta["round_start_ts"],
              f"a brand-new init should have start_ts == round_start_ts: {meta}")

        # freshly init'd, within its 5s timebox -> ACTIVE.
        active = _run(lib, "is_active", model, section, check_rc=0).stdout.strip()
        check(active == "true", f"freshly-init'd section should be is_active=true, got {active!r}")

        # hand-age the meta.json to simulate an ABANDONED run (25h-old
        # start_ts/round_start_ts, exactly the incident this fixes) -
        # never touching the real runs/ tree, this is the SCRATCH copy.
        meta["start_ts"] = now - 90000
        meta["round_start_ts"] = now - 90000
        _meta_path(tmp, model, section).write_text(json.dumps(meta))
        stale_active = _run(lib, "is_active", model, section, check_rc=0).stdout.strip()
        check(stale_active == "false",
              f"a section past its own timebox with no active extension should be is_active=false (stale), got {stale_active!r}")

        # re-`init` (as bench.sh's prepare_section does on the non-resume
        # path) must stamp a BRAND NEW fresh start_ts, not preserve the
        # 25h-old one.
        _run(lib, "init", model, section, "5", check_rc=0)
        meta2 = json.loads(_meta_path(tmp, model, section).read_text())
        check(abs(time.time() - meta2["start_ts"]) < 5,
              f"re-init over stale state did not stamp a fresh start_ts: {meta2.get('start_ts')}")
        check(meta2["attempts"] == 0, "re-init over stale state should reset attempts to 0")


def part2_guard_active_run() -> None:
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-guard-") as td:
        tmp = Path(td)
        lib = _make_scratch_lib(tmp)
        model, section = "guard-model", "S2"

        _run(lib, "init", model, section, "300", check_rc=0)  # long timebox -> stays ACTIVE

        # BENCH_GUARD_ACTIVE_RUN=1 (what bench.sh sets) must REFUSE to
        # clobber this genuinely active section.
        blocked = _run(lib, "init", model, section, "300",
                        env_extra={"BENCH_GUARD_ACTIVE_RUN": "1"}, check_rc=1)
        check("ACTIVE" in blocked.stderr or "active" in blocked.stderr.lower(),
              f"guarded re-init of an ACTIVE section should print a clear refusal to stderr, got: {blocked.stderr!r}")

        # without the guard env var (run.sh/run-many.sh's default), init
        # still unconditionally resets - existing legacy contract preserved.
        _run(lib, "init", model, section, "300", check_rc=0)

        # now age it past its timebox (stale) and confirm the SAME guarded
        # call is now ALLOWED (staleness overrides the active-guard).
        meta = json.loads(_meta_path(tmp, model, section).read_text())
        meta["start_ts"] = time.time() - 400
        meta["round_start_ts"] = time.time() - 400
        _meta_path(tmp, model, section).write_text(json.dumps(meta))
        allowed = _run(lib, "init", model, section, "300",
                        env_extra={"BENCH_GUARD_ACTIVE_RUN": "1"}, check_rc=0)
        check(bool(allowed.stdout.strip()), "guarded re-init of a STALE section should be allowed and print a worktree path")


def part3_round_based_timeout() -> None:
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-round-") as td:
        tmp = Path(td)
        lib = _make_scratch_lib(tmp)
        model, section = "round-model", "S3"

        _run(lib, "init", model, section, "3", check_rc=0)  # 3s timebox per round

        # first attempt: fail the gate (not pass, not timeout yet) - this
        # should NOT finalize, and should reset round_start_ts to "now".
        rec1 = json.loads(_run(lib, "record", model, section, "40", "fail", check_rc=0).stdout)
        check(rec1["finalize"] is False, f"first failing round should not finalize: {rec1}")
        check(rec1["timed_out"] is False, f"first round (well within its 3s timebox) should not be timed_out: {rec1}")

        meta_after_r1 = json.loads(_meta_path(tmp, model, section).read_text())
        round_start_after_r1 = meta_after_r1["round_start_ts"]
        check(round_start_after_r1 > meta_after_r1["start_ts"] - 0.001,
              f"round_start_ts should have advanced (>= start_ts) after round 1: {meta_after_r1}")

        # sleep past the ORIGINAL section start's cumulative window (but
        # well within a FRESH round's 3s budget) to prove the timeout is
        # judged against the reset round_start_ts, not the original start_ts.
        time.sleep(2)
        rec2 = json.loads(_run(lib, "record", model, section, "95", "pass", check_rc=0).stdout)
        check(rec2["finalize"] is True, f"a passing gate should always finalize: {rec2}")
        check(rec2["timed_out"] is False,
              f"round 2 (2s into a fresh 3s round budget) should NOT be timed_out even though "
              f"cumulative section time exceeds one round's timebox: {rec2}")
        check(rec2["final_score"] == 95, f"a passing, non-timed-out round should keep the real score: {rec2}")


def part4_lock_contention() -> None:
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-lock-") as td:
        tmp = Path(td)
        lib = _make_scratch_lib(tmp)
        model, section = "lock-model", "S4"

        _run(lib, "init", model, section, "300", check_rc=0)

        lock_file = tmp / "runs" / model / section / ".lock"
        check(lock_file.exists(), f"init should create a .lock file at {lock_file}")

        try:
            import fcntl
        except ImportError:
            return  # non-POSIX - lock test not applicable

        fh = open(lock_file, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            blocked = _run(lib, "record", model, section, "80", "pass", check_rc=1)
            check("lock" in blocked.stderr.lower(),
                  f"record while the lock is externally held should refuse with a lock-related message, got: {blocked.stderr!r}")
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()

        # lock released - record should now succeed normally.
        _run(lib, "record", model, section, "80", "pass", check_rc=0)


def part6_record_refuses_stale() -> None:
    """bench-run-collision RESIDUAL (harness-hardening adversarial review
    must-fix #1): `cmd_record` must refuse (not silently score 0) when this
    (model, section)'s state is already STALE - the gap that let a
    misattributed/omitted --model fallback still reproduce the incident's
    poisoned score=0/huge-time_s row even after `start`'s own is_active gate
    was fixed. Also proves a genuinely-active section's `record` call is
    completely unaffected (compliant path untouched)."""
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-stale-record-") as td:
        tmp = Path(td)
        lib = _make_scratch_lib(tmp)
        model, section = "stale-record-model", "S5"

        _run(lib, "init", model, section, "5", check_rc=0)  # 5s timebox

        # age it well past its own timebox with nobody having extended it
        # via `record` - exactly the abandoned-state shape of the incident.
        meta = json.loads(_meta_path(tmp, model, section).read_text())
        meta["start_ts"] = time.time() - 90000
        meta["round_start_ts"] = time.time() - 90000
        _meta_path(tmp, model, section).write_text(json.dumps(meta))

        refused = _run(lib, "record", model, section, "77", "pass", check_rc=1)
        check("stale" in refused.stdout.lower() or "stale" in refused.stderr.lower(),
              f"record on STALE state should refuse with a message mentioning STALE, got "
              f"stdout={refused.stdout!r} stderr={refused.stderr!r}")
        meta_after = json.loads(_meta_path(tmp, model, section).read_text())
        check(meta_after.get("finalized") is not True,
              "a refused (stale) record call must NOT finalize/poison the section's state")
        check("final_score" not in meta_after,
              "a refused (stale) record call must NOT write a final_score - no poisoned row")

        # compliant path, completely separate section: a genuinely-active
        # record call (well within its timebox) must be totally unaffected
        # by this new gate - same behavior as before this fix.
        model2, section2 = "compliant-record-model", "S5"
        _run(lib, "init", model2, section2, "300", check_rc=0)
        ok = json.loads(_run(lib, "record", model2, section2, "88", "pass", check_rc=0).stdout)
        check(ok["finalize"] is True and ok["final_score"] == 88,
              f"a genuinely-active section's record call must finalize normally, unaffected "
              f"by the stale-record gate, got: {ok}")


def part7_bench_sh_fallback_fail_closed() -> None:
    """bench-run-collision RESIDUAL, shell-level half (harness-hardening
    adversarial review must-fix #2): when --model is omitted, `bench.sh`
    must FAIL-CLOSED (refuse, clear error) rather than silently proceeding
    whenever the shared runs/.current_model pointer resolves to a STALE
    section - this is the exact "forgot --model AND a concurrent tab
    clobbered the pointer" mistake that misattributed a kimi-k2.6 grade to
    deepseek-v4-pro. `do_status` and `do_grade` share the identical
    `refuse_if_stale_fallback` function (only the subcmd label differs), so
    exercising it via `bench.sh status` - side-effect-free, needs no
    fixtures/graders/scorecard - is a full proof of the same gate `do_grade`
    also runs before ever touching a worktree or grader. Also proves an
    explicit `--model` override is COMPLETELY unaffected even against the
    exact same stale state (never reaches this gate at all - override
    branch skips it structurally)."""
    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-benchsh-") as td:
        tmp = Path(td)
        bench_dir = tmp / "benchmark"
        lib_dir = bench_dir / "lib"
        lib_dir.mkdir(parents=True)
        (bench_dir / "runs").mkdir()
        for name in ("bench.sh", "run.sh"):
            shutil.copy(BENCH_DIR / name, bench_dir / name)
        # detect_model.py: MODEL-ID-NORMALIZE (fleet ticket) - bench.sh's
        # own `normalize_model_id` shell helper shells out to this module's
        # `normalize_model_id()` for every `--model` override (not just
        # auto-detect), so it is now a genuine runtime dependency of
        # `bench.sh status --model <id>` below, not just of the no-override
        # auto-detect path - the scratch lib/ must mirror that or the
        # override call fails with ModuleNotFoundError before ever reaching
        # the STALE-fallback logic this test actually exercises.
        for name in ("sections.sh", "grade_state.py", "charon_cost.py", "detect_model.py"):
            shutil.copy(LIB_DIR / name, lib_dir / name)
        os.chmod(bench_dir / "bench.sh", 0o755)

        # S0 (not some later section) - current_section() walks ALL_SECTIONS
        # in order and returns the first non-finalized one, so with only
        # this one section's state on disk it must be the FIRST in the
        # queue, else current_section would report S0 (no meta.json at all
        # = not finalized) instead of the section we actually staged.
        model, section = "clobbered-model", "S0"
        state_py = lib_dir / "grade_state.py"
        env = os.environ.copy()
        for var in ("CHARON_BENCH_STATUS_URL", "CHARON_BENCH_STATUS_TOKEN", "CHARON_BENCH_SESSION_ID"):
            env.pop(var, None)

        subprocess.run([sys.executable, str(state_py), "init", model, section, "5"],
                        capture_output=True, text=True, env=env, timeout=30, check=True)
        meta_path = bench_dir / "runs" / model / section / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["start_ts"] = time.time() - 90000
        meta["round_start_ts"] = time.time() - 90000
        meta_path.write_text(json.dumps(meta))
        (bench_dir / "runs" / ".current_model").write_text(model)

        def _bench(*args):
            return subprocess.run(["bash", str(bench_dir / "bench.sh"), *args],
                                   capture_output=True, text=True, env=env, timeout=30)

        no_override = _bench("status")
        check(no_override.returncode != 0,
              f"bench.sh status with no --model, against a STALE fallback pointer, must refuse "
              f"(nonzero exit), got rc={no_override.returncode} stdout={no_override.stdout!r} "
              f"stderr={no_override.stderr!r}")
        check("stale" in no_override.stderr.lower() and "--model" in no_override.stderr,
              f"the refusal must mention STALE and instruct passing --model, got: {no_override.stderr!r}")

        with_override = _bench("status", "--model", model)
        check(with_override.returncode == 0,
              f"bench.sh status --model <id>, against the SAME STALE state, must be UNAFFECTED "
              f"(the fallback gate only runs when --model is omitted), got rc="
              f"{with_override.returncode} stdout={with_override.stdout!r} stderr={with_override.stderr!r}")
        check(f"model={model}" in with_override.stdout and f"current_section={section}" in with_override.stdout,
              f"bench.sh status --model <id> should report the real model/section normally, "
              f"got: {with_override.stdout!r}")


def part5_mtime_stability_gate() -> None:
    sections_sh = BENCH_DIR / "lib" / "sections.sh"
    check(sections_sh.exists(), f"lib/sections.sh not found at {sections_sh}")
    if not sections_sh.exists():
        return

    with tempfile.TemporaryDirectory(prefix="run-isolation-selftest-mtime-") as td:
        worktree = Path(td) / "worktree"
        worktree.mkdir()
        (worktree / "a.txt").write_text("hello")

        # (a) a file already >= stable_for seconds old -> returns immediately
        # (no sleeping needed).
        old_mtime = time.time() - 5
        os.utime(worktree / "a.txt", (old_mtime, old_mtime))
        t0 = time.monotonic()
        proc = subprocess.run(
            ["bash", "-c",
             f'source "{sections_sh}"; BENCH_MTIME_STABLE_SEC=2 BENCH_MTIME_MAX_WAIT_SEC=10 wait_for_worktree_stable "{worktree}"'],
            capture_output=True, text=True, timeout=30)
        elapsed = time.monotonic() - t0
        check(proc.returncode == 0, f"wait_for_worktree_stable should exit 0 on an already-stable worktree: {proc.stderr!r}")
        check(elapsed < 3, f"an already-stable (5s-old mtime, 2s stable_for) worktree should return almost immediately, took {elapsed:.1f}s")

        # (b) a file freshly touched -> must wait roughly stable_for seconds
        # before returning (proves it actually gates, not a no-op).
        (worktree / "a.txt").write_text("fresh write")
        t0 = time.monotonic()
        proc2 = subprocess.run(
            ["bash", "-c",
             f'source "{sections_sh}"; BENCH_MTIME_STABLE_SEC=2 BENCH_MTIME_MAX_WAIT_SEC=10 wait_for_worktree_stable "{worktree}"'],
            capture_output=True, text=True, timeout=30)
        elapsed2 = time.monotonic() - t0
        check(proc2.returncode == 0, f"wait_for_worktree_stable should still exit 0 after waiting out a fresh write: {proc2.stderr!r}")
        check(1.5 <= elapsed2 <= 8, f"a just-written worktree with stable_for=2s should wait ~2s before returning, took {elapsed2:.1f}s")

        # (c) max-wait cap: a file continuously touched every 0.5s must not
        # hang forever - the max_wait cap forces a return with a warning.
        stopper = worktree / ".stop"
        toucher = subprocess.Popen(
            ["bash", "-c",
             f'while [ ! -e "{stopper}" ]; do touch "{worktree}/a.txt"; sleep 0.5; done'])
        try:
            t0 = time.monotonic()
            proc3 = subprocess.run(
                ["bash", "-c",
                 f'source "{sections_sh}"; BENCH_MTIME_STABLE_SEC=5 BENCH_MTIME_MAX_WAIT_SEC=3 wait_for_worktree_stable "{worktree}"'],
                capture_output=True, text=True, timeout=30)
            elapsed3 = time.monotonic() - t0
            check(proc3.returncode == 0, f"wait_for_worktree_stable must still return 0 past its max_wait cap (never hang): {proc3.stderr!r}")
            check(elapsed3 < 8, f"a continuously-touched worktree must be capped by max_wait (3s), took {elapsed3:.1f}s")
            check("still" in proc3.stderr.lower() or "grading anyway" in proc3.stderr.lower(),
                  f"hitting the max_wait cap should print a clear warning to stderr, got: {proc3.stderr!r}")
        finally:
            stopper.touch()
            toucher.wait(timeout=5)


def main() -> None:
    part1_fresh_timestamps_and_staleness()
    part2_guard_active_run()
    part3_round_based_timeout()
    part4_lock_contention()
    part5_mtime_stability_gate()
    part6_record_refuses_stale()
    part7_bench_sh_fallback_fail_closed()

    if failures:
        print(f"RUN-ISOLATION SELF-TEST FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("RUN-ISOLATION SELF-TEST PASS: init always stamps a fresh start_ts/"
          "round_start_ts; is_active correctly tells a genuinely-active section "
          "from a stale/abandoned one and bench.sh's re-init path resets a "
          "stale one's clock; BENCH_GUARD_ACTIVE_RUN=1 refuses to clobber an "
          "active section but allows reclaiming a stale one; record's timeout "
          "is judged per-correction-round (round_start_ts), not cumulatively; "
          "a per-(model,section) flock makes concurrent init/record fail fast "
          "with a clear message; wait_for_worktree_stable gates grading on "
          "mtime-stability and respects its max-wait cap; cmd_record itself now "
          "refuses (never silently scores 0) against STALE state while leaving a "
          "genuinely-active section's record call untouched; bench.sh's "
          "--model-omitted fallback fails closed against a stale shared pointer "
          "while an explicit --model override is completely unaffected. All "
          "against scratch copies - the real benchmark/runs/ tree was never touched.")


if __name__ == "__main__":
    main()
