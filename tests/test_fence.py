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


def test_hybrid_regression_matches_current_default_behavior() -> None:
    """hybrid == byte-for-byte current behavior; no-sandbox-env also equals hybrid (D013)."""
    # All of these are also tested by the pre-existing T7 suite above; repeating
    # here with an explicit sandbox=hybrid to prove the policy is the identity.
    assert _pol("hybrid").ceiling() is Autonomy.L1
    assert _pol("hybrid", container=True).ceiling() is Autonomy.L3
    assert _pol("hybrid", override=True).ceiling() is Autonomy.L2
    assert _pol("hybrid", override=True, unattended=True).ceiling() is Autonomy.L3
    assert _pol("hybrid", container=True).resolve(Autonomy.L2).clamped is False
    # Absent CHARON_SANDBOX defaults to hybrid.
    no_sandbox = AutonomyPolicy.from_env({})
    assert no_sandbox.sandbox is SandboxPolicy.HYBRID
    assert no_sandbox.ceiling() == _pol("hybrid").ceiling()


def test_container_policy_requires_container_for_l1_plus() -> None:
    """container: ≥L1 needs CHARON_CONTAINER_VERIFIED; override path is refused (D013)."""
    # No container → ceiling L0 (L1 check fails without container).
    assert _pol("container").ceiling() is Autonomy.L0
    # Override alone is refused — container policy ignores the override.
    assert _pol("container", override=True).ceiling() is Autonomy.L0
    # Container satisfies all rungs.
    assert _pol("container", container=True).ceiling() is Autonomy.L3
    assert _pol("container", container=True).resolve(Autonomy.L2).clamped is False


def test_container_policy_refuses_uncontained_l2_even_with_override() -> None:
    """Spec: container refuses uncontained L2 even WITH the override (D013)."""
    with pytest.raises(FenceDenied, match="container"):
        Fence(Autonomy.L2).assert_environment(
            env={
                "CHARON_SANDBOX": "container",
                "CHARON_ALLOW_UNCONTAINED_AUTONOMY": "1",
            }
        )


def test_host_policy_requires_loud_override_for_l2_plus() -> None:
    """host: L0/L1 free; L2+ requires the loud override; container alone is not sufficient."""
    # No override → ceiling L1.
    assert _pol("host").ceiling() is Autonomy.L1
    # Override → L2.
    assert _pol("host", override=True).ceiling() is Autonomy.L2
    # Override + unattended → L3.
    assert _pol("host", override=True, unattended=True).ceiling() is Autonomy.L3
    # Container alone is NOT sufficient in host policy.
    assert _pol("host", container=True).ceiling() is Autonomy.L1


def test_host_policy_l2_denied_without_override_even_if_containerized() -> None:
    """host: L2 with container only → denied; L2 with override → OK."""
    # No override, no container → denied.
    with pytest.raises(FenceDenied):
        Fence(Autonomy.L2).assert_environment(env={"CHARON_SANDBOX": "host"})
    # Container alone → still denied (host policy demands override).
    with pytest.raises(FenceDenied, match="CHARON_ALLOW_UNCONTAINED_AUTONOMY"):
        Fence(Autonomy.L2).assert_environment(
            env={"CHARON_SANDBOX": "host", "CHARON_CONTAINER_VERIFIED": "1"}
        )
    # Override → OK.
    Fence(Autonomy.L2).assert_environment(
        env={"CHARON_SANDBOX": "host", "CHARON_ALLOW_UNCONTAINED_AUTONOMY": "1"}
    )


def test_host_policy_l3_still_needs_unattended_on_top_of_override() -> None:
    """host L3: override alone is not enough; must also have unattended opt-in."""
    with pytest.raises(FenceDenied, match="CHARON_ALLOW_UNATTENDED"):
        Fence(Autonomy.L3).assert_environment(
            env={"CHARON_SANDBOX": "host", "CHARON_ALLOW_UNCONTAINED_AUTONOMY": "1"}
        )
    Fence(Autonomy.L3).assert_environment(
        env={
            "CHARON_SANDBOX": "host",
            "CHARON_ALLOW_UNCONTAINED_AUTONOMY": "1",
            "CHARON_ALLOW_UNATTENDED": "1",
        }
    )


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
