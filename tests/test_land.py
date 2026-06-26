"""ADR-0007 D3/D4/D6 — the propose-default land gate + consumer-supplied units
loader.

Binding properties (proven, not asserted against a happy path only):
  - a green, in-scope unit PROPOSES (never auto-merges);
  - any out-of-scope write HOLDS (diff-scope guard);
  - a sensitive-path touch HOLDS even when everything else is green;
  - failing acceptance HOLDS;
  - a detected secret HOLDS; a missing-but-expected scanner fails closed;
  - the units loader parses TOML+JSON, validates loudly, and maps onto the
    existing run path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon import gitutil, land
from charon.acceptance import AcceptanceCheck
from charon.land import GitleaksResult
from charon.ledger import Ledger


# --------------------------------------------------------------- helpers
def _clean_gitleaks(_repo: str) -> GitleaksResult:
    return GitleaksResult("clean")


def _missing_gitleaks(_repo: str) -> GitleaksResult:
    return GitleaksResult("unavailable")


def _commit_file(repo: Path, rel: str, body: str = "x\n") -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return gitutil.commit_all(repo, f"add {rel}") or gitutil.head(repo)


def _ledger_for(state_dir: Path, repo: Path, accept: list[str], *, base: str,
                tip: str, goal: str = "do the thing") -> Ledger:
    checks = [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(accept)]
    led = Ledger.create(state_dir, "unit-1", goal, checks, str(repo), base)
    led.lkg_ref = tip  # the blessed completion commit (what we land)
    led._write_meta()
    return led


# --------------------------------------------------------------- is_sensitive
@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
    "Dockerfile",
    "install.sh",
    "scripts/setup.sh",
    "bootstrap.py",
    ".pre-commit-config.yaml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "package.json",
    "go.mod",
    ".git/hooks/pre-commit",
    "conftest.py",
    "tests/test_x.py",
    "pkg/tests/test_y.py",
    "pyproject.toml",
    "setup.py",
    "Makefile",
    ".claude/settings.json",
    "CODEOWNERS",
    ".github/CODEOWNERS",
    ".envrc",
])
def test_sensitive_paths_flagged(path: str) -> None:
    assert land.is_sensitive(path) is not None, path


@pytest.mark.parametrize("path", [
    "src/charon/land.py",
    "src/charon/cli.py",
    "docs/adr/0007.md",
    "README.md",
    "mytestfile.py",      # 'test' substring, but not a tests/ dir or conftest
    "src/setupy.py",      # not an install/setup script
])
def test_non_sensitive_paths_pass(path: str) -> None:
    assert land.is_sensitive(path) is None, path


# --------------------------------------------------------------- in_scope
def test_in_scope_matches_file_and_dir() -> None:
    owned = ["src/charon/land.py", "src/charon/sub/"]
    assert land.in_scope("src/charon/land.py", owned)
    assert land.in_scope("src/charon/sub/x.py", owned)
    assert not land.in_scope("src/charon/cli.py", owned)


def test_empty_owned_is_never_in_scope() -> None:
    assert not land.in_scope("anything.py", [])


# --------------------------------------------------------------- the gate
def test_land_proposes_when_in_scope_and_green(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["test -f src/feature.py"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "propose", out.holds
    assert out.holds == []
    assert out.changed_files == ["src/feature.py"]


def test_land_holds_on_out_of_scope_write(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    _commit_file(git_repo, "src/owned.py", "ok\n")
    tip = _commit_file(git_repo, "other/sneaky.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    assert "other/sneaky.py" in out.out_of_scope
    assert any("out-of-scope" in h for h in out.holds)


def test_land_holds_on_sensitive_path_even_when_green(
    state_dir: Path, git_repo: Path
) -> None:
    """Sensitive-path HOLD fires ALWAYS — the file is in scope and acceptance
    passes, yet a workflow edit still forces human review."""
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, ".github/workflows/ci.yml", "on: push\n")
    led = _ledger_for(state_dir, git_repo, ["test -f .github/workflows/ci.yml"],
                      base=base, tip=tip)
    out = land.land_unit(led, [".github/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    assert ".github/workflows/ci.yml" in out.sensitive
    assert out.acceptance_failed == []  # green, but still held


def test_land_holds_on_failing_acceptance(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["test -f src/MISSING.py"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    assert out.acceptance_failed == ["a0"]


def test_land_holds_when_nothing_to_land(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=base)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    assert any("nothing to land" in h for h in out.holds)


def test_land_holds_when_no_owned_paths_declared(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    out = land.land_unit(led, [], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    assert any("no declared owned_paths" in h for h in out.holds)


def test_land_holds_on_detected_secret(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"],
                         gitleaks_runner=lambda _r: GitleaksResult("leaks"))
    assert out.decision == "hold"
    assert out.gitleaks == "leaks"
    assert any("gitleaks" in h for h in out.holds)


def test_land_fail_closed_when_gitleaks_expected_but_missing(
    state_dir: Path, git_repo: Path
) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_expected=True,
                         gitleaks_runner=_missing_gitleaks)
    assert out.decision == "hold"
    assert any("fail-closed" in h for h in out.holds)


def test_land_missing_gitleaks_is_advisory_by_default(
    state_dir: Path, git_repo: Path
) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["test -f src/feature.py"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_missing_gitleaks)
    assert out.decision == "propose"  # missing scanner is advisory unless expected
    assert out.gitleaks == "unavailable"


def test_land_never_advances_lkg(state_dir: Path, git_repo: Path) -> None:
    """land is read-only: the gate must not advance lkg or mutate the ledger,
    even on a green propose. A human merge is the only thing that lands."""
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["test -f src/feature.py"], base=base, tip=tip)
    land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    reloaded = Ledger.load(state_dir, "unit-1")
    assert reloaded.lkg_ref == tip  # unchanged from what we set; gate did not move it


# --------------------------------------------------------------- propose (PR)
def test_open_pr_builds_gh_argv_and_never_merges(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "src/feature.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["test -f src/feature.py"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    captured: list[str] = []

    def fake_runner(argv: list[str]) -> str:
        captured[:] = argv
        return "https://example/pr/1"

    url = land.open_pr(led, out, "feat/unit-1", base="master",
                       repo_slug="SLOP-Platform/charon", runner=fake_runner)
    assert url == "https://example/pr/1"
    assert captured[:3] == ["gh", "pr", "create"]
    assert "--draft" in captured
    assert "--base" in captured and captured[captured.index("--base") + 1] == "master"
    assert "--head" in captured and captured[captured.index("--head") + 1] == "feat/unit-1"
    # never a merge verb
    assert "merge" not in captured


def test_open_pr_refuses_held_unit(state_dir: Path, git_repo: Path) -> None:
    base = gitutil.head(git_repo)
    tip = _commit_file(git_repo, "other/x.py", "ok\n")
    led = _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    out = land.land_unit(led, ["src/"], gitleaks_runner=_clean_gitleaks)
    assert out.decision == "hold"
    with pytest.raises(land.LandError):
        land.open_pr(led, out, "feat/unit-1", runner=lambda _a: "")


# --------------------------------------------------------------- units loader
_TOML_UNITS = """
[[units]]
goal = "build land gate"
accept = ["pytest -q tests/test_land.py"]
tier = "high"
owned_paths = ["src/charon/land.py", "src/charon/cli.py"]

[[units]]
goal = "tweak docs"
accept = ["test -f README.md"]
tier = "low"
owned_paths = ["README.md"]
"""

_JSON_UNITS = json.dumps([
    {"goal": "g1", "accept": ["true"], "tier": "low", "owned_paths": ["a/"]},
    {"goal": "g2", "accept": ["true"], "owned_paths": [], "autonomy": "L1",
     "decompose": True},
])


def test_load_units_toml(tmp_path: Path) -> None:
    f = tmp_path / "units.toml"
    f.write_text(_TOML_UNITS)
    units = land.load_units(str(f))
    assert [u["goal"] for u in units] == ["build land gate", "tweak docs"]
    assert units[0]["owned_paths"] == ["src/charon/land.py", "src/charon/cli.py"]
    assert units[0]["tier"] == "high"


def test_load_units_json(tmp_path: Path) -> None:
    f = tmp_path / "units.json"
    f.write_text(_JSON_UNITS)
    units = land.load_units(str(f))
    assert units[1]["goal"] == "g2"
    assert units[1]["decompose"] is True
    assert units[1]["autonomy"] == "L1"


def test_load_units_rejects_missing_goal(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text(json.dumps([{"accept": ["true"]}]))
    with pytest.raises(ValueError, match="goal"):
        land.load_units(str(f))


def test_load_units_rejects_empty_accept(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text(json.dumps([{"goal": "g", "accept": []}]))
    with pytest.raises(ValueError, match="accept"):
        land.load_units(str(f))


def test_load_units_rejects_empty_list(tmp_path: Path) -> None:
    f = tmp_path / "empty.json"
    f.write_text("[]")
    with pytest.raises(ValueError, match="non-empty list"):
        land.load_units(str(f))


def test_units_to_run_maps_onto_run_path(tmp_path: Path) -> None:
    f = tmp_path / "units.json"
    f.write_text(_JSON_UNITS)
    units = land.units_to_run(land.load_units(str(f)))
    assert [u.goal for u in units] == ["g1", "g2"]
    assert units[1].autonomy == "L1"
    assert units[1].decompose is True


def test_owned_from_units_matches_by_goal(tmp_path: Path) -> None:
    f = tmp_path / "units.toml"
    f.write_text(_TOML_UNITS)
    owned = land.owned_from_units(str(f), "build land gate")
    assert owned == ["src/charon/land.py", "src/charon/cli.py"]
    assert land.owned_from_units(str(f), "no such goal") == []


# --------------------------------------------------------------- CLI surface
def test_cli_run_units_fans_out(tmp_path: Path, capsys) -> None:
    from charon.cli import main
    units = tmp_path / "units.json"
    units.write_text(json.dumps([
        {"goal": "u0", "accept": ["test -f f0.txt"], "owned_paths": ["f0.txt"],
         "autonomy": "L1"},
        {"goal": "u1", "accept": ["test -f f1.txt"], "owned_paths": ["f1.txt"],
         "autonomy": "L1"},
    ]))
    rc = main(["run", "--units", str(units), "--state-dir", str(tmp_path / "state")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(out["units"]) == 2
    assert all(u["status"] == "complete" for u in out["units"])


def test_cli_run_units_bad_file_errors(tmp_path: Path, capsys) -> None:
    from charon.cli import main
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"accept": ["true"]}]))
    rc = main(["run", "--units", str(bad), "--state-dir", str(tmp_path / "state")])
    assert rc == 2
    assert "goal" in capsys.readouterr().err


def test_cli_land_holds_out_of_scope(state_dir: Path, git_repo: Path, capsys) -> None:
    from charon.cli import main
    base = gitutil.head(git_repo)
    _commit_file(git_repo, "src/owned.py", "ok\n")
    tip = _commit_file(git_repo, "other/sneaky.py", "ok\n")
    _ledger_for(state_dir, git_repo, ["true"], base=base, tip=tip)
    rc = main(["land", "unit-1", "--state-dir", str(state_dir), "--owned", "src/"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1  # held → nonzero so a wrapper can gate on it
    assert out["decision"] == "hold"
    assert "other/sneaky.py" in out["out_of_scope"]


def test_cli_land_missing_ledger_errors(state_dir: Path, capsys) -> None:
    from charon.cli import main
    rc = main(["land", "nope", "--state-dir", str(state_dir)])
    assert rc == 2
    assert "error" in capsys.readouterr().err
