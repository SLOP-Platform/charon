repo: charon-private
tier: strong
priority: 2
difficulty: 4
work_class: ci-infra
branch: feat/work-gate-universal
depends_on:
owns: fleet/checks/work-gate.sh, fleet/hooks/pretooluse-work-gate.sh, fleet/tests/work-gate.test.sh
serial_justified: Gate A and Gate B both live in the SAME two files — work-gate.sh dispatches both
  checks, and pretooluse-work-gate.sh self-checks both at launch AND at done — so decomposing by
  gate would make two workers concurrent writers of the same work-gate.sh/pretooluse-work-gate.sh,
  exactly the owns-collision decompose.sh itself refuses to emit.
accept: |
  MECHANIZE (not doctrine) two work-discipline gates that FIRE regardless of how work is launched — inline, sub-session,
  detached, or tab/droid. Operator directive: "encoding into doctrine is not enough." REUSE existing pieces; do NOT rebuild.
  GATE A — decompose-sizing @ LAUNCH (minimize wall-clock): before a BIG batch fans out, run charon.decompose_sizing
    (N* optimal, cap 4, diminishing-returns) and REFUSE/warn on an un-sized big serial launch. Enforcement points:
    (1) fleet/launch-plan.sh + LAUNCH-PLAN-GATE (tabs + plan); (2) a PreToolUse:Agent|Task hook (fleet/hooks/pretooluse-work-gate.sh)
    for Claude sub-sessions/detached/inline; (3) fleet-droid.sh for droid tabs. Honor validate_board SPLITTABLE-SERIAL (stop treating advisory).
  GATE B — E2E-fully-wired @ DONE (no inert/unwired code ships): at work-done/land, run tools/check_inert_code.py + graphify
    (code map) wiring-gap check + the dogfood observable-effects e2e assertion; REFUSE merge if what was built is not FULLY
    WIRED end-to-end. The land/CI gate is the UNIVERSAL chokepoint every launch mode must pass — put Gate B there so it cannot
    be skipped by any mode; also surface it via the PreToolUse hook so sub-agents self-check before returning.
  REUSE: LAUNCH-PLAN-GATE, SESSION-CTX-PROPAGATE's PreToolUse hook substrate, GATE-INTEGRITY / FAIL-LOUD-CONTRACT / dogfood
    e2e gate, decompose_sizing.py, check_inert_code.py, graphify. This ticket WIRES them into mandatory gates, it does not reimplement them.
  FAIL-ON-REVERT (fleet/tests/work-gate.test.sh): an un-sized big-batch launch is REFUSED/flagged (revert Gate A -> passes -> RED);
    an inert/unwired change is REFUSED at land (revert Gate B -> merges -> RED). Both NON-VACUOUS + FAIL-LOUD.
