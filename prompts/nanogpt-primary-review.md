# NANOGPT-PRIMARY-REVIEW — Review whether drainable balances should outrank NanoGPT

## Context
Operator decision #30: keep NanoGPT primary unless a specific drain fast-path applies,
AND create a parked ticket to review whether drainable balances should generally outrank
NanoGPT later.

## Review criteria (after DRAIN-ROUTING is live)
1. Did NanoGPT's $12/mo flat sub get underutilized because drainable balances were spent
   first? (Check usage logs for NanoGPT token volume vs. drainable provider volumes.)
2. Did any drainable balance expire unused because NanoGPT was always primary? (Check
   balance expiry events.)
3. Should the policy change to "drain expiring balances first, then NanoGPT, then metered"?
   (Compare cost outcomes: expired-balance-wasted vs. NanoGPT-underutilized.)
4. Is the 60M tok/wk NanoGPT cap ever hit? If so, does drainable-first help avoid it?

## Deliverable
A data-driven review with a recommendation to the operator. Not a code change. If the
recommendation is to change the policy, create a follow-up build ticket.

## Dependencies & sequence
- depends_on: DRAIN-ROUTING (must be live to observe actual behavior).
- PARKED — do not build this session.

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
