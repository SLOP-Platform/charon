tier: strong
work_class: bugfix
branch: feat/inc-401-failover
depends_on:
owns: src/charon/proxy.py, src/charon/proxy_server.py, tests/test_proxy.py
accept: PYTHONPATH=src python3 -m pytest tests/test_proxy.py -v -q
prompt: /home/stack/charon-private/prompts/inc-401-failover.md
scope: BUG 2 fix from 2026-07-04 incident. Two problems in the failover loop:
  (1) `_is_auth_error()` (proxy.py:161-171) classifies a 401 as auth ONLY if the body matches
  `_AUTH_BODY_PATTERNS`; a 401 body like "Model gpt-5.5 is not supported" matches NEITHER
  `_EXHAUSTION_BODY_PATTERNS` NOR `_AUTH_BODY_PATTERNS`, so `obs.failover=False` and the loop
  does NOT advance — it relays the raw 401 to the client instead of trying the next provider.
  Fix: add a third classification — "unknown 401" or "model-not-found 401" — that triggers
  failover (not auth-terminate). Add patterns: "not supported", "model not found",
  "no such model", "unknown model". These are NOT auth errors; they are provider-capability
  mismatches that should fail over to the next pool member.
  (2) `proxy_server.py:751-756` relays the LAST provider's raw error body when the failover
  loop terminates (either `obs.failover=False` or `more=False`). There is NO synthesized
  "all providers exhausted" terminal. Fix: when the loop exhausts ALL pool members via
  failover, synthesize a clear error response:
  `{"error":{"type":"all_providers_exhausted","message":"All providers in the <model> pool failed","failover_reasons":[...]}}`
  with HTTP 502, instead of relaying the last raw upstream error. Preserve the
  `X-Charon-Failover-Reasons` header. When `obs.failover=False` (auth error, genuine
  non-failover), keep relaying the raw body — that path is correct.
  Tests: (a) 401 "not supported" body → failover advances, not terminates; (b) all pool
  members exhausted → synthesized 502 "all_providers_exhausted" response, not raw relay;
  (c) genuine auth 401 → still relays raw (no regression); (d) genuine billing 402 → still
  failovers (no regression). Suggested agent: DeepSeek V4-Pro (strong tier) — mechanical
  classification logic + well-specified test cases, no design judgement needed.
