#!/usr/bin/env python3
"""FAIL-ON-REVERT proof for SW-PHASE0-GRADE-READ: the no-control→admit fallback
so live rows reach the ranker instead of being silently dropped.

The audit found ``grep -c strong-control fleet/model-scorecard.tsv`` = 0,
so ``_control_panel_for()`` returned ``split_ok=False`` for EVERY ref and
``_rows_for()`` dropped every live row → ``grade()`` returned ``None`` for
all models → ``assign.py`` always answered ``REFUSED — no eligible candidate``.

The fix ports the product-side ``_is_fallback_admit`` (commit 0947401): when
a ref has ZERO control rows at all (pass_n==0 AND fail_n==0), admit its live
rows with ``fallback_admit=True``.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_CAP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CAP))

from grades import ScorecardGradesProvider  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def _row(model: str, verdict: str, gate: str, wc: str = "money-path",
         ref: str = "LIVE-1", stage: str = "\t") -> str:
    ts = "2026-07-24"
    source = "live"
    tier = "med"
    score = "-"
    time_s = "10"
    cost = "0.01"
    corr = "0"
    note = "note"
    tokens_in = ""
    tokens_out = ""
    return "\t".join([ts, source, ref, wc, tier, model, verdict, gate,
                      score, time_s, cost, corr, note, tokens_in, tokens_out, stage])


def _write_fixture(rows: list[str]) -> Path:
    fd = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
    fd.write("\n".join(rows) + "\n")
    fd.close()
    return Path(fd.name)


def test_no_control_admits_live_rows():
    """FAIL-ON-REVERT: live rows on a ref with ZERO control rows (no
    ``strong-control``, no ``deepseek-v4-flash``) MUST be admitted via the
    no-control→admit fallback.  Dropping them (``split_ok=False``) means the
    gate is structurally unsatisfiable on the live lane."""
    rows = [
        _row("glm-5.2", "MERGE", "pass", ref="T-NOCTRL-1", wc="bugfix"),
        _row("glm-5.2", "MERGE", "pass", ref="T-NOCTRL-2"),
        _row("glm-5.2", "BLOCK", "fail", ref="T-NOCTRL-1", wc="bugfix"),
    ]
    tsv = _write_fixture(rows)
    gp = ScorecardGradesProvider(tsv)

    panel = gp._control_panel_for("T-NOCTRL-1")
    check("split_ok is True via no-control→admit fallback",
          panel["split_ok"] is True,
          f"split_ok={panel['split_ok']} pass_n={panel['control_pass_n']} fail_n={panel['control_fail_n']}")
    check("fallback_admit is True — not a clean control-panel pass",
          panel["fallback_admit"] is True,
          f"fallback_admit={panel['fallback_admit']}")

    live_rows = gp._rows_for("glm-5.2", "money-path", require_control_panel=True)
    check("live rows reach _rows_for (not dropped by the gate)",
          len(live_rows) == 1,
          f"got {len(live_rows)} rows for glm-5.2 money-path (expected 1, T-NOCTRL-2)")
    check("admitted row is the money-path row from T-NOCTRL-2",
          len(live_rows) == 1 and live_rows[0]["ref"] == "T-NOCTRL-2")


def test_grade_returns_non_none_with_no_controls():
    """The ranking's ``grade()`` returns a non-None ``Grade`` when live rows
    exist but the gate has no controls — the fix that unblocks assign.py."""
    rows = []
    for _ in range(4):
        rows.append(_row("minimax-m3-free", "MERGE", "pass", ref="T-GRADE-1"))
    rows.append(_row("minimax-m3-free", "BLOCK", "fail", ref="T-GRADE-1"))
    tsv = _write_fixture(rows)
    gp = ScorecardGradesProvider(tsv)

    g = gp.grade("minimax-m3-free", "money-path")
    check("grade() returns non-None with no controls seeded",
          g is not None,
          "got: None")
    if g is not None:
        check("grade has the correct row count", g.n == 5,
              f"expected n=5 (4 MERGE + 1 BLOCK), got n={g.n}")


def test_non_vacuous_empty_scorecard_returns_none():
    """NON-VACUOUS: a completely empty scorecard MUST return ``None`` — the
    gate must NOT silently pass on an empty ledger (a silent pass would be
    structurally indistinguishable from "the fallback worked")."""
    tsv = _write_fixture([])
    gp = ScorecardGradesProvider(tsv)

    g = gp.grade("glm-5.2", "money-path")
    check("empty scorecard -> grade() returns None (non-vacuous)",
          g is None,
          f"unexpected grade: {g}")


def test_fallback_does_not_weaken_partial_controls():
    """Integrity: a ref with partial control rows (1–2, below the ≥3
    threshold) but NOT zero MUST still be excluded.  The fallback admits
    ONLY the zero-control case."""
    rows = []
    for _ in range(2):
        rows.append(_row("strong-control", "MERGE", "pass", ref="T-PARTIAL"))
    rows.append(_row("glm-5.2", "MERGE", "pass", ref="T-PARTIAL"))
    tsv = _write_fixture(rows)
    gp = ScorecardGradesProvider(tsv)

    panel = gp._control_panel_for("T-PARTIAL")
    check("partial controls (2 strong-control, <3): split_ok is False",
          panel["split_ok"] is False,
          f"split_ok={panel['split_ok']} pass_n={panel['control_pass_n']}")
    check("partial controls: fallback_admit is False (not zero-control)",
          panel["fallback_admit"] is False,
          f"fallback_admit={panel['fallback_admit']}")

    live_rows = gp._rows_for("glm-5.2", None, require_control_panel=True)
    check("partial controls: live rows are STILL excluded",
          len(live_rows) == 0,
          f"got {len(live_rows)} rows — partial controls should exclude")


def test_gate_disabled_admits_without_fallback():
    """When ``require_control_panel=False``, rows are admitted cleanly without
    the fallback flag — the gate is disabled, not just relaxed."""
    rows = [_row("glm-5.2", "MERGE", "pass", ref="T-OFF")]
    tsv = _write_fixture(rows)
    gp = ScorecardGradesProvider(tsv)

    live_rows = gp._rows_for("glm-5.2", None, require_control_panel=False)
    check("gate disabled: row is admitted",
          len(live_rows) == 1,
          f"got {len(live_rows)} rows (should be 1)")
    check("gate disabled: no fallback flag needed",
          len(live_rows) == 1 and live_rows[0]["ref"] == "T-OFF")


def main() -> int:
    test_no_control_admits_live_rows()
    test_grade_returns_non_none_with_no_controls()
    test_non_vacuous_empty_scorecard_returns_none()
    test_fallback_does_not_weaken_partial_controls()
    test_gate_disabled_admits_without_fallback()
    print("-" * 60)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
