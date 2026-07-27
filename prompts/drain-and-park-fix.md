# BRIEF — METER drain-and-park: FIX the 2 review defects

The build is money-path and its sole-leg guard already passed adversarial review — do NOT change that logic.
Fix only the 2 defects below. Correctness + REAL evidence over speed.

## Where you are
- Worktree on branch `feat/drain-and-park` (@8d65af4) of the charon product repo. Fix in place, commit here. No push/merge.
- READ the review (authoritative defect list): `/home/stack/charon-private/fleet/state/overnight/DRAIN-AND-PARK-REVIEW.md`.

## Fix
- **F2 (PRIMARY — the brief's core deliverable was faked as prose):** replace the PROSE "real-traffic proof" with ACTUAL CAPTURED output. Boot the gateway via the module form (`PYTHONPATH=src python3 -m charon.cli gateway --state-dir <tmp> --port <p>`; the `charon` shim is broken). Configure a **fixed-mode funding-class-3** provider with a small `starting_balance`. Drive REAL `/v1/chat/completions` requests until its balance → ~0; CAPTURE (paste real output) the before/after balances + routing decisions showing: AUTO-PARK, routing SKIPS it, NO fail-churn; then top-up and show RE-ARM. Separately show a pool where the target is the SOLE leg is NOT parked. Commit the captured transcript as `drain_and_park_traffic_proof.txt`.
- **F1:** add a FAIL-ON-REVERT test at the forwarder integration guard **call-site** (not just the helper). Reverting the guard CALL in the forwarder must turn this test RED. (Today only the helper is covered, so the call-site could regress silently green.)

## Do NOT
- Do NOT touch `test_failover_chain_check_warns` — it is a confirmed PRE-EXISTING HOME-isolation failure, tracked separately.
- Do NOT push, merge, or change the sole-leg guard logic.

## LAST STEP
- FULL gate pipe-free: `PYTHONPATH=src python3 -m charon.cli gate; echo "EXIT=$?"` → 0.
- Commit on `feat/drain-and-park`; report SHA. Do NOT push/merge (separate line).
- Write `/home/stack/charon-private/fleet/state/overnight/DRAIN-AND-PARK-FIX-REPORT.md`: the 2 fixes, the REAL captured traffic proof (paste it), the new fail-on-revert test, gate EXIT, SHA.
- Print `PACKET: <report path>` + ≤8-line honest summary. Real captured outputs only — a prose description of the traffic proof is a FAILED deliverable.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
