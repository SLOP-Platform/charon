# RFL-4 — inline limit editor + hot-reload in the console (pairs with RFL-1)

## Dependencies & sequence
**depends_on: RFL-2, RFL-1 — Wave RFL, on the proxy_server.py single-writer chain.** `proxy_server.py`
is the single-writer bottleneck (chain … SR-13 -> RFL-1 -> RFL-3 -> RFL-2). RFL-4 adds POST endpoints +
console-table edits to the SAME file, so it MUST rebase onto RFL-2's file, never write it concurrently
(`real-dep: RFL-2 build`, single-owner file). It ALSO has a FUNCTIONAL prereq on RFL-1 (`real-dep: RFL-1
build`): there is nothing to hot-edit until RFL-1's quota tracker + limits config exist — RFL-4 edits
those exact RPM/TPM/RPD numbers. RFL-4 is the current TAIL of the RFL proxy_server.py chain.
Concurrency-safe vs RFL-5 (disjoint owns).

## Why
RelayFreeLLM comparison R4. Pairs naturally with RFL-1: you need to SEE and TUNE the upstream quota
numbers. Turns Charon's read-only status console into an ops surface. Good home-user ergonomics.

## Shared context (grounding for a fresh session)
- The console renders a provider/pool table inline in `proxy_server.py` (dashboard ~:99/:326; setup
  page ~:575). The setup page already POSTs to console endpoints (e.g. `/charon/pools` ~:277) behind the
  token gate — mirror that pattern.
- RFL-1 introduces `src/charon/quota.py` (per-provider/model RPM/TPM/RPD limits) + an overridable limits
  config persisted to a config file. RFL-4 edits THOSE.

## What to build (proxy_server.py)
Make the console's provider/limit view EDITABLE:
- Add POST endpoint(s) behind the EXISTING console token gate that accept edited RPM/TPM/RPD/cooldown
  (and enabled/disabled) values, VALIDATE them, mutate the in-memory quota/limits config (RFL-1's
  tracker), and PERSIST to the config file — applied WITHOUT a restart (hot-reload).
- Add the inline edit controls to the already-rendered provider table (vanilla JS, self-contained).
Additive + token-gated; no change to `/v1/*`.

## Acceptance / tests (`tests/test_limit_editor.py` + regression)
- A POST (authorized) to the limit endpoint updates the in-memory limits AND persists to the config file;
  a subsequent read reflects the new value with NO restart.
- The write path is token-gated (unauthorized POST rejected) and validates inputs (bad values rejected,
  not silently applied).
- Full suite green.

## Red-proof
Include a test that FAILS if the update does not hot-reload (assert the in-memory tracker reflects the
new limit immediately) so the gate proves the feature is live.

## CONSTRAINTS
- **Owns:** `src/charon/proxy_server.py`, `tests/test_limit_editor.py` ONLY. Do NOT edit quota.py (RFL-1
  owns it) — consume its public API.
- Stdlib only; self-contained console assets; provider/agent-agnostic; product-clean; no `/home/stack`
  paths or dev-meta. Guard the write path (token gate + input validation).

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_limit_editor.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy_server.py && mypy src/charon/proxy_server.py
```
