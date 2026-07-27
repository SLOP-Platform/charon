# SR-5b — wire captured pricing into cost_usd (the consumption half of SR-5)

## Dependencies & sequence
**depends_on: SR-5, SR-2, TIER-SELECT — after the SR proxy_server.py chain.** SR-5 (W2) CAPTURES
per-token pricing into the model registry; this ticket CONSUMES it. `real-dep: SR-5 build` — the
pricing must be captured and stored in SR-5's canonical unit before the multiply is meaningful; owns
are disjoint (SR-5 config/discover/providers vs SR-5b proxy.py/proxy_server.py), so the dep is a
JUSTIFIED build/correctness prereq, not merge-order. **Coordinate the price UNIT with SR-5** (per-token
vs per-million-token): read whatever canonical unit SR-5 persisted and match it exactly. `real-dep:
SR-2 / TIER-SELECT build` — proxy_server.py has a strict single-owner chain
SR-2 -> SR-6 -> SR-7 -> SR-8 -> TIER-SELECT; SR-5b lands AFTER TIER-SELECT (the last current owner) so
it rebases onto the final file and is never a concurrent second writer. That chain also transitively
orders SR-5b after SR-1 (the proxy.py owner, via SR-2 -> SR-1). SR-5b is then the sole live owner of
proxy.py + proxy_server.py, concurrency-safe. **SR-13 sequences after SR-5b** (next proxy_server.py
owner).

## Shared context (grounding for a fresh session)
Charon's usage ledger records `cost_usd` in `_gateway_usage` (`proxy.py` ~:98). Today it reads ONLY the
provider's self-reported `cost` / `total_cost` field. Most providers do NOT echo a per-request cost, so
those requests record `cost_usd=0`. SR-5 (W2) fixed the OTHER half — it captures each model's per-token
input/output pricing into the registry — but nothing multiplies that pricing by the actual token counts,
so the ledger is still 0 for cost-less providers. Downstream effect: cost-based ranking and the monthly
spend cap are BOTH inert for most providers (the cap only meaningfully records entries where cost>0).
This is the root of the "cost_usd always 0 / availability-only routing" symptom seen all session. Two
more sites in `proxy_server.py` use the wrong number: the pre-flight spend estimate (~:657) uses a
HARDCODED rate, and `spend_limiter.record` (~:777) records the provider's self-reported number.

## What to build (proxy.py + proxy_server.py only)
1. **Compute cost_usd from stored pricing when the provider reports none.** In `_gateway_usage`
   (`proxy.py` ~:98), when the provider does NOT return a cost field, compute
   `cost_usd = tokens_in * cost_input + tokens_out * cost_output` from the model's stored pricing
   (units per SR-5's canonical unit — coordinate with SR-5). When the provider DOES report a cost, keep
   using it (unchanged). **Distinguish three states explicitly:** (a) provider-reported cost → use it;
   (b) no provider cost but model IS priced → compute it; (c) model is UNKNOWN/unpriced → leave
   `cost_usd=0` AND flag it (do not silently treat unpriced as free, and do not confuse it with a model
   that is genuinely priced at 0).
2. **Feed the same computed cost to the spend limiter.** In `proxy_server.py`, replace the hardcoded
   pre-flight estimate rate (~:657) and the provider number passed to `spend_limiter.record` (~:777)
   with the SAME computed cost from (1), so the pre-flight estimate and the recorded spend both reflect
   real stored pricing. Do NOT modify `spend_limits.py` itself — that is SR-7's file; only change its
   call sites in proxy_server.py.

## Acceptance / tests
- A provider that returns usage WITHOUT a cost field yields a NONZERO `cost_usd` computed from the
  model's stored pricing; a test asserts the actual computed number end-to-end (tokens x price).
- The spend limiter trips on the COMPUTED cost (a request over a small monthly cap is blocked/flagged on
  the computed number, not the provider's absent/zero number).
- An UNKNOWN/unpriced model stays `cost_usd=0` AND is flagged (not silently 0); a model genuinely priced
  at 0 is distinguishable from unpriced.
- A provider that DOES report a cost still uses that reported cost (no regression).
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/proxy.py`, `src/charon/proxy_server.py` ONLY (+ their tests). Do NOT touch
  config.py / discover.py / providers.py (SR-5) or spend_limits.py (SR-7) — only proxy_server.py's
  spend-limiter CALL SITES.
- Provider/agent-agnostic (no hardcoded per-model prices — pricing comes from the registry SR-5
  populates or SR-5's configurable fallback); product-clean; money-path math must be exact.
- Never re-bill or double-count: computing cost_usd changes only the RECORDED number, never the number
  of upstream calls.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_proxy.py tests/test_proxy_server.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy.py src/charon/proxy_server.py && mypy src/charon/proxy.py src/charon/proxy_server.py
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
