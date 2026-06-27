"""ADR-0007 D12 — End-product Validator: quality gate on the assembled result.

Runs ONCE after all units have landed (at the role-DAG Validate stage, or on the
integrated end-product the work-engine assembles) and reports pass/fail against
the captured acceptance criteria.

QUALITY GATE, NOT A SECURITY BOUNDARY. An automated validator is
gameable/prompt-injectable — it catches *broken/incomplete* results, not
*clean-and-hostile* ones. Human review of sensitive paths is the security gate.
(See ADR-0007 D12; coordinator D-GATE-6 parallel.)

Two entry points, one gate:
- :func:`validate` runs against an explicit list of acceptance checks. The
  role-DAG (``decompose.py``) uses it against the unit-level checks — the honest
  stopgap when no top-level acceptance exists.
- :func:`validate_product` runs against the **top-level product acceptance**
  captured by intake (ADR-0008): it extracts the executable checks from that
  acceptance text and validates the assembled/integrated worktree. This is the
  real end-product gate the work-engine wires (E6), replacing the unit-level
  stopgap at the integration boundary.

On fail: the result is held and a fix-unit is proposed. Never silently passed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .acceptance import AcceptanceCheck, derive_remaining, derive_verified

# An inline-code span — the form intake captures executable acceptance commands
# in (a ``## Product acceptance`` section's backtick-wrapped commands). Mirrors
# ``intake._INLINE_CODE_RE`` so the validator reads exactly what intake emits.
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


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


def top_level_checks(product_acceptance: str) -> list[AcceptanceCheck]:
    """Extract executable acceptance checks from intake's top-level product
    acceptance text (ADR-0008).

    The intake ``## Product acceptance`` section is captured verbatim; its
    executable criteria are the inline-code (backtick-wrapped) commands — the same
    convention intake uses for a unit's ``accept`` field. Each becomes one
    :class:`AcceptanceCheck`. Prose with no command yields an empty list, which the
    validator treats as "no executable acceptance → hold for human review" (never a
    silent pass). The text is parsed as DATA — nothing is executed here."""
    cmds = [m.strip() for m in _INLINE_CODE_RE.findall(product_acceptance or "")]
    return [
        AcceptanceCheck(id=f"p{i}", cmd=cmd)
        for i, cmd in enumerate(c for c in cmds if c)
    ]


def validate_product(product_acceptance: str, worktree: str) -> ValidationResult:
    """Run the D12 end-product quality gate ONCE on the assembled/integrated
    result at ``worktree`` against the TOP-LEVEL product acceptance (ADR-0008),
    replacing the unit-level stopgap at the integration boundary (E6).

    Derives the executable checks from ``product_acceptance`` and delegates to
    :func:`validate`, so the contract is identical: never silently passes a failed
    result; on fail the caller must hold the integrated result and surface
    ``fix_proposal`` (a fix-unit the operator can spawn). A product acceptance with
    no executable command is held for human review — an unverifiable product is
    never declared done. Still a QUALITY gate, NOT a trust boundary."""
    return validate(top_level_checks(product_acceptance), worktree)
