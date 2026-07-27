# INC-401-FAILOVER — Fix 401 misclassification + synthesize "all providers exhausted" terminal

## Context
On 2026-07-04, the operator started a session with `gpt-5.5` as the opencode model. The
gateway's `gpt-5.5` pool tried opencode-go, which returned 401 "Model gpt-5.5 is not
supported". The gateway relayed this raw error to opencode instead of failing over to
NanoGPT (which works). The operator saw a misleading "not supported" error instead of a
balance/exhaustion message.

## Root cause (verified in source)
- `src/charon/proxy.py:31`: `_EXHAUSTION_STATUSES = {429, 402, 503}` — 401 is NOT in the set.
- `_is_billing_error()` catches 401 + billing body patterns.
- `_is_auth_error()` catches 401 + auth body patterns.
- But opencode-go's 401 body ("Model gpt-5.5 is not supported") matches NEITHER set →
  `obs.failover=False` → loop does NOT advance → `proxy_server.py:751-756` relays raw 401.
- There is NO synthesized "all providers exhausted" terminal — the client always sees the
  last-tried provider's raw error body.

## Fix (two parts)

### Part 1: Classify "model not supported" 401s as failover-class
In `proxy.py`, add a third 401 classification: provider-capability mismatch. Add a new
pattern set `_MODEL_NOT_FOUND_PATTERNS = ["not supported", "model not found", "no such
model", "unknown model"]`. When status==401 and the body matches these patterns, set
`obs.failover=True` (fail over to next pool member), NOT `auth_error`. This is NOT an auth
error — it's a provider that doesn't have this model in its catalog.

### Part 2: Synthesize "all providers exhausted" terminal
In `proxy_server.py`, when the failover loop's last provider fails via failover (not via
auth-terminate), synthesize a clear error response instead of relaying the last raw
upstream error:
```json
{"error":{"type":"all_providers_exhausted","message":"All providers in the <model> pool failed","failover_reasons":[...]}}
```
HTTP 502. Preserve `X-Charon-Failover-Reasons` header. When `obs.failover=False` (genuine
auth error), keep relaying the raw body — that path is correct.

## Tests
1. 401 "not supported" body → failover advances, not terminates.
2. All pool members exhausted via failover → synthesized 502 "all_providers_exhausted".
3. Genuine auth 401 ("invalid api key") → still relays raw (no regression).
4. Genuine billing 402 → still failovers (no regression).
5. Red-proof: write a test that WOULD have failed before this fix (the 401 "not supported"
   case relaying raw instead of failing over).

## Dependencies & sequence
No depends_on. This is the highest-priority fix — it gates DRAIN-ROUTING,
REQUEST-NORMALIZER, and GPT5-POOL-REORDER. Land first.

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_proxy.py -v -q ; ruff check ; mypy src tests ;
python3 tools/check_boundary.py src ; python3 tools/check_version.py`

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
