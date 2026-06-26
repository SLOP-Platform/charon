"""ADR-0007 D12 — End-product Validator: quality gate on the assembled result.

Runs ONCE after all units have landed (at the role-DAG Validate stage) and
reports pass/fail against the captured acceptance criteria.

QUALITY GATE, NOT A SECURITY BOUNDARY. An automated validator is
gameable/prompt-injectable — it catches *broken/incomplete* results, not
*clean-and-hostile* ones. Human review of sensitive paths is the security gate.
(See ADR-0007 D12; coordinator D-GATE-6 parallel.)

Stopgap (until ADR-0008 ships top-level product acceptance): runs against the
unit-level acceptance checks. Partial but honest — if unit checks pass the
product is at least self-consistent with its own stated goal.

On fail: the result is held and a fix-unit is proposed. Never silently passed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .acceptance import AcceptanceCheck, derive_remaining, derive_verified


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of one end-product quality-gate run."""

    passed: bool
    verified: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    note: str = ""
    # Suggested fix-unit description for the operator to review and spawn.
    # Non-empty only when passed=False.
    fix_proposal: str = ""


def validate(
    checks: list[AcceptanceCheck],
    worktree: str,
) -> ValidationResult:
    """Run the quality gate on the assembled product at ``worktree``.

    ``checks`` should be the top-level product acceptance from ADR-0008 intake
    when available.  Until then pass the unit-level checks (honest stopgap).

    Contract: never silently passes a failed result.  When passed=False the
    caller must hold the result (do not advance lkg) and surface fix_proposal
    to the operator so a follow-up unit can be spawned.
    """
    if not checks:
        return ValidationResult(
            passed=False,
            note="no acceptance checks defined — cannot validate; held for human review",
            fix_proposal="Define executable acceptance checks and re-run validation.",
        )

    verified = sorted(derive_verified(checks, worktree))
    remaining = sorted(derive_remaining(checks, worktree))

    if not remaining:
        return ValidationResult(
            passed=True,
            verified=verified,
            note="all acceptance checks passed",
        )

    fix_prompt = (
        f"The following acceptance checks failed on the assembled product: "
        f"{remaining}. Fix the product so all checks pass."
    )
    return ValidationResult(
        passed=False,
        verified=verified,
        remaining=remaining,
        note=f"validation failed: {len(remaining)} check(s) unmet",
        fix_proposal=fix_prompt,
    )
