repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/vulture-investigate-retire-inert
depends_on: GITLEAKS-ADOPT, BANDIT-ADOPT
real-dep: GITLEAKS-ADOPT — genuine sequencing prereq (operator directive: retire hand-rolls AFTER the
  additive maintained scanners land; lower-risk order). This ticket reuses the same
  adopt-a-CI-scanner-with-canary pattern that gitleaks establishes, and must not replace a working
  hand-roll (tools/check_inert_code.py) until the additive scanners are green. owns are DISJOINT so this
  dep is JUSTIFIED, not implied by file overlap.
real-dep: BANDIT-ADOPT — same sequencing prereq: land the additive Python SAST first, then investigate
  swapping the hand-rolled dead-code checker for maintained vulture. Reuses the canary/required-check
  pattern. owns DISJOINT — JUSTIFIED sequencing dep.
owns: fleet/checks/vulture.sh, .github/workflows/vulture.yml, fleet/tests/vulture-canary.test.sh, fleet/tests/fixtures/vulture-known-dead.py, fleet/state/VULTURE-EVAL.md
serial_justified: This is one investigate-then-adopt unit: the eval doc (VULTURE-EVAL.md) drives the
  ADOPT/KEEP decision, and only if ADOPT do the wrapper+workflow+canary+fixture ship together (a
  half-wired check is the zero-work-green defect) alongside retiring the hand-roll. The retirement must
  be atomic with the replacement so two dead-code checkers never run in parallel. Not splittable.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep (operator directive: RETIRE hand-rolls where a maintained tool
  exists). INVESTIGATE adopting maintained `vulture` (dead-code / unused-symbol detector) to REPLACE the
  hand-rolled tools/check_inert_code.py in the product repo.

  DO (investigation-then-adopt, evidence-first per [[confirm-dont-trust-documentation]]):
    (a) fleet/state/VULTURE-EVAL.md — compare vulture vs the hand-rolled tools/check_inert_code.py on the
        REAL product tree: coverage (does vulture catch what the hand-roll catches + more?), false-positive
        rate, whitelist/allow-list ergonomics, maintenance burden. Cite file:line + real run output, not
        docstrings. Record an ADOPT / KEEP-HANDROLL / ADOPT-DiD verdict as an EVAL-REGISTRY.md row.
    (b) IF ADOPT: fleet/checks/vulture.sh (thin wrapper) + .github/workflows/vulture.yml reusing the
        SEMGREP/gitleaks required-check + canary scaffold, then RETIRE tools/check_inert_code.py (delete +
        redirect any callers/gates to the vulture check). Do not leave two overlapping dead-code checkers.
    (c) KNOWN-BAD-FIXTURE CANARY (NON-NEGOTIABLE if adopted): fleet/tests/fixtures/vulture-known-dead.py
        contains a planted unused symbol vulture MUST flag; fleet/tests/vulture-canary.test.sh asserts
        >=1 finding — no zero-work-green.

  FAIL-ON-REVERT (if adopted, fleet/tests/vulture-canary.test.sh): wrapper on the known-dead fixture ->
  >=1 finding; neuter it -> 0 -> canary FAILS. Also assert the retired tools/check_inert_code.py no
  longer runs as a parallel checker (no double-gating). [[gates-must-actually-run]]
  IF the verdict is KEEP-HANDROLL, ship VULTURE-EVAL.md + the EVAL-REGISTRY row and close — do NOT force
  an adoption the evidence doesn't support.
scope: |
  Investigate maintained vulture as a replacement for the hand-rolled tools/check_inert_code.py, record
  an evidence-backed EVAL-REGISTRY verdict, and IF it dominates, adopt it as a CI check (reusing the
  SEMGREP/gitleaks scaffold + canary) and retire the hand-roll. Sequenced AFTER gitleaks/bandit per
  operator directive. [[adopt-substrate-build-only-novel-slice]] [[confirm-dont-trust-documentation]]
  [[reviews-use-our-own-tools]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence
  depends_on: GITLEAKS-ADOPT, BANDIT-ADOPT — QUEUED behind both (see top-level real-dep lines: operator
    sequencing — retire hand-rolls only AFTER the additive maintained scanners land; reuses their
    required-check + canary pattern). Both are themselves queued behind SEMGREP-CI-REQUIRED-CHECK, so
    this is the third wave transitively.
  concurrency: DISJOINT owns from every other sweep ticket (its own check/workflow/eval/fixture files +
    the eventual retirement of the product hand-roll). Runs alone in its wave.
  wave: strong, third wave (after gitleaks + bandit).
  repo: charon-private (rig) — branch + eval doc here; the check targets the product Python tree and the
    retirement deletes tools/check_inert_code.py in the product repo.
note: Created 2026-07-21 from the KS31/KS32 sweep. Operator directive: retire hand-rolls where a
  maintained tool exists. Investigate-first (verdict may be KEEP-HANDROLL). Queued behind GITLEAKS-ADOPT
  + BANDIT-ADOPT.
