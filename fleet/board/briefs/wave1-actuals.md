# ACTUALS-LEDGER (Wave 1 scaffold) — deepseek-v4-flash — cwd: a worktree of /home/stack/code/charon
GOAL: scaffold the real-outcomes ranker. Append ONE row per headless sub-session, keyed by (model,
work_class), from DETERMINISTIC byproducts: charon-run result, packet-parses, fail-on-revert+gate pass/fail,
failover hops, tokens/wall-clock.

OWNS (only these): src/charon/capability/actuals.py, src/charon/capability/scorecard.py, tests/test_actuals_ledger.py
D2: store manager accept/reject as a SEPARATE, low-weight column (tracked, not dominant).
RED-TEAM FIX #2 (freeze-ring reader — REQUIRED): the reader returns the LATEST FROZEN scorecard artifact
with a **last-known-good fallback** if the latest is missing/corrupt. The product must NOT import the rig
grader (fleet/benchmark). 
FAIL-ON-REVERT TEST: corrupt the latest artifact -> reader returns last-known-good (test RED if fallback removed).

## CHARON-RUN CONTRACT (required)
End your run by writing a REVIEW PACKET (to REVIEW-PACKET.md in the worktree AND print it) containing:
- files + line ranges changed; root cause / approach
- the FAIL-ON-REVERT test: name + exact run command (must go RED if the change is reverted)
- self-run FULL GATE result: `PYTHONPATH=src python3 -m charon.cli gate` (paste pass/fail tail)
- residual risk + blast radius
- the commit SHA
LAST STEP (required): commit all changes on this branch and report the SHA.
Do NOT push or merge.
