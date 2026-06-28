Give the decision register + ADRs a mechanical backstop and fix the drift the 2026-06-27
fragility audit (THEME 9) found. Read docs/DECISIONS.md (the register + its consult-first
protocol, D011) and docs/adr/0008/0009/0010 FIRST.

BUILD:
1. tools/check_decisions.py (NEW, stdlib-only) — lint docs/DECISIONS.md and the ADRs, exit
   non-zero on any of:
   - a `Source` token in a register row that doesn't resolve to a real ADR/section;
   - non-monotonic or duplicate decision IDs (D001, D002, ... — flag gaps/dupes/out-of-order;
     D015 is currently inserted out of order — surface it);
   - a Status value off the allowed enum (`Settled` | `Open` | `Superseded→Dxxx`); D015's
     "Open (deferred)" is off-enum — normalize the enum or the row;
   - a register row whose Status is "Settled" while its source ADR is still "Proposed"
     (register-Status must be <= ADR-Status);
   - dangling ADR cross-refs (e.g. D013 cites ADR-0010 sandbox text that doesn't exist;
     D015 cites only an ambiguous "DTC 2026-06-26").
   Provide a `--check` mode (CI) and a default human-readable report mode.
2. Reconcile the live drift the lint will flag:
   - Flip ADR-0008/0009/0010 lifecycle status Proposed -> Accepted (engine code shipped under
     them; follow the ADR-0006 "Accepted" precedent).
   - Fix the dangling D013/D015 source refs to point at real text.
   - Resolve the D007 vs ADR-0010 D4 contradiction on ruff (always-on vs change-triggered) —
     pick one, cite it, note the supersession in the register if needed.
   - Put D015 in monotonic order / normalize its Status to the enum.
3. tools/check_boundary.py — fix ONLY the stale comment (~L87,109) that claims the engine
   scan is a no-op "while engine/ does not exist"; the engine modules now exist and the code
   is correct — update the comment to match. Do not change behavior.

Tests: add coverage for check_decisions.py (proven-red): a planted bad Source / non-monotonic
ID / off-enum Status / register-ahead-of-ADR each make `--check` exit non-zero; a clean
register passes. (Put tests in tests/test_check_decisions.py — add it to this ticket's owns
in board/FB6.md if needed, or inline doctest-style within the tool if you cannot add a test
file; do not write outside your owns.)

CONSTRAINTS: own ONLY the files in board/FB6.md `owns:`. Stdlib-only. Gate green every commit
(pytest, ruff, mypy src tests, check_boundary, check_version). Write your review note as
docs/review-log/FB6.md. Conventional commits. Open a DRAFT PR base=master; do NOT merge.
