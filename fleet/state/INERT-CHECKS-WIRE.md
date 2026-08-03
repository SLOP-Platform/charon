# INERT-CHECKS-WIRE — state and wiring plan

**Ticket:** INERT-CHECKS-WIRE · **Date:** 2026-08-01
**Source:** fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md (measured), own inspection.

---

## SCOPE NOTE — OWNERSHIP MISMATCH

This file documents the full wiring plan. **Implementation requires edits to files outside this
ticket's `owns:`**, specifically:
- `fleet/checks/*.sh` — the 9 inert checks to wire
- `fleet/preflight.sh` — primary wiring surface
- `fleet/gate.sh` — secondary wiring surface
- `fleet/land.sh` — G4 gap wiring (leak-guard, push-verify)

This ticket's `owns:` is only:
- `fleet/state/INERT-CHECKS-WIRE.md` (this file)
- `docs/review-log/INERT-CHECKS-WIRE.md`

The `owns:` discrepancy means this ticket **cannot implement** its own wiring. The plan below
is the documentation; the implementation needs a separate ticket that owns the wiring targets,
or a scope amendment to add those files to `owns:`.

---

## PART 0 — Faktory CLAIMED-BUT-ABSENT (done first, per ticket sequence)

### Finding: CLAIM-LEASE-EXACTLY-ONCE

OSS Faktory does NOT provide unique-job deduplication — it is an Enterprise feature. The test
`fleet/tests/lease-exactly-once.test.sh` asserts exactly-once behavior. The pipeline WAS designed
for a guarantee the tool does not make.

**Disposition: DOCUMENTED, NOT FIXED HERE**

`lease-enqueue.sh` lines 116-122 already implements a compensating control:
```bash
exec 9>"$LOCK"; flock 9
if [ -e "$ENQ/$TICKET" ] || live_faktory_job; then
  echo "DUP: $TICKET already enqueued — no-op (exactly-once)"
  exit 0
fi
```
The `flock + marker + live_faktory_job` triple-guard provides at-least-once idempotency without
requiring Faktory Enterprise's unique-job feature. `lease-enqueue.sh` itself is NOT inert —
`fleet-droid.sh` and the claim loop invoke it. The CLAIMED-BUT-ABSENT finding is about the
EXPLICIT claim in the test ("an ACKed ticket cannot be re-fetched") not matching OSS capability,
not about the enqueue path being unprotected.

**Corrective action:** Update `fleet/tests/lease-exactly-once.test.sh`'s docstring to remove the
"exactly-once job delivery" claim (which requires Enterprise), replacing it with the accurate
statement: "at-least-once via compensating control (flock + marker + live_faktory_job)".

**Owner:** PROOF-SUITES-ENFORCE or a sibling ticket — not this one.

---

## PART 1 — 9 INERT CHECKS: wiring plan per check

### 1. `fleet/checks/reconcile-board-pr-done.sh`

**What it catches:** FAILURE #1 — 19 tickets merged but not marked done.
R-A: open ticket with merged PR. R-B: merged PR with no ticket. AMBIGUOUS: N>1 owns overlap.

**Wiring recommendation:** `fleet/preflight.sh` (the preflight/gate/CI registration surface).
Best placement: as an advisory detector in `cmd_detect()`, similar to `detect_gate_integrity`.
The check queries GH and returns non-zero when R-A/R-B/AMBIGUOUS exist, but since it requires
GH and cannot run offline, it should be advisory (always exit 0) in preflight, with a note
that it is also a candidate for land.sh.

**Alternative wiring:** `fleet/land.sh` — before land, verify no merged-PR/done drift.
This is the tighter gate (closes failure #1 at the actual land step).

**Disposition:** Wire to `fleet/land.sh` as a pre-land check (hard gate — exit 1 = refuse to
land). Add to land.sh alongside the existing leak-guard/push-verify checks.

**Wiring line (land.sh):** Add `bash "$HERE/checks/reconcile-board-pr-done.sh" || exit 1`
before the "step 5/5: land" block.

**Companion:** companion test `fleet/tests/reconcile-board-pr-done.test.sh` does not exist yet —
need to create it with red-proof cases (R-A red, R-B red, AMBIGUOUS red, clean green).

---

### 2. `fleet/checks/stuck-ticket-loud.sh`

**What it catches:** FAILURE #3 — 46 tickets never dispatched, FAILURE #4 — false quarantine.
Four categories: quarantined, parked, dep-dissolved, orphan-marker.

**Wiring recommendation:** `fleet/preflight.sh` as an ADVISORY in `cmd_detect()`, NOT a
hard gate. The check reads board state and has no false-positive risk — stuck tickets are
objective. But the pre-existing backlog (46 stuck tickets) means hard-gating preflight would
block every session until the backlog is cleared.

**Disposition:** Wire to preflight.sh as advisory (always exit 0, always print findings).
This matches the `detect_gate_integrity` pattern (advisory scan, hard ratchet in CI).

**Reentrancy:** The script already exports `STUCK_TICKET_LOUD_ACTIVE=1` — safe for preflight.

---

### 3. `fleet/checks/board-file-ratchet.sh`

**What it catches:** FAILURE #6 — merge destroys tickets. Board file count never decreases
without explicit archive move or retire.

**Wiring recommendation:** `fleet/gate.sh` — this runs on every land/push cycle.
The check needs a base SHA and HEAD SHA, which gate.sh can provide via `RATCHET_BASE` and
`RATCHET_HEAD` env vars.

**Disposition:** Wire to `fleet/gate.sh`. Since gate.sh runs with bounded concurrency and
this check is read-only git operations, it can run alongside the existing test suite.

**Alternative:** `fleet/preflight.sh` — but `preflight.sh`'s existing gates are in `cmd_detect()`
(advisory). A board ratchet should fire at land time, not session start.

---

### 4. `fleet/checks/reconcile-review-gate.sh`

**What it catches:** FAILURE #2 — draft PRs never reviewed. R-J: ≥hot-path with no review
evidence. R-K: stale review. R-L: doom loop (FIXES without CONFIRMED-CLEAN).

**Wiring recommendation:** `fleet/land.sh` — this is a review-consistency gate that should fire
before a ticket lands. Alternatively: `fleet/preflight.sh` as an ADVISORY to surface pending
review gaps at session start.

**Disposition:** Wire to `fleet/land.sh` as a pre-land check (hard gate), and as advisory in
`fleet/preflight.sh`'s `cmd_detect()`.

**NOTE:** The check reads board tickets + `docs/review-log/` + `fleet/state/reviewed/`. It
depends on done-merge gate logic for merge SHA verification. Already well-structured.

---

### 5. `fleet/checks/egress-key-canary.sh`

**What it catches:** Security — egress allowlist blocking provider repointing. Starts a real
charon gateway subprocess and attempts the exfil sequence.

**Wiring recommendation:** `fleet/gate.sh` — this is a real-SUT canary, not a static check.
It should run in the product gate CI (alongside ruff, mypy, pytest), NOT in the fleet rig gate.

**Disposition:** Wire to product `.github/workflows/ci.yml` or as a separate `ci-canary.yml`.
Alternatively: `fleet/gate.sh` for the fleet-internal copy, with a note that the product copy
should be in product CI.

**Scope note:** The product CI wiring is in `repo: charon` — outside this ticket's scope.

---

### 6. `fleet/checks/gate-creation-standard.sh`

**What it catches:** Meta-gate — gate quality degradation. Checks gates.json registry,
call-site enumeration, companion tests, ledger, standard doc.

**Wiring recommendation:** `fleet/validate_board.sh` — the meta-gate's own docstring (line 358)
says "validate_board.sh does not yet run this meta-gate's scan." Wire it there.

**Disposition:** Wire to `fleet/validate_board.sh` as a hard gate.

**NOTE:** The check is already sophisticated (S1-S10 enforcement, grandfather lists, call-site
enumeration). It just needs the invocation.

---

### 7. `fleet/checks/large-file-guard.sh`

**What it catches:** Performance creep — oversized staged/untracked files that would block push.

**Wiring recommendation:** `fleet/preflight.sh` as ADVISORY (prints findings, does not hard-block).
Also: as a pre-commit hook registration candidate. The script itself (line 22) says "NOT YET WIRED"
and names `fleet/preflight.sh` as the intended home.

**Disposition:** Wire to `fleet/preflight.sh` in `cmd_detect()` as advisory.

**NOTE:** The script is already fully functional and has a companion test `fleet/tests/`.
Companion test exists (need to verify): `fleet/tests/large-file-guard.test.sh`.

---

### 8. `fleet/checks/registry-discovery.sh`

**What it catches:** Tool inventory drift — unregistered components, stale entries, malformed rows.
Three legs: CONFORMANCE, DISCOVERY, DRIFT.

**Wiring recommendation:** `fleet/preflight.sh` as ADVISORY in `cmd_detect()`.
The DISCOVERY leg requires graphify graph, which may not be fresh at every preflight.
The check already has `--quiet` behavior for CI.

**Disposition:** Wire to preflight.sh as advisory.

---

### 9. `fleet/checks/selfcheck-cycle.sh`

**What it catches:** Fork-bomb class — unguarded reentrancy cycles in fleet scripts.

**Wiring recommendation:** `fleet/gate.sh` — this IS already implicitly invoked by gate.sh via
the `*.test.sh` glob (gate.sh runs `fleet/tests/selfcheck-cycle.test.sh`, which invokes this check).
BUT: `selfcheck-cycle.sh` itself is NOT in the gate.sh invocation list directly — it runs as
part of the test suite, not as a standalone check.

**Disposition:** This check IS already wired through the test suite. The companion test
`fleet/tests/selfcheck-cycle.test.sh` invokes it and proves it fires on reentrancy cycles.
STATUS: **NOT INERT** — already wired through `gate.sh`'s test glob.

---

## PART 2 — 2 DOCUMENTED G4 GAPS (fleet/land.sh:361-362)

### G4-A: leak-guard.sh NOT wired into land.sh

**Finding:** `fleet/land.sh:361` prose states leak-guard.sh is NOT wired into land.sh.
The script exists and is invoked by `fleet-droid.sh`, `retire-done.sh`, `branch-reaper.sh`
but NOT by `land.sh` or `push-verify.sh`.

**What it catches:** Main-checkout writes during work — the dogfood dogfood case.

**Disposition:** Wire into `fleet/land.sh` step 3.5 (before the git add step).
Add `bash "$HERE/leak-guard.sh" check || exit 1` before the push step.

**Evidence:** `grep -c "leak-guard" fleet/land.sh` = 0. Prose gap confirmed.

---

### G4-B: push-verify.sh NOT wired into land.sh

**Finding:** `fleet/land.sh:362` prose states push-verify.sh is NOT wired into land.sh.

**What it catches:** Pre-push verification (branch protection, up-to-date base, etc.).

**Disposition:** Wire into `fleet/land.sh` step 4/5. Already sourced at land.sh:14 but the
actual invocation is commented/not wired. Add the check before `git push`.

**Evidence:** `grep -c "push-verify\|pv_" fleet/land.sh` = only the source line at :14.

---

## PART 3 — graphify affected (blast-radius, 0 call sites)

**Finding:** `graphify affected <file>` — the blast-radius reverse traversal — has 0 invocations.
The graph is built (114 `update` call sites), refreshed (graphify-freshness.sh in preflight),
but never queried for impact analysis.

**Disposition:** Wire into `fleet/reuse-check.sh` per the plan in `fleet/board/GRAPHIFY-AFFECTED-WIRE.md`.

**NOTE:** `GRAPHIFY-AFFECTED-WIRE.md` is a separate ticket (`feat/graphify-affected-wire`) with
its own `owns:` and branch. This work should proceed as the sibling ticket lands. The
INERT-CHECKS-WIRE ticket should not duplicate that work — instead, record the dependency and
defer to the dedicated ticket.

**Dependency:** `GRAPHIFY-AFFECTED-WIRE` (or GRAPHIFY-AFFECTED-WIRE.md in board/).

---

## PART 4 — Summary wiring table

| Check | Target file | Mode | Priority | Notes |
|---|---|---|---|---|
| reconcile-board-pr-done.sh | land.sh | HARD gate | P0 | Closes failure #1 |
| stuck-ticket-loud.sh | preflight.sh | ADVISORY | P0 | Closes failures #3/#4 |
| board-file-ratchet.sh | gate.sh | HARD gate | P1 | RATCHET_BASE/HEAD env |
| reconcile-review-gate.sh | land.sh + preflight.sh | HARD + ADVISORY | P1 | Closes failure #2 |
| egress-key-canary.sh | gate.sh / product CI | HARD canary | P1 | Real SUT; product copy separate |
| gate-creation-standard.sh | validate_board.sh | HARD gate | P1 | Already designed, just not invoked |
| large-file-guard.sh | preflight.sh | ADVISORY | P2 | |
| registry-discovery.sh | preflight.sh | ADVISORY | P2 | |
| selfcheck-cycle.sh | — | — | — | Already wired via test suite |
| leak-guard.sh (G4-A) | land.sh | HARD gate | P0 | Add to step 3.5 |
| push-verify.sh (G4-B) | land.sh | HARD gate | P0 | Add to step 4 |
| graphify affected | reuse-check.sh | ADVISORY | P1 | Delegate to GRAPHIFY-AFFECTED-WIRE |

---

## PART 5 — What can this ticket actually do

Given `owns: fleet/state/INERT-CHECKS-WIRE.md, docs/review-log/INERT-CHECKS-WIRE.md`,
this ticket can:
1. Document the full wiring plan (this file)
2. Create the review log fragment
3. Flag the owns mismatch to the manager

This ticket **cannot** implement any wiring without a scope amendment.

**Recommended next steps:**
1. Amend this ticket's `owns:` to include `fleet/preflight.sh`, `fleet/gate.sh`, `fleet/land.sh`, `fleet/validate_board.sh`, `fleet/tests/reconcile-board-pr-done.test.sh`, `fleet/tests/board-file-ratchet.test.sh`, `fleet/tests/large-file-guard.test.sh`
2. OR: spawn sub-tickets per check that each own their wiring target
3. OR: create a new "wiring" implementation ticket that owns the wiring targets and references this plan
