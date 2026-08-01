repo: charon
tier: economy
difficulty: 1
work_class: ci-infra
priority: 2
branch: feat/pylint-unused-args
depends_on:
owns: tests/test_pylint_unused_args.py
substrate: pylint — adopt — the ONLY tool of five tested (check_inert_code.py, ruff, vulture, deadcode, pylint) that emits an unused-ARGUMENT signal (W0613). EVAL-REGISTRY row + full matrix landed 2026-08-01 in fleet/state/DEADCODE-TOOL-REDERIVE.md. ruff F841 is variable-only and does not cover arguments; vulture is PARTIAL at 100% confidence only; deadcode classifies args as DC01 with no argument-specific signal.
serial_justified: |
  One check, one narrow rule, one config entry. Nothing to split.
source: |
  DEADCODE-TOOL-REDERIVE lane (executed 5 tools x 4 corpora, merged d90381d). Operator approved
  2026-08-01 as rec #1.
note: |
  ## THE MEASURED GAP
  pylint `W0613` (unused-argument) found **46 instances in the product tree and 3 in ksf** — a
  signal NO other tool in our stack produces. Everything else we run (ruff, check_inert_code.py)
  is structurally blind to it.

  ## SCOPE — NARROW ON PURPOSE
  Enable **W0613 only** (plus W0611/W0612 only if they add findings ruff does not already
  produce — the matrix says ruff F401/F841 already cover those, so most likely NOT).
  Do NOT enable pylint wholesale: it overlaps ruff heavily and a full pylint run would drown the
  signal in noise we already have covered. The value here is one rule nothing else provides.

  Treat the existing 46 findings as the starting population: fix or explicitly waive each with a
  reason. A blanket disable comment is a waive without a reason and is not acceptable — an unused
  argument is often a real signal (a parameter threaded but never read = a wiring bug, which is
  exactly the class this rig keeps hitting).

  ## RATCHET, NOT BASELINE
  If a baseline is needed to land, it must SHRINK-ONLY and carry a count that CI enforces
  downward. A frozen baseline that reports green over 46 live findings is the fake-green class
  [[best-not-defensible]]. Prefer fixing them outright — 46 is a tractable number.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. A newly-introduced unused argument makes the check RED. Revert the wire -> RED.
    b. The check RUNS in CI (registered in the product's workflow / gate), not merely configured.
       Prove it fires; a configured-but-unrun linter is the inert class.
    c. Findings count is reported and is <= the recorded baseline; increasing it fails.
    d. ANTI-OVER-BLOCK: a function using all its arguments passes untouched; ruff's existing
       F401/F841 behaviour is unchanged.
  Report before/after counts (baseline: 46 product, 3 ksf).

D&S — Deps & Sequence:
  - Depends on: nothing. Product gate must be green (AMBIENT-COUPLED-TESTS) before it can merge.
