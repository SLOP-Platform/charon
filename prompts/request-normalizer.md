# REQUEST-NORMALIZER — Strip output-only fields for cross-provider multi-turn

## Context
The KNOWN CROSS-PROVIDER BUG (HANDOFF-2026-07-04-v2 §"4-LOM live routing"): routing
deepseek-v4-pro to a non-DeepSeek provider (e.g. Groq gpt-oss) breaks multi-turn because
the replayed assistant `reasoning_content` field is rejected by the non-DeepSeek provider.

## Fix
A request-normalizer that inspects `messages[]` in the inbound request. For any message
with `role=="assistant"`, strip output-only fields the target provider doesn't support:
- `reasoning_content` (DeepSeek chain-of-thought — not understood by Groq, OpenRouter
  passthrough, etc.)
- Any other provider-specific output-only fields discovered during implementation.

Must run BEFORE the request is sent to the upstream provider, in the proxy_server.py
request path. Must be provider-aware: only strip when the target provider is non-DeepSeek.
For DeepSeek-serving providers, pass through unchanged.

## Edge cases to test
- Streaming responses (don't strip mid-stream).
- Tool calls alongside reasoning_content (strip reasoning_content, keep tool_calls).
- Multiple assistant messages in history (strip all).
- No reasoning_content present (no-op, no regression).
- Provider-aware: DeepSeek target → no strip; non-DeepSeek target → strip.

## Dependencies & sequence
- depends_on: INC-401-FAILOVER (failover loop must correctly advance before
  cross-provider substitution is safe).
- Operator decision #14: request-normalizer FIRST, before quota/tool-repair hook wiring.
- Until this lands, keep non-DeepSeek providers out of deepseek-v4-pro pool (decision #31).

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_proxy.py -v -q ; ruff check ; mypy src tests
; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

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
