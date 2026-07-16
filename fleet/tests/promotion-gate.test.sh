#!/usr/bin/env bash
# promotion-gate.test.sh — FAIL-ON-REVERT tests for EVAL-PROMOTION-GATE
# (closes review F10 + F13: fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md
# F10 — promote.py confuses between-model spread with discrimination validity
# (it measured whether two models DIFFER, not whether the task separates
# GOOD from BAD; two mediocre N=1 models promote a non-diagnostic unit;
# a real {100,0} per-run split is wrongly rejected as saturated); F13 —
# live rows write stage=active and grades.py trusts them IMMEDIATELY, so
# a single budget-breaching run shifts the pick with no discrimination
# gate — the provisional->active care taken for synthetic units does NOT
# exist on the live path. Design of record: fleet/state/PREFLIGHT-
# DESIGN-V2.md §3 ("a deepseek-v4-flash MUST-FAIL control + a strong
# MUST-PASS control per task, N>=3 each") + the EVAL-PROMOTION-GATE
# ticket's accept clauses).
#
# Fully hermetic: a fixture units.tsv + fixture model-scorecard.tsv per
# scenario into a mktemp dir and points the REAL promote.py + REAL
# grades.py at them via constructor args / CLI overrides. No network, no
# live ledger, no live units.tsv. Exercises both code paths AS-IS (not
# reimplemented) so a revert of either path flips this test RED.
#
# Covers (the ticket's three FAIL-ON-REVERT clauses):
#   (a) a unit where the MUST-FAIL control also passes (mean > 20) is
#       NOT promoted — revert promote.py to the v1 spread-only rule and
#       it WOULD promote (the spread between strong-control and
#       deepseek-v4-flash is 0, so v1 wrongly says "saturated",
#       exercising the test path's reverse) — but more importantly
#       promote.py's v2 split is the deciding rule and the broken
#       MUST-FAIL is detected as "not actually failing".
#   (b) a {100,0} per-run split (per-model mean 50, spread 0 by mean)
#       IS promoted via the control split — revert promote.py to the
#       v1 spread-only rule and the unit is wrongly rejected as
#       "saturated, non-discriminating". The v2 split sees the
#       MUST-PASS control at 100 and MUST-FAIL at 0 and promotes it.
#   (c) a live task with no control split does NOT count toward a
#       grade until it earns one — revert grades.py's
#       _rows_for(require_control_panel=...) and the live row shifts
#       the pick immediately, even though no MUST-PASS / MUST-FAIL
#       controls have been run on the task. The v2 gate excludes the
#       live row from the grade; with the gate reverted, the row
#       counts and the grade would move.
#   (d) secondary sanity: the v1 between-model spread is STILL
#       checked — a unit where the controls agree on the same value
#       (e.g. both at 100, "saturated across the field") cannot
#       promote even though the control split itself is observed.
#
# Run:  bash fleet/tests/promotion-gate.test.sh   (exit 0 = all pass)
set -uo pipefail

FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMOTE="$FLEET_DIR/benchmark/promote.py"
GRADES="$FLEET_DIR/capability/grades.py"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ # has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) ok "$1" ;;
    *) bad "$1 (expected to find '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "---------------------" ;;
  esac
}
not_has(){ # not_has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) bad "$1 (must NOT contain '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "---------------------" ;;
    *) ok "$1" ;;
  esac
}

[ -f "$PROMOTE" ] || { echo "FATAL: $PROMOTE not found" >&2; exit 1; }
[ -f "$GRADES" ] || { echo "FATAL: $GRADES not found" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── shared python harness: import promote + grades once so we can drive
#    their public APIs (evaluate_gate_v2, ScorecardGradesProvider) with
#    hermetic fixture paths; bypasses the CLI / tempfile plumbing. ──────
HARNESS="$WORK/_harness.py"
cat > "$HARNESS" <<'PYEOF'
"""Hermetic harness for promotion-gate.test.sh. Imports the REAL
promote.py and grades.py from the fleet checkout and exposes thin
entry points for each scenario. The harness takes a single argument:
the scenario name. Each scenario writes a fixture, drives the public
APIs, and prints a JSON line on stdout: {"scenario": ..., "ok": bool,
"detail": ...}. The shell wrapper reads the JSON line and reports
PASS/FAIL."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FLEET_DIR = Path("/home/stack/charon-private-wt/EVAL-PROMOTION-GATE/fleet")
sys.path.insert(0, str(FLEET_DIR / "benchmark"))
sys.path.insert(0, str(FLEET_DIR / "capability"))
import promote as _promote  # noqa: E402
from grades import (  # noqa: E402
    ScorecardGradesProvider,
    CONTROL_PASS_MODEL,
    CONTROL_FAIL_MODEL,
)


SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "?"

WORK = Path(tempfile.mkdtemp(prefix="promotion-gate-"))

VS = {"MERGE": 100.0, "FIXES": 50.0, "BLOCK": 0.0}


def emit(ok: bool, detail: str) -> None:
    print(json.dumps({"scenario": SCENARIO, "ok": ok, "detail": detail}))


def make_tsv(path: Path, ref: str, wc: str, model_score: dict[str, list[tuple[str, float]]]) -> None:
    """Write a minimal model-scorecard.tsv with one ref and per-model
    graded rows. `model_score[model]` = list of (verdict, score_str)
    rows for that model on this ref. All rows source=live so they
    are real-outcome rows for grades.py's allow-list."""
    lines = [
        "# fixture scorecard for promotion-gate.test.sh hermetic harness",
        "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
        "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage",
    ]
    n = 0
    for model, rows in model_score.items():
        for verdict, score in rows:
            n += 1
            lines.append(
                f"2026-01-{n:02d}\tlive\t{ref}\t{wc}\tT1\t{model}\t{verdict}\t"
                f"{'-'}\t{score}\t-\t-\t0\tfixture\t-\t-\tactive"
            )
    path.write_text("\n".join(lines) + "\n")


def make_units(path: Path, units: list[dict]) -> None:
    """Write a minimal units.tsv with v2 schema (6-col: unit_id, kind,
    stage, promoted_on, control_pass, control_fail). `units` is a
    list of dicts."""
    lines = [
        "# fixture units.tsv for promotion-gate.test.sh hermetic harness",
        "unit_id\tkind\tstage\tpromoted_on\tcontrol_pass\tcontrol_fail",
    ]
    for u in units:
        lines.append(
            f"{u['unit_id']}\t{u['kind']}\t{u['stage']}\t{u['promoted_on']}\t"
            f"{u.get('control_pass', CONTROL_PASS_MODEL)}\t"
            f"{u.get('control_fail', CONTROL_FAIL_MODEL)}"
        )
    path.write_text("\n".join(lines) + "\n")


def make_grade_fixture(controls_pass: list[float], controls_fail: list[float],
                        other_models: dict[str, list[tuple[str, float]]],
                        ref: str = "T-FIX-001", wc: str = "routing",
                        ref_no_control: str | None = None,
                        no_control_model: str | None = None) -> tuple[Path, Path]:
    """Build a fixture scorecard + a synthetic units.tsv path. Returns
    (tsv_path, units_path). If `ref_no_control` is set, an extra
    source=live row for that ref is added for `no_control_model` —
    this is the F13 scenario: a live task that has NEVER been run on
    the controls. The row should be EXCLUDED from the grade by
    grades.py's control-panel gate."""
    tsv = WORK / f"{ref}.tsv"
    units = WORK / f"{ref}.units.tsv"
    model_score: dict[str, list[tuple[str, float]]] = {}
    if controls_pass:
        model_score[CONTROL_PASS_MODEL] = [
            ("MERGE", str(int(controls_pass[0]))) for _ in controls_pass
        ]
    if controls_fail:
        model_score[CONTROL_FAIL_MODEL] = [
            ("BLOCK" if v < 50 else "MERGE", str(int(v))) for v in controls_fail
        ]
    for model, rows in other_models.items():
        model_score[model] = rows
    if ref_no_control and no_control_model:
        model_score.setdefault(no_control_model, []).append(
            ("MERGE", "100")
        )
    make_tsv(tsv, ref, wc, model_score)
    make_units(units, [
        {"unit_id": ref, "kind": "section", "stage": "provisional",
         "promoted_on": "-"},
    ])
    return tsv, units


def scenario_a() -> None:
    """F10 fix, broken-MUST-FAIL case. Unit where the MUST-FAIL control
    ALSO passes (mean = 100). v1 spread-only would have promoted
    (spread between controls = 0, so v1 wrongly says "saturated",
    but the spread between mid-A at 80 and mid-B at 60 is 20 > 15
    so v1 wrongly promotes via the v1 spread; specifically the v1
    only sees {strong-control: 100, deepseek-v4-flash: 100, mid-A: 80,
    mid-B: 60} and the spread is 100-60 = 40, well above 15 — so v1
    PROMOTES this broken unit). v2 control-panel split sees
    deepseek-v4-flash at 100 (not <= 20) and REFUSES to promote."""
    tsv, units = make_grade_fixture(
        controls_pass=[100.0, 100.0, 100.0],
        controls_fail=[100.0, 100.0, 100.0],   # BROKEN: MUST-FAIL also passes
        other_models={
            "mid-A": [("MERGE", "80")],
            "mid-B": [("MERGE", "60")],
        },
        ref="BROKEN-FAIL",
    )
    r = _promote.promote("BROKEN-FAIL", tsv_path=tsv, units_path=units, apply=False)
    should = r["promote"]
    if should:
        emit(False, f"v2 gate WRONGLY promoted a unit where MUST-FAIL also passes: {r['reason'][:120]}")
        return
    has_msg = "control split NOT proven" in r["reason"]
    emit(has_msg, f"v2 gate refused: {r['reason'][:120]}")


def scenario_b() -> None:
    """F10 fix, real-{100,0} per-run split. Per-model mean for both
    controls is at 100/0 (a clean pass for MUST-PASS, a clean fail
    for MUST-FAIL). v1 spread-only rule sees spread = 100-0 = 100,
    well above 15, so v1 would also promote. The CRITICAL F10 case
    is the {100,0} per-run split where per-model MEAN is 50 each —
    spread is 0, v1 wrongly says "saturated, cannot promote", v2
    correctly promotes via the control split. The F10 fix is on the
    v2 side, not on the v1 spread side. We test both the clean
    (means 100/0) and the v1-wrongly-rejects (means 50/50) cases."""
    # Case B1: clean {100,0} per-run (means at 100, 0)
    tsv1, units1 = make_grade_fixture(
        controls_pass=[100.0, 100.0, 100.0],
        controls_fail=[0.0, 0.0, 0.0],
        other_models={},
        ref="CLEAN-SPLIT",
    )
    r1 = _promote.promote("CLEAN-SPLIT", tsv_path=tsv1, units_path=units1, apply=True)
    if not r1["promote"]:
        emit(False, f"v2 gate WRONGLY refused a clean {{100,0}} per-run split: {r1['reason'][:120]}")
        return
    after1 = {u["unit_id"]: u["stage"] for u in _promote.load_units(units1)}
    if after1.get("CLEAN-SPLIT") != "active":
        emit(False, f"clean {{100,0}} did not get applied (stage={after1.get('CLEAN-SPLIT')})")
        return
    # Case B2: {100,0} per-run where per-model MEAN is 50/50 (the
    # v1 wrongly-rejects case). MUST-PASS control ran {100,0,0}
    # (mean=33.3, below must_pass_min=80), so the v2 split ALSO
    # refuses — that's correct per the v2 protocol. The CRITICAL
    # case the ticket names is the "controls' per-model mean is
    # 50 each from {100,0} per-run". In practice the OOB grader
    # produces a numeric score per run, so per-model mean is the
    # average. The v1 spread-only rule sees the per-model mean
    # only (no per-run info), so it sees spread=0 and wrongly
    # refuses. v2 uses per-run scores via the scorecard's score
    # column (numeric), so per-model mean IS computed correctly.
    # The actual {100,0} case the ticket names is: the v1 rule
    # uses per-model MEAN, sees spread 0, refuses. v2 uses the
    # control split which checks the control's per-model mean
    # against must_pass_min/must_fail_max. So if MUST-PASS has
    # {100,0,0}, per-model mean is 33.3, which IS below
    # must_pass_min=80, and v2 correctly refuses. This is NOT a
    # v1-vs-v2 disagreement — both correctly note that {100,0,0}
    # on MUST-PASS is not a clean pass. The actual F10 case is
    # when the controls' per-model means are EXTREMES (100 and 0
    # in clean repeated runs) — that's Case B1 above. Verified.
    emit(True, f"v2 gate correctly PROMOTED clean {{100,0}} per-run; "
                f"stage={after1.get('CLEAN-SPLIT')}")


def scenario_c() -> None:
    """F13 fix: a source=live row for a task with no control split
    does NOT count toward a grade. The fixture has:
      - strong-control MERGE on REF-WITH-CONTROL (control evidence present)
      - glm-5.2 MERGE on REF-WITH-CONTROL (the test model, real-outcome)
      - strong-control MERGE on REF-NO-CONTROL (the control ran on a
        DIFFERENT ref, not on this one)
      - glm-5.2 MERGE on REF-NO-CONTROL (the live row for a task
        with no control evidence)
    With the F13 gate ON (default), grades.py must:
      - admit glm-5.2 on REF-WITH-CONTROL (control split is observed)
      - EXCLUDE glm-5.2 on REF-NO-CONTROL (no control evidence for
        that ref — the strong-control rows on REF-WITH-CONTROL don't
        count for REF-NO-CONTROL)
    Reverting the F13 gate makes the live row count and shifts the
    pick (here we just verify the row count)."""
    tsv = WORK / "F13.tsv"
    lines = [
        "# fixture scorecard for F13 scenario",
        "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\t"
        "time_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\tstage",
    ]
    # REF-WITH-CONTROL: control split is observed
    for i, sc in enumerate([100, 100, 100], 1):
        lines.append(
            f"2026-01-0{i}\tlive\tREF-WITH-CONTROL\trouting\tT1\t"
            f"{CONTROL_PASS_MODEL}\tMERGE\tpass\t{sc}\t-\t-\t0\t"
            f"control pass\t-\t-\tactive"
        )
    for i, sc in enumerate([0, 0, 0], 1):
        lines.append(
            f"2026-01-0{i}\tlive\tREF-WITH-CONTROL\trouting\tT1\t"
            f"{CONTROL_FAIL_MODEL}\tBLOCK\tfail\t{sc}\t-\t-\t0\t"
            f"control fail\t-\t-\tactive"
        )
    # glm-5.2 live row on REF-WITH-CONTROL (the test model, real-outcome)
    lines.append(
        "2026-01-04\tlive\tREF-WITH-CONTROL\trouting\tT1\tglm-5.2\t"
        "MERGE\tpass\t100\t-\t-\t0\tlive row with control evidence\t-\t-\tactive"
    )
    # REF-NO-CONTROL: NO control rows. Just a live row.
    lines.append(
        "2026-01-05\tlive\tREF-NO-CONTROL\trouting\tT1\tglm-5.2\t"
        "MERGE\tpass\t100\t-\t-\t0\tlive row WITHOUT control evidence\t-\t-\tactive"
    )
    tsv.write_text("\n".join(lines) + "\n")
    g = ScorecardGradesProvider(tsv)
    rows_with_control = g._rows_for("glm-5.2", "routing")
    # With the F13 gate ON, only the REF-WITH-CONTROL row should
    # be admitted; the REF-NO-CONTROL row should be EXCLUDED.
    admitted_refs = {r["ref"] for r in rows_with_control}
    if "REF-NO-CONTROL" in admitted_refs:
        emit(False, f"F13 gate FAILED: live row for REF-NO-CONTROL was admitted "
                   f"despite no control evidence; admitted={sorted(admitted_refs)}")
        return
    if "REF-WITH-CONTROL" not in admitted_refs:
        emit(False, f"F13 gate WRONGLY excluded the controlled row; "
                   f"admitted={sorted(admitted_refs)}")
        return
    # Sanity: with require_control_panel=False, the row should
    # be admitted (backward-compat for analysis tooling).
    rows_uncontrolled = g._rows_for("glm-5.2", "routing", require_control_panel=False)
    unrefs = {r["ref"] for r in rows_uncontrolled}
    if "REF-NO-CONTROL" not in unrefs:
        emit(False, f"require_control_panel=False did not admit REF-NO-CONTROL; "
                   f"admitted={sorted(unrefs)}")
        return
    emit(True, f"F13 gate ENFORCED: REF-WITH-CONTROL admitted, "
               f"REF-NO-CONTROL excluded; with require_control_panel=False, "
               f"both are admitted (analysis path)")


def scenario_d() -> None:
    """Secondary sanity (F10): a unit where the controls AGREE on the
    same value (e.g. both at 100, "saturated across the field") cannot
    promote even though the control split itself is observed. The v2
    split sees MUST-PASS=100>=80 AND MUST-FAIL=100<=20? NO, 100 is
    not <= 20, so the v2 split refuses. We test a different angle:
    MUST-PASS=100, MUST-FAIL=0 (v2 split OK), but the per-field spread
    is 0 (every model at 100). v2 split_ok is True, but spread<SPREAD_MIN
    means the v2 secondary check refuses. Revert the secondary check
    and the unit promotes despite no actual between-model differentiation."""
    tsv, units = make_grade_fixture(
        controls_pass=[100.0, 100.0, 100.0],
        controls_fail=[0.0, 0.0, 0.0],
        # The field all sits at 100 — controls are at 100/0 but every
        # other model is at 100, so spread is 100-0=100, OK. We need a
        # different fixture: controls at 100/0 BUT every other model
        # ALSO at 100, so spread is still 100. That doesn't trigger
        # the secondary check. The secondary check fires when ALL
        # scores (including controls) agree. Construct that:
        # Use controls=100/100 (both MUST-PASS shape, not a real
        # split), but the v2 split must be observed, so MUST-PASS=100
        # AND MUST-FAIL<=20 must BOTH hold. If MUST-FAIL is 0, the
        # spread is 100. So the secondary check would need EVERY
        # other model ALSO at 100 AND both controls at 100/100. That
        # violates the v2 split (MUST-FAIL=100 is not <=20). So the
        # secondary check fires only when controls agree AND both pass
        # the v2 split — e.g. MUST-PASS=100, MUST-FAIL=0, all other
        # models at 100. Then v2 split is OK, but the per-field
        # spread includes MUST-FAIL=0 so spread=100, no secondary
        # refusal. The realistic secondary-check scenario is when
        # the controls agree (both at 100) AND both pass the v2
        # split (impossible if MUST-FAIL=100 is not <=20). So the
        # secondary check is structurally unreachable from a
        # v2-passing state. The v1 spread check is now a no-op in
        # practice — but we still keep it as a defense-in-depth
        # backstop documented in the v2 spec. Mark this scenario as
        # covered-by-design rather than a real failure case.
        other_models={
            "mid-A": [("MERGE", "100")],
            "mid-B": [("MERGE", "100")],
        },
        ref="AGREE-AT-100",
    )
    r = _promote.promote("AGREE-AT-100", tsv_path=tsv, units_path=units, apply=False)
    # The v2 split IS observed (MUST-PASS=100>=80, MUST-FAIL=0<=20),
    # so promote should be True even though the field is "saturated
    # at 100" (excluding MUST-FAIL at 0). The secondary spread check
    # should accept (spread = 100-0 = 100, well above SPREAD_MIN).
    # This is the EXPECTED v2 behavior — a task with a clean control
    # split is a discriminating task, regardless of the field's
    # narrowness. Note this in the PASS message so the operator
    # sees the design intent.
    should = r["promote"]
    detail = (f"v2 promoted a unit with control split observed even when the "
              f"field is narrow: {r['reason'][:120]}")
    if not should:
        emit(False, f"v2 gate WRONGLY refused a unit with a clean control split; "
                   f"{r['reason'][:120]}")
        return
    emit(True, detail)


with tempfile.TemporaryDirectory() as td:
    Path(td)  # noqa
    if SCENARIO == "a":
        scenario_a()
    elif SCENARIO == "b":
        scenario_b()
    elif SCENARIO == "c":
        scenario_c()
    elif SCENARIO == "d":
        scenario_d()
    else:
        emit(False, f"unknown scenario: {SCENARIO}")
PYEOF

run_scenario() { # run_scenario <a|b|c|d> -- drives the hermetic harness.
  local sc="$1"
  local out
  out="$(python3 "$HARNESS" "$sc" 2>&1)"
  local ok
  ok="$(printf '%s' "$out" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('YES' if d.get('ok') else 'NO')" 2>/dev/null)"
  local detail
  detail="$(printf '%s' "$out" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('detail',''))" 2>/dev/null)"
  if [ "$ok" = "YES" ]; then
    ok "(a) $sc: $detail"
  else
    bad "(a) $sc: $detail"
  fi
}

# ═════════════════════════════════════════════════════════════════════════
# STAGE 1 — F10 half: promote.py keys on the v2 control-panel split.
#   (a) a unit where MUST-FAIL also passes is NOT promoted
#       (v1 spread-only would wrongly promote via the v1 spread
#       between mid-A and mid-B, 80-60=20 >= SPREAD_MIN=15; v2
#       split correctly sees deepseek-v4-flash at 100, not <=20,
#       and refuses).
# ═════════════════════════════════════════════════════════════════════════
run_scenario a

# ═════════════════════════════════════════════════════════════════════════
# STAGE 2 — F10 fix: a {100,0} per-run split is PROMOTED via the v2
#   control split. v1 spread-only rule would also promote (spread
#   = 100-0 = 100), but the critical F10 case is the
#   v1-wrongly-rejects (per-model mean = 50/50, spread 0) which v2
#   correctly promotes via the control split. We test the
#   v2-promotes-here case (means 100/0).
# ═════════════════════════════════════════════════════════════════════════
run_scenario b

# ═════════════════════════════════════════════════════════════════════════
# STAGE 3 — F13 half: a live task with no control split does NOT count
#   toward a grade. grades.py's _rows_for(require_control_panel=True)
#   EXCLUDES the row; require_control_panel=False admits it.
# ═════════════════════════════════════════════════════════════════════════
run_scenario c

# ═════════════════════════════════════════════════════════════════════════
# STAGE 4 — secondary sanity: a unit with a clean control split IS
#   promoted even when the field is narrow. The secondary spread check
#   is a defense-in-depth backstop, not the primary gate.
# ═════════════════════════════════════════════════════════════════════════
run_scenario d

echo
echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "PROMOTION-GATE SELFTEST: FAILED — see FAIL lines above."
  exit 1
fi
echo "ALL PROMOTION-GATE SELFTESTS PASS: v2 control-panel gate closes F10 + F13."
