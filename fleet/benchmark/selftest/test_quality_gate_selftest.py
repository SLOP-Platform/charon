#!/usr/bin/env python3
"""test-quality-gate.py self-test (TEST-QUALITY-GATE-SPEC.md).

Proves, against FROZEN copies of REAL captured
fleet/state/dogfood-eval/results/*-SUMMARY.md files (selftest/fixtures/
test-quality-gate/ — verbatim copies, never the live results/ dir, so this test
can't flake when a new dogfood-eval batch lands mid-run — confirmed happening
live in this same session):

  1. TOOL-REPAIR-MUTATING's real candidate outcomes (7 graded rows across 4
     historical batches, 3 distinct non-RETRY models, all REVIEW-READY=100) are
     flagged NON-DISCRIMINATING (real-world confirmed) - the exact "D1 bugfix
     passed by all 5 candidates, zero signal" gap this gate exists to catch.
  2. PROVIDER-URL-HELPER's real candidate outcomes (5 distinct non-RETRY
     models, spread 100 vs 50) are flagged DISCRIMINATES - the one ticket this
     session already confirmed differentiates - and must NOT be mis-flagged.
  3. RETRY(...) rows are excluded from the score set entirely (never scored,
     never disqualifying) - a fail-on-revert guard: if a future edit folds
     RETRY rows back into scoring (the exact class of bug
     lib/dogfood-attribution.sh already fixed once for a different classifier),
     case 1's spread would flip nonzero and this assertion catches it.
  4. classify_red_proof() - the pure Step-1 decision table - fail-on-revert
     guard for all 4 (unmodified_pass, ref_result) combinations, independent of
     git/subprocess.
  5. parse_ticket() correctly extracts `accept:` from the two real board
     tickets (single-line style) - a parsing regression here would silently
     make Step 1 a no-op (empty test_cmd).
  6. Live confirmation (skipped gracefully if the product repo / origin/master
     is unreachable): TOOL-REPAIR-MUTATING's accept: check, run UNMODIFIED in a
     fresh worktree off origin/master, actually PASSES today (rc=0) - manually
     confirmed this session - so end-to-end red_proof() must report
     verdict=TOO-EASY on the real ticket, not just on synthetic fixtures.

Usage: python3 selftest/test_quality_gate_selftest.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH_DIR = HERE.parent
FIXTURES = HERE / "fixtures" / "test-quality-gate"
BOARD_DIR = BENCH_DIR.parent / "board"

sys.path.insert(0, str(BENCH_DIR))
import importlib.util

_spec = importlib.util.spec_from_file_location("test_quality_gate", BENCH_DIR / "test-quality-gate.py")
tqg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tqg)  # noqa

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    status = "ok" if cond else "FAIL"
    print(f"{status}: {msg}")
    if not cond:
        failures.append(msg)


# ---------------------------------------------------------------------------
# 1 + 2 + 3: discrimination score against frozen real fixtures
# ---------------------------------------------------------------------------
scores, files, excluded = tqg.load_ticket_scores("TOOL-REPAIR-MUTATING", FIXTURES)
verdict, reason = tqg.discrimination_verdict(scores)
check(len(files) == 4, f"TOOL-REPAIR-MUTATING fixture: 4 summary files read (got {len(files)})")
check(scores == {"minimax-m2.7": 100.0, "glm-5.2": 100.0, "deepseek-v4-pro": 100.0},
      f"TOOL-REPAIR-MUTATING fixture: all-REVIEW-READY per-model scores (got {scores})")
check(verdict == "NON-DISCRIMINATING (real-world confirmed)",
      f"TOOL-REPAIR-MUTATING fixture: flagged NON-DISCRIMINATING (real-world confirmed) (got {verdict!r})")
check(len(excluded) == 8, f"TOOL-REPAIR-MUTATING fixture: 8 RETRY/unrecognized rows excluded (got {len(excluded)})")
check(all(v.startswith("RETRY") for _, _, v in excluded),
      "TOOL-REPAIR-MUTATING fixture: every excluded row's verdict actually starts with RETRY "
      "(fail-on-revert: proves the exclusion filter, not an accidental drop, produced this set)")

scores2, files2, excluded2 = tqg.load_ticket_scores("PROVIDER-URL-HELPER", FIXTURES)
verdict2, reason2 = tqg.discrimination_verdict(scores2)
check(len(files2) == 3, f"PROVIDER-URL-HELPER fixture: 3 summary files read (got {len(files2)})")
check(scores2 == {"deepseek-v4-pro": 100.0, "deepseek-v4-flash": 50.0, "glm-5.2": 50.0,
                   "kimi-k2.6": 50.0, "minimax-m2.7": 50.0},
      f"PROVIDER-URL-HELPER fixture: mixed REVIEW-READY/FIXES-NEEDED scores (got {scores2})")
check(verdict2 == "DISCRIMINATES", f"PROVIDER-URL-HELPER fixture: flagged DISCRIMINATES (got {verdict2!r})")

# fail-on-revert: if RETRY rows were (incorrectly) scored as FIXES-NEEDED-equivalent instead of
# excluded, TOOL-REPAIR-MUTATING's spread would go nonzero and hide the real gap.
_would_include_retry = tqg.score_for_verdict("RETRY(provider-symptom-not-model-fault)")
check(_would_include_retry is None, "score_for_verdict(RETRY(...)) is None (excluded), never a number")

# ---------------------------------------------------------------------------
# 4: classify_red_proof pure decision table
# ---------------------------------------------------------------------------
check(tqg.classify_red_proof(True, None) == "TOO-EASY", "classify_red_proof(pass-unmodified, *) -> TOO-EASY regardless of ref_result")
check(tqg.classify_red_proof(True, "pass") == "TOO-EASY", "classify_red_proof(pass-unmodified, ref=pass) -> still TOO-EASY (rule #3 wins)")
check(tqg.classify_red_proof(False, None) == "UNVERIFIED", "classify_red_proof(fail-unmodified, no ref) -> UNVERIFIED")
check(tqg.classify_red_proof(False, "pass") == "OK", "classify_red_proof(fail-unmodified, ref=pass) -> OK (healthy RED-proof)")
check(tqg.classify_red_proof(False, "fail") == "BUGGY-TEST", "classify_red_proof(fail-unmodified, ref=fail) -> BUGGY-TEST")
check(tqg.classify_red_proof(False, "did-not-apply") == "BUGGY-TEST", "classify_red_proof(fail-unmodified, ref=did-not-apply) -> BUGGY-TEST")

# ---------------------------------------------------------------------------
# 5: parse_ticket against the two real board tickets
# ---------------------------------------------------------------------------
trm = tqg.parse_ticket(BOARD_DIR / "TOOL-REPAIR-MUTATING.md")
check(trm.get("accept") == "PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q",
      f"parse_ticket(TOOL-REPAIR-MUTATING.md)['accept'] matches exactly (got {trm.get('accept')!r})")

puh = tqg.parse_ticket(BOARD_DIR / "PROVIDER-URL-HELPER.md")
check(puh.get("accept") == "PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_config.py tests/test_discover.py -q",
      f"parse_ticket(PROVIDER-URL-HELPER.md)['accept'] matches exactly (got {puh.get('accept')!r})")

# ---------------------------------------------------------------------------
# 6: live end-to-end confirmation against the real product repo (skips gracefully
# if the repo/origin isn't reachable in this environment — never a hard failure
# for an environment reason, matches dogfood-eval.sh's own provider-symptom stance)
# ---------------------------------------------------------------------------
PRODUCT_REPO = tqg.DEFAULT_PRODUCT_REPO
live_skipped = False
if not (PRODUCT_REPO / ".git").exists():
    live_skipped = True
    print(f"SKIP (live): product repo not found at {PRODUCT_REPO}")
else:
    fetch = subprocess.run(["git", "-C", str(PRODUCT_REPO), "fetch", "origin", "--quiet"],
                            capture_output=True, timeout=60)
    if fetch.returncode != 0:
        live_skipped = True
        print("SKIP (live): could not fetch origin — no network in this environment")
    else:
        red = tqg.red_proof(
            "TOOL-REPAIR-MUTATING", trm["accept"],
            product_repo=PRODUCT_REPO, worktree_parent=tqg.DEFAULT_WORKTREE_PARENT,
            base_ref="origin/master", ref_diff=None, keep_worktree=False, timeout_s=120,
        )
        check(red["unmodified_pass"] is True,
              f"LIVE: TOOL-REPAIR-MUTATING's accept: check passes on unmodified origin/master today (rc={red['unmodified_rc']})")
        check(red["verdict"] == "TOO-EASY",
              f"LIVE: end-to-end red_proof() flags the real ticket TOO-EASY (got {red['verdict']!r})")

print()
if failures:
    print(f"SELF-TEST FAILURES ({len(failures)}):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
suffix = " (live check skipped)" if live_skipped else ""
print(f"ALL test-quality-gate SELF-TESTS PASS{suffix}: TOOL-REPAIR-MUTATING correctly flagged "
      f"NON-DISCRIMINATING, PROVIDER-URL-HELPER correctly passes as DISCRIMINATES, RETRY rows "
      f"never scored, RED-proof decision table holds.")
