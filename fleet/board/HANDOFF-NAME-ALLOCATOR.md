repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: feat/handoff-name-allocator
owns: fleet/claim-jedi-name.sh, fleet/state/jedi-name-pool.txt, fleet/tests/claim-jedi-name.test.sh
serial_justified: The allocator, its checked-in name pool, and the fail-on-revert test are one
  invariant — a name-uniqueness gate must ship with the fixture proving it EXCLUDES a name present in
  git history but absent from the live tree (the exact luminara-unduli regression); picker and proof
  are inseparable and share the exclusion-set logic.
depends_on:
source: scratchpad HANDOFF-FAILURE-RCA.md §2 + §5.1 (RCA of the luminara-unduli stale-handoff incident, PR #203); operator directive 2026-07-23 "previously-used names must NOT be claimable while never-before-claimed names remain"
note: |
  ROOT FIX for the recurring stale/frankenstein-handoff class. On 2026-07-23 a session free-picked
  the name `luminara-unduli` — already used 2026-07-21 (commit 6f29737) — so its session-end handoff
  write (73eb30c, PR #203) landed ON TOP of the 07-21 file instead of a fresh one, carrying a
  GENERATED-STATE block ~30 commits stale to the next fresh manager. Confirmed root cause: session
  names are a 100% model free-pick with NO mechanized allocator and NO check against history; the only
  "uniqueness" surface (session-bridge) has a 600s TTL and structurally cannot remember a 2-day-old
  name. The persistent ledger of used names is git itself, and nothing queries it at name-pick time.

  OPERATOR PRINCIPLE (verbatim): previously-used names must NOT be claimable while never-before-claimed
  names remain; only when the fresh pool is exhausted may reuse occur, and then only with explicit
  disambiguation (never silent).
accept: |
  ⛔ BOUNCE-1 (2026-07-23) — attempt #1 (PR #210, frontier droid) REJECTED by adversarial review. The
  allocator CORE (exclusion-set + atomic claim + the luminara-regression fail-on-revert test) was
  independently VERIFIED CORRECT — REUSE/extend branch feat/handoff-name-allocator's core, do NOT rebuild.
  These are HARD MUST-FIX accept items (the builder wrongly self-rescoped them to "follow-up" — self-
  regrading accept is PROHIBITED [[document-model-self-report-lies]] [[adversarial-review-must-not-silently-override-operator]]):
    M1. WIRE IT — handoff.sh MUST call claim-jedi-name.sh (emit the claimed name into the Bootstrap line
        handoff.sh produces). Attempt #1 shipped the script but nothing INVOKES it — built-but-inert, the
        exact class this ticket exists to kill. Not follow-up: the fix has NO EFFECT until wired.
    M2. end-session.sh:176 — the named root-cause line (file-existence skip that let the reused name
        bypass regeneration) MUST be fixed (refuse/regenerate when the handoff file predates the process),
        as the belt-and-suspenders guard. Not follow-up.
    M3. The "concurrent-claim" test must exercise the REAL race window (actual parallel processes), not a
        sequential stand-in; and not depend on `diff.renames` being unset (portability).
  - fleet/state/jedi-name-pool.txt: checked-in Jedi/Star-Wars slug pool, one name per line, matching
    the existing 19 historical name slugs' format.
  - fleet/claim-jedi-name.sh: computes pool MINUS exclusion-set, where exclusion-set =
    union of (a) `ls fleet/SESSION-HANDOFF-*.md` present names AND (b) every name ever created
    `git log --diff-filter=A --all -- 'fleet/SESSION-HANDOFF-*.md'` (this is the query that would have
    caught luminara-unduli). Deterministically claims the first available name and IMMEDIATELY writes a
    claim marker (append fleet/state/session-name-ledger.tsv OR create+commit an empty
    fleet/SESSION-HANDOFF-<name>.md stub) BEFORE returning — claim-before-build, so a concurrent session
    cannot race the same name (same pattern as WORK-LEASE-GATE). Prints ONLY the claimed name on stdout.
  - Fresh pool exhausted => FAIL LOUD (non-zero exit, explicit "pool exhausted" message, require an
    explicit `-2`-suffixed disambiguated name); NEVER silently reuse.
  - Belt-and-suspenders (anchor edits, minimal): handoff.sh + end-session.sh REFUSE outright when
    invoked with a $SESSION whose fleet/SESSION-HANDOFF-$SESSION.md already has commits predating this
    process's start — a cheap independent guard even if the picker is bypassed. (end-session.sh:176's
    file-existence check is the literal line that let the reused name skip regeneration.)
  - fail-on-revert test (fleet/tests/claim-jedi-name.test.sh): (a) a name present in git history but
    NOT in the live tree is still excluded (regression fixture reproducing luminara-unduli) → picker
    never returns it; revert the git-history half of the exclusion-set → test goes RED. (b) exhausted
    pool → non-zero exit + no name printed. (c) two concurrent invocations never return the same name.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — critical session-start gate code;
    manager gates, PR does NOT merge on the builder's self-report. Fix root cause, not symptoms; any
    pre-existing red touched is fixed or ticketed, never stepped around.
scope: |
  Session-START allocator + belt-and-suspenders refuse-check. Does NOT belong in the reconciliation
  gate #178 (that is build/merge-time; this is session-start-time). Its own small mechanized gate,
  wired as the first line of the Bootstrap block handoff.sh emits (handoff.sh:86-90) so the operator/
  model READS a name instead of choosing one.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq. Independent of the RECONCILE-* cluster (disjoint owns:). Highest-leverage
  single fix — prevents the filename collision every downstream handoff check assumes cannot happen.
