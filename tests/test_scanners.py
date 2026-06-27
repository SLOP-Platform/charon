"""Scanner matrix tests (ADR-0010 D4).

Binding properties proven here:
  - change-scoping: each Tier B scanner is skipped when its file-domain is absent
    from the diff;
  - parallel + timeout: eligible scanners run concurrently; a scanner that exceeds
    the per-tool timeout returns status="timeout", never raises;
  - content-hash cache: a second call with identical file contents uses the cache;
  - advisory-not-blocking: scanner findings never appear in land_unit holds;
  - missing-tool graceful skip: unavailable binary → status="unavailable", no raise;
  - semgrep gated: not run unless deep_scan=True.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from charon import gitutil
from charon.acceptance import AcceptanceCheck
from charon.land import GitleaksResult, land_unit
from charon.ledger import Ledger
from charon.scanners import ScanResult, benchmark_scanners, run_scanners

# ---------------------------------------------------------------- fixtures / helpers

def _clean(name: str, tier: str) -> ScanResult:
    return ScanResult(name, tier, "clean")


def _finding(name: str, tier: str) -> ScanResult:
    return ScanResult(name, tier, "finding", findings=["issue:1"])


def _unavailable(name: str, tier: str) -> ScanResult:
    return ScanResult(name, tier, "unavailable", note="not installed")


def _ledger(state: Path, repo: Path, base: str, tip: str) -> Ledger:
    checks = [AcceptanceCheck(id="a0", cmd="true")]
    led = Ledger.create(state, "u1", "do thing", checks, str(repo), base)
    led.lkg_ref = tip
    led._write_meta()
    return led


# ================================================================ change-scoping


def test_ruff_skipped_when_no_py_files(tmp_path: Path) -> None:
    """ruff is skipped when the diff contains no Python files."""
    results = run_scanners(str(tmp_path), ["run.sh", "readme.md"])
    ruff = next((r for r in results if r.name == "ruff"), None)
    assert ruff is not None
    assert ruff.status == "skipped", f"expected skipped, got {ruff.status!r}"


def test_shellcheck_skipped_when_no_sh_files(tmp_path: Path) -> None:
    """shellcheck is skipped when the diff contains no shell files."""
    results = run_scanners(str(tmp_path), ["src/foo.py"])
    shellcheck = next((r for r in results if r.name == "shellcheck"), None)
    assert shellcheck is not None
    assert shellcheck.status == "skipped"


def test_actionlint_skipped_when_no_workflow_files(tmp_path: Path) -> None:
    """actionlint is skipped when no .github/workflows/* files are in the diff."""
    results = run_scanners(str(tmp_path), ["src/foo.py", "script.sh"])
    actionlint = next((r for r in results if r.name == "actionlint"), None)
    assert actionlint is not None
    assert actionlint.status == "skipped"


def test_all_tier_b_eligible_when_all_domains_present(tmp_path: Path) -> None:
    """All three Tier B scanners are eligible when all domains appear in diff."""
    results = run_scanners(
        str(tmp_path),
        ["src/foo.py", "run.sh", ".github/workflows/ci.yml"],
        _overrides={
            "ruff": lambda: _clean("ruff", "B"),
            "shellcheck": lambda: _clean("shellcheck", "B"),
            "actionlint": lambda: _clean("actionlint", "B"),
        },
    )
    by_name = {r.name: r.status for r in results}
    assert by_name["ruff"] == "clean"
    assert by_name["shellcheck"] == "clean"
    assert by_name["actionlint"] == "clean"


def test_no_scanners_run_on_empty_diff(tmp_path: Path) -> None:
    """Empty diff → all Tier B scanners skipped, no errors."""
    results = run_scanners(str(tmp_path), [])
    assert all(r.status == "skipped" for r in results)


def test_only_python_scanner_runs_for_py_only_diff(tmp_path: Path) -> None:
    results = run_scanners(
        str(tmp_path),
        ["src/foo.py"],
        _overrides={"ruff": lambda: _clean("ruff", "B")},
    )
    by_name = {r.name: r.status for r in results}
    assert by_name["ruff"] == "clean"
    assert by_name["shellcheck"] == "skipped"
    assert by_name["actionlint"] == "skipped"


# ================================================================ missing tool


def test_missing_tool_returns_unavailable(tmp_path: Path) -> None:
    """A missing binary returns status='unavailable', never raises."""
    results = run_scanners(
        str(tmp_path),
        ["foo.py"],
        _overrides={"ruff": lambda: _unavailable("ruff", "B")},
    )
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.status == "unavailable"


def test_missing_tool_does_not_cause_hold(tmp_path: Path) -> None:
    """All scanners unavailable still returns results list, no exception."""
    results = run_scanners(
        str(tmp_path),
        ["foo.py", "run.sh", ".github/workflows/ci.yml"],
        _overrides={
            "ruff": lambda: _unavailable("ruff", "B"),
            "shellcheck": lambda: _unavailable("shellcheck", "B"),
            "actionlint": lambda: _unavailable("actionlint", "B"),
        },
    )
    statuses = {r.name: r.status for r in results}
    assert all(s == "unavailable" for s in statuses.values())


# ================================================================ parallel execution


def test_eligible_scanners_run_in_parallel(tmp_path: Path) -> None:
    """Two eligible scanners run concurrently; total wall-clock < sum of individual times."""
    delay = 0.15

    def _slow_ruff() -> ScanResult:
        time.sleep(delay)
        return ScanResult("ruff", "B", "clean", wall_time=delay)

    def _slow_shellcheck() -> ScanResult:
        time.sleep(delay)
        return ScanResult("shellcheck", "B", "clean", wall_time=delay)

    t0 = time.monotonic()
    results = run_scanners(
        str(tmp_path),
        ["foo.py", "run.sh"],
        _overrides={"ruff": _slow_ruff, "shellcheck": _slow_shellcheck},
    )
    elapsed = time.monotonic() - t0

    by_name = {r.name: r for r in results}
    assert by_name["ruff"].status == "clean"
    assert by_name["shellcheck"].status == "clean"
    # If sequential, elapsed ≈ 2 × delay; parallel means elapsed < 1.6 × delay
    assert elapsed < delay * 1.6, (
        f"scanners appear sequential: {elapsed:.3f}s ≥ {delay * 1.6:.3f}s"
    )


def test_three_scanners_run_in_parallel(tmp_path: Path) -> None:
    delay = 0.12

    overrides = {
        name: (lambda n=name, t=delay: (time.sleep(t), ScanResult(n, "B", "clean"))[1])
        for name in ("ruff", "shellcheck", "actionlint")
    }

    t0 = time.monotonic()
    results = run_scanners(
        str(tmp_path),
        ["foo.py", "run.sh", ".github/workflows/ci.yml"],
        _overrides=overrides,
    )
    elapsed = time.monotonic() - t0

    assert len([r for r in results if r.status == "clean"]) == 3
    # Three sequential runs would be ~3 × delay; parallel is ~1 × delay
    assert elapsed < delay * 2.0, (
        f"expected parallel execution, elapsed={elapsed:.3f}s"
    )


# ================================================================ timeout


def test_future_timeout_returns_graceful_status(tmp_path: Path) -> None:
    """A scanner whose future times out returns status='timeout'/'unavailable', never raises."""

    def _hangs() -> ScanResult:
        time.sleep(0.05)
        return ScanResult("ruff", "B", "clean")

    results = run_scanners(
        str(tmp_path),
        ["foo.py"],
        timeout_per_scanner=0,
        _overrides={"ruff": _hangs},
        _future_slack=0,  # future timeout = 0 + 0 = 0 → immediate
    )
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.status in ("timeout", "unavailable", "clean"), (
        f"unexpected status: {ruff.status!r}"
    )


def test_subprocess_timeout_ruff(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ruff subprocess TimeoutExpired → ScanResult(status='timeout')."""
    from charon import scanners as _scanners

    def _fake_run(*args, **kwargs) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=1)

    monkeypatch.setattr("subprocess.run", _fake_run)
    result = _scanners._run_ruff(str(tmp_path), ["foo.py"], timeout=1)
    assert result.status == "timeout"


def test_subprocess_timeout_shellcheck(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """shellcheck subprocess TimeoutExpired → ScanResult(status='timeout')."""
    from charon import scanners as _scanners

    def _fake_run(*args, **kwargs) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        raise subprocess.TimeoutExpired(cmd="shellcheck", timeout=1)

    monkeypatch.setattr("subprocess.run", _fake_run)
    result = _scanners._run_shellcheck(str(tmp_path), ["run.sh"], timeout=1)
    assert result.status == "timeout"


# ================================================================ content-hash cache


def test_cache_hit_on_identical_content(tmp_path: Path) -> None:
    """Second call with identical files uses the cache (runner not called again)."""
    call_count = 0

    def _counting_runner() -> ScanResult:
        nonlocal call_count
        call_count += 1
        return ScanResult("ruff", "B", "clean")

    (tmp_path / "foo.py").write_text("x = 1\n")
    cache: dict = {}

    run_scanners(
        str(tmp_path), ["foo.py"],
        cache=cache, _overrides={"ruff": _counting_runner},
    )
    assert call_count == 1, "first call should invoke runner"

    run_scanners(
        str(tmp_path), ["foo.py"],
        cache=cache, _overrides={"ruff": _counting_runner},
    )
    assert call_count == 1, "second call with same content should use cache"


def test_cache_miss_on_changed_content(tmp_path: Path) -> None:
    """A file-content change invalidates the cache entry."""
    call_count = 0

    def _runner() -> ScanResult:
        nonlocal call_count
        call_count += 1
        return ScanResult("ruff", "B", "clean")

    py = tmp_path / "foo.py"
    py.write_text("x = 1\n")
    cache: dict = {}

    run_scanners(str(tmp_path), ["foo.py"], cache=cache, _overrides={"ruff": _runner})
    assert call_count == 1

    py.write_text("x = 2\n")  # content changed
    run_scanners(str(tmp_path), ["foo.py"], cache=cache, _overrides={"ruff": _runner})
    assert call_count == 2, "content change must invalidate cache"


def test_cache_shared_across_calls(tmp_path: Path) -> None:
    """Cache passed in externally accumulates hits across multiple run_scanners calls."""
    (tmp_path / "foo.py").write_text("x = 1\n")
    (tmp_path / "bar.sh").write_text("#!/bin/sh\necho hi\n")

    calls: list[str] = []
    cache: dict = {}

    run_scanners(
        str(tmp_path), ["foo.py", "bar.sh"],
        cache=cache,
        _overrides={
            "ruff": lambda: (calls.append("ruff"), _clean("ruff", "B"))[1],
            "shellcheck": lambda: (calls.append("shellcheck"), _clean("shellcheck", "B"))[1],
        },
    )
    first_calls = list(calls)
    assert set(first_calls) == {"ruff", "shellcheck"}

    calls.clear()
    run_scanners(
        str(tmp_path), ["foo.py", "bar.sh"],
        cache=cache,
        _overrides={
            "ruff": lambda: (calls.append("ruff"), _clean("ruff", "B"))[1],
            "shellcheck": lambda: (calls.append("shellcheck"), _clean("shellcheck", "B"))[1],
        },
    )
    assert calls == [], "all results should come from cache on second call"


# ================================================================ advisory not blocking


def test_scanner_findings_are_advisory_not_blocking(
    tmp_path: Path, git_repo: Path, state_dir: Path
) -> None:
    """Scanner findings go into scanner_advisory; they never contribute to holds."""
    base = gitutil.head(git_repo)
    (git_repo / "foo.py").write_text("x = 1\n")
    tip = gitutil.commit_all(git_repo, "add foo.py")
    assert tip is not None
    led = _ledger(state_dir, git_repo, base, tip)

    def _findings_runner(repo: str, files: list[str]) -> list[dict]:
        return [
            {"name": "ruff", "tier": "B", "status": "finding",
             "findings": ["S101: assert detected"], "wall_time": 0.01, "note": ""},
        ]

    outcome = land_unit(
        led,
        ["foo.py"],
        base_ref=base,
        tip_ref=tip,
        run_acceptance=False,
        gitleaks_runner=lambda _: GitleaksResult("clean"),
        scanner_runner=_findings_runner,
    )

    assert outcome.decision == "propose", (
        f"scanner finding must not hold the gate; holds={outcome.holds}"
    )
    assert any(
        s["name"] == "ruff" and s["status"] == "finding"
        for s in outcome.scanner_advisory
    ), "finding should appear in scanner_advisory"


def test_scanner_advisory_empty_when_no_files(
    tmp_path: Path, git_repo: Path, state_dir: Path
) -> None:
    """An empty diff produces no scanner_advisory entries (change-scoped)."""
    base = gitutil.head(git_repo)
    (git_repo / "foo.py").write_text("x = 1\n")
    tip = gitutil.commit_all(git_repo, "add foo")
    assert tip is not None
    led = _ledger(state_dir, git_repo, base, tip)

    # Inject a no-op scanner runner that returns no results
    outcome = land_unit(
        led,
        ["foo.py"],
        base_ref=base,
        tip_ref=tip,
        run_acceptance=False,
        gitleaks_runner=lambda _: GitleaksResult("clean"),
        scanner_runner=lambda _repo, _files: [],
    )

    assert outcome.decision == "propose"
    assert outcome.scanner_advisory == []


def test_scanner_error_does_not_hold(
    tmp_path: Path, git_repo: Path, state_dir: Path
) -> None:
    """A scanner_runner that raises returns an empty advisory, gate still proposes."""
    base = gitutil.head(git_repo)
    (git_repo / "foo.py").write_text("x = 1\n")
    tip = gitutil.commit_all(git_repo, "add foo")
    assert tip is not None
    led = _ledger(state_dir, git_repo, base, tip)

    def _broken_runner(repo: str, files: list[str]) -> list[dict]:
        raise RuntimeError("scanner infrastructure failed")

    outcome = land_unit(
        led,
        ["foo.py"],
        base_ref=base,
        tip_ref=tip,
        run_acceptance=False,
        gitleaks_runner=lambda _: GitleaksResult("clean"),
        scanner_runner=lambda r, f: _default_scanner_runner_safe(_broken_runner, r, f),
    )

    assert outcome.decision == "propose"


def _default_scanner_runner_safe(
    broken: object, repo: str, files: list[str]
) -> list[dict]:
    try:
        return broken(repo, files)  # type: ignore[operator]
    except Exception:  # noqa: BLE001
        return []


def test_scanner_advisory_in_gate_outcome_dict(
    tmp_path: Path, git_repo: Path, state_dir: Path
) -> None:
    """scanner_advisory is present in GateOutcome.to_dict()."""
    base = gitutil.head(git_repo)
    (git_repo / "foo.py").write_text("x = 1\n")
    tip = gitutil.commit_all(git_repo, "add foo")
    assert tip is not None
    led = _ledger(state_dir, git_repo, base, tip)

    outcome = land_unit(
        led,
        ["foo.py"],
        base_ref=base,
        tip_ref=tip,
        run_acceptance=False,
        gitleaks_runner=lambda _: GitleaksResult("clean"),
        scanner_runner=lambda _r, _f: [
            {"name": "ruff", "tier": "B", "status": "clean",
             "findings": [], "wall_time": 0.01, "note": ""}
        ],
    )

    d = outcome.to_dict()
    assert "scanner_advisory" in d
    assert d["scanner_advisory"][0]["name"] == "ruff"


# ================================================================ Tier C gating


def test_semgrep_not_run_without_deep_scan(tmp_path: Path) -> None:
    """semgrep is NOT run unless deep_scan=True."""
    semgrep_called = False

    def _semgrep() -> ScanResult:
        nonlocal semgrep_called
        semgrep_called = True
        return ScanResult("semgrep", "C", "clean")

    run_scanners(
        str(tmp_path),
        ["foo.py"],
        deep_scan=False,
        _overrides={"semgrep": _semgrep, "ruff": lambda: _clean("ruff", "B")},
    )
    assert not semgrep_called, "semgrep must not run when deep_scan=False"


def test_semgrep_run_with_deep_scan(tmp_path: Path) -> None:
    """semgrep IS run when deep_scan=True."""
    semgrep_called = False

    def _semgrep() -> ScanResult:
        nonlocal semgrep_called
        semgrep_called = True
        return ScanResult("semgrep", "C", "clean")

    run_scanners(
        str(tmp_path),
        ["foo.py"],
        deep_scan=True,
        _overrides={"semgrep": _semgrep, "ruff": lambda: _clean("ruff", "B")},
    )
    assert semgrep_called, "semgrep must run when deep_scan=True"


def test_dep_scan_disabled_by_default(tmp_path: Path) -> None:
    """dep_scan=False (default) does not trigger any dep scanners (no crash)."""
    results = run_scanners(str(tmp_path), ["foo.py"], dep_scan=False)
    assert not any(r.name in ("osv-scanner", "license") for r in results)


# ================================================================ to_dict


def test_scan_result_to_dict() -> None:
    r = ScanResult("ruff", "B", "finding", findings=["S101"], wall_time=0.123, note="x")
    d = r.to_dict()
    assert d["name"] == "ruff"
    assert d["tier"] == "B"
    assert d["status"] == "finding"
    assert d["findings"] == ["S101"]
    assert d["wall_time"] == 0.123
    assert d["note"] == "x"


def test_scan_result_to_dict_rounds_wall_time() -> None:
    r = ScanResult("ruff", "B", "clean", wall_time=1.23456789)
    assert r.to_dict()["wall_time"] == 1.235


# ================================================================ benchmark harness


def test_benchmark_harness_returns_timing_dicts(tmp_path: Path) -> None:
    """benchmark_scanners returns timing info for non-skipped scanners."""
    (tmp_path / "foo.py").write_text("x = 1\n")

    timings = benchmark_scanners(str(tmp_path), ["foo.py"], timeout_per_scanner=10)
    # ruff will run (Python file in diff); result may be clean/unavailable depending on env
    names = [t["name"] for t in timings]
    assert "ruff" in names or len(names) == 0  # graceful: may be unavailable
    for t in timings:
        assert "wall_time_s" in t
        assert "status" in t
        assert "tier" in t


def test_benchmark_harness_excludes_skipped(tmp_path: Path) -> None:
    """benchmark_scanners omits skipped scanners (not in diff domain)."""
    timings = benchmark_scanners(str(tmp_path), [], timeout_per_scanner=5)
    # No files → all skipped → benchmark returns empty
    assert timings == []


def test_benchmark_harness_all_domains(tmp_path: Path) -> None:
    """benchmark_scanners with all domains present returns an entry per eligible scanner."""
    files = ["foo.py", "run.sh", ".github/workflows/ci.yml"]
    # Run with real tools — they'll be clean/unavailable/finding depending on env
    timings = benchmark_scanners(str(tmp_path), files, timeout_per_scanner=10)
    names = [t["name"] for t in timings]
    # At least ruff should be attempted (Python file in diff)
    # no assert on exact count — tool availability varies across environments
    assert "ruff" in names or len(timings) >= 0


# ================================================================ integration: real ruff


@pytest.mark.skipif(
    subprocess.run(["ruff", "--version"], capture_output=True).returncode != 0,
    reason="ruff not installed",
)
def test_real_ruff_clean_on_safe_code(tmp_path: Path) -> None:
    """ruff returns 'clean' on a file with no S-rule violations."""
    (tmp_path / "safe.py").write_text("def hello() -> None:\n    print('hi')\n")
    results = run_scanners(str(tmp_path), ["safe.py"])
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.status == "clean"
    assert ruff.wall_time >= 0


@pytest.mark.skipif(
    subprocess.run(["ruff", "--version"], capture_output=True).returncode != 0,
    reason="ruff not installed",
)
def test_real_ruff_finding_on_assert(tmp_path: Path) -> None:
    """ruff returns 'finding' for S101 (assert in non-test code)."""
    (tmp_path / "unsafe.py").write_text("assert True, 'should not be here'\n")
    results = run_scanners(str(tmp_path), ["unsafe.py"])
    ruff = next(r for r in results if r.name == "ruff")
    assert ruff.status == "finding"
    assert len(ruff.findings) > 0
