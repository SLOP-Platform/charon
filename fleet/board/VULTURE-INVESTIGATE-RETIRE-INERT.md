repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/vulture-investigate-retire-inert
depends_on: GITLEAKS-ADOPT, BANDIT-ADOPT
substrate: vulture — reject — vulture is a reference-counting unused-symbol detector and cannot replace tools/check_inert_code.py, which is a reachability-from-entrypoint gate — vulture MISSES mutually-referencing built-but-never-wired dead islands (proven, hand-roll flags them and vulture passes) and has no registration-awareness and no @inert_by_design allowlist, so KEEP-HANDROLL (see fleet/state/VULTURE-EVAL.md).
real-dep: GITLEAKS-ADOPT — genuine sequencing prereq (operator directive, retire hand-rolls AFTER the additive maintained scanners land; lower-risk order). Reuses the same adopt-a-CI-scanner-with-canary pattern gitleaks establishes, and must not replace a working hand-roll (tools/check_inert_code.py) until the additive scanners are green. owns are DISJOINT so this dep is JUSTIFIED, not implied by file overlap.
real-dep: BANDIT-ADOPT — same sequencing prereq, land the additive Python SAST first, then investigate swapping the hand-rolled dead-code checker for maintained vulture. Reuses the canary/required-check pattern. owns DISJOINT — JUSTIFIED sequencing dep.
owns: fleet/state/VULTURE-EVAL.md
serial_justified: |
  This is one investigate-then-decide unit: the eval doc (VULTURE-EVAL.md) drives the
  ADOPT/KEEP decision. The evidence (real runs on the product tree + a reproduction fixture) returned
  KEEP-HANDROLL, so no wrapper/workflow/canary ships and the product hand-roll is retained unchanged.
  Not splittable.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep (operator directive: RETIRE hand-rolls where a maintained tool
  exists). This ticket INVESTIGATED adopting maintained `vulture` (dead-code / unused-symbol detector) to
  REPLACE the hand-rolled tools/check_inert_code.py — and the evidence says KEEP-HANDROLL.

  DONE (investigation-then-decide, evidence-first per [[confirm-dont-trust-documentation]]):
    (a) fleet/state/VULTURE-EVAL.md — compared vulture 2.16 vs the hand-rolled tools/check_inert_code.py on
        the REAL product tree (coverage, false-positive rate, whitelist ergonomics, maintenance burden) with
        cited file:line + real run output. VERDICT: REJECT / KEEP-HANDROLL. Recorded as an EVAL-REGISTRY.md
        row (alignment=aligned, evidence-link=fleet/state/VULTURE-EVAL.md).
    (b) NOT ADOPTED — no fleet/checks/vulture.sh, no .github/workflows/vulture.yml, no canary/fixture built.
        vulture is reference-counting and structurally CANNOT replace the hand-roll's reachability-from-
        entrypoint gate (it passes the mutually-referencing dead-island bug class the gate exists to catch;
        proven in the eval), and lacks the registration-awareness + @inert_by_design allowlist the hand-roll
        provides. Even as defense-in-depth its only delta (unused locals/imports) is already ruff territory.
    (c) tools/check_inert_code.py in the PRODUCT repo is RETAINED unchanged and NOT touched by this ticket.

  CLOSE AS KEEP-HANDROLL: ship VULTURE-EVAL.md + the EVAL-REGISTRY row and close — the evidence does not
  support adoption. [[gates-must-actually-run]]
scope: |
  Investigate maintained vulture as a replacement for the hand-rolled tools/check_inert_code.py and record
  an evidence-backed EVAL-REGISTRY verdict. Outcome: KEEP-HANDROLL — vulture does not dominate; it cannot
  replace a reachability gate. No CI check adopted; the product hand-roll stays. Sequenced AFTER
  gitleaks/bandit per operator directive. [[adopt-substrate-build-only-novel-slice]]
  [[confirm-dont-trust-documentation]] [[reviews-use-our-own-tools]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence
  depends_on: GITLEAKS-ADOPT, BANDIT-ADOPT — QUEUED behind both (see top-level real-dep lines: operator
    sequencing — retire hand-rolls only AFTER the additive maintained scanners land; reuses their
    required-check + canary pattern). Both are themselves queued behind SEMGREP-CI-REQUIRED-CHECK, so
    this is the third wave transitively.
  concurrency: DISJOINT owns from every other sweep ticket (now just its eval doc, since the verdict is
    KEEP-HANDROLL and no check/workflow/fixture is built). Runs alone in its wave.
  wave: strong, third wave (after gitleaks + bandit).
  land-order: gitleaks -> bandit -> vulture. All three append an EVAL-REGISTRY.md row; a trivial rebase
    conflict at the append point is EXPECTED — resolve by keeping all rows.
  repo: charon-private (rig) — branch + eval doc + registry row here. The product hand-roll is NOT modified.
note: |
  Created 2026-07-21 from the KS31/KS32 sweep. Operator directive: retire hand-rolls where a maintained
  tool exists. Investigate-first — and the investigation returned KEEP-HANDROLL (2026-07-22): vulture is
  reference-counting and misses the reachability class the hand-roll catches. Queued behind GITLEAKS-ADOPT
  + BANDIT-ADOPT. Closed as KEEP; tools/check_inert_code.py retained. No product-repo follow-up (there is
  no retirement to defer — the replacement was rejected on evidence).
