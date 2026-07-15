# RULE-SYNC-AUDIT — review-log fragment

**Ticket:** RULE-SYNC-AUDIT
**Branch:** audit/rule-sync-register
**Date:** 2026-07-15
**Author:** cal-kestis (droid)

## What was produced

`fleet/state/RULE-SYNC-REGISTER.tsv` — a complete bidirectional
classification of every rule in the sibling frameworks (SLOP +
KSF) against Charon, in BOTH directions.

## Counts (header line)

```
slop=309 ksf=14 charon-reverse=16
```

- **309 SLOP rows** — every rule in `SLOP-RULES-INVENTORY.md`
  (Sections 1-3, plus the 23 anti-built-but-not-wired rules in
  Section 2) gets exactly one into-charon row. No silent drops.
- **14 KSF rows** — every gate in `ksf/gates/*.py` (8 gates) +
  the 3 module-contract rules + reuse_check + verify_self +
  open_seam.
- **16 charon-reverse rows** — Charon mechanisms SLOP and KSF
  lack, each with a proposed ticket title for the sibling project
  to file (`file-slop-ticket` or `file-ksf-ticket`).

## Classification outcomes

| source | ported | gap | n-a | total |
|--------|--------|-----|-----|-------|
| slop   | 73     | 112 | 124 | 309   |
| ksf    | 6      | 8   | 0   | 14    |
| charon | 16     | 0   | 0   | 16    |

## The two previously-missed rules (per ticket note)

Both are present and classified `ported` with explicit citations
to MANAGER-OPERATING-RULES §12:

1. **blast-radius** (`SLOP-INV:5.5` → row 5.5) — "Reuse-and-blast-
   radius checkpoint... parameterize interface over known plural
   set, not hardcode" → `charon_status=ported`; `note` cites
   "MANAGER-OPERATING-RULES §12 'FIX AT THE CLASS LEVEL' (explicit
   PORT of SLOP CLAUDE.md:147-172)".
2. **§6 anti-accretion** (`SLOP-INV:5.9` → row 5.9) — "Anti-
   accretion: gap remediated ONLY by fixing, generalizing
   existing lens, or co-located time-boxed exemption; minting new
   per-instance gate script is forbidden" → `charon_status=
   ported`; `note` cites "MANAGER-OPERATING-RULES §12 '§6 ANTI-
   ACCRETION meta-rule' (explicit PORT of SLOP CLAUDE.md:383)".

## Method

Read the three source inventories fully (per ticket directive
"do NOT re-derive — classify against them"):

- `mediastack/SLOP-RULES-INVENTORY.md` (434 lines, 238 rules
  per their Section 4 stats)
- `mediastack/docs/CORE_RULES.md` (999 lines, cross-referenced
  for SLOP-INV section 5.x and 7.x)
- `keystone/ksf/gates/*.py` (8 gates) + `ksf/reuse_check.py` +
  `keystone/ksf/modules/*/module.toml` (module contract)
- `charon-private/fleet/MANAGER-OPERATING-RULES.md` (129 lines,
  12 sections)

Classified every rule against Charon; cited the MANAGER-
OPERATING-RULES section that ports the rule where applicable;
flagged gaps (`action=port-to-charon`); flagged n-a rules
(`action=none`, `note` explains why).

## What this is NOT

- Not a meta-gate. (KSF `coverage_ssot` is the meta-gate
  analog; this register is its DATA INPUT.)
- Not a porting plan. (The register is a classification; the
  porting happens in subsequent tickets — each `action=
  port-to-charon` row seeds a ticket.)
- Not a coverage claim. (339 rows ≠ 100% coverage; the gaps
  column shows 120 rules that Charon has NOT ported yet, of
  which the operator can decide which to port next.)

## File changes in this commit

- `fleet/state/RULE-SYNC-REGISTER.tsv` (new, 339 rows)
- `.gitignore` (added 4-line exception block allowing the new
  durable file in fleet/state/, following the existing
  ROADMAP.tsv / REDS-CORPUS.md precedent)
- `docs/review-log/RULE-SYNC-AUDIT.md` (this fragment)

## Why two files outside the `owns:` line

The ticket's `owns:` is exactly `fleet/state/RULE-SYNC-REGISTER.tsv`.
Two adjacent edits are required to ship that owned file:

1. **`.gitignore`** — the target path is in the `fleet/state/*`
   block; without the `!` exception, the file is gitignored and
   cannot be committed. This is a minimum-edit exception of the
   same shape as the existing `!fleet/state/ROADMAP.tsv` and
   `!fleet/state/REDS-CORPUS.md` precedent — both are durable
   artifacts tracked alongside the gate. The RULE-SYNC-REGISTER
   is the same kind of artifact (durable, derived, not
   regenerated each session).
2. **`docs/review-log/RULE-SYNC-AUDIT.md`** — the join-prompt
   explicitly says "your own review-log fragment, below, is the
   lone exception" — this file is the per-ticket fragment, not
   a shared append.

No other files outside `owns:` are touched.

## Scope self-check

```
git diff --name-only master...HEAD
```

Expected: `.gitignore`, `docs/review-log/RULE-SYNC-AUDIT.md`,
`fleet/state/RULE-SYNC-REGISTER.tsv`. (Verified post-commit.)
