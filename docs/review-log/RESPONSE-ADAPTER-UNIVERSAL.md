# RESPONSE-ADAPTER-UNIVERSAL — review log

**Ticket:** RESPONSE-ADAPTER-UNIVERSAL (frontier / bugfix, money-path)
**ADR:** `fleet/ADR-UNIVERSAL-RESPONSE-ADAPTER.md` (T1–T5; T6 streaming DEFERRED)
**Base:** `feat/response-adapter-universal` off `origin/master` @ `3b434dc`
(BILLING-EST-COST-FIX #88 already merged — branched off it, no rebase conflict).

## What landed
- **`response_adapters.py` (new):** `ResponseAdapter` Protocol (`@runtime_checkable`);
  `IdentityAdapter` + `IDENTITY` singleton (byte-identical passthrough, the default for
  every provider); `ClineAdapter` (unwraps `{"data":{…choices…},"success":true}` →
  inner OpenAI object; guarded + idempotent + total; error unwrap for
  `{"data":{"error":…},"success":false}`); `_ADAPTERS` registry + `get_adapter`
  (unknown/absent → `IDENTITY`). Stdlib-only, no network.
- **Plumbing (mirrors `wire`):** `adapter: str|None` on `ProviderPreset` → resolved in
  `_route_from_spec` (per-model override wins, then preset) → `adapter` field on
  `UpstreamRoute` → `get_adapter(route.adapter)` resolved once per attempt in the forwarder.
  `resolve()` now carries the `adapter` override key.
- **`cline-pass` preset:** `base=https://api.cline.bot/api/v1`, `key_env=CLINE_PASS_API_KEY`,
  `strip_v1=True`, `adapter="cline"`, note documenting the no-`/models` setup-probe caveat.
- **Forwarder plug-in (guarded by `if route.adapter:` so IDENTITY is provably byte-identical):**
  - non-stream 200: between `_drain` and `_extract` — unwrap, re-encode ONLY if the object
    actually changed (`canon is not parsed`), so downgrade-detection + usage/cost see the
    canonical shape. Restores real `usage`/cost metering for cline non-stream.
  - non-200 terminal relay: `normalize_error` on the relayed error body (guarded).
  - streaming path untouched (Cline SSE already canonical; T6 deferred).

## Key decisions
- **Guard everywhere.** Every adapter call sits behind `if route.adapter`, and re-encode
  happens only on an actual change — the default (no-adapter) path never parses/re-serializes,
  so it stays byte-for-byte identical. Proven by `test_identity_provider_body_byte_identical`.
- **No fabricated usage (ADR §6 invariant).** ClineAdapter only unwraps a real inner OpenAI
  object; it never synthesizes a zero `usage`, so the "unknown pricing → nominal floor" path
  still applies rather than a false zero.
- **Layer boundary.** Shape/envelope adapter (this) runs FIRST; the existing content
  `response_normalizer` runs after, on the canonical body — unchanged.

## Verification
- Accept: `pytest tests/test_proxy_server.py tests/test_response_adapters.py -q` → 38 passed.
- FAIL-ON-REVERT: `test_proxy_nonstream_cline_shaped_upstream_returns_openai_body` asserts
  client body has top-level `choices` (content matches inner) AND `limiter._spent_usd > 0`
  (reverting the shim → wrapped body → no `choices`, cost 0 → RED).
- Full gate: `ruff` OK · `mypy` OK (172 files) · `charon gate` all checks OK · full suite
  1315 passed.
- Product-standalone: no `/home/stack`/fleet/SLOP/runner refs in `src/` or config.

## Adversarial notes (money-path)
- Cost metering: with the adapter, the unwrapped inner `usage.cost` flows through
  `observer.classify → spend_limiter.record` exactly as a native OpenAI body would; without
  it, top-level `usage` is absent → cost silently 0 (the bug this fixes).
- Idempotency: a canonical body (already has top-level `choices`) is returned unchanged, so a
  double-apply or an already-unwrapped upstream is safe.
- Error path guarded and low-risk (Cline error envelope shape unverified — conservative
  passthrough when no inner `error` present; ADR Q2).
