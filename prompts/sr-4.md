# SR-4 — SMART-ROUTING.md doc corrections

## Dependencies & sequence
**depends_on: (none) — Wave 2 (W2), parallel with SR-3 and SR-5.** DOC-ONLY, touches NO product
code. Owns only `/home/stack/charon-private/fleet/SMART-ROUTING.md`, disjoint from every other SR
ticket — fully concurrency-safe. No disjoint-owns dep to justify.

## Shared context (grounding for a fresh session)
`SMART-ROUTING.md` documents the gateway request pipeline. Its §1 pipeline and §5 hook diagram
currently show `SpeculativeExecutor` and `ConsensusRouter` firing inside `_handle()`. In reality
those two are CONSTRUCTED but NEVER invoked in the request path — only spend, guardrail, cache,
quality, and normalizer are actually wired into `_handle()`. (See the constructor at
`proxy_server.py:882-924` where session_affinity/speculative/consensus/virtual_key_manager are stored
but not called on the hot path.) SR-8 later decides whether to wire or remove those modules; this
ticket only makes the DOC honest.

## What to build
1. In §1 (pipeline) and §5 (hook diagram), mark `SpeculativeExecutor` and `ConsensusRouter` as
   **"constructed, not yet wired into `_handle`"** (do not depict them as firing).
2. Make §1/§5 reflect the REAL active set that actually runs in `_handle()`: spend, guardrail,
   cache, quality, normalizer.

## Acceptance
- The doc no longer claims any unwired module fires in the request path.
- §1 and §5 list exactly the actually-wired modules as active, with speculative + consensus clearly
  flagged as constructed-but-not-wired.
- Cross-reference SR-8 (the wire-or-remove decision) so a reader knows the follow-up.

## CONSTRAINTS
- **Owns:** `/home/stack/charon-private/fleet/SMART-ROUTING.md` ONLY. No product-code edits.
- Documentation change only — no tests to run; verify by re-reading §1/§5 for accuracy.

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
