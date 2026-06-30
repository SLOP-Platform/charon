from __future__ import annotations

import os
from pathlib import Path

import pytest

from charon.config import SandboxPolicy
from charon.fence import (
    ESCALATION_TOKENS,
    AutonomyPolicy,
    Fence,
    FenceDenied,
    detect_escape,
    snapshot_outside,
)
from charon.types import Autonomy, PrivilegedOp


def test_default_deny_l0_propose_only() -> None:
    f = Fence(autonomy=Autonomy.L0)
    assert f.authorize(PrivilegedOp.PROPOSE) is True
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is False
    assert f.authorize(PrivilegedOp.DELETE) is False
    assert f.authorize(PrivilegedOp.DEPLOY) is False


def test_l1_allows_apply_reversible_only() -> None:
    f = Fence(autonomy=Autonomy.L1)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is True
    assert f.authorize(PrivilegedOp.DELETE) is False  # always denied


def test_l2_requires_consensus() -> None:
    f = Fence(autonomy=Autonomy.L2)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=False) is False
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=True) is True


def test_l3_full_auto_within_fence_but_destructive_still_denied() -> None:
    f = Fence(autonomy=Autonomy.L3)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is True
    assert f.authorize(PrivilegedOp.DELETE) is False


def test_scrubbed_env_blocks_global_git_and_drops_secrets() -> None:
    os.environ["AWS_SECRET_ACCESS_KEY"] = "leak-me"
    try:
        env = Fence.scrubbed_env(Path("/tmp/wt"))
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert env["GIT_CONFIG_GLOBAL"] == os.devnull
        assert env["HOME"] == "/tmp/wt"
    finally:
        del os.environ["AWS_SECRET_ACCESS_KEY"]


# ----------------------------------------------- T7: autonomy escalation gate

_CONTAINED = {"CHARON_CONTAINER_VERIFIED": "1"}
_OVERRIDE = {"CHARON_ALLOW_UNCONTAINED_AUTONOMY": "1"}
_UNATTENDED = {"CHARON_ALLOW_UNATTENDED": "1"}


def test_policy_ceiling_is_l1_by_default_deny() -> None:
    # No tokens: the gate caps at L1 (apply-reversible) — L2+ is default-denied.
    pol = AutonomyPolicy.from_env({})
    assert pol.ceiling() is Autonomy.L1
    assert pol.resolve(Autonomy.L0).granted is Autonomy.L0
    assert pol.resolve(Autonomy.L1).granted is Autonomy.L1
    # L2/L3 requested with no env ⇒ clamped down to the ceiling.
    assert pol.resolve(Autonomy.L2).clamped is True
    assert pol.resolve(Autonomy.L3).granted is Autonomy.L1


def test_policy_container_grants_l3_blessed_bounded() -> None:
    # Inside the verified Mode-B container L3 is the blessed, bounded behaviour —
    # the container IS the boundary, so the highest rung is reachable (PLAN-tier4).
    pol = AutonomyPolicy.from_env(_CONTAINED)
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L2).clamped is False
    assert pol.resolve(Autonomy.L3).clamped is False


def test_policy_uncontained_override_alone_does_not_reach_l3() -> None:
    # The flag that unlocks L2 testing must NOT silently grant UNCONTAINED full-auto
    # (D-ESC-1): override alone caps at L2.
    pol = AutonomyPolicy.from_env(_OVERRIDE)
    assert pol.ceiling() is Autonomy.L2
    assert pol.resolve(Autonomy.L3).clamped is True
    assert pol.resolve(Autonomy.L3).granted is Autonomy.L2


def test_policy_uncontained_l3_needs_its_own_opt_in_on_top() -> None:
    # The unattended opt-in WITHOUT container/override is not enough either…
    assert AutonomyPolicy.from_env(_UNATTENDED).ceiling() is Autonomy.L1
    # …but the uncontained override PLUS the distinct opt-in reaches L3 uncontained.
    pol = AutonomyPolicy.from_env({**_OVERRIDE, **_UNATTENDED})
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L3).clamped is False


def test_policy_is_monotone_non_skipping() -> None:
    # opt-in set but the L2 precondition missing: cannot skip the L2 rung to reach
    # L3 — the climb stops at the first forbidden rung (D-ESC-2).
    pol = AutonomyPolicy.from_env(_UNATTENDED)
    assert pol.ceiling() is Autonomy.L1
    assert pol.resolve(Autonomy.L3).granted is Autonomy.L1


def test_assert_environment_l0_l1_always_ok() -> None:
    Fence(Autonomy.L0).assert_environment(env={})
    Fence(Autonomy.L1).assert_environment(env={})  # no raise


def test_assert_environment_l2_refused_uncontained() -> None:
    with pytest.raises(FenceDenied, match="container"):
        Fence(Autonomy.L2).assert_environment(env={})
    Fence(Autonomy.L2).assert_environment(env=_CONTAINED)  # ok contained


def test_assert_environment_l3_in_container_ok() -> None:
    # Inside the container L3 is the blessed bounded behaviour — no extra token.
    Fence(Autonomy.L3).assert_environment(env=_CONTAINED)


def test_assert_environment_uncontained_l3_override_only_now_raises() -> None:
    # PROVEN-RED: before T7 the uncontained override alone passed L3 (the L2 flag
    # silently granted full-auto). Now uncontained L3 demands its own distinct
    # opt-in and the override-only request fails LOUD (D-ESC-1/3).
    with pytest.raises(FenceDenied, match="CHARON_ALLOW_UNATTENDED"):
        Fence(Autonomy.L3).assert_environment(env=_OVERRIDE)
    # …with the distinct opt-in added it passes (uncontained, loudly).
    Fence(Autonomy.L3).assert_environment(env={**_OVERRIDE, **_UNATTENDED})


def test_escalation_tokens_are_not_leaked_into_scrubbed_env() -> None:
    # D-ESC-5: a fenced agent must not be able to read — let alone forge — the
    # parent's autonomy tokens. None of them survive the scrub.
    for tok in ESCALATION_TOKENS:
        os.environ[tok] = "1"
    try:
        env = Fence.scrubbed_env(Path("/tmp/wt"))
        for tok in ESCALATION_TOKENS:
            assert tok not in env
    finally:
        for tok in ESCALATION_TOKENS:
            del os.environ[tok]


# ----------------------------------------------- S1: sandbox policy (D013)

def _pol(
    sandbox: str,
    *,
    container: bool = False,
    override: bool = False,
    unattended: bool = False,
) -> AutonomyPolicy:
    e: dict[str, str] = {"CHARON_SANDBOX": sandbox}
    if container:
        e["CHARON_CONTAINER_VERIFIED"] = "1"
    if override:
        e["CHARON_ALLOW_UNCONTAINED_AUTONOMY"] = "1"
    if unattended:
        e["CHARON_ALLOW_UNATTENDED"] = "1"
    return AutonomyPolicy.from_env(e)


@pytest.mark.parametrize(
    "sandbox,container,override,unattended,expected_ceiling,resolve_checks",
    [
        ("hybrid", False, False, False, Autonomy.L1, [(Autonomy.L2, True)]),
        ("hybrid", True, False, False, Autonomy.L3, [(Autonomy.L2, False)]),
        ("hybrid", False, True, False, Autonomy.L2, []),
        ("hybrid", False, True, True, Autonomy.L3, []),
        ("container", False, False, False, Autonomy.L0, []),
        ("container", False, True, False, Autonomy.L0, []),
        ("container", True, False, False, Autonomy.L3, [(Autonomy.L2, False)]),
        ("host", False, False, False, Autonomy.L1, []),
        ("host", False, True, False, Autonomy.L2, []),
        ("host", False, True, True, Autonomy.L3, []),
        ("host", True, False, False, Autonomy.L1, []),
    ],
)
def test_sandbox_policy_ceiling(
    sandbox: str,
    container: bool,
    override: bool,
    unattended: bool,
    expected_ceiling: Autonomy,
    resolve_checks: list,
) -> None:
    pol = _pol(sandbox, container=container, override=override, unattended=unattended)
    assert pol.ceiling() is expected_ceiling
    for autonomy, expected_clamped in resolve_checks:
        assert pol.resolve(autonomy).clamped is expected_clamped


def test_hybrid_is_default_when_no_sandbox_env() -> None:
    no_sandbox = AutonomyPolicy.from_env({})
    assert no_sandbox.sandbox is SandboxPolicy.HYBRID
    assert no_sandbox.ceiling() == _pol("hybrid").ceiling()


@pytest.mark.parametrize(
    "sandbox,container,override,unattended,autonomy,should_raise,match",
    [
        ("container", False, True, False, Autonomy.L2, True, "container"),
        ("host", False, False, False, Autonomy.L2, True, None),
        ("host", True, False, False, Autonomy.L2, True, "CHARON_ALLOW_UNCONTAINED_AUTONOMY"),
        ("host", False, True, False, Autonomy.L2, False, None),
        ("host", False, True, False, Autonomy.L3, True, "CHARON_ALLOW_UNATTENDED"),
        ("host", False, True, True, Autonomy.L3, False, None),
    ],
)
def test_sandbox_policy_assert_environment(
    sandbox: str,
    container: bool,
    override: bool,
    unattended: bool,
    autonomy: Autonomy,
    should_raise: bool,
    match: str | None,
) -> None:
    env: dict[str, str] = {"CHARON_SANDBOX": sandbox}
    if container:
        env["CHARON_CONTAINER_VERIFIED"] = "1"
    if override:
        env["CHARON_ALLOW_UNCONTAINED_AUTONOMY"] = "1"
    if unattended:
        env["CHARON_ALLOW_UNATTENDED"] = "1"
    if should_raise:
        with pytest.raises(FenceDenied, match=match or ""):
            Fence(autonomy).assert_environment(env=env)
    else:
        Fence(autonomy).assert_environment(env=env)


def test_escape_detection(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    guard = tmp_path
    before = snapshot_outside(worktree, guard)
    # write OUTSIDE the worktree (sibling) -> must be detected
    (tmp_path / "escaped.txt").write_text("pwned")
    escaped = detect_escape(worktree, guard, before)
    assert any("escaped.txt" in e for e in escaped)
    # a write INSIDE the worktree is fine
    before2 = snapshot_outside(worktree, guard)
    (worktree / "ok.txt").write_text("fine")
    assert detect_escape(worktree, guard, before2) == []
