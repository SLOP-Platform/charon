repo: charon
tier: strong
difficulty: 2
work_class: design-review
priority: 1
branch: docs/sw-adr0016-settle
depends_on:
owns: docs/adr/0016-demand-driven-capability-match.md,
  docs/adr/0011-the-switchboard-demand-routed-no-pools.md
serial_justified: |
  A supersede/fold decision cannot be made in one file. Either 0016 is Accepted on its own terms, or it
  is folded into 0011 and 0011 must simultaneously absorb its invariant — writing one without the other
  leaves the tree with two live, differently-worded statements of the same rule, which is the drift this
  ticket exists to end.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded run — record into fleet/model-scorecard.tsv under work_class `design-review`. Own git worktree.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session). Status values read from the
  product tree at HEAD — do NOT re-derive.
note: |
  `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` is **Accepted**: "The Switchboard" — no
  pools, no lists, no static candidate slate. INV-SW1 no list; INV-SW2 never falsely exhausted;
  INV-SW3 cheapest-capable-with-context-and-available.

  `docs/adr/0016-demand-driven-capability-match.md` is still status **Proposed**. It is the SAME fight
  one layer down: zero static rank. Two documents, one rule, one of them un-adopted — so any
  implementation can cite whichever suits it, and a reviewer cannot say which is binding.

  Settle it. Exactly one of:
  (a) **PROMOTE** 0016 to Accepted with a dated decision line, and state in 0011 how the two compose
      (0011 = no static SLATE, 0016 = no static RANK within the slate that no longer exists), or
  (b) **FOLD** 0016 into 0011 as Superseded-by-0011, and amend 0011 to carry the zero-static-rank
      invariant verbatim so nothing is lost in the merge.
  Do not invent option (c). Do not leave it Proposed.

  Check the tree for implementations that cite 0016 before choosing — if live code already implements it,
  (a) is the honest answer and leaving it Proposed is a documentation lie about shipped behaviour.
  State which refs you checked; a zero-hit grep is NOT evidence of absence.
accept: |
  DONE-CONTRACT (observable):
  - `docs/adr/0016-demand-driven-capability-match.md` no longer reads `Proposed`. Its status line is
    either `Accepted <date>` or `Superseded by ADR-0011 <date>`.
  - If folded: 0011 contains the zero-static-rank invariant in its own words, and a reader of 0011 alone
    can state the rule without opening 0016.
  - If promoted: 0011 and 0016 each say, in one sentence, how they compose — no reader has to guess
    which governs a given decision.
  - The change names the live code (file:line) that does or does not implement the invariant, so the
    ADR is a claim about the tree and not an aspiration. State the ref you measured on.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN (docs-only change must not break the ADR/gate
    registry checks).

## Dependencies & sequence

- **Depends on: NOTHING.** Startable immediately, in parallel with the anchor.
- **Blocks: nothing structurally.** It is deliberately docs-only so it can never gate a code lane —
  but leaving it open means every Switchboard ticket cites an un-adopted ADR.
- **Wave:** wave 1, PHASE 1. Fully CONCURRENT with SW-IDENTITY-FOLD, SW-STATIC-LEGS-RETIRE and all of
  PHASE 2 — owns is docs-only and disjoint from every code ticket in the wave.
- **Concurrency safety:** neither ADR file is owned by any other live board ticket (verified against the
  full `owns:` set of `fleet/board/*.md`, 2026-07-26).
- **Related:** `SW-P2-GRADE-PLANE-SETTLE` owns `docs/adr/0017-outcome-graded-gateway.md` — a different
  file and a different decision. Do not edit 0017 here.
