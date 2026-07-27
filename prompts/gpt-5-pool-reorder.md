# GPT5-POOL-REORDER — Immediate mitigation: reorder gpt-5* pools to NanoGPT-primary

## Context
BUG 1 from the 2026-07-04 incident: the live gpt-5.5 pool on 4-LOM is ordered
`["gpt-5.5-or", "gpt-5.5-ng", "gpt-5.5", "gpt-5.5-go"]` — NanoGPT (working) is SECOND.
OpenRouter (no credits) is first. POOLS-EDIT-PLAN.md explicitly excluded gpt-5* from
reordering ("branded premium pools — LEAVE"), which caused the incident.

## Fix (live config change, NOT code)
Reorder the live pools on 4-LOM via the /charon/pools setup API or direct pools.json edit:
- `gpt-5.5`: `["gpt-5.5-ng", "gpt-5.5-or", "gpt-5.5", "gpt-5.5-go"]` — NanoGPT first.
- Audit `gpt-5`, `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.5-pro` for the same stale -or-first
  order. Reorder any that have NanoGPT not-first.

## Verification
```bash
curl -s -H "Authorization: Bearer <token>" \
  -d '{"model":"gpt-5.5","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
  http://10.0.1.60:8080/v1/chat/completions | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'choices' in d, d; print('OK')"
```
Also check `X-Charon-Provider` header is `nanogpt` (or `cache` if cached from the working
response).

## Dependencies & sequence
- depends_on: INC-401-FAILOVER (the 401 fix must land first, or reordering just changes
  which provider's raw error gets relayed).
- This is an IMMEDIATE MITIGATION, not the systemic fix. The systemic fix is DRAIN-ROUTING
  + COST-RANK-AUTO (auto-deriving rank from pricing so the order is always correct).

## Gate
The `accept` command is a live curl test against 4-LOM, not a pytest gate. This ticket is
done when the live gpt-5.5 request succeeds via NanoGPT.

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
