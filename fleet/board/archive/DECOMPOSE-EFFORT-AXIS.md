tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/decompose-effort-axis
repo: charon
depends_on: DECOMPOSE-DEFAULT-GATE
real-dep: DECOMPOSE-DEFAULT-GATE — this ADDS a second decomposition trigger to the same intake gate; it edits the gate's logic, so it must land on top of it.
owns: src/charon/intake.py, tests/test_decompose_effort_axis.py
accept: |
  Add an EFFORT/SIZE axis to the decompose gate (operator 2026-07-13). DECOMPOSE-DEFAULT-GATE decomposes on change
  SURFACE (owns split into >1 provably-INDEPENDENT group). That is BLIND to "single-file / coupled but LARGE-and-
  slow" work — e.g. DECOMPOSE-DEFAULT-GATE itself (one file, ~21 min) or R46 (coupled gateway.py+balance.py, admitted
  as one domain yet the poster child for over-scope). Surface-breadth != effort.
  DO: at intake, ALSO estimate effort — from `difficulty` (already on every ticket) + estimated change size
  (blast-radius LOC / #call-sites from decompose_surface) + count of distinct required behaviors (e.g. accept-
  criteria bullets / fail-on-revert cases). Above a threshold → SPLIT further (invoke the planner) or FLAG.
  SOFT above the threshold (advisory: warn + record, still admit — some work is irreducibly one-file-but-big;
  forcing artificial seams there is worse), HARD only on clear over-scope. SELF-CALIBRATING: feed per-model
  build-time ACTUALS from the model-scorecard so the estimate improves (a 21-min Opus task != a 21-min weak-model
  task); the threshold is per-executor-tier, not absolute.
  FAIL-ON-REVERT (tests/test_decompose_effort_axis.py): a single-file over-effort fixture (high difficulty + many
  behaviors) is FLAGGED/split; a normal single-domain ticket is untouched; the advisory case admits with a warning
  recorded. Revert the effort check → over-effort ticket admitted silently → RED.
scope: complements DECOMPOSE-DEFAULT-GATE's surface axis with an effort axis. [[charon-work-composition-intelligence]] [[decomposed-by-design-not-reactive]]
ds: |
  depends_on: DECOMPOSE-DEFAULT-GATE (edits the same gate). co-owns intake.py — sequence AFTER it. Adversarial review (gates all work creation).
note: catches coupled/single-file-but-large over-scope that the surface gate misses; advisory-soft + scorecard-calibrated.
