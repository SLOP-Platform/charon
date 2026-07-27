repo: charon
tier: frontier
difficulty: 4
work_class: tests
priority: 0
branch: feat/dogfood-gate
depends_on:
owns: tests/e2e/test_dogfood_gate.py, src/charon/cli.py
serial_justified: |
  ONE gate and its registration. A gate file that exists but is never invoked is the exact defect this
  ticket exists to prevent, so the assertion and its wiring cannot be split.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Own worktree.
source: |
  Roadmap R44, unbuilt since Wave 3. Escalated to P0 by operator 2026-07-26 (decision 33) after an
  audit showed a full day of merged work had NEVER been observed running.
note: |
  ## THE EVIDENCE THAT THIS IS URGENT (2026-07-26, verified)
  Five tickets merged that day. THREE carried done-contracts requiring proof on the LIVE gateway.
  NONE delivered it, and nothing noticed:
  * SW-IDENTITY-FOLD demanded live `/charon/status` before/after pool counts — never produced.
  * SECRET-HOTROTATE (a SECURITY fix) demanded proof a rotated key works without restart — the
    session honestly reported it could not reach the gateway, and it merged anyway.
  * The deployed gateway sat 15 commits behind master; the orphan pool the anchor "fixed"
    (`minimax-m2.5-fp4`) was STILL PRESENT live, with Together still stranded.
  A day of green unit tests and merged PRs, and the observable half of every contract went unpaid.
  The operator caught it by asking, not by any gate.

  ## WHAT THIS GATE MUST DO
  A merge-gate that asserts an OBSERVABLE EFFECT of a real request through the real selection path —
  not a mocked router returning a mocked pool. That mock is the theater this ticket exists to end.
  Minimum assertions:
  1. A real config + real request produces a routing decision with observable effects (which provider
     was selected, what was metered, what was recorded).
  2. The effect is asserted against the SAME surfaces an operator would inspect (`/charon/status`
     pools, the meter, the ledger) — so a passing gate means the operator's view is true.
  3. The gate FAILS when the effect is absent, not merely when code throws.

  ## ANTI-THEATER (this gate exists to prevent theater; it must not become it)
  * NON-VACUOUS: zero providers, zero models or an empty catalog is RED, never a silent pass.
  * WIRED: registered where the merge gate ACTUALLY runs. Prove it by pasting gate output showing
    this test executing — not a passing pytest run [[gates-must-actually-run]].
  * FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` everywhere.
  * It must be runnable WITHOUT the live 4-LOM gateway (CI has no access) while still asserting real
    effects — say honestly what it can and cannot cover in that mode, and do not claim live coverage
    it does not have.
accept: |
  DONE-CONTRACT:
  - The gate exists, is REGISTERED, and its execution is shown in real gate output.
  - RED-PROOF BY EXECUTION: break each asserted effect in turn -> gate goes RED naming that effect.
    Report ALL exit codes (green run plus one per deliberately-broken run).
  - Demonstrate it would have caught the 2026-07-26 miss: show it going RED against a build where the
    fp4 fold is reverted. This is the acceptance test for the gate itself.
  - NON-VACUOUS proven by execution against an empty catalog.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `pytest -q` GREEN.
## Dependencies & sequence
- **Depends on: NOTHING. Startable immediately.** `src/charon/cli.py` is owned by no other live ticket
  and `tests/e2e/` is new.
- **Blocks:** trustworthy landing of every future wave.
- **Wave:** gate lane, P0.
