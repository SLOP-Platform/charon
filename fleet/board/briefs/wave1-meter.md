# METER-MODEL-PROVIDER (Wave 1) — deepseek-v4-pro — cwd: a worktree of /home/stack/code/charon
GOAL: real per-(model, provider) COST METERING to replace est_cost fabrication (the block behind
DRAIN-THEN-PARK and cost-rank routing). Record the ACTUAL metered cost per request keyed by model+provider.

OWNS (only these): src/charon/proxy.py, src/charon/balance.py, tests/test_meter_model_provider.py
MONEY-PATH — RED-TEAM FIX #5 (REQUIRED, merge precondition): build a **metering-invariant canary** harness:
replay a recorded request stream through the new meter and ASSERT (a) cost-total delta == 0 vs the prior
path on a no-op stream, and (b) credential-shape invariance. This canary must be runnable by the reviewer.
FAIL-ON-REVERT TEST: assert a real $-metered cost is recorded (NOT the est_cost floor) — RED if reverted
to est_cost fabrication.

## CHARON-RUN CONTRACT (required)
End your run by writing a REVIEW PACKET (to REVIEW-PACKET.md in the worktree AND print it) containing:
- files + line ranges changed; root cause / approach
- the FAIL-ON-REVERT test: name + exact run command (must go RED if the change is reverted)
- self-run FULL GATE result: `PYTHONPATH=src python3 -m charon.cli gate` (paste pass/fail tail)
- residual risk + blast radius
- the commit SHA
LAST STEP (required): commit all changes on this branch and report the SHA.
Do NOT push or merge.
