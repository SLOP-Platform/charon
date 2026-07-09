# SR-8 — wire the 6 constructed-but-dead modules (DECISION CLEARED)

## ✅ DECISION CLEARED (operator-approved 2026-07-04): WIRE all 6 modules per `SR-8-RECS.md`
No recommendation step is needed — the operator has signed off. **WIRE all six** modules into
`_handle()`; none are removed or left-marked. Implement exactly these approved per-module decisions
(you need no other doc — these are the full instructions):

1. **Observability** — WIRE **always-on**. Export path only, zero spend/latency risk; docs already
   claim it fires.
2. **RequestInspector** — WIRE **always-on**. Pure single-pass hints, stdlib, no cost; makes the code
   match the docs.
3. **SessionAffinity** — WIRE **always-on**. Pins `X-Session-ID`; keeps Anthropic prompt caches warm.
4. **VirtualKeyManager** — WIRE **opt-in**, inert unless `virtual_keys.json` is present (no keys →
   no-op auth/quota gate).
5. **SpeculativeExecutor** — WIRE **opt-in / OFF by default**. Races N providers → multiplies spend;
   gate on `speculative.json`.
6. **ConsensusRouter** — WIRE **opt-in / OFF by default**. Cross-provider verify → multiplies spend;
   gate on `consensus.json`.

**Cost-multiplier guard (HARD):** #5 SpeculativeExecutor and #6 ConsensusRouter MUST be OFF by
default and only activate on their explicit config file — they multiply spend. Tests must assert both
are OFF absent their gate file.

## Dependencies & sequence
**depends_on: SR-2, SR-6, SR-7 — Wave 3 (W3), LAST in the SR-6 → SR-7 → SR-8 chain.**
- `real-dep: SR-2 build (single-owner file proxy_server.py)` — shared-file sequencing.
- `real-dep: SR-6 build (single-owner file proxy_server.py)` — shared-file sequencing.
- `real-dep: SR-7 build (single-owner file proxy_server.py)` — shared-file sequencing; SR-8 lands
  LAST so all four proxy_server.py owners (SR-2/6/7/8) are fully ordered and never write the file
  concurrently.
Concurrency-safety: strictly ordered chain → SR-8 is the sole writer of proxy_server.py while in
flight. The module files it owns (consensus, speculative_execution, request_inspector,
session_affinity, virtual_keys, observability) are owned by no other live SR ticket.

## Shared context (grounding for a fresh session)
Part of the SR gateway cost-correctness series. Six modules are CONSTRUCTED in the proxy_server
constructor (`proxy_server.py:882-924`) but NEVER invoked in `_handle()`: consensus,
speculative(_execution), request_inspector, session_affinity, virtual_key(s)_manager, observability.
SR-4 (W2) already corrected the SMART-ROUTING.md docs to stop claiming speculative + consensus fire;
SR-8 makes the CODE match a decision.

## What to build (decision is CLEARED — go straight to implementation)
1. Wire ALL SIX modules into `_handle()` per the approved decisions above (no removals, no
   leave-marked). Each module ends WIRED.
2. **Cost-multiplier guard:** `speculative_execution` (races N providers) and `consensus`
   (cross-provider verify) are wired opt-in and OFF by default — they multiply spend. Gate them on
   `speculative.json` / `consensus.json` respectively.

## Acceptance / tests
- Each of the six modules is invoked in `_handle()` (no module remains silently constructed-but-dead).
- The 4 always-on modules (Observability, RequestInspector, SessionAffinity, VirtualKeyManager) fire
  by default; VirtualKeyManager is a no-op without `virtual_keys.json`.
- Speculative + consensus tests assert they are OFF by default and require explicit opt-in
  (`speculative.json` / `consensus.json`).
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/proxy_server.py`, `src/charon/consensus.py`,
  `src/charon/speculative_execution.py`, `src/charon/request_inspector.py`,
  `src/charon/session_affinity.py`, `src/charon/virtual_keys.py`, `src/charon/observability.py`.
- Provider/agent-agnostic; product-clean; cost-multipliers opt-in + OFF by default if wired.

## accept
```
PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy_server.py src/charon/consensus.py src/charon/speculative_execution.py src/charon/request_inspector.py src/charon/session_affinity.py src/charon/virtual_keys.py src/charon/observability.py && mypy src/charon
```
