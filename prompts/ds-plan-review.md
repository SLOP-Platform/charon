# DS-PLAN-REVIEW — adversarially review the optimized backlog plan before launching the waves

## Dependencies & sequence
**depends_on: NONE — Wave 0 (run BEFORE unparking any build wave).** Owns NO product/source files
(a review produces findings + ticket-metadata corrections), so it cannot collide and is safe to run
any time. It SHOULD run first because it validates the plan the other tickets are sequenced by.

## Why (manager is least-confident here)
The optimized backlog (waves, `depends_on` edges, owns-disjointness, and several BAKED-IN
assumptions) was authored by the manager in a single pass and only SPOT-verified. Before any wave is
launched, adversarially review the plan so a wrong dep / hidden collision / bad assumption is caught
before a droid hits it mid-build. Source of truth: `fleet/OPTIMIZATION-PASS.md` + each ticket's
`## Dependencies & sequence`.

## What to check (try to REFUTE the plan, don't bless it)
1. **owns-disjointness** — confirm NO two tickets that could be live at once share a file (the claim
   that every buildable ticket is the sole writer of its files). Re-derive from each board `owns:`.
2. **depends_on edges** — are they correct and minimal? Specifically: WCI←ADR-0015, WCI-FOLLOWON←WCI
   (+ DSGN-WCI-PROOF approval), ATC←all. Any MISSING real build-dep? Any UNJUSTIFIED disjoint dep?
3. **wave ordering** — does the sequence actually minimize blocking and maximize safe concurrency?
4. **the baked-in assumptions** (highest risk):
   - OBS-CAPTURE scoped to `acp.py` ONLY assumes the per-unit log path is DERIVABLE from the
     worktree `acp._start` receives — verify that's true; if not, OBS-CAPTURE needs the scheduler
     seam and must re-sequence vs WCI.
   - ORCH-ROUTE's Step-0 (does `opencode acp` honor the injected config override?) — is the
     verify-then-build framing sound, or should Step-0 be its own spike ticket?
   - OBS-UI's "console panel off the hot path" — confirm that's achievable without touching the
     per-request gateway path.
5. **D&S completeness** — every live-able ticket carries a valid `## Dependencies & sequence` (the
   `validate_board.sh` D&S gate enforces presence; this checks CORRECTNESS, which the gate can't).

## Output
Findings note at `docs/review-log/DS-PLAN-REVIEW.md` (or a rig doc): per item, refute/confirm +
the correction. APPLY metadata fixes to the affected parked tickets' board/prompt files where a
correction is clear (rig files, low-risk); flag anything needing an operator call. If the plan is
sound, say so with the evidence checked.

## CONSTRAINTS
Read-only over product `src/`; may EDIT fleet board/prompt files to correct ticket metadata (rig,
not product). Owns no product source. No PR to master. Review note → `docs/review-log/DS-PLAN-REVIEW.md`.
BACKLOG (parked) — Wave 0. Branch `docs/ds-plan-review`.
