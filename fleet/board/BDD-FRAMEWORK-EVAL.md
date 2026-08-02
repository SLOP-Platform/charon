repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: design-review
branch: eval/bdd-framework
depends_on:
owns: fleet/state/BDD-FRAMEWORK-EVAL.md, docs/review-log/BDD-FRAMEWORK-EVAL.md
serial_justified: |
  One comparative evaluation. Candidates only rank against each other when measured in one pass
  against the same real code, by the same reviewer, under the same bar.
substrate: N/A
substrate-novel: |
  This ticket IS a substrate evaluation - it exists to decide what to ADOPT, so it cannot itself
  cite a prior adopt-verdict. VERIFIED 2026-08-02 - fleet/state/EVAL-REGISTRY.md contains ZERO
  rows for pytest-bdd, behave, cucumber, Hypothesis or any BDD tool, so there is no prior verdict
  to inherit and none to supersede. The deliverable APPENDS the registry rows that are missing.
execution: |
  Off-Claude, SG tab. EVAL lane - measure and report. Wire NOTHING, add no dependency, change no
  pyproject. The deliverable is a verdict with evidence.
source: |
  Operator, 2026-08-02, verbatim intent - adopt Behaviour-Driven Development as the CORE
  FOUNDATIONAL framework for how code is developed, with pytest-bdd paired with Hypothesis as the
  leading candidate. Explicitly requested a DEEP review of real FEATURES, not a surface view, and
  noted that any earlier research predates the lens shift AWAY from hand-coding.
note: |
  ## THE LENS THIS MUST BE JUDGED UNDER — read before evaluating anything
  Operator, 2026-08-02 - "we generate more work then we complete." The rig is in a
  self-sustaining rig-work cycle. Therefore the FIRST-ORDER question is NOT "is BDD good
  practice." It is - **does this REDUCE the total work the rig must do, given that AGENTS write
  the code and a human reviews outcomes?**
  A framework that adds a second artifact (`.feature` files) which must be kept in sync with the
  code BY HAND is a work MULTIPLIER, and must be reported as such even if it is excellent
  practice for human-written code. Judge honestly in both directions - do not strawman BDD to
  protect the status quo, and do not sell it because it is fashionable
  [[research-posture-solution-seeking]].

  ## WHY BDD IS PLAUSIBLE HERE — the operator's mechanism, to be VERIFIED not assumed
  Charon's orchestration validates agent work by running an `accept:` list of SHELL COMMANDS and
  checking exit codes - `pytest -q` is already the documented shape. So a declarative test suite
  feeds straight into the acceptance gate, and the loop can score OUTCOME without caring HOW the
  agent restructured the internals. CONFIRM this by reading the real `accept:` execution path in
  this rig before building any argument on it [[confirm-dont-trust-documentation]]. State the
  file and line where accept commands are executed.

  ## FEATURE-DEPTH REVIEW REQUIRED — surface comparisons will be rejected
  For pytest-bdd specifically, evaluate and give a verdict on EACH, with a code example:
    - Scenario Outlines and Examples tables - do they subsume our parametrised cases?
    - Step definition REUSE across features, and the step-collision failure mode at scale.
    - Interaction with pytest fixtures - scope, ordering, and whether `given` steps can replace
      fixtures or must wrap them.
    - Tags/markers - can they express our tier/work_class/money-path selection?
    - `pytest-xdist` parallelism - do BDD steps survive it?
    - Reporting - what a failure looks like, and whether it is MORE legible to a human reviewer
      than a plain pytest assertion (this is the actual claimed benefit; test it).
    - THE MAINTENANCE COST - who writes and updates the `.feature` gherkin when an agent changes
      behaviour? If the answer is "the agent", show a worked example of an agent editing gherkin
      correctly. If it is "a human", say so plainly - that is the work multiplier.
    - Failure modes at scale - undefined/ambiguous steps, gherkin drift from code.

  ## CANDIDATES — do not evaluate pytest-bdd in isolation
    1. **pytest-bdd** - primary candidate. Lives inside pytest, so the `accept:` integration is free.
    2. **behave** - standalone BDD runner. Judge the cost of a SECOND runner beside pytest.
    3. **plain pytest with given/when/then naming and docstrings** - the NULL HYPOTHESIS, and it
       must be taken seriously. It delivers much of BDD's legibility with ZERO new dependency and
       ZERO gherkin to maintain. If it wins, say so.
    4. Any other serious candidate found (e.g. Cucumber via a bridge). Reject with a reason.

  ## THE DEPENDENCY COLLISION — this is load-bearing, do not skip it
  MEASURED 2026-08-02 - Keystone (`/home/stack/code/keystone`) declares itself a "stdlib-only
  enforcement layer" and its `dependencies=[]` posture is ENFORCED by `tools/check_arch.py` and
  `tools/check_boundary.py`. Adopting pytest-bdd or Hypothesis is the FIRST dependency and would
  trip those gates. A stranded branch already removes the prohibition -
  `chore/remove-stdlib-only-prohibition` @ `ca7d046` ("adopt-first", 14 files, -215/+85), PUSHED
  WITH NO PR. State explicitly whether the BDD verdict DEPENDS on that branch landing, and if so
  say that it is a hard prerequisite rather than a footnote.
accept: |
  DELIVERABLE `fleet/state/BDD-FRAMEWORK-EVAL.md` containing -
  a. A VERDICT - ADOPT pytest-bdd / ADOPT another / DO NOT ADOPT (plain pytest wins). One line,
     up front, before the reasoning.
  b. The work-multiplier answer, quantified as far as possible - who maintains the gherkin, and
     what it costs per behaviour change. This is the deciding question; a verdict that dodges it
     is not a verdict.
  c. A per-feature table for pytest-bdd (the list above), each row backed by a RUN example, not a
     doc quote. Install into a scratch venv and actually execute it - do not evaluate from README.
  d. The `accept:`-gate integration answer, citing the real file and line where accept commands
     execute in this rig.
  e. The null-hypothesis comparison - what plain pytest with disciplined naming gives us for free,
     and precisely what BDD adds beyond it.
  f. EVAL-REGISTRY rows appended for every tool evaluated (| tool | scope | date | verdict |
     alignment | reason | evidence-link | supersedes |), honestly classified, in a SEPARATE
     EARLIER commit than this ticket's own (the substrate gate refuses same-push registry rows).
  g. If ADOPT - a MIGRATION SHAPE - what a pilot looks like on ONE real Charon behaviour, how
     much of the existing suite would have to move, and what stays as plain pytest forever.
scope: |
  Evaluation and written verdict only. Adds no dependency, edits no pyproject, converts no test.
  Hypothesis is evaluated by HYPOTHESIS-FAILOVER-EVAL - reference its findings, do not duplicate.

## Dependencies & Sequence

- **depends_on: none.** Reads this rig, the product repo and public tool docs/source.
- Runs in PARALLEL with HYPOTHESIS-FAILOVER-EVAL and KSF-PLUGIN-FRAMEWORK-RESUME. Disjoint owns;
  all three are read-only evaluations.
- HARD PREREQUISITE IF ADOPT - `chore/remove-stdlib-only-prohibition` (`ca7d046`) must land before
  any dependency can be added to Keystone. Do not treat that as this ticket's work; name it.
- The three lanes are synthesised by the MANAGER into one recommendation. Do not self-merge them.
