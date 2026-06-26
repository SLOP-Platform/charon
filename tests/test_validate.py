"""ADR-0007 D12 — end-product Validator quality gate.

Binding properties proven:
  - passes when all acceptance checks pass;
  - fails (with fix_proposal) when any check fails;
  - fails (held for human review) when no checks are defined;
  - never silently passes a failed result;
  - wired into run_decomposed: Validate stage holds + proposes fix on failure,
    continues to close on pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from charon import decompose, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend
from charon.fence import Fence
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, WorkUnit
from charon.validate import ValidationResult, validate

# ---------------------------------------------------------------- unit tests


def test_validate_passes_when_all_checks_pass(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    p.write_text("x")
    checks = [AcceptanceCheck("a0", f"test -f {p}")]
    result = validate(checks, str(tmp_path))
    assert result.passed is True
    assert "a0" in result.verified
    assert result.remaining == []
    assert result.fix_proposal == ""


def test_validate_fails_when_check_fails(tmp_path: Path) -> None:
    checks = [AcceptanceCheck("a0", "test -f missing_file.txt")]
    result = validate(checks, str(tmp_path))
    assert result.passed is False
    assert "a0" in result.remaining
    assert result.fix_proposal != ""


def test_validate_fix_proposal_names_failing_checks(tmp_path: Path) -> None:
    checks = [AcceptanceCheck("fail-me", "false")]
    result = validate(checks, str(tmp_path))
    assert result.passed is False
    assert "fail-me" in result.fix_proposal


def test_validate_fails_when_no_checks_defined(tmp_path: Path) -> None:
    result = validate([], str(tmp_path))
    assert result.passed is False
    assert result.fix_proposal != ""
    assert "no acceptance checks" in result.note


def test_validate_partial_pass_still_fails(tmp_path: Path) -> None:
    p = tmp_path / "present.txt"
    p.write_text("x")
    checks = [
        AcceptanceCheck("a0", f"test -f {p}"),
        AcceptanceCheck("a1", "test -f absent.txt"),
    ]
    result = validate(checks, str(tmp_path))
    assert result.passed is False
    assert "a0" in result.verified
    assert "a1" in result.remaining


def test_validate_result_is_frozen() -> None:
    r = ValidationResult(passed=True, verified=["a0"], note="ok")
    with pytest.raises((AttributeError, TypeError)):
        r.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------- integration with decompose


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="build the thing")


def _led(state_dir: Path, repo: Path, checks: list[AcceptanceCheck]) -> Ledger:
    return Ledger.create(state_dir, "t1", "goal", checks, str(repo), gitutil.head(repo))


def test_validate_stage_passes_and_pipeline_reaches_close(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(creates=["out.txt"])
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    assert res.status == "complete"
    roles = [cp.role for cp in led.checkpoints()]
    assert "validate" in roles
    assert "close" in roles
    assert roles.index("validate") < roles.index("close")


def test_validate_stage_failure_halts_before_close(
    state_dir: Path, git_repo: Path
) -> None:
    """If the validate gate fails the pipeline stops with validate-failed, never
    reaching close, and the worktree is rolled back to lkg."""
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    # BLOCKED mode: backend does nothing, out.txt never appears → validate fails.
    from charon.adapters.mock import MockMode
    backend = MockBackend(mode=MockMode.BLOCKED)
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    assert res.status == "validate-failed"
    roles = [cp.role for cp in led.checkpoints()]
    assert "validate" in roles
    assert "close" not in roles


def test_validate_stage_failure_holds_lkg(
    state_dir: Path, git_repo: Path
) -> None:
    """On validate failure lkg must not advance — result is held."""
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    from charon.adapters.mock import MockMode
    backend = MockBackend(mode=MockMode.BLOCKED)
    led = _led(state_dir, git_repo, checks)
    base = led.base_ref
    decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    assert led.lkg_ref == base


def test_validate_stage_failure_note_contains_fix_proposal(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    from charon.adapters.mock import MockMode
    backend = MockBackend(mode=MockMode.BLOCKED)
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    assert res.status == "validate-failed"
    assert res.note.startswith("validate-failed:")
    assert len(res.note) > len("validate-failed:")


def test_validate_checkpoint_records_pass_result(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(creates=["out.txt"])
    led = _led(state_dir, git_repo, checks)
    decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    vcp = next(cp for cp in led.checkpoints() if cp.role == "validate")
    assert vcp.reviewer_passed is True


def test_validate_checkpoint_records_fail_result(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    from charon.adapters.mock import MockMode
    backend = MockBackend(mode=MockMode.BLOCKED)
    led = _led(state_dir, git_repo, checks)
    decompose.run_decomposed(
        _unit(), {backend.name: backend}, led,
        Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
    )
    vcp = next(cp for cp in led.checkpoints() if cp.role == "validate")
    assert vcp.reviewer_passed is False
    assert vcp.reviewer_note != ""
