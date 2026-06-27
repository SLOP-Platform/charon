"""ADR-0012 — opt-in, batch-atomic auto-land on top of the propose-default gate.

These are proven-RED properties (each asserts a HOLD/no-mutation, not a happy path
only), because auto-land is the highest-blast-radius path in Charon:
  - the default is propose: a disabled config lands nothing and never touches git;
  - an out-of-allowlist write HOLDS (even if in the unit's owned_paths);
  - a sensitive path HOLDS even when everything else is green;
  - a failing acceptance / test HOLDS;
  - a required-scanner finding HOLDS (D007 is flipped when auto-land is on);
  - a gitleaks leak HOLDS;
  - a fully-clean in-allowlist batch auto-lands atomically (base branch advances);
  - a partial-batch failure lands NOTHING (the base branch is unchanged).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from charon import config, gitutil, land
from charon.acceptance import AcceptanceCheck
from charon.config import AutoLandConfig
from charon.land import GitleaksResult
from charon.ledger import Ledger


# --------------------------------------------------------------- helpers
def _clean_gitleaks(_repo: str) -> GitleaksResult:
    return GitleaksResult("clean")


def _no_scanners(_repo: str, _files: list[str]) -> list[dict]:
    """All scanners skipped (file-domain not in diff) — the green baseline."""
    return []


def _ledger(state_dir: Path, repo: Path, task: str, accept: list[str], *,
            base: str, tip: str, goal: str = "do it") -> Ledger:
    checks = [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(accept)]
    led = Ledger.create(state_dir, task, goal, checks, str(repo), base)
    led.lkg_ref = tip
    led._write_meta()
    return led


def _unit_branch(repo: Path, base: str, branch: str, rel: str, body: str = "ok\n") -> str:
    """Create a commit off ``base`` on its own branch touching ``rel`` (in a
    throwaway worktree, so units are genuinely parallel/file-disjoint). Returns the
    commit sha; a real branch ref keeps it alive after the worktree is torn down."""
    wt = repo.parent / f"wt-{branch}"
    gitutil.add_worktree(repo, wt, base)
    p = wt / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    sha = gitutil.commit_all(wt, f"{branch}: add {rel}") or gitutil.head(wt)
    subprocess.run(["git", "-C", str(repo), "branch", branch, sha], check=True)
    gitutil.remove_worktree(repo, wt)
    return sha


def _branch_sha(repo: Path, branch: str = "master") -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", branch],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


ALLOW = ("src/",)


# =============================================================== config surface
def test_autoland_default_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A fresh install has NO auto-land config → the default is OFF (propose)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_AUTOLAND", raising=False)
    cfg = config.load_autoland_config()
    assert cfg.enabled is False
    assert cfg.allowlist == ()


def test_autoland_env_can_enable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("CHARON_AUTOLAND", "1")
    assert config.load_autoland_config().enabled is True


def test_autoland_garbage_env_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("CHARON_AUTOLAND", "maybe")
    assert config.load_autoland_config().enabled is False


def test_autoland_persisted_config_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_AUTOLAND", raising=False)
    config.save_autoland_config(enabled=True, allowlist=["src/", "lib/"],
                                extra_sensitive=["secrets/"], base_branch="main")
    cfg = config.load_autoland_config()
    assert cfg.enabled and cfg.allowlist == ("src/", "lib/")
    assert cfg.extra_sensitive == ("secrets/",) and cfg.base_branch == "main"


# =============================================================== the batch gate
def test_disabled_config_lands_nothing(state_dir: Path, git_repo: Path) -> None:
    """The master switch: with auto-land OFF the batch HOLDS and git is untouched."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)
    before = _branch_sha(git_repo)
    res = land.auto_land_batch([(led, ALLOW)], AutoLandConfig(enabled=False))
    assert res.landed is False and res.decision == "hold"
    assert _branch_sha(git_repo) == before  # no mutation


def test_out_of_allowlist_holds(state_dir: Path, git_repo: Path) -> None:
    """A write outside the allowlist HOLDS even though it is in the unit's owned
    paths and acceptance is green."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "other/x.py")
    led = _ledger(state_dir, git_repo, "u1", ["true"], base=base, tip=tip)
    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ["other/"])], cfg,
                               gitleaks_runner=_clean_gitleaks,
                               scanner_runner=_no_scanners)
    assert res.landed is False
    assert any("allowlist" in h for h in res.holds + res.outcomes[0].holds)
    assert _branch_sha(git_repo) == before


def test_sensitive_path_holds_even_on_green(state_dir: Path, git_repo: Path) -> None:
    """An in-allowlist, acceptance-passing edit to a sensitive path STILL holds."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/tests/test_x.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/tests/test_x.py"],
                  base=base, tip=tip)
    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks,
                               scanner_runner=_no_scanners)
    assert res.landed is False
    assert any("sensitive" in h for h in res.outcomes[0].holds)
    assert _branch_sha(git_repo) == before


def test_failing_acceptance_holds(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/MISSING.py"],
                  base=base, tip=tip)
    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks,
                               scanner_runner=_no_scanners)
    assert res.landed is False
    assert res.outcomes[0].acceptance_failed == ["a0"]
    assert _branch_sha(git_repo) == before


def test_required_scanner_finding_holds(state_dir: Path, git_repo: Path) -> None:
    """D007 is flipped under auto-land: a scanner FINDING blocks (it is advisory
    only in propose-mode)."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)

    def _finding(_repo: str, _files: list[str]) -> list[dict]:
        return [{"name": "ruff", "tier": "B", "status": "finding",
                 "findings": ["S105 hardcoded password"], "note": ""}]

    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks,
                               scanner_runner=_finding)
    assert res.landed is False
    assert any("ruff" in h for h in res.outcomes[0].holds)
    assert _branch_sha(git_repo) == before


def test_required_scanner_unavailable_fails_closed(state_dir: Path, git_repo: Path) -> None:
    """A required scanner that cannot run must HOLD (never read as green)."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)

    def _unavail(_repo: str, _files: list[str]) -> list[dict]:
        return [{"name": "ruff", "tier": "B", "status": "unavailable",
                 "findings": [], "note": "ruff not installed"}]

    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks,
                               scanner_runner=_unavail)
    assert res.landed is False
    assert any("fail-closed" in h for h in res.outcomes[0].holds)


def test_gitleaks_leak_holds(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)
    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=lambda _r: GitleaksResult("leaks"),
                               scanner_runner=_no_scanners)
    assert res.landed is False
    assert any("gitleaks" in h for h in res.outcomes[0].holds)
    assert _branch_sha(git_repo) == before


def test_gitleaks_missing_fails_closed(state_dir: Path, git_repo: Path) -> None:
    """gitleaks is `expected` under auto-land: missing → HOLD (unlike propose-mode,
    where a missing scanner is merely advisory)."""
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(led, ALLOW)], cfg,
                               gitleaks_runner=lambda _r: GitleaksResult("unavailable"),
                               scanner_runner=_no_scanners)
    assert res.landed is False


def test_empty_allowlist_lands_nothing(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _unit_branch(git_repo, base, "u1", "src/a.py")
    led = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=tip)
    res = land.auto_land_batch([(led, ALLOW)], AutoLandConfig(enabled=True, allowlist=()),
                               gitleaks_runner=_clean_gitleaks, scanner_runner=_no_scanners)
    assert res.landed is False
    assert any("allowlist is empty" in h for h in res.holds)


# =============================================================== the atomic land
def test_clean_batch_auto_lands_atomically(state_dir: Path, git_repo: Path) -> None:
    """Two clean, in-allowlist, file-disjoint units → the base branch advances to an
    integrated tip that contains BOTH files (one atomic land)."""
    base = gitutil.head(git_repo)
    t1 = _unit_branch(git_repo, base, "u1", "src/a.py")
    t2 = _unit_branch(git_repo, base, "u2", "src/b.py")
    l1 = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=t1)
    l2 = _ledger(state_dir, git_repo, "u2", ["test -f src/b.py"], base=base, tip=t2)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW, base_branch="master")
    res = land.auto_land_batch([(l1, ALLOW), (l2, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks, scanner_runner=_no_scanners)
    assert res.landed is True and res.decision == "auto-landed", res.holds
    # master moved off base to the integrated tip…
    assert _branch_sha(git_repo) != base
    assert _branch_sha(git_repo) == res.landed_ref
    # …and the integrated tip contains BOTH units' files.
    integ_files = land.changed_files(str(git_repo), base, res.landed_ref)
    assert set(integ_files) == {"src/a.py", "src/b.py"}


def test_partial_batch_failure_lands_nothing(state_dir: Path, git_repo: Path) -> None:
    """One clean unit + one held unit (out-of-allowlist) → the WHOLE batch holds and
    the base branch never moves (batch-atomic: all-or-nothing)."""
    base = gitutil.head(git_repo)
    t1 = _unit_branch(git_repo, base, "u1", "src/a.py")
    t2 = _unit_branch(git_repo, base, "u2", "evil/x.py")
    l1 = _ledger(state_dir, git_repo, "u1", ["test -f src/a.py"], base=base, tip=t1)
    l2 = _ledger(state_dir, git_repo, "u2", ["true"], base=base, tip=t2)
    before = _branch_sha(git_repo)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(l1, ALLOW), (l2, ["evil/"])], cfg,
                               gitleaks_runner=_clean_gitleaks, scanner_runner=_no_scanners)
    assert res.landed is False
    assert _branch_sha(git_repo) == before  # the clean unit did NOT land either
    # nothing leaked onto master: src/a.py is absent from the live branch tip
    assert "src/a.py" not in land.changed_files(str(git_repo), base, before or base)


def test_batch_spanning_bases_holds(state_dir: Path, git_repo: Path) -> None:
    """Units cut from different floors are not one decomposition → fail closed."""
    base = gitutil.head(git_repo)
    t1 = _unit_branch(git_repo, base, "u1", "src/a.py")
    other = _unit_branch(git_repo, base, "floor2", "src/floor.py")
    t2 = _unit_branch(git_repo, other, "u2", "src/b.py")
    l1 = _ledger(state_dir, git_repo, "u1", ["true"], base=base, tip=t1)
    l2 = _ledger(state_dir, git_repo, "u2", ["true"], base=other, tip=t2)
    cfg = AutoLandConfig(enabled=True, allowlist=ALLOW)
    res = land.auto_land_batch([(l1, ALLOW), (l2, ALLOW)], cfg,
                               gitleaks_runner=_clean_gitleaks, scanner_runner=_no_scanners)
    assert res.landed is False
    assert any("spans bases" in h for h in res.holds)
