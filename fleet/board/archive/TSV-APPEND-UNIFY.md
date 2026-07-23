tier: frontier
difficulty: 1
work_class: refactor
branch: feat/tsv-append-unify
repo: charon-private
parent: DEDUP-GRAPHS-LEDGERS
depends_on:
note: |
  Filed by DEDUP-ACTUALS-DELETE per accept step 2. From
  fleet/state/TOOL-AUDIT-REDUNDANCY.md finding 6 — dual TSV-scorecard appenders:
  `fleet/model-scorecard.sh cmd_append` (live, shell) vs
  `fleet/capability/auto_append.py` (built, tested, 0 real callers). Two independent
  implementations of the identical "validate + append one row to model-scorecard.tsv"
  contract, kept in sync only by comment discipline. RIG-side work: either make the
  shell path delegate to `python3 capability/auto_append.py` (one impl, two callers)
  or delete one. This ticket only files the finding — does NOT implement.
accept: |
  - One of the two appenders is removed or unified.
  - TOOL-AUDIT-REDUNDANCY.md finding 6 is resolved.
scope: fleet/model-scorecard.sh, fleet/capability/auto_append.py, fleet/capability/tests/
