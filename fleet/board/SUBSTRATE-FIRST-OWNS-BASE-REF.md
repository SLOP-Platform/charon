repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: fix/substrate-first-owns-base-ref
owns: fleet/checks/substrate_first_gate.py, fleet/tests/substrate_first_gate.test.sh
depends_on:
source: 2026-07-23 — systemic CI-RED across the ENTIRE feature-PR queue (#204/205/207/208/210/211/214/215/…); root-caused live from rig-ci run 30044035629
note: |
  The substrate-first gate REDs every ticketed feature PR: "touches CODE but changes NO fleet/board/*.md
  ticket." It requires the board ticket to be touched IN THE PR DIFF — but the fleet workflow MINTS
  tickets SEPARATELY (manager mints+lands the ticket, then a droid builds ONLY code on a separate
  branch). So legitimately-ticketed code fails, uniform CI-RED gives ZERO signal on the rig (a genuinely
  broken PR looks identical to a fine one — #200 was substrate-RED AND had 4 real blockers, conflated),
  and it HARD-BLOCKS every feature PR on the public product (CI required there). This is the gate-decay /
  false-positive-gate class. RATCHET — the fix must be STRONGER, never weaker. [[security-is-a-ratchet-gate]]
accept: |
  - substrate_first_gate.py is satisfied for a changed CODE file when that file is covered by an EXISTING
    board ticket's `owns:` on the BASE ref (origin/master / the PR base), NOT only when a board/*.md is
    touched in the diff. Genuinely UNOWNED code (no live ticket owns it) STILL REDs — the ratchet holds.
  - Reuse the board `owns:` parser already in validate_board / the reconcile machinery — do NOT hand-roll
    a second owns-parser. Resolve owns against the BASE board (checked-out base ref), not the PR head.
  - fail-CLOSED: if base-board owns can't be resolved, RED (assume unowned), never silently pass.
  - fail-on-revert test (fleet/tests/substrate_first_gate.test.sh): (a) a code change whose file IS in a
    base-ref ticket's owns: => GREEN; (b) a code change to a file owned by NO ticket => RED; (c) revert the
    base-ref owns-resolution => case (a) goes RED again (proves the fix is load-bearing).
  - Verify against the live pileup: the fix makes #210 / #204 / #207 pass substrate (they are ticketed)
    while a fabricated unowned-code diff still REDs.
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — RATCHET gate code; manager gates,
    PR does NOT merge on the builder's self-report. Prove the ratchet still bites unowned code.
scope: |
  Fix the substrate-first false-positive so ticketed feature PRs (ticket pre-minted separately) pass,
  while genuinely ticketless code still fails. Unblocks the whole feature-PR merge flow + restores CI
  as a meaningful signal. This is the gate that gates landing — LANDING IS PAUSED until this lands +
  passes review (operator 2026-07-23).
ds: |
  ## Dependencies & sequence
  P0, no build prereq. Disjoint owns. Highest priority — the pause on landing feature PRs lifts only
  after this lands and CI is trustworthy again. Manager lands this via land.sh (bypasses the false CI)
  as the exception that lifts the pause.
