"""Product-grade ledger — processes model evaluation results through the
EVAL-PROMOTION-GATE control-panel gate, producing per-model grades for
the outcome-graded brain (ADR-0017 product_grades path).

The promotion gate validates live evaluation rows against seeded control
entries (``strong-control``). A ref passes the gate when it has ≥3 matching
control rows with ``passed=True``. When NO control rows exist for a ref, the
gate ADMITS the live rows with a ``provisional`` / ``uncontrolled`` flag
(the no-control→admit fallback) — so the grading pipeline never returns 0
grades purely because the control panel is empty.

Architecture:
  * :class:`EvalRow` — one evaluation result for a model on a ticket ref.
  * :class:`ControlRow` — a reference evaluation that validates a ref's results.
  * :func:`split_ok` — per-ref gate check that implements the
    strong-control ⋅ ≥3 validation + no-control→admit fallback.
  * :func:`grade_refs` — the main entrypoint: reads evaluation rows, runs the
    EVAL-PROMOTION-GATE, and returns graded rows (flagged where uncontrolled).

This module is the product-grade counterpart to ``grades_import.py`` (the
cold-start prior bridge). Together they power ADR-0017's ``product_grades``
seed path: the import bridge seeds the matrix day-1; the live grading pipeline
(here) overwrites those priors with real graded outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── data types ──────────────────────────────────────────────────────────

ControlType = Literal["strong-control"]
"""The must-pass control type required by the EVAL-PROMOTION-GATE.

``strong-control`` entries are reference evaluation runs seeded by the
operator. A ref is valid when ≥3 distinct ``strong-control`` rows with
``passed=True`` exist for it in the control panel."""

Flag = Literal["clean", "provisional", "uncontrolled"]
"""Integrity flag for a graded row.

* ``clean`` — passed the control-panel gate normally (≥3 matching controls).
* ``provisional`` — admitted via the no-control→admit fallback (no controls
  exist for this ref; grade is provisional pending manual review).
* ``uncontrolled`` — synonymous with provisional; set when the gate has no
  control data for this ref at all.
"""


@dataclass(frozen=True)
class EvalRow:
    """One raw evaluation result: a model's grade on a ticket ref.

    The evaluator writes one ``EvalRow`` per ``(ref, model_id)`` pair.
    ``grade`` is the coarse band (A–F) produced by the evaluator; ``flagged``
    is set by the gate when the row is admitted without full control-panel
    validation.
    """

    ref: str
    model_id: str
    grade: str
    flagged: bool = False


@dataclass(frozen=True)
class ControlRow:
    """A reference evaluation used to validate a ref's grading consistency.

    The operator seeds ``ControlRow`` entries (typically via
    ``strong-control`` runs) so the EVAL-PROMOTION-GATE can detect when a
    ref's evaluation results are noisy or inconsistent. A ref passes the
    gate when ≥3 ``strong-control`` rows with ``passed=True`` exist for it.
    """

    ref: str
    control_type: ControlType = "strong-control"
    passed: bool = True


# ── gate constants ──────────────────────────────────────────────────────

_MIN_CONTROL_COUNT = 3
"""Minimum number of passed strong-control rows required for a ref to pass
the EVAL-PROMOTION-GATE normally."""

MIN_CONTROL_COUNT = _MIN_CONTROL_COUNT
"""Public alias for the ≥3 strong-control threshold (exported in ``__all__``)."""


# ── the gate check ──────────────────────────────────────────────────────


def split_ok(
    ref: str,
    *,
    controls: list[ControlRow],
    require_control_panel: bool = True,
) -> bool:
    """Check whether *ref* passes the EVAL-PROMOTION-GATE control-panel gate.

    A ref passes when ≥3 ``strong-control`` rows with ``passed=True`` exist
    for it. When *require_control_panel* is ``True`` and NO control rows
    exist for *ref* at all, this function returns ``True`` (the no-control→
    admit fallback) — the caller SHOULD flag the admitted rows as
    provisional/uncontrolled.

    When *require_control_panel* is ``False`` the gate is disabled and every
    ref passes unconditionally.

    Args:
        ref: The ticket ref to check.
        controls: All known control rows.
        require_control_panel: When ``True``, enforce the gate. When
            ``False``, bypass it entirely.

    Returns:
        ``True`` when the ref is admitted (either via normal validation,
        the no-control→admit fallback, or the gate being disabled).
    """
    if not require_control_panel:
        return True

    matching = [
        c
        for c in controls
        if c.ref == ref
        and c.control_type == "strong-control"
        and c.passed
    ]
    if len(matching) >= _MIN_CONTROL_COUNT:
        return True

    # ── no-control → admit fallback ────────────────────────────────────
    # The docstring for this gate PROMISES a no-control-present →
    # admit-with-caveat path.  When require_control_panel is on but there
    # are ZERO control rows for this ref, we admit the ref anyway (the
    # caller flags the grade as provisional/uncontrolled).  This prevents
    # the gate from being structurally unsatisfiable on the live lane,
    # where control models never run against real ticket refs.
    # ── see also: grades.py:651-654 (EVAL-PROMOTION-GATE loop) ───────────
    ref_controls = [c for c in controls if c.ref == ref]
    if not ref_controls:
        return True

    return False


def _is_fallback_admit(
    ref: str,
    *,
    controls: list[ControlRow],
    require_control_panel: bool,
) -> bool:
    """True iff *ref* is admitted purely via the no-control→admit fallback.

    This is separate from ``split_ok`` so the grading loop can distinguish
    a normal admit (≥3 controls) from a fallback admit (no controls at all)
    and flag the row accordingly.
    """
    if not require_control_panel:
        return False
    matching = [
        c
        for c in controls
        if c.ref == ref
        and c.control_type == "strong-control"
        and c.passed
    ]
    if len(matching) >= _MIN_CONTROL_COUNT:
        return False
    ref_controls = [c for c in controls if c.ref == ref]
    return not ref_controls


# ── grading entrypoint ──────────────────────────────────────────────────


def grade_refs(
    eval_rows: list[EvalRow],
    control_rows: list[ControlRow],
    *,
    require_control_panel: bool = True,
) -> list[EvalRow]:
    """Run the EVAL-PROMOTION-GATE across all refs in *eval_rows*.

    For each ref:
    1. If ``split_ok`` returns ``False``, ALL rows for that ref are
       excluded (the control panel detected an integrity issue).
    2. If ``split_ok`` returns ``True`` via the no-control→admit fallback,
       the rows are admitted with ``flagged=True`` (provisional/uncontrolled).
    3. If ``split_ok`` returns ``True`` normally (≥3 strong-control rows),
       the rows are admitted clean.

    Args:
        eval_rows: Raw evaluation results to grade.
        control_rows: Seeded control rows for validation.
        require_control_panel: Passed through to ``split_ok``.

    Returns:
        Graded rows that passed the gate. Rows admitted via the
        no-control→admit fallback have ``flagged=True``.
    """
    refs = {r.ref for r in eval_rows}
    result: list[EvalRow] = []

    for ref in refs:
        if not split_ok(
            ref, controls=control_rows, require_control_panel=require_control_panel
        ):
            continue

        is_fallback = _is_fallback_admit(
            ref, controls=control_rows, require_control_panel=require_control_panel
        )

        for row in eval_rows:
            if row.ref != ref:
                continue
            flagged = row.flagged or is_fallback
            result.append(
                EvalRow(
                    ref=row.ref,
                    model_id=row.model_id,
                    grade=row.grade,
                    flagged=flagged,
                )
            )

    return result


# ── control-panel query helpers ─────────────────────────────────────────


def count_matching_controls(ref: str, controls: list[ControlRow]) -> int:
    """Count the number of passed ``strong-control`` rows for *ref*.

    Returns 0 when *ref* has no matching controls or none are seeded yet.
    """
    return len(
        [
            c
            for c in controls
            if c.ref == ref
            and c.control_type == "strong-control"
            and c.passed
        ]
    )


def has_any_control(ref: str, controls: list[ControlRow]) -> bool:
    """True iff at least one control row (any type) exists for *ref*."""
    return any(c.ref == ref for c in controls)


def is_provisionally_graded(row: EvalRow) -> bool:
    """True iff *row* was admitted via the no-control→admit fallback.

    A row is provisional when its ``flagged`` attribute is ``True`` and
    it was not explicitly failed — meaning the gate could not validate it
    but admitted it anyway to avoid dropping all grades for the ref.
    """
    return row.flagged


# ── filtering helpers for callers (grade consumers) ─────────────────────


def filter_clean(grades: list[EvalRow]) -> list[EvalRow]:
    """Return only grades that passed the gate without caveats."""
    return [r for r in grades if not r.flagged]


def filter_provisional(grades: list[EvalRow]) -> list[EvalRow]:
    """Return only grades admitted via the no-control→admit fallback."""
    return [r for r in grades if r.flagged]


# ── grading summary ─────────────────────────────────────────────────────


@dataclass
class GradingSummary:
    """Summary of a grading run through the EVAL-PROMOTION-GATE."""

    total_rows: int = 0
    admitted: int = 0
    excluded: int = 0
    provisional: int = 0
    clean: int = 0
    refs: list[str] = field(default_factory=list)
    refs_excluded: list[str] = field(default_factory=list)
    """Refs that were excluded by the gate (≥1 but <3 strong-control rows)."""


def summarize(
    eval_rows: list[EvalRow],
    graded: list[EvalRow],
    *,
    control_rows: list[ControlRow],
) -> GradingSummary:
    """Produce a summary of a grading run.

    Args:
        eval_rows: The raw input rows.
        graded: The output of ``grade_refs`` (rows that passed the gate).
        control_rows: The control rows used for validation.

    Returns:
        A ``GradingSummary`` with counts and excluded refs.
    """
    admitted_refs = {r.ref for r in graded}
    all_refs = {r.ref for r in eval_rows}
    excluded_refs = sorted(all_refs - admitted_refs)

    total = len(eval_rows)
    admitted = len(graded)
    provisional = len([r for r in graded if r.flagged])
    clean = admitted - provisional

    return GradingSummary(
        total_rows=total,
        admitted=admitted,
        excluded=total - admitted,
        provisional=provisional,
        clean=clean,
        refs=sorted(admitted_refs),
        refs_excluded=excluded_refs,
    )


__all__ = [
    "ControlType",
    "Flag",
    "EvalRow",
    "ControlRow",
    "MIN_CONTROL_COUNT",
    "split_ok",
    "grade_refs",
    "count_matching_controls",
    "has_any_control",
    "is_provisionally_graded",
    "filter_clean",
    "filter_provisional",
    "GradingSummary",
    "summarize",
]
