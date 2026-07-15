repo: charon-private
tier: frontier
difficulty: 3
work_class: rig-meta
branch: audit/rule-sync-register
serial_justified: Single new register file (one cohesive classification pass over fixed source inventories) — one owned surface, nothing to parallelize.
owns: fleet/state/RULE-SYNC-REGISTER.tsv
depends_on:
note: |
  BIDIRECTIONAL rule-coverage audit across the three sibling rulesets. The prior Charon
  gap-audit (GAP-REGISTER.md A3) was self-admittedly MANUAL and cherry-picked — it looked
  for gaps in EXISTING Charon surfaces, so ABSENT rules (blast-radius, §6 anti-accretion)
  fell through. This ticket fixes that at the CLASS level: a systematic, complete
  classification of EVERY rule in the sibling frameworks against Charon, in BOTH directions.
accept: |
  ## Sources (read fully; do NOT re-derive — classify against them)
  - SLOP: /home/stack/code/mediastack/SLOP-RULES-INVENTORY.md (complete catalog) +
    /home/stack/code/mediastack/docs/CORE_RULES.md
  - KSF:  /home/stack/code/keystone/ksf/gates/coverage_ssot.py (+ any KSF rules catalog /
    CORE_RULES in that repo — find it first)
  - Charon (the target): /home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md
    (+ any fleet/state/RULE-REGISTRY.tsv if present)

  ## Task — produce fleet/state/RULE-SYNC-REGISTER.tsv
  One row PER rule, columns:
    source_framework   (slop|ksf|charon)
    rule_id            (source file:line or stable slug)
    rule_summary       (one line)
    charon_status      (ported | gap | n-a)
    direction          (into-charon | out-of-charon)
    mechanized         (gate name | none)
    action             (none | port-to-charon | file-slop-ticket | file-ksf-ticket)
    note               (one line: why n-a, or where it should live)
  - **into-charon**: every SLOP + KSF rule → ported / gap(→port-to-charon) / n-a(reason).
    Do NOT cherry-pick; classify the WHOLE inventory. Blast-radius (SLOP CLAUDE.md:147-172)
    and §6 anti-accretion (CLAUDE.md:383) must appear (they were the missed ones — they are
    now PORTED via MANAGER-OPERATING-RULES §12; mark them ported and cite the section).
  - **out-of-charon** (the TWO-WAY half — operator directive): any Charon rule/mechanism the
    sibling frameworks LACK but need → row with action=file-slop-ticket / file-ksf-ticket and a
    proposed ticket title in the note. This is what the mechanized two-way sync will assign.

  ## Accept
  - RULE-SYNC-REGISTER.tsv exists, well-formed TSV, header row matches the columns above.
  - Every SLOP-RULES-INVENTORY.md rule and every KSF rule has exactly one into-charon row
    (no silent drops — a count line at the top comment: "slop=N ksf=M charon-reverse=K").
  - At least the two known-missed rules (blast-radius, §6) are present and classified.
  - No `/home/stack` absolute paths inside the committed TSV values (product-clean; refer to
    rules by repo-relative source path).
  ## Dependencies & sequence
  depends_on: (none) — pure read+classify over fixed inventories. Feeds RULE-SYNC-GATE.
