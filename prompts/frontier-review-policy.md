# FRONTIER-REVIEW-POLICY — Spec the "frontier review for free-tier work" policy

## Context
Operator caveat on decision #2 (DRAIN priority: free-first-then-drain): "Work done by free
tiers should have a frontier model review." Operator decision #22/#23: create a parked
ticket to review/spec this policy, but do NOT implement/enforce it this session.

## Open questions to resolve in the spec
1. Is it a hard gate for ALL free-tier-generated code, or only for
   money/auth/routing/deploy-sensitive changes?
2. Which models count as "frontier" for review purposes? (Claude Opus 4.8? GPT-5.5-pro?
   Gemini 3.1 Pro?)
3. Does the review happen pre-merge or post-merge-as-follow-up?
4. How does this interact with the autonomous land-push workflow?
5. What constitutes "free-tier work"? (Any code generated while the session model was a
   free-tier model? Or only code that shipped via a free-tier routing path?)

## Deliverable
A spec document, not enforcement code. The spec should define the policy, the gate
mechanism, the model list, and the merge interaction. After operator approval, a separate
build ticket would implement it.

## Dependencies & sequence
No depends_on. PARKED — do not build this session.

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
