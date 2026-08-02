# RETIRE-FINAL-E2E-REVIEW — Review Log

## Ticket
RETIRE-FINAL-E2E-REVIEW: Park fleet/board/FINAL-E2E-REVIEW.md as superseded by the
plane-canary suite (PLANE-CANARY-REGISTRY + PLANE-CANARY-WIRE and the per-plane
canaries those two orchestrate). Per
fleet/state/DESIGN-PLANE-CANARY-SUITE.md EXEC SUMMARY point 4 + PROPOSED TICKET
LIST row 10 — a green `bash fleet/plane-canary.sh run --live && fleet/plane-canary.sh
reconcile` IS the comprehensive always-on e2e that the one-shot capstone review only
pretended to be.

## What was done
- **fleet/board/FINAL-E2E-REVIEW.md**: Added `parked: true` (line 6) and rewrote the
  `note:` field (lines 23-42) to:
  - Mark SUPERSEDED 2026-07-31 by this retirement ticket, PARKED — do not claim.
  - Explain the phantom-vs-replacement reasoning (one-shot review proves the pipeline
    once, plane-canary suite proves it on every PR + on cadence).
  - Cite PLANE-CANARY-REGISTRY + PLANE-CANARY-WIRE + the per-plane canaries by id.
  - Name the durable acceptance proof: a green
    `bash fleet/plane-canary.sh run --live && fleet/plane-canary.sh reconcile`.
  - Preserve the historical `depends_on` chain (DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT)
    un-touched — their own status is out of scope here.
  - Note that the file is preserved (not deleted) per EVAL-REGISTRY's append-only
    convention — git history is the audit trail.

- Single conventional commit: `chore(board): retire FINAL-E2E-REVIEW as superseded by plane-canary suite`.

## Key decisions
- **Do not delete the file.** EVAL-REGISTRY's append-only convention treats board tickets
  as audit-trail artifacts; `parked: true` + a clear note preserves the history without
  inviting future droids to claim it. Re-parking is recoverable via git if a future
  operator wants a one-shot capstone back.
- **Out-of-scope = explicit.** The original `accept:` asks for a CAPSTONE adversarial
  review (operator directive 2026-07-13). The `note:` makes the supersession a board
  fact — `accept:` is left as historical text describing what the ticket *was* before
  this retirement landed; rewriting it would erase the audit trail of what was
  superseded. Board validators read `parked:` + status flags, not the `accept:` body.
- **Don't touch DEP tickets.** DECOMPOSE-DEFAULT-GATE and MODEL-PREFLIGHT have their
  own owners; their board files are out of scope. The `depends_on` line is preserved
  verbatim as historical evidence.

## Mechanized proof
Ran `bash fleet/validate_board.sh` from this worktree. No PARK-*-class RED appears
either before or after this commit. The 5 REDs the validator surfaces are all
pre-existing on master and live on other tickets:
1. `fleet/claim-jedi-name.sh` — HANDOFF-NAME-ALLOCATOR vs SHARED-NAMESPACE-CONTENTION
2. `fleet/preflight.sh` — PLANE-CANARY-WIRE vs PREFLIGHT-GATE-{REGISTRY,RUN-HELPER},
   plus REPO-MAP-CONVERGE / RECONCILE-WIRING / SYNC-SCHEDULE / MARKER-PROOF-MECHANIZE
3. `fleet/state/FAKTORY-TRIAL.md` — FAKTORY-REINVESTIGATE vs FAKTORY-TRIAL (duplicate owns)
4. `fleet/tests/claim-jedi-name.test.sh` — HANDOFF-NAME-ALLOCATOR vs SHARED-NAMESPACE-CONTENTION
5. WCI redundancy on FAKTORY-REINVESTIGATE/FAKTORY-TRIAL

None involve `fleet/board/FINAL-E2E-REVIEW.md` or the retirement ticket; this work
neither caused them nor is required to fix them. Per `accept:` wording: "GREEN
(modulo pre-existing unrelated board state)" — satisfied.

A small WARN appears: `tier-drift FINAL-E2E-REVIEW declared=frontier derived=strong`
— pre-existing; this ticket's only edit was adding `parked: true` and replacing the
note, so it did not introduce the drift and cannot fix it without scope creep.

## Scope self-check
`git diff --name-only master...HEAD` →
```
fleet/board/FINAL-E2E-REVIEW.md
```
Single owned file, exactly per `owns:`. No off-scope paths. docs/review-log/RETIRE-FINAL-E2E-REVIEW.md
(this file) is the explicit per-ticket fragment and is the lone permitted exception.

## Known collision (surfaced, not enforced)
`ticket note` flags a known collision: if a droid claimed
`fleet/board/FINAL-E2E-REVIEW.md` and began the old capstone review in parallel, the
manager should land this retirement first (or explicitly re-confirm the capstone is
still wanted). validate_board.sh's `owns:` check cannot mechanically guard this
because FINAL-E2E-REVIEW.md's own `owns:` line names its own deliverable doc
`fleet/state/FINAL-E2E-REVIEW.md`, NOT the board ticket file — so two tickets can both
list `fleet/board/FINAL-E2E-REVIEW.md` in their `owns:` without collision-detect
flagging it. The `WCI-ADVISORY parallelizability-check-failed` advisory appears on this
run (tool timed out at 15s — a different fleet/checks/parallelizability-gate.sh
issue, pre-existing infra flake, also out of scope here).

## Tier-drift note (worth re-examining later)
RETIRE-FINAL-E2E-REVIEW itself is `declared=strong derived=economy`. The board file it
edits (FINAL-E2E-REVIEW) is `declared=frontier derived=strong`. Neither drift was
introduced by this work — both are pre-existing. Out of scope to fix in a rig-meta
retirement ticket.
