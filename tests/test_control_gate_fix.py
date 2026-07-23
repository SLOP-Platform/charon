"""EVAL-CONTROL-GATE-FIX — fail-on-revert tests for the no-control→admit fallback.

Audited root defect (ranking-pipeline audit 2026-07-23): the EVAL-PROMOTION-GATE
control-panel gate in ``grades.py`` requires a per-ref MUST-PASS control
``strong-control`` with ≥3 rows, but ``strong-control`` has 0 rows in the entire
ledger and control models never run against real ticket refs — so ``split_ok``
was ALWAYS ``False`` and EVERY live row was excluded → 0 grades for all 6
models. The gate was STRUCTURALLY UNSATISFIABLE on the live lane.

The fix implements the no-control→admit fallback the gate's docstring already
promised (but the old code did a hard ``continue`` instead): when a ref has ZERO
control rows present, admit its live rows flagged ``provisional``/``uncontrolled``.

These tests pin the fallback so a future revert (re-introducing the hard
``continue``) FAILS the suite. The gate's integrity where controls DO exist is
unchanged — partial controls (1–2 rows, below the ≥3 threshold) STILL exclude.
"""
from __future__ import annotations

from charon.capability.grades import (
    ControlRow,
    EvalRow,
    GradingSummary,
    count_matching_controls,
    filter_clean,
    filter_provisional,
    grade_refs,
    has_any_control,
    is_provisionally_graded,
    split_ok,
    summarize,
)

# ── the structural fix: a live ref with NO control rows must still grade ─────


def test_no_control_ref_admits_flagged_not_dropped():
    """FAIL-ON-REVERT: a live row with no matching control MUST produce a
    (flagged) grade, not be excluded. Re-introducing the hard ``continue``
    (the structurally-unsatisfiable gate) makes this test fail — 0 grades
    instead of 1 flagged grade for the live ref."""
    live = [EvalRow(ref="T-100", model_id="glm-5.2", grade="A")]
    graded = grade_refs(live, control_rows=[], require_control_panel=True)

    # The ref is admitted (not excluded) — the gate is no longer duck-0.
    assert len(graded) == 1, "no-control ref was dropped (gate unsatisfiable)"
    assert graded[0].ref == "T-100"
    assert graded[0].model_id == "glm-5.2"
    # ...but flagged provisional/uncontrolled — the gate's integrity intent is
    # preserved (the row did NOT pass real control-panel validation).
    assert graded[0].flagged is True
    assert is_provisionally_graded(graded[0]) is True


def test_no_control_admits_all_six_live_models_flagged():
    """The audit found 0 grades for all 6 live models with the gate on. With
    the fallback, the 6 live models each produce a flagged grade — the #1
    unblock for real per-model ranking."""
    live = [
        EvalRow(ref="T-1", model_id=f"model-{i}", grade="B")
        for i in range(6)
    ]
    graded = grade_refs(live, control_rows=[], require_control_panel=True)

    assert len(graded) == 6, (
        f"expected 6 flagged grades (one per live model), got {len(graded)}"
    )
    assert {r.model_id for r in graded} == {f"model-{i}" for i in range(6)}
    assert all(r.flagged for r in graded), "uncontrolled rows must be flagged"


def test_no_control_split_ok_admits_and_is_fallback():
    """``split_ok`` returns True for a ref with no controls, and
    ``_is_fallback_admit`` confirms it's the no-control→admit path (so the
    grading loop flags it), not a clean pass."""
    assert split_ok("T-9", controls=[], require_control_panel=True) is True
    # The fallback detector distinguishes "clean ≥3 pass" from "admit fallback".
    from charon.capability.grades import _is_fallback_admit

    assert _is_fallback_admit(
        "T-9", controls=[], require_control_panel=True
    ) is True


# ── gate integrity where controls DO exist is unchanged ──────────────────────


def test_three_strong_controls_passes_clean():
    """A ref with ≥3 passed ``strong-control`` rows passes the gate normally
    (clean — NOT flagged). The fix does not weaken the gate where controls
    exist; it ONLY adds the no-control fallback."""
    live = [EvalRow(ref="T-clean", model_id="m", grade="A")]
    controls = [
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
    ]
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)

    assert len(graded) == 1
    assert graded[0].flagged is False, (
        "≥3 controls should pass clean, not provisional"
    )
    assert is_provisionally_graded(graded[0]) is False


def test_partial_controls_below_threshold_still_exclude():
    """Integrity preserved: a ref with 1–2 (below the ≥3 threshold) control
    rows is STILL excluded. The fix admits refs with NO controls at all; it
    does NOT lower the ≥3 bar where controls exist."""
    live = [EvalRow(ref="T-partial", model_id="m", grade="A")]
    controls = [ControlRow(ref="T-partial"), ControlRow(ref="T-partial")]
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)

    # Partial controls present → gate is NOT unsatisfiable-for-no-controls →
    # the ref fails the ≥3 check and is excluded (not admitted via fallback).
    assert graded == [], (
        "partial controls below the ≥3 threshold must exclude the ref, "
        "not admit it via the no-control fallback"
    )
    assert split_ok("T-partial", controls=controls, require_control_panel=True) is False


def test_failed_control_rows_do_not_count_toward_threshold():
    """A ``strong-control`` row with ``passed=False`` does not count toward the
    ≥3 threshold. If that leaves ZERO passing controls AND no other control
    rows exist, the no-control→admit fallback does NOT trigger — integrity
    preserved (the operator seeded a control that failed; don't paper over it).
    """
    live = [EvalRow(ref="T-fail", model_id="m", grade="A")]
    controls = [ControlRow(ref="T-fail", passed=False)]
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)

    # The ref has a control row present (it failed), so this is NOT the
    # no-control case — the gate excludes it rather than admitting fallback.
    assert graded == []
    assert has_any_control("T-fail", controls) is True
    assert count_matching_controls("T-fail", controls) == 0
    # split_ok is False: passing-controls < 3 AND a control IS present.
    assert split_ok("T-fail", controls=controls, require_control_panel=True) is False


def test_gate_disabled_admits_clean():
    """require_control_panel=False bypasses the gate entirely → clean grades.
    The fallback must NOT flag rows when the operator explicitly disables the
    gate (that's a separate code path from "no controls seeded")."""
    live = [EvalRow(ref="T-off", model_id="m", grade="A")]
    graded = grade_refs(live, control_rows=[], require_control_panel=False)

    assert len(graded) == 1
    assert graded[0].flagged is False


# ── mixed refs: fallback only flags the uncontrolled ones ────────────────────


def test_mixed_refs_clean_and_fallback_in_same_run():
    """In a single grading run, the clean ref (≥3 controls) passes unflagged
    and the no-control ref is admitted flagged — the gate distinguishes the
    two rather than collapsing to a single admit/exclude decision."""
    live = [
        EvalRow(ref="T-clean", model_id="m1", grade="A"),
        EvalRow(ref="T-none", model_id="m2", grade="B"),
    ]
    controls = [
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
    ]
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)

    by_ref = {r.ref: r for r in graded}
    assert by_ref["T-clean"].flagged is False
    assert by_ref["T-none"].flagged is True
    assert len(graded) == 2, "neither ref should be dropped"


def test_filter_helpers_split_clean_and_provisional():
    """``filter_clean`` / ``filter_provisional`` partition graded rows so
    ranking consumers can treat flagged ones as a separate cohort."""
    live = [
        EvalRow(ref="T-clean", model_id="m1", grade="A"),
        EvalRow(ref="T-none", model_id="m2", grade="B"),
    ]
    controls = [
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
        ControlRow(ref="T-clean"),
    ]
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)

    clean = filter_clean(graded)
    provisional = filter_provisional(graded)
    assert len(clean) == 1 and clean[0].ref == "T-clean"
    assert len(provisional) == 1 and provisional[0].ref == "T-none"


# ── summary reports the unblocked grading run ───────────────────────────────


def test_summarize_reports_provisional_admits():
    """``summarize`` reports admitted vs excluded vs provisional counts — the
    no-control refs are counted as provisional (admitted), NOT excluded. This
    is the audit's unblock signal: excluded=0 when all refs are no-control."""
    live = [
        EvalRow(ref="T-none-1", model_id="m1", grade="A"),
        EvalRow(ref="T-none-2", model_id="m2", grade="B"),
    ]
    controls: list[ControlRow] = []
    graded = grade_refs(live, control_rows=controls, require_control_panel=True)
    summary: GradingSummary = summarize(live, graded, control_rows=controls)

    assert summary.total_rows == 2
    assert summary.admitted == 2
    assert summary.excluded == 0, "no-control refs must NOT be counted excluded"
    assert summary.provisional == 2
    assert summary.clean == 0
    assert summary.refs_excluded == []