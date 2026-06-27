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


# ----------------------------------- D013: sandbox policy gate (S1)

def _pol(env: dict, sandbox: SandboxPolicy) -> AutonomyPolicy:
    """Helper: build a policy with an explicit sandbox, bypassing env-var lookup."""
    return AutonomyPolicy.from_env(env, sandbox=sandbox)


# --- hybrid regression: must be byte-for-byte the existing default gate ---------

def test_hybrid_regression_matches_default() -> None:
    """hybrid == the current default at every env/rung combination (D013)."""
    envs = [
        {},
        _CONTAINED,
        _OVERRIDE,
        _UNATTENDED,
        {**_OVERRIDE, **_UNATTENDED},
        {**_CONTAINED, **_OVERRIDE},
    ]
    for env in envs:
        default = AutonomyPolicy.from_env(env, sandbox=SandboxPolicy.hybrid)
        # ceiling and every resolve result must match
        for level in Autonomy:
            assert default.ceiling() == _pol(env, SandboxPolicy.hybrid).ceiling(), env
            dr = default.resolve(level)
            hr = _pol(env, SandboxPolicy.hybrid).resolve(level)
            assert dr.granted == hr.granted, (env, level)
            assert dr.clamped == hr.clamped, (env, level)


def test_hybrid_default_deny_no_tokens() -> None:
    pol = _pol({}, SandboxPolicy.hybrid)
    assert pol.ceiling() is Autonomy.L1


def test_hybrid_contained_grants_l3() -> None:
    pol = _pol(_CONTAINED, SandboxPolicy.hybrid)
    assert pol.ceiling() is Autonomy.L3


def test_hybrid_override_alone_caps_at_l2() -> None:
    pol = _pol(_OVERRIDE, SandboxPolicy.hybrid)
    assert pol.ceiling() is Autonomy.L2
    assert pol.resolve(Autonomy.L3).clamped is True


def test_hybrid_uncontained_l3_needs_both_flags() -> None:
    pol = _pol({**_OVERRIDE, **_UNATTENDED}, SandboxPolicy.hybrid)
    assert pol.ceiling() is Autonomy.L3


# --- container mode: ALL rungs require container; override refused ---------------

def test_container_mode_refuses_l0_without_container() -> None:
    # Even L0 is refused uncontained — the whole point of container mode.
    pol = _pol({}, SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L0
    assert pol.resolve(Autonomy.L0).clamped is False  # L0 ceiling IS L0 — not clamped
    # but assert_environment with L1 raises:
    with pytest.raises(FenceDenied, match="sandbox=container"):
        Fence(Autonomy.L1).assert_environment(env={"CHARON_SANDBOX": "container"})


def test_container_mode_with_container_grants_l3() -> None:
    pol = _pol(_CONTAINED, SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L3).clamped is False


def test_container_mode_refuses_l2_even_with_override() -> None:
    # PROVEN-RED: override is refused in container mode — container is mandatory.
    pol = _pol(_OVERRIDE, SandboxPolicy.container)
    assert pol.resolve(Autonomy.L2).clamped is True
    with pytest.raises(FenceDenied, match="sandbox=container"):
        Fence(Autonomy.L2).assert_environment(
            env={**_OVERRIDE, "CHARON_SANDBOX": "container"}
        )


def test_container_mode_refuses_l2_even_with_override_and_unattended() -> None:
    # Even all uncontained tokens together are refused in container mode.
    env = {**_OVERRIDE, **_UNATTENDED, "CHARON_SANDBOX": "container"}
    with pytest.raises(FenceDenied, match="sandbox=container"):
        Fence(Autonomy.L2).assert_environment(env=env)


def test_container_mode_ceiling_is_l0_without_container() -> None:
    pol = _pol({}, SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L0


# --- host mode: L0/L1 always OK; L2+ need override; D-ESC-1 still applies -----

def test_host_mode_l0_l1_always_ok() -> None:
    for level in (Autonomy.L0, Autonomy.L1):
        pol = _pol({}, SandboxPolicy.host)
        assert pol.resolve(level).clamped is False


def test_host_mode_l2_requires_override() -> None:
    pol = _pol({}, SandboxPolicy.host)
    assert pol.resolve(Autonomy.L2).clamped is True
    pol_with_override = _pol(_OVERRIDE, SandboxPolicy.host)
    assert pol_with_override.resolve(Autonomy.L2).clamped is False


def test_host_mode_l3_requires_override_and_unattended() -> None:
    # D-ESC-1 still applies in host mode: override alone does NOT grant L3.
    pol_override_only = _pol(_OVERRIDE, SandboxPolicy.host)
    assert pol_override_only.resolve(Autonomy.L3).clamped is True
    with pytest.raises(FenceDenied, match="CHARON_ALLOW_UNATTENDED"):
        Fence(Autonomy.L3).assert_environment(
            env={**_OVERRIDE, "CHARON_SANDBOX": "host"}
        )


def test_host_mode_l3_with_both_flags_granted() -> None:
    pol = _pol({**_OVERRIDE, **_UNATTENDED}, SandboxPolicy.host)
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L3).clamped is False


def test_host_mode_container_alone_does_not_grant_l2() -> None:
    # In host mode the container flag is irrelevant — override is still required.
    pol = _pol(_CONTAINED, SandboxPolicy.host)
    assert pol.resolve(Autonomy.L2).clamped is True


# --- env-var resolution: CHARON_SANDBOX routes to the right policy -------------

def test_sandbox_env_var_default_is_hybrid(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SANDBOX", raising=False)
    pol = AutonomyPolicy.from_env({})
    assert pol.sandbox is SandboxPolicy.hybrid


def test_sandbox_env_var_container(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SANDBOX", "container")
    pol = AutonomyPolicy.from_env()
    assert pol.sandbox is SandboxPolicy.container


def test_sandbox_env_var_host(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SANDBOX", "host")
    pol = AutonomyPolicy.from_env()
    assert pol.sandbox is SandboxPolicy.host


def test_sandbox_env_var_invalid_raises(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SANDBOX", "badvalue")
    with pytest.raises(ValueError, match="CHARON_SANDBOX"):
        AutonomyPolicy.from_env()


# -----------------------------------------------------------------------

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
