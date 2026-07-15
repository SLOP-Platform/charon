repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/rule-sync-gate
serial_justified: One checker script + its test read one register — cohesive single mechanism (port of KSF coverage_ssot); nothing independent to parallelize.
owns: fleet/checks/rule-sync.sh, fleet/tests/rule-sync.test.sh
depends_on: RULE-SYNC-AUDIT
real-dep: RULE-SYNC-AUDIT produces fleet/state/RULE-SYNC-REGISTER.tsv — the gate reads its schema+rows to enforce on; a true build/correctness prereq, not merge-order.
dep-kind: build
note: |
  Mechanize the operator's TWO-WAY rule sync (Charon <-> SLOP <-> KSF) so the rule-port
  class stops regressing (this was GAP-REGISTER A3, identified 2026-07-12 but never built).
  Ports the KSF coverage_ssot pattern (/home/stack/code/keystone/ksf/gates/coverage_ssot.py)
  rather than inventing a new engine (§6 anti-accretion: generalize the existing lens).
accept: |
  ## Task — fleet/checks/rule-sync.sh (+ fleet/tests/rule-sync.test.sh)
  Read fleet/state/RULE-SYNC-REGISTER.tsv (produced by RULE-SYNC-AUDIT) and enforce, in BOTH
  directions, that no rule is silently un-triaged:
  - RED if any into-charon row has charon_status=gap AND action!=port-to-charon (an untriaged
    inbound gap — a SLOP/KSF rule Charon lacks with no decision).
  - RED if any out-of-charon row has action=file-slop-ticket / file-ksf-ticket but no linked
    ticket id recorded (a Charon rule the siblings need that hasn't been assigned across) —
    i.e. the two-way obligation is enforced, not advisory.
  - For each out-of-charon row, ACTUALLY CREATE the ticket in the target sibling repo (operator
    directive: "create a ticket in SLOP for that work" — not just recommend). SLOP create =
    `python3 /home/stack/code/mediastack/tracking/query.py add --title "<rule> (from Charon)"
    --batch <BATCH>` (discover the current open batch first); KSF create = its equivalent. Record
    the created ticket id back into the register row (a new `linked_ticket` column) so the gate
    can verify it exists. Idempotent: if a linked ticket already exists, do NOT create a duplicate.
  - Print a summary of every ticket created/would-create so the manager/operator sees the two-way
    assignments at a glance.
  - Wire it into validate_board.sh as an ADVISORY surface first (like parallelizability scan),
    then note the promotion-to-blocking step in the review-log once the register is clean.
  ## Accept (fail-on-revert)
  - Seed a temp register with (a) an untriaged inbound gap -> gate RED; (b) an out-of-charon
    row missing a ticket id -> gate RED; (c) a fully-triaged register -> GREEN. Prove each.
  - Test asserts the printed cross-repo assignment names the right target repo (slop|ksf).
  - `bash fleet/tests/rule-sync.test.sh` exits 0 (all pass); wired into validate_board (advisory).
  ## Dependencies & sequence
  depends_on: RULE-SYNC-AUDIT (needs the register schema + real rows to gate on).
