from __future__ import annotations

import os
from pathlib import Path

import pytest

from charon.fence import (
    ESCALATION_TOKENS,
    AutonomyPolicy,
    Fence,
    FenceDenied,
    SandboxPolicy,
    _SANDBOX_ENV,
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


# ----------------------------------------- D013: sandbox policy gate behavior

# Regression: hybrid must reproduce pre-D013 behavior byte-for-byte.
# Each case below is run twice — once via the old code path (from_env with no
# sandbox kw, which defaults to hybrid) and once explicitly (sandbox=hybrid).
# Any divergence between the two means the default has changed.

def _old_ceiling(env: dict) -> Autonomy:
    """Simulate the pre-D013 ceiling: from_env with no sandbox argument."""
    return AutonomyPolicy.from_env(env).ceiling()


def _hybrid_ceiling(env: dict) -> Autonomy:
    return AutonomyPolicy.from_env(env, sandbox=SandboxPolicy.hybrid).ceiling()


def test_hybrid_regression_no_tokens() -> None:
    assert _old_ceiling({}) == _hybrid_ceiling({}) == Autonomy.L1


def test_hybrid_regression_contained() -> None:
    assert _old_ceiling(_CONTAINED) == _hybrid_ceiling(_CONTAINED) == Autonomy.L3


def test_hybrid_regression_override_only() -> None:
    assert _old_ceiling(_OVERRIDE) == _hybrid_ceiling(_OVERRIDE) == Autonomy.L2


def test_hybrid_regression_override_plus_unattended() -> None:
    env = {**_OVERRIDE, **_UNATTENDED}
    assert _old_ceiling(env) == _hybrid_ceiling(env) == Autonomy.L3


def test_sandbox_env_var_read_by_from_env() -> None:
    # CHARON_SANDBOX in the env dict is honoured by from_env.
    env = {_SANDBOX_ENV: "host", **_OVERRIDE}
    pol = AutonomyPolicy.from_env(env)
    assert pol.sandbox is SandboxPolicy.host
    assert pol.ceiling() is Autonomy.L2  # override present → L2 in host mode


def test_sandbox_env_var_unknown_value_falls_back_to_hybrid() -> None:
    env = {_SANDBOX_ENV: "bogus"}
    pol = AutonomyPolicy.from_env(env)
    assert pol.sandbox is SandboxPolicy.hybrid  # fail-safe


# --- policy: container ---

def test_container_policy_l1_refused_without_container() -> None:
    # Applying rungs (L1+) require the container in container mode.
    # L0 (propose-only, no apply) stays freely grantable even without the container.
    pol = AutonomyPolicy.from_env({}, sandbox=SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L0  # nothing above L0 grantable without container
    assert pol._rung_ok(Autonomy.L0) is True   # propose-only: always allowed
    assert pol._rung_ok(Autonomy.L1) is False  # apply-reversible: container required


def test_container_policy_override_is_refused() -> None:
    # container policy refuses the uncontained-override path even for L2.
    pol = AutonomyPolicy.from_env(_OVERRIDE, sandbox=SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L0
    assert pol.resolve(Autonomy.L2).clamped is True


def test_container_policy_l3_inside_container() -> None:
    pol = AutonomyPolicy.from_env(_CONTAINED, sandbox=SandboxPolicy.container)
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L3).clamped is False


def test_container_policy_assert_environment_l2_refuses_without_container() -> None:
    with pytest.raises(FenceDenied):
        Fence(Autonomy.L2).assert_environment(env=_OVERRIDE, sandbox=SandboxPolicy.container)
    # passes inside the container
    Fence(Autonomy.L2).assert_environment(env=_CONTAINED, sandbox=SandboxPolicy.container)


# --- policy: host ---

def test_host_policy_l1_always_ok() -> None:
    pol = AutonomyPolicy.from_env({}, sandbox=SandboxPolicy.host)
    assert pol.ceiling() is Autonomy.L1
    assert pol._rung_ok(Autonomy.L1) is True


def test_host_policy_l2_requires_uncontained_override() -> None:
    # host: override grants L2 (no container needed).
    pol_with = AutonomyPolicy.from_env(_OVERRIDE, sandbox=SandboxPolicy.host)
    assert pol_with.ceiling() is Autonomy.L2
    assert pol_with.resolve(Autonomy.L2).clamped is False
    # without override: L2 is denied (loud override still required).
    pol_no = AutonomyPolicy.from_env({}, sandbox=SandboxPolicy.host)
    assert pol_no.resolve(Autonomy.L2).clamped is True


def test_host_policy_container_alone_does_not_grant_l2() -> None:
    # In host mode the container is irrelevant — the loud override is still needed.
    pol = AutonomyPolicy.from_env(_CONTAINED, sandbox=SandboxPolicy.host)
    assert pol.ceiling() is Autonomy.L1
    assert pol.resolve(Autonomy.L2).clamped is True


def test_host_policy_l3_requires_override_and_unattended() -> None:
    # L3 in host mode: both loud override flags, no container needed.
    pol = AutonomyPolicy.from_env({**_OVERRIDE, **_UNATTENDED}, sandbox=SandboxPolicy.host)
    assert pol.ceiling() is Autonomy.L3
    assert pol.resolve(Autonomy.L3).clamped is False
    # override alone: caps at L2 (same as hybrid uncontained).
    pol2 = AutonomyPolicy.from_env(_OVERRIDE, sandbox=SandboxPolicy.host)
    assert pol2.resolve(Autonomy.L3).clamped is True


def test_host_policy_assert_environment_l2_refuses_without_override() -> None:
    with pytest.raises(FenceDenied):
        Fence(Autonomy.L2).assert_environment(env=_CONTAINED, sandbox=SandboxPolicy.host)
    Fence(Autonomy.L2).assert_environment(env=_OVERRIDE, sandbox=SandboxPolicy.host)


# --- CHARON_SANDBOX env var flows through Fence.assert_environment ---

def test_assert_environment_reads_sandbox_from_env_dict() -> None:
    # container policy via env var: assert_environment with no explicit sandbox=
    # reads CHARON_SANDBOX from the supplied env dict (no override path).
    env = {_SANDBOX_ENV: "container"}
    with pytest.raises(FenceDenied):
        Fence(Autonomy.L2).assert_environment(env={**env, **_OVERRIDE})
    Fence(Autonomy.L2).assert_environment(env={**env, **_CONTAINED})


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
