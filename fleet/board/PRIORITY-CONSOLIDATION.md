repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/priority-consolidation
priority: 0
depends_on:
owns: fleet/claim.sh, fleet/state/PRIORITY-LADDER.md
serial_justified: |
  One tightly-coupled change to a single hot-path awk (claim.sh's pick loop) + its axis doc: the
  numeric priority axis, the priority→blocking→blast→difficulty selection ladder, and the legacy-ticket
  normalization are one contract — splitting them orphans the selection semantics (a half-applied ladder
  reads a priority field nothing writes, or writes fields nothing reads). Genuinely serial verification.
work_class_note: |
  Operator-set (2026-07-23). Consolidate the DRIFTED ranking nomenclatures (RANK-0 / R0.x, the P0-P4
  cg-priority ladder, the project ladder, and a `priority:` field used 3 inconsistent ways —
  HIGH/MEDIUM/P2) into ONE numeric machine-read axis, and make claim.sh SELECT BY PRIORITY instead of
  alphabetical-first. Touches a PERF-sensitive hot path (the single-awk claim loop) + doctrine — hence
  strong tier + careful tests. [[cg-priority-ladder]] [[charon-work-composition-intelligence]]
accept: |
  ONE canonical priority axis + a claim.sh that honours it. Specifically:

  1. **Single axis** — `priority: N` (integer, LOWER = MORE URGENT) is the ONLY machine-read priority.
     Numbers ALIGN WITH the P-bands (operator abbreviates them "P:0".."P:5"):
       P:0  = top band — operator-escalated / direct CG-active work. RANK-0 FOLDS IN HERE (no separate
              super-tier; "R0.0" is just a human label for a P:0 ticket).
       P:1  = attached CG work, not huge / not over-dependent.
       P:2  = standalone, biggest blast-radius.
       P:3  = Router standalone.
       P:4  = quick wins.
       P:5  = reserved lowest explicit band.
       unset = tickets with NO `priority:` field → treated as the lowest band, auto-sequenced by the graph.
     NOTE: `parked:` is ORTHOGONAL — a parked ticket is NOT claimable AT ALL (already skipped by
     claim.sh); parked is NOT a priority band and must not be folded into "unset". Stale/merged tickets
     are handled by reconcile→done (also already skipped), not by a priority band.

  2. **claim.sh selection ladder** (replaces the current alphabetical-first pick; KEEP the single-awk
     PERF structure — no per-ticket fork). Among the already-filtered claimable set
     (tier/deps/parked/submitted/claimed/done/loop-guard), pick by, in order:
       a. `priority:` band ascending (unset = +infinity / lowest)
       b. BLOCKING impact — reverse-dependency count DESC (how many OPEN board tickets list this id in
          their `depends_on:`). Compute in the same index pre-pass.
       c. BLAST radius — `owns:` surface count DESC.
       d. `difficulty:` DESC (start the big ones early).
       e. id alphabetical — deterministic final tie-break.
     The `CLAIM_ONLY` hard-pin (already wired — see below) short-circuits ALL of this.

  3. **Normalize the 3 mis-formatted `priority:` tickets** to the numeric scheme (map HIGH→2, MEDIUM→3,
     LOW→4; `P2`→2): REACHABILITY-GATE (HIGH→2), REVIEWER-DOGFOOD-REDS (MEDIUM→3),
     SUBAGENT-WORKTREE-SANDBOX (P2→2). Flag these 3 for operator sanity-check in the PR body (the old
     labels were informal). WORKLOOP-INTEGRITY-STACK-SPIKE is already `priority: 0`.

  4. **Doc** — write `fleet/state/PRIORITY-LADDER.md` (the canonical axis + band table above) and update
     `fleet/session-notes/NEXT-SESSION-RANK0.md` to say "RANK-0 = priority: 0; P-band N = priority: N".
     (The `cg-priority-ladder` manager MEMORY lives outside the rig repo — the MANAGER updates that; do
     NOT attempt to edit ~/.claude from this ticket. Note it in the PR body as a manager follow-up.)

  5. **Validator** (small, keeps it from re-drifting): a gate/test asserting every board `priority:`
     value is an integer 0..5 (or absent) — reject `HIGH`/`P2`/etc. Wire into the existing gate/test
     harness. FAIL-ON-REVERT test for the claim ladder (assert priority beats alpha; blocking beats blast).

  ALREADY DONE (do NOT rebuild) — the `CLAIM_ONLY` hard-pin bootstrap: `claim.sh` reads `CLAIM_ONLY`
  (case-insensitive single-ticket filter) and `fleet-droid.sh --only <ID>` exports it. This ticket
  BUILDS ON that; leave the pin behaviour intact and covered by a test.
scope: |
  Consolidate 4 overlapping ranking schemes into one numeric `priority:` axis (P:0..P:5 + unset), make
  claim.sh select by priority→blocking→blast→difficulty→alpha (not alphabetical), normalize the 3
  legacy-format tickets, document the axis, and add a drift validator. Parked stays orthogonal.
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Owns fleet/claim.sh + a new doc; the 3 ticket normalizations are one-line
    frontmatter edits (park the pool while this runs so no other droid claims those 3).
  - sequence: land claim.sh ladder + doc + validator together; the 3 ticket normalizations can ride the
    same PR (flagged for operator sanity-check). Manager updates the cg-priority-ladder memory after merge.
