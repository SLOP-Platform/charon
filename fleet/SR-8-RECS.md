# SR-8 — Dead-module wire/remove/leave recommendations

**Summary:** All **6** modules are confirmed constructed and stored on the server
(`proxy_server.py` ctor, `self.<x> = <x>`) but **never invoked in `_handle()`** — dead on the hot path.
**Overall lean: WIRE all six** — 4 are free/read-only (wire always-on to make code match the
"always on" docs), 2 are cost-multipliers (wire only as opt-in / OFF-by-default). **None recommended
for removal** — each is a documented feature with a config surface; removing would contradict
SMART-ROUTING.md.

Ordered by confidence (highest first):

`Observability — WIRE (always-on) — export path only, zero spend/latency risk, docs already claim it fires`
`RequestInspector — WIRE (always-on) — pure single-pass hints, stdlib, no cost; makes code match docs`
`SessionAffinity — WIRE (always-on) — pins X-Session-ID; keeps Anthropic prompt caches warm (SR-6 multiplier)`
`VirtualKeyManager — WIRE (opt-in, inert unless virtual_keys.json present) — auth/quota gate, no keys → no-op`
`SpeculativeExecutor — WIRE (opt-in, OFF by default) — races N providers, multiplies spend; gate on speculative.json`
`ConsensusRouter — WIRE (opt-in, OFF by default) — cross-provider verify, multiplies spend; gate on consensus.json`
