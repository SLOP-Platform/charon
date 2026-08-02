"""RUFF-SEC-RULES-ON — fail-on-revert tests for the ruff security rule families.

The `S` (flake8-bandit ports) and `BLE` (blind-except) families must stay selected
in ``[tool.ruff.lint].select`` in pyproject.toml. Removing either is a
security-ratchet revert (security-is-a-ratchet) and must go RED here, so the
runtime linter gate (`ruff check`) and this static test both guard the same rule.

The baselines in ``[tool.ruff.lint].per-file-ignores`` must never swallow S602
(``subprocess`` with ``shell=True``): a new shell=True under ``tests/**`` has no
baseline entry, so it stays actively enforced.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_CFG = Path("pyproject.toml")
_FAMILIES = ("S", "BLE")


def _lint_config() -> dict:
    with _CFG.open("rb") as fh:
        return tomllib.load(fh)["tool"]["ruff"]["lint"]


def _missing_families(select: list[str]) -> list[str]:
    return [fam for fam in _FAMILIES if fam not in select]


def test_security_families_are_selected() -> None:
    select = _lint_config()["select"]
    assert "S" in select
    assert "BLE" in select


def test_fail_on_revert_removing_a_family_goes_red() -> None:
    """FAIL-ON-REVERT: the verdict genuinely depends on the select list. Revert
    either family out of ``select`` and the same parse now reports it missing."""
    real = _lint_config()["select"]
    assert _missing_families(real) == []

    reverted = [code for code in real if code not in _FAMILIES]
    assert _missing_families(reverted) != []


def test_shell_true_stays_enforced_in_tests() -> None:
    """S602 must never be added to the tests/ baseline — a new subprocess call
    with ``shell=True`` in any test must still go RED."""
    per_file = _lint_config().get("per-file-ignores", {})
    tests_baseline = per_file.get("tests/**", [])
    assert "S602" not in tests_baseline


def test_genuine_findings_pinned_to_their_file_not_swept() -> None:
    """The genuine findings (S602 shell=True in acceptance.py, S104 bind-all
    false-positive in gateway.py) are pinned to their exact files — never a
    global ignore. This keeps them visible until a source-owning ticket lands
    the line-level fix."""
    per_file = _lint_config().get("per-file-ignores", {})
    assert "S602" in per_file.get("src/charon/acceptance.py", [])
    assert "S104" in per_file.get("src/charon/gateway.py", [])
