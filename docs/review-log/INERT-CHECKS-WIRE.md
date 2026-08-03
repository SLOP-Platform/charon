# INERT-CHECKS-WIRE review log

**Ticket:** INERT-CHECKS-WIRE · **Review date:** 2026-08-01
**Reviewer:** cal-kestis (session: charon-private-wt/INERT-CHECKS-WIRE)
**Status:** SCOPE BLOCKER — owns mismatch

---

## OWNERSHIP DISPOSITION

The ticket's `owns:` is `fleet/state/INERT-CHECKS-WIRE.md` and `docs/review-log/INERT-CHECKS-WIRE.md`.
The implementation targets (9 inert checks, their wiring locations, companion tests) are ALL outside
this owns list.

**Verdict:** CANNOT IMPLEMENT as scoped.

---

## FAKTORY CLAIMED-BUT-ABSENT (PART 0)

Inspected `fleet/lease-enqueue.sh:116-122` and `fleet/tests/lease-exactly-once.test.sh`.

The compensating control exists and is functional: `flock + ENQ/$TICKET marker + live_faktory_job`
triple-guard provides at-least-once idempotency. The "exactly-once" language in the test docstring
is the inaccurate claim. **Corrective:** update the test docstring to say "at-least-once via
compensating control" instead of "exactly-once job delivery."

Not fixed here — `owns:` doesn't cover `fleet/tests/lease-exactly-once.test.sh`.

---

## 9 INERT CHECKS — WIRING PLAN

| Check | Best wiring target | Mode | Blocks preflight? |
|---|---|---|---|
| reconcile-board-pr-done.sh | land.sh | HARD | Yes |
| stuck-ticket-loud.sh | preflight.sh cmd_detect() | ADVISORY | No |
| board-file-ratchet.sh | gate.sh | HARD | Yes |
| reconcile-review-gate.sh | land.sh + preflight | HARD + ADVISORY | Yes |
| egress-key-canary.sh | gate.sh (fleet) / product CI | HARD | Yes |
| gate-creation-standard.sh | validate_board.sh | HARD | Yes |
| large-file-guard.sh | preflight.sh cmd_detect() | ADVISORY | No |
| registry-discovery.sh | preflight.sh cmd_detect() | ADVISORY | No |
| selfcheck-cycle.sh | — (via test suite) | — | — already wired |

---

## 2 G4 GAPS (land.sh:361-362)

- leak-guard.sh into land.sh step 3.5: HARD
- push-verify.sh into land.sh step 4: HARD

---

## graphify affected

Dependency on `GRAPHIFY-AFFECTED-WIRE.md` (separate ticket). Do NOT duplicate.

---

## SCOPE DECISION

This ticket documents the complete wiring plan. The actual implementation needs either:
(a) a scope amendment adding wiring targets to owns, OR
(b) a decomposition into per-check sub-tickets that each own their wiring targets.

This file + fleet/state/INERT-CHECKS-WIRE.md constitute the full documentation deliverable.
