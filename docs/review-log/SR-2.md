## 2026-07-03 — SR-1/SR-2 — silent-downgrade double-bill incident + fix

- **Incident:** the gateway failover loop treated any 200 whose returned `model` id
  differed from the requested id as a "silent downgrade": it discarded that
  already-billed completion (`count_usage=False`) and refetched from the next
  provider — **double-billing** an already-paid 200. Confirmed live: `recent_failovers`
  was 50/50 with `status==200`, every one `asked 'deepseek-v4-pro', got
  'accounts/fireworks/models/deepseek-v4-pro'`.
- **Root cause:** v0.2.0 compared model ids raw (`returned != expected`).
  feat/prod-install's `_normalize_model_id` stripped only the FIRST `/`-segment, so a
  provider-namespaced echo like `accounts/fireworks/models/deepseek-v4-pro` normalized
  to `fireworks/models/deepseek-v4-pro`, still `!=` the bare `deepseek-v4-pro` → the
  same model was false-flagged as a downgrade. The discarded attempt was invisible in
  `/charon/status` because `count_usage=False` (plus missing pricing) hid the spend.
- **Fix — SR-1 (`proxy.py`):** compare the FINAL `/`-segment, so namespace-only
  differences (`accounts/fireworks/models/<id>` vs `<id>`) are recognized as the same
  model and are no longer flagged. Genuine family differences (opus vs haiku) still
  flag.
- **Fix — SR-2 (`proxy_server.py`):** for the GENUINE downgrades that remain, stop
  discard-and-rebill. A completed 200 is already billed, so the failover loop now
  SERVES it with the existing `X-Charon-Downgrade` header (both the non-stream and the
  streaming commit paths) instead of throwing it away and re-billing the next provider.
  A completed 200 is never re-billed. SR-2 also fixed the streaming path to populate
  the semantic cache (previously only the non-stream 200 was cached), and surfaced the
  running build via `CHARON_BUILD_SHA` in `/charon/status` (SR-10 rider).
- **Tests:** a genuine downgrade with an alternative provider is served-with-header and
  makes NO second upstream call (asserted the alternative upstream is invoked zero
  times); a streaming 200 populates the semantic cache (identical follow-up hits it);
  `/charon/status` includes the `build_sha` field. Two prior tests that asserted the
  old discard-and-rebill behavior (`test_gateway_failover.py`) were rewritten to assert
  serve-not-rebill.
- **Gate:** full suite green; ruff/mypy/boundary/version OK.
