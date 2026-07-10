# BENCH-OOB-GRADING #26 (Wave 1) — glm-5.2 — cwd: a worktree of /home/stack/charon-private (RIG repo)
GOAL: build the OUT-OF-BAND grader daemon **fleet/benchmark/grader-daemon.py** that grades REAL tasks
(reds-replay + real sub-session actuals) — NOT synthetic S0-S6 (synthetic ranker RETIRED). It runs as the
dedicated **bench-grader** unix user (substrate already created: user + /home/bench-grader/keys 0700 +
/var/lib/bench-grader/spool + ledger ownership).

RED-TEAM FIX #2 (artifact seam — REQUIRED): the grader WRITES **versioned, append-only scorecard artifacts**
scorecard.v{n}.json; it is NEVER imported by the product. Consumers read frozen artifacts only. Do not add
any product import of the grader.
Daemon flow: watch /var/lib/bench-grader/spool/req -> grade against keys in /home/bench-grader/keys ->
write result to spool/res + append the scored row to a new scorecard.v{n}.json.
OWNS: fleet/benchmark/grader-daemon.py, fleet/benchmark/graders/ (real-task graders), fleet/benchmark/RUN-BENCHMARK.md
FAIL-ON-REVERT TEST: the daemon writes scorecard.v{n}.json for a spooled req AND the graded agent's unix
user cannot read /home/bench-grader/keys (permission-denied) — RED if the isolation or versioning is removed.
NOTE: do NOT run step-5 systemd enable; the operator wires the service after this daemon lands.

## CHARON-RUN CONTRACT (required)
End your run by writing a REVIEW PACKET (to REVIEW-PACKET.md in the worktree AND print it) containing:
- files + line ranges changed; root cause / approach
- the FAIL-ON-REVERT test: name + exact run command (must go RED if the change is reverted)
- self-run FULL GATE result: `PYTHONPATH=src python3 -m charon.cli gate` (paste pass/fail tail)
- residual risk + blast radius
- the commit SHA
LAST STEP (required): commit all changes on this branch and report the SHA.
Do NOT push or merge.
