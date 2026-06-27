"""Scanner matrix (ADR-0010 D4) — change-scoped, parallel, cached advisory scanners.

Tier A: gitleaks — already in the land gate; reuse, never re-run here.
Tier B: ruff (*.py; bandit S-rules, already in the gate — zero new cost),
        shellcheck (*.sh/*.bash/*.bats), actionlint (.github/workflows/*).
Tier C: semgrep (opt-in via ``deep_scan=True`` only; pinned local ruleset,
        NEVER ``--config auto``). osv-scanner + license = off by default
        (stdlib-only core has no deps); ``dep_scan=True`` feature-flag reserved
        for dep-bearing consumer repos.

Performance contract (D4):
  (1) change-scoped — a scanner runs only if its file-domain is in the diff;
  (2) parallel — ThreadPoolExecutor, hard per-tool subprocess timeout;
  (3) content-hash cache — domain-relevant files hashed; unchanged files not
      re-scanned across retries / sibling units;
  (4) advisory in propose-mode — a missing tool or timeout is noted, never a
      hard fail; required/fail-closed status is reserved for auto-land (deferred).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


@dataclass
class ScanResult:
    """Result from one scanner in the advisory matrix."""

    name: str
    tier: str  # "A" | "B" | "C"
    status: str  # "clean" | "skipped" | "finding" | "unavailable" | "timeout"
    findings: list[str] = field(default_factory=list)
    wall_time: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tier": self.tier,
            "status": self.status,
            "findings": self.findings,
            "wall_time": round(self.wall_time, 3),
            "note": self.note,
        }


# ---------------------------------------------------------------- domain checks

def _is_python(files: list[str]) -> bool:
    return any(f.endswith(".py") for f in files)


def _is_shell(files: list[str]) -> bool:
    return any(f.endswith((".sh", ".bash", ".bats")) for f in files)


def _is_workflow(files: list[str]) -> bool:
    return any(
        f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))
        for f in files
    )


# ---------------------------------------------------------------- cache keying

def _domain_hash(repo: str, domain_files: list[str]) -> str:
    """SHA-256 of sorted (relative-path, content) pairs — per-scanner cache key."""
    h = hashlib.sha256()
    for rel in sorted(domain_files):
        h.update(rel.encode())
        try:
            h.update((Path(repo) / rel).read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()


# ---------------------------------------------------------------- runner functions

def _run_ruff(repo: str, files: list[str], timeout: int) -> ScanResult:
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return ScanResult("ruff", "B", "skipped", note="no .py files in diff")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["ruff", "check", "--select", "S", "--", *py_files],
            capture_output=True, text=True, timeout=timeout, cwd=repo,
        )
    except FileNotFoundError:
        return ScanResult("ruff", "B", "unavailable",
                          wall_time=time.monotonic() - t0, note="ruff not installed")
    except subprocess.TimeoutExpired:
        return ScanResult("ruff", "B", "timeout", wall_time=time.monotonic() - t0)
    elapsed = time.monotonic() - t0
    if proc.returncode == 0:
        return ScanResult("ruff", "B", "clean", wall_time=elapsed)
    if proc.returncode == 1:
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        return ScanResult("ruff", "B", "finding", findings=lines, wall_time=elapsed)
    # exit 2+ = usage error or internal ruff error
    return ScanResult("ruff", "B", "unavailable", wall_time=elapsed,
                      note=f"ruff exit {proc.returncode}: {proc.stderr.strip()[:120]}")


def _run_shellcheck(repo: str, files: list[str], timeout: int) -> ScanResult:
    sh_files = [f for f in files if f.endswith((".sh", ".bash", ".bats"))]
    if not sh_files:
        return ScanResult("shellcheck", "B", "skipped", note="no shell files in diff")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["shellcheck", "--format", "gcc", "--", *sh_files],
            capture_output=True, text=True, timeout=timeout, cwd=repo,
        )
    except FileNotFoundError:
        return ScanResult("shellcheck", "B", "unavailable",
                          wall_time=time.monotonic() - t0, note="shellcheck not installed")
    except subprocess.TimeoutExpired:
        return ScanResult("shellcheck", "B", "timeout", wall_time=time.monotonic() - t0)
    elapsed = time.monotonic() - t0
    if proc.returncode == 0:
        return ScanResult("shellcheck", "B", "clean", wall_time=elapsed)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return ScanResult("shellcheck", "B", "finding", findings=lines, wall_time=elapsed)


def _run_actionlint(repo: str, files: list[str], timeout: int) -> ScanResult:
    wf_files = [
        f for f in files
        if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))
    ]
    if not wf_files:
        return ScanResult("actionlint", "B", "skipped", note="no workflow files in diff")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["actionlint", "--", *wf_files],
            capture_output=True, text=True, timeout=timeout, cwd=repo,
        )
    except FileNotFoundError:
        return ScanResult("actionlint", "B", "unavailable",
                          wall_time=time.monotonic() - t0, note="actionlint not installed")
    except subprocess.TimeoutExpired:
        return ScanResult("actionlint", "B", "timeout", wall_time=time.monotonic() - t0)
    elapsed = time.monotonic() - t0
    if proc.returncode == 0:
        return ScanResult("actionlint", "B", "clean", wall_time=elapsed)
    output = (proc.stdout + proc.stderr).strip()
    lines = [ln for ln in output.splitlines() if ln.strip()]
    return ScanResult("actionlint", "B", "finding", findings=lines, wall_time=elapsed)


def _run_semgrep(
    repo: str, files: list[str], timeout: int, ruleset: str
) -> ScanResult:
    """Semgrep with a pinned local ruleset. NEVER ``--config auto``."""
    existing = [f for f in files if (Path(repo) / f).exists()]
    if not existing:
        return ScanResult("semgrep", "C", "skipped", note="no matching files exist")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["semgrep", "--config", ruleset, "--quiet", "--json", "--", *existing],
            capture_output=True, text=True, timeout=timeout, cwd=repo,
        )
    except FileNotFoundError:
        return ScanResult("semgrep", "C", "unavailable",
                          wall_time=time.monotonic() - t0, note="semgrep not installed")
    except subprocess.TimeoutExpired:
        return ScanResult("semgrep", "C", "timeout", wall_time=time.monotonic() - t0)
    elapsed = time.monotonic() - t0
    if proc.returncode not in (0, 1):
        return ScanResult("semgrep", "C", "unavailable", wall_time=elapsed,
                          note=f"semgrep exit {proc.returncode}")
    try:
        data = json.loads(proc.stdout)
        findings = [str(r.get("check_id", "?")) for r in data.get("results", [])]
    except (ValueError, AttributeError, KeyError):
        findings = []
    if findings:
        return ScanResult("semgrep", "C", "finding", findings=findings, wall_time=elapsed)
    return ScanResult("semgrep", "C", "clean", wall_time=elapsed)


# ---------------------------------------------------------------- internal types

class _ScannerDef(NamedTuple):
    name: str
    tier: str
    domain: Callable[[list[str]], bool]
    run: Callable[[str, list[str], int], ScanResult]


_TIER_B: list[_ScannerDef] = [
    _ScannerDef("ruff", "B", _is_python, _run_ruff),
    _ScannerDef("shellcheck", "B", _is_shell, _run_shellcheck),
    _ScannerDef("actionlint", "B", _is_workflow, _run_actionlint),
]

# Timeout guard: how much slack to add to the subprocess timeout before killing
# the future. Gives the subprocess timeout a chance to fire first.
_FUTURE_SLACK = 5


# ---------------------------------------------------------------- public API

def run_scanners(
    repo: str,
    changed_files: list[str],
    *,
    deep_scan: bool = False,
    dep_scan: bool = False,
    timeout_per_scanner: int = 60,
    cache: dict[str, ScanResult] | None = None,
    semgrep_ruleset: str = ".charon/semgrep-rules.yml",
    _overrides: dict[str, Callable[[], ScanResult]] | None = None,
    _future_slack: int = _FUTURE_SLACK,
) -> list[ScanResult]:
    """Run the advisory scanner matrix and return all ScanResult objects.

    Tier A (gitleaks) is already handled by the land gate — not re-run here.
    Non-eligible scanners return ``status="skipped"``.
    Missing tools return ``status="unavailable"`` — never a hard fail.
    ``_overrides`` is ``{scanner_name: zero-arg callable}`` injected by tests.
    ``dep_scan`` is a reserved feature-flag for dep-bearing repos (osv/license);
    no dep scanners are built in v1 (stdlib-only core has no deps to scan).
    """
    if cache is None:
        cache = {}

    overrides = _overrides or {}

    # Decide which Tier B scanners are domain-eligible for this diff
    active: list[_ScannerDef] = [s for s in _TIER_B if s.domain(changed_files)]
    skipped_names = {s.name for s in _TIER_B if not s.domain(changed_files)}

    # Tier C: semgrep opt-in only (pinned ruleset; NEVER --config auto)
    if deep_scan:
        _ruleset = semgrep_ruleset

        def _semgrep_runner(r: str, f: list[str], t: int) -> ScanResult:
            return _run_semgrep(r, f, t, _ruleset)

        active.append(_ScannerDef("semgrep", "C", lambda _: True, _semgrep_runner))

    # dep_scan (osv-scanner, license): feature-flagged; off in v1
    # Acknowledged: dep_scan reserved, no dep scanner built yet
    _ = dep_scan

    # Skipped results for non-eligible scanners (included so callers can see full matrix)
    results: list[ScanResult] = [
        ScanResult(name, "B", "skipped", note="file-domain not in diff")
        for name in sorted(skipped_names)
    ]

    if not active:
        return results

    # Cache check + parallel dispatch for eligible scanners
    to_run: list[tuple[_ScannerDef, str]] = []

    for scanner in active:
        domain_files = [f for f in changed_files if scanner.domain([f])]
        ck = f"{scanner.name}:{_domain_hash(repo, domain_files)}"
        if ck in cache:
            results.append(cache[ck])
        else:
            to_run.append((scanner, ck))

    if not to_run:
        return results

    with ThreadPoolExecutor(max_workers=len(to_run)) as pool:
        future_map: dict[Future[ScanResult], tuple[_ScannerDef, str]] = {}
        for scanner, ck in to_run:
            if scanner.name in overrides:
                fn: Callable[[], ScanResult] = overrides[scanner.name]
            else:
                def _make_fn(s: _ScannerDef) -> Callable[[], ScanResult]:
                    return lambda: s.run(repo, changed_files, timeout_per_scanner)

                fn = _make_fn(scanner)
            future_map[pool.submit(fn)] = (scanner, ck)

        for fut, (scanner, ck) in future_map.items():
            try:
                result = fut.result(timeout=timeout_per_scanner + _future_slack)
            except TimeoutError:
                result = ScanResult(scanner.name, scanner.tier, "timeout",
                                    note="future-level timeout")
            except Exception as exc:  # noqa: BLE001
                result = ScanResult(scanner.name, scanner.tier, "unavailable",
                                    note=f"runner error: {exc}")
            cache[ck] = result
            results.append(result)

    return results


def benchmark_scanners(
    repo: str,
    changed_files: list[str],
    *,
    timeout_per_scanner: int = 30,
) -> list[dict]:
    """Measure wall-time for each eligible scanner on a representative diff.

    This is the ADR-0010 D4 'measured-before-required' harness: a scanner earns
    required status only when catch-rate × signal beats its measured wall-time on
    representative diffs. Returns timing dicts for non-skipped scanners.
    """
    results = run_scanners(repo, changed_files, timeout_per_scanner=timeout_per_scanner)
    return [
        {
            "name": r.name,
            "tier": r.tier,
            "status": r.status,
            "wall_time_s": round(r.wall_time, 3),
        }
        for r in results
        if r.status != "skipped"
    ]
