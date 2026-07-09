# SR-1 — P0: fix namespaced-id false-downgrade double-bill

## Dependencies & sequence
**depends_on: (none) — Wave 1 (W1), ships ALONE.** This is the P0 root-cause fix the whole SR
series builds on; land + merge it before opening W2. Concurrency-safe: owns only `src/charon/proxy.py`
and a NEW test file `tests/test_proxy_downgrade.py` — no other live SR ticket touches either, so it
can run with nothing else in flight. SR-2 depends on this (same classify()/failover decision).

## Shared context (grounding for a fresh session)
Charon's failover loop treats a 200 whose returned model id differs from the requested id as a
"silent downgrade": it discards that already-billed completion (`count_usage=False`) and refetches
from the next provider — DOUBLE-BILLING. CONFIRMED live: `recent_failovers` = 50/50 entries with
`status==200`, all `asked 'deepseek-v4-pro', got 'accounts/fireworks/models/deepseek-v4-pro'` — the
provider just returned the SAME model under its namespaced id. Root cause: `_normalize_model_id`
(`src/charon/proxy.py:174-184`) strips only the FIRST `/` segment, so a namespaced echo of the same
model still looks different. `classify()` is at `proxy.py:243-252`; the discard branches are
`proxy_server.py:756-760` (non-stream) and `:814-817` (stream); the `X-Charon-Downgrade` header is
already computed/sent at `proxy_server.py:778/820`.

## What to build
1. Change `_normalize_model_id` to compare the FINAL path segment:
   `return model_id.rsplit("/", 1)[-1]` — so `accounts/fireworks/models/deepseek-v4-pro` normalizes
   to `deepseek-v4-pro` and equals a bare `deepseek-v4-pro`.
2. Confirm `classify()` (`proxy.py:243-252`) uses `_normalize_model_id` for its pseudo_success /
   downgrade test, so the normalization actually reaches the failover decision.

**OUT OF SCOPE (do NOT add here):** naive version-suffix tolerance (`gpt-4o` vs
`gpt-4o-2024-11-20`). Plain `startswith` is too loose — it would wrongly equate `gpt-4` and `gpt-4o`.
Handle ONLY the path-segment (namespace) case in this ticket.

## Acceptance / tests
New file `tests/test_proxy_downgrade.py`:
- A namespaced 200 (`accounts/fireworks/models/deepseek-v4-pro` for requested `deepseek-v4-pro`) is
  NOT classified as pseudo_success / downgrade.
- Bare id and single-prefix (`fireworks/deepseek-v4-pro`) cases still match the requested model.
- A GENUINE different family (requested `opus`, got `haiku`) is STILL flagged as a downgrade.
- Post-deploy expectation (document in the test/PR): `recent_failovers` stops logging `status==200`
  for namespaced echoes.
- Full suite green: `PYTHONPATH=src python3 -m pytest -q` (≈1016 tests).

## CONSTRAINTS
- **Owns:** `src/charon/proxy.py`, `tests/test_proxy_downgrade.py` (NEW). Touch nothing else.
- Provider/agent-agnostic; no hardcoded model names in the engine path. Product-clean.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_proxy_downgrade.py tests/test_proxy.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy.py && mypy src/charon/proxy.py
```
