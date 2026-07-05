tier: strong
branch: feat/sr-8-dead-module-decision
depends_on: SR-2, SR-6, SR-7
real-dep: SR-2 build (single-owner file proxy_server.py) — shared-file sequencing on proxy_server.py.
real-dep: SR-6 build (single-owner file proxy_server.py) — shared-file sequencing on proxy_server.py.
real-dep: SR-7 build (single-owner file proxy_server.py) — shared-file sequencing; SR-8 lands LAST in
  the W3 chain SR-6 -> SR-7 -> SR-8 so all four proxy_server.py owners (SR-2/6/7/8) are fully
  ordered and never write the shared file concurrently.
owns: src/charon/proxy_server.py, src/charon/consensus.py, src/charon/speculative_execution.py, src/charon/request_inspector.py, src/charon/session_affinity.py, src/charon/virtual_keys.py, src/charon/observability.py
prompt: /home/stack/charon-private/prompts/sr-8.md
scope: W3, last in the SR-6 -> SR-7 -> SR-8 chain. DECISION CLEARED (operator-approved 2026-07-04):
  WIRE all 6 modules per SR-8-RECS.md. Approved per-module decisions:
    - Observability      — WIRE always-on
    - RequestInspector   — WIRE always-on
    - SessionAffinity    — WIRE always-on
    - VirtualKeyManager  — WIRE opt-in (inert without virtual_keys.json)
    - SpeculativeExecutor — WIRE opt-in / OFF by default (gate speculative.json)
    - ConsensusRouter    — WIRE opt-in / OFF by default (gate consensus.json)
