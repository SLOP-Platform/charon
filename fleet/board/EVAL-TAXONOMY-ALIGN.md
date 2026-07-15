repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-taxonomy-align
depends_on:
serial_justified: picking ONE taxonomy and repointing grades to it is a single atomic decision; splitting it would leave two class systems live at once (the exact bug).
owns: fleet/capability/grades.py, fleet/state/EVAL-TAXONOMY.md
accept: |
  BLOCKER (review F3): the eval grades the WRONG taxonomy. grades.py:138 keys on fleet BUILD work_classes; the PRODUCT
  ROUTER asks in its OWN semantic classes (src/charon matrix.py:20 / taxonomy.py). grades.py's "two consumers, one
  taxonomy" claim is FALSE — the gateway router that is supposed to consume assign.py's grades will find ZERO data
  because the class labels don't match. Every downstream data-collection decision depends on fixing this FIRST.
  DO:
  - DECIDE ONE canonical taxonomy (the PRODUCT router's semantic work_classes are the meaningful axis — routing serves
    the product, not the build rig). Write the decision + the full class list + the fleet↔product mapping to
    fleet/state/EVAL-TAXONOMY.md as the single source of truth. Cross-check src/charon (matrix.py, taxonomy.py) and the
    WORKCLASS-TAXONOMY work already on master — reconcile, don't fork again. NOTE: matrix.py + taxonomy.py
    live in the PRODUCT repo /home/stack/code/charon/src/charon/ (NOT this rig repo) — read them there.
  - Repoint grades.py to the canonical classes (map/normalize legacy fleet-class rows so historical data isn't lost).
    Do NOT touch assign.py's tier filter here (EVAL-TIER-CANON owns that) — this ticket is taxonomy only.
  FAIL-ON-REVERT (extend the grades.py tests): a scorecard row in a product-router semantic class is graded and is
  retrievable by the SAME class string the router uses; a legacy fleet-class row maps to its canonical class (revert
  the mapping → the router-class query returns empty → test fails). Add an assertion that grades.py's class set ==
  the canonical set in EVAL-TAXONOMY.md (drift guard).

## Context (added by manager, )
see: fleet/state/MSOT-BLAST-RADIUS-AUDIT.md — taxonomy is MSOT #2: a 4-way split (grades.py 11 / model-scorecard.sh 9 / scorecard.tsv 9 / product router 6 semantic classes) and the product router currently reads ZERO grade data. The ONE taxonomy you pick MUST be the product router semantic classes; repoint grades.py to it. grades.py already carries a (now-false) "single source of truth" comment — make it true.
