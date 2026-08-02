repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: fix/ledger-no-evidence-no-verdict
owns: fleet/charon-run.sh, fleet/tests/ledger-no-evidence-no-verdict.test.sh
serial_justified: One predicate in one function plus its fail-on-revert test; landing the fix without the proof is what let this rot.
substrate: N/A
substrate-novel: |
  This is a policy predicate over OUR OWN run-classification taxonomy (infra-fault vs
  model-attributable) feeding OUR OWN grading ledger. No external library models "did the model
  produce a bad result, or did the local box fail to run it" for this rig's client and exit-code
  conventions. Nothing is being hand-rolled that a tool provides: the change is a guard clause in
  an existing shell function.
depends_on:
note: |
  A grade is an ACCUSATION. `is_infra_fault()` decides whether a failed run is charged to the
  MODEL — a BLOCK row in fleet/model-scorecard.tsv that permanently drags that model's grade and
  therefore its tier placement — or to the local box.

  Every branch of the predicate asked "is there a recognised infra signature in the tail?", so a
  run that produced NO OUTPUT AT ALL fell through to `return 1` and was booked as a model-QUALITY
  failure on the strength of an EMPTY string. That is fail-OPEN in the one path that must fail
  closed.

  MEASURED 2026-08-01: `deepseek-v4-flash-ds` sat at score -100 in the live ledger on a single row
  whose entire basis was `opencode exited rc=1 (non-limit, non-infra failure)`. The client had
  failed BEFORE EVER REACHING THE MODEL — its id was undeclared to opencode (OPENCODE-MODEL-SYNC),
  so opencode answered `{"name":"UnknownError"}` client-side. The model was never asked anything,
  and it is now carrying a -100 for it.

  SAME ANTI-PATTERN, THIRD SIGHTING TODAY: an infrastructure failure laundered into a
  normal-looking outcome. (1) review-pool writes a BOUNCE verdict + done marker on a diff-fetch
  failure; (2) review-pool reports an empty queue when `gh` is missing; (3) this. Each one makes a
  box problem look like a judgement about work.

  DELIBERATELY NARROW. The fix fires ONLY on an empty/whitespace-only tail. A tail with real
  content and no infra signature is STILL charged to the model — the existing rc=1 comment is
  right that a false INFRA is exactly as corrosive as a false BLOCK, and tests 3a/3b pin that so a
  later "simplification" to blanket rc=1 => infra fails the suite.
accept: |
  - rc=1 with an empty / whitespace-only / newline-only tail classifies as INFRA, never a model
    verdict, so no scorecard BLOCK row is written for it.
  - The opencode `{"name":"UnknownError"}` client-side shape classifies as INFRA.
  - ANTI-OVER-CLAIM: rc=1 with substantive non-infra text is STILL charged to the model.
  - Every pre-existing classification is unchanged (rc=2/3/125/126/127, rc>=128 signal deaths,
    and the rc=1 text-discriminated infra signatures 401/403/connection-reset/etc.).
  - fail-on-revert proof: fleet/tests/ledger-no-evidence-no-verdict.test.sh EXTRACTS the real
    is_infra_fault() from charon-run.sh rather than re-implementing it. Externally red-proofed
    2026-08-01: 12/12 pass with the fix, 3 FAIL on revert. shellcheck -S error clean.

## Dependencies & Sequence

- **depends_on: (none).** One guard clause plus its test.
- **Sequence: BEFORE any further dogfood/grading run**, or every unattributable failure keeps
  minting false BLOCK rows into the ledger that tier placement is derived from.
- **Blocks / unblocks:** prerequisite for trusting real-work grades at all, which is the session
  priority (grading live + ledger gradeable + promotion/demotion).
- **owns-collision:** `fleet/charon-run.sh` is ALSO owned by CAPTURE-WIRING-TIMEOUT-FIX (P0) and
  MODEL-HARDCODE-PURGE (P0). (An earlier draft of this ticket claimed "none" — that was wrong, and
  validate_board caught it.) Resolution: this ticket lands FIRST as the anchor line and both others
  now `depends_on` it, so the file stays single-writer. This change touches a DISJOINT region —
  the `is_infra_fault()` predicate — while CAPTURE-WIRING-TIMEOUT-FIX works the capture/timeout
  path and MODEL-HARDCODE-PURGE the model-id handling, so the rebases are mechanical.
- **NOT fixed here (needs the grader, not this ticket):** the already-poisoned rows. The ledger is
  owned by the `bench-grader` unix user and is READ-ONLY to manager sessions BY DESIGN (the
  out-of-band grader substrate exists so sessions cannot hand-edit grades). Correcting existing
  rows must go through the grader's own append path, not a manager edit. Requires operator action.
