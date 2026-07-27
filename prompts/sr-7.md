# SR-7 — spend-cap hardening

## Dependencies & sequence
**depends_on: SR-2, SR-6, SR-5 — Wave 3 (W3), SECOND in the SR-6 → SR-7 → SR-8 chain.**
- `real-dep: SR-2 build (single-owner file proxy_server.py)` — shared-file sequencing.
- `real-dep: SR-6 build (single-owner file proxy_server.py)` — shared-file sequencing; SR-7 lands
  after SR-6.
- `real-dep: SR-5 needs pricing` — SR-7's estimated-cost path relies on the pricing SR-5 captures;
  a true correctness prereq. Owns are DISJOINT vs SR-5 (spend_limits.py/proxy_server.py vs
  config/discover/providers), so the dep is JUSTIFIED, not assumed.
Concurrency-safety: the W3 chain is strictly ordered, so SR-7 is the only writer of proxy_server.py
while it is in flight.

## Shared context (grounding for a fresh session)
Part of the SR gateway cost-correctness series. The universal monthly cap is GOOD in design — one
global cumulative total across ALL providers — but it is blind to (a) discarded calls and (b)
`cost==0` models (it only records entries where `cost>0`). SR-2 (W3 predecessor via the chain, and
W2 origin) removes MOST discards by serving genuine downgrades; SR-5 adds pricing so most models now
cost>0. SR-7 closes the remaining hole.

## What to build (in spend_limits.py + proxy_server.py)
1. Record an ESTIMATED cost even when the computed cost is 0, so a zero-priced or otherwise
   uncosted-but-served response still advances the cap — the cap can't be bypassed.
2. Keep the universal monthly cap semantics: one global cumulative total across providers, and the
   monthly reset still fires.

## Acceptance / tests
- A zero-priced but SERVED response still advances the cap via the estimate (assert the cumulative
  total increases).
- The cap still resets monthly (existing reset behavior preserved).
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/spend_limits.py`, `src/charon/proxy_server.py`. Do NOT touch config/discover/
  providers (SR-5) — consume the pricing they added, don't re-implement it.
- Provider/agent-agnostic; product-clean.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_spend_limits.py tests/test_proxy_server.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/spend_limits.py src/charon/proxy_server.py && mypy src/charon/spend_limits.py src/charon/proxy_server.py
```

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
