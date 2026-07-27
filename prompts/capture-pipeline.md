# BRIEF — REAL model-outcome CAPTURE PIPELINE (feeds the tamper-resistant scorecard)

Build the pipeline that captures real CG-build outcomes AND false-success (model claimed SUCCESS but
review found FAIL) into the `bench-grader`-owned scorecard, ONLY through the grader's spool. Portable
stdlib/POSIX. This touches the integrity boundary — correctness over speed; it gets an independent review
before deploy.

## Authoritative design (READ FIRST)
`/home/stack/charon-private/fleet/state/CAPTURE-PIPELINE-BUILD-PLAN.md` — schema (§1), flow (§2), wiring
(§3), false-success (§4), acceptance (§5), chunks (§6). Build to that plan. Operator step E (spool perms)
is DONE — stack can now enqueue to `/var/lib/bench-grader/spool/req/` (sticky 1733) and read `res/`.

## Where you are / HARD safety rules
- CWD is a git worktree on branch `feat/capture-pipeline` of the charon-private rig. Commit here. No remote push/merge.
- `model-scorecard.tsv` is owned by `bench-grader` and is NOT writable by you — do NOT attempt to write it. All scorecard writes happen inside the grader daemon (as bench-grader). You only produce code + enqueue JSON.
- The grader daemon runs LIVE as `bench-grader`. Do NOT restart/kill/signal it. Deploy of your daemon change = a separate OPERATOR step. You only WRITE + unit-test the new code.
- Do NOT flood the live spool. Test the daemon `capture` handler LOGIC directly (call the handler function against a SCRATCH ledger/DB fixture in your worktree), NOT via the live daemon loop. At most ONE clearly-named probe file in the real spool, removed after.

## Build (chunks A/B/C/D/F — one writer per file, all in the rig)
- **A** `fleet/capture/enqueue-capture.sh` (new): builds a `{kind:"capture", ...}` JSON per §1/§2 and drops it in `spool/req/`. Reads job-meta (chunk B).
- **B** brief `<brief>.meta.json {work_class,ref,difficulty}` convention + a loader; env fallback `CHARON_JOB_{WORK_CLASS,REF,DIFFICULTY}`.
- **C** `fleet/capture/emit-verdict.sh <review-packet>` (new): parse a review packet → `<packet>.verdict.json {verdict,gate,score,evidence}` → enqueue the FINAL capture request.
- **D** `fleet/benchmark/grader-daemon.py`: add a `capture` request kind — SKIPS snapshot/grade, validates claimed+actual, computes `discrepancy = (claimed==SUCCESS ∧ (actual_verdict==BLOCK ∨ gate==fail))`, appends a `source=live` row via the existing `_append_to_ledger` shape (verdict=actual_verdict, gate=actual_gate, tier=difficulty, note includes ref;evidence and `FALSE-SUCCESS` when discrepancy). Provisional→active promotion per §2.
- **F** in A: when discrepancy, ALSO call the existing `fleet/log-model-report.sh` (F18) to append the stack-owned reliability ledger (no boundary crossing).

## Acceptance — FAIL-ON-REVERT (unit-level; the live end-to-end is operator-gated on daemon deploy)
- Daemon `capture` handler: feed a synthetic PROVISIONAL then FINAL(actual_verdict=BLOCK, gate=fail) pair → the handler appends ONE `live` row to a SCRATCH ledger with the `FALSE-SUCCESS` discrepancy note and score≤20. Revert the handler (or the discrepancy computation) → NO row / no discrepancy. Must go RED on revert.
- `enqueue-capture.sh` emits schema-valid JSON (all §1 fields); `emit-verdict.sh` extracts verdict/gate from a real review packet (use `fleet/state/overnight/BRIDGE-PUSH-REVIEW.md` as a fixture).
- Note: the kimi-k2.6-nw false-success backfill (claimed SUCCESS, actual BLOCK, score~15) flows through this pipeline once the daemon is DEPLOYED — do NOT hand-write the scorecard; just include the ready-to-enqueue capture JSON for it as an artifact.

## LAST STEP (required)
- Run the new tests pipe-free: `python3 -m pytest <your new test file> -q; echo "EXIT=$?"` → 0.
- Commit on `feat/capture-pipeline`; report SHA.
- Do NOT push. Do NOT merge. Do NOT restart the grader daemon. (deliberate, separate line.)
- Write `/home/stack/charon-private/fleet/state/overnight/CAPTURE-PIPELINE-BUILD-REPORT.md`: chunks built (file:line), the fail-on-revert handler test REAL output, the kimi capture-JSON artifact path, exactly what remains gated on the OPERATOR daemon-deploy, pytest EXIT, SHA. Flag that the grader edit needs an independent review (tamper-resistance / integrity) before deploy.
- Print `PACKET: fleet/state/overnight/CAPTURE-PIPELINE-BUILD-REPORT.md` + ≤8-line honest summary. Real outputs only.

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
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
