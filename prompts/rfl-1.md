# RFL-1 — proactive free-tier quota tracking (sliding-window RPM/TPM/RPD + pre-flight)

## Dependencies & sequence
**depends_on: SR-13 — sequences AFTER the whole proxy_server.py single-writer chain.** `proxy_server.py`
has a strict single-owner chain (SR-2 -> SR-6 -> SR-7 -> SR-8 -> TIER-SELECT -> SR-5b -> SR-13); SR-13
is the current TAIL. RFL-1 wires a pre-flight quota check into the failover/selection call site in
`_handle`, so it MUST rebase onto the final file and never write it concurrently (`real-dep: SR-13
build`, single-owner file). RFL-1 then becomes the new tail; RFL-3 -> RFL-2 -> RFL-4 sequence after it.
**Split option:** the new `src/charon/quota.py` module + `tests/test_quota.py` are fully INDEPENDENT of
the chain (pure stdlib, no proxy_server.py touch) and could ship as an earlier phase; only the ~call-site
wiring needs the rebase. Concurrency-safe against RFL-5 (disjoint owns — new module).

## Why
This is the TOP pick from the RelayFreeLLM comparison (R1). Charon's whole reason to exist is free-tier
failover, yet it is purely REACTIVE: it only learns a provider is exhausted AFTER sending a request and
getting a 429 (`set_cooldown`, Retry-After aware). That burns a request + latency + a 429 to learn what
a counter already knew, and trips provider abuse heuristics. RelayFreeLLM tracks per-(provider,model)
request+token deques over sliding windows and does a pre-flight `can_handle()` so it never sends a
doomed request; `get_wait_time()` computes exact seconds to availability. Adopting this lets Charon SKIP
a provider that would 429 and pick the one with the most remaining quota — better than
round-robin-until-429. This COMPLEMENTS, does not replace, the existing Retry-After cooldown.

## Shared context (grounding for a fresh session)
- Failover loop is `proxy_server.py:_handle` (~:515). The provider chain is built at ~:649
  (`srv.chain_for(requested)`) and ordered at ~:697 (`srv.order_by_cooldown(chain)` — fresh providers
  first, cooled last). The quota exclude/order hook goes right alongside `order_by_cooldown`.
- Per-response token counts are already available on the success path (usage). Record usage there.
- Note the DIFFERENT axis: virtual keys already carry `max_rpm`/`max_tpm` — that is CLIENT-side
  throttling. RFL-1 is UPSTREAM provider free-tier quota. Both are worth having; keep them separate.

## What to build
1. **`src/charon/quota.py` (new, stdlib-only).** A thread-locked `QuotaTracker` mirroring RelayFreeLLM's
   `api_limits_tracker.py`, keyed by (provider/upstream_base, model):
   - `collections.deque` of `time.monotonic()` timestamps for REQUESTS over 1s / 60s / 1h / 24h windows,
     and of (timestamp, token_count) for TOKENS over 60s / 1h / 24h.
   - `can_handle(provider, model, est_tokens) -> bool` — evict entries older than each window, then check
     every configured limit (RPM/RPS/RPD, TPM/TPH/TPD) has headroom for one more request + `est_tokens`.
   - `get_wait_time(provider, model, est_tokens) -> float` — seconds until the tightest window frees up
     (0.0 if it can handle now).
   - `record(provider, model, tokens)` — append a request + token sample.
   - Limits come from provider/model metadata (Charon already captures model metadata + pricing);
     accept an overridable limits config (a `provider_model_limits.json`-style dict / the providers
     config `limits: {...}` field). A missing limit = unlimited on that dimension (no false blocking).
2. **Wire into the failover loop (proxy_server.py).** At the pool exclude/order step (alongside
   `order_by_cooldown`), skip chain entries where `can_handle()` is False; prefer the entry with the
   most remaining headroom / shortest `get_wait_time()`. On each successful response, call
   `record(provider, model, tokens)`. Keep it ADDITIVE and guarded — if the tracker has no limits for a
   provider it must be a no-op (never block a provider we have no data for).

## Acceptance / tests (`tests/test_quota.py` + regression)
- `can_handle` returns False once a window's request/token budget is exhausted and True again after the
  window slides past (drive `time.monotonic` via a small injectable clock — keep the test hermetic, no
  real sleeps).
- `get_wait_time` returns ~the remaining seconds of the tightest window; 0.0 when it can handle now.
- A provider with NO configured limits is never blocked (no-op path).
- The failover loop skips a quota-exhausted provider WITHOUT making an upstream call to it (assert the
  exhausted upstream is not invoked) and records usage on success.
- Full suite green.

## Red-proof
Add at least one test that FAILS if the pre-flight check is removed (e.g. assert the exhausted upstream
is never called) so the gate can prove the feature is live.

## CONSTRAINTS
- **Owns:** `src/charon/quota.py`, `src/charon/proxy_server.py`, `tests/test_quota.py`. Touch nothing
  else. Do NOT edit proxy.py, gateway.py, spend_limits.py.
- **Stdlib only** — `collections.deque` + `time` + `threading`; NO third-party imports.
- Provider/agent-agnostic; product-clean; no `/home/stack` paths or dev-meta in committed files.
- Additive + backward-compatible: with no limits configured, behavior is unchanged.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_quota.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/quota.py src/charon/proxy_server.py && mypy src/charon/quota.py src/charon/proxy_server.py
```
