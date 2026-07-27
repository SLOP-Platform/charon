# SR-5 — pricing / cost visibility

## Dependencies & sequence
**depends_on: (none) — Wave 2 (W2), parallel with SR-3 and SR-4.** Board-unblocked. Owns
`src/charon/config.py`, `src/charon/discover.py`, `src/charon/providers.py` — disjoint from SR-2
(proxy_server.py), SR-3 (cache.py), SR-4 (doc). Concurrency-safe within W2. SR-5 is a real
prereq for SR-7 (W3), which needs this pricing to estimate cost for the spend cap.

## Shared context (grounding for a fresh session)
Part of the SR gateway cost-correctness series. Live `usage.cost_usd` reads `0.0` because
imported/discovered models carry NO pricing metadata → both the usage LEDGER and the spend CAP are
blind (the cap only records entries where `cost>0`, so zero-priced models bypass it entirely). SR-7
(W3) later hardens the cap; this ticket gives it real numbers to work with.

## What to build
1. **Capture pricing on discovery/import.** Ensure discovered/imported models record their
   per-token input/output pricing (via `discover.py` / `providers.py`) into the model registry
   (`config.py` schema) so served models carry cost data.
2. **Configurable per-token fallback.** Add a configurable fallback per-token price so cost>0 even
   when a provider gives no pricing — so nothing silently costs 0.
3. **Surface unknown-pricing models.** In status output, FLAG models with unknown/absent pricing
   (do not silently treat them as free).

## Acceptance / tests
- A model WITH pricing yields `cost_usd > 0` for a sized request (assert non-zero).
- A model with unknown pricing is FLAGGED in status (not silently 0); the configurable fallback,
  when set, makes its cost > 0.
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/config.py`, `src/charon/discover.py`, `src/charon/providers.py`. Do NOT
  touch proxy_server.py or spend_limits.py (that is SR-7's job in W3).
- Provider/agent-agnostic (no hardcoded prices per named model — pricing comes from the provider or
  the configurable fallback); product-clean; config-path only, never the hot request path.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_discover.py tests/test_config.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/config.py src/charon/discover.py src/charon/providers.py && mypy src/charon/config.py src/charon/discover.py src/charon/providers.py
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
