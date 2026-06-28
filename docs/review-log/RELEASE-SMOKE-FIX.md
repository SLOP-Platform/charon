# RELEASE-SMOKE-FIX review note

**Date:** 2026-06-27
**Ticket:** RELEASE-SMOKE-FIX
**Branch:** feat/release-smoke-fix

## What changed

Rewrote the `image-smoke` job's "run service + healthz" step in
`.github/workflows/release.yml` to exercise the image's actual default surface.

**Before:**
```yaml
docker run -d --name charon-rel -p 127.0.0.1:8473:8473 charon:ci
curl -fsS http://127.0.0.1:8473/healthz
```

**After:**
```yaml
docker run -d --name charon-rel \
  -e CHARON_GATEWAY_TOKEN=ci-smoke-token \
  -p 127.0.0.1:8080:8080 charon:ci
# polls /v1/models with Authorization: Bearer, asserts HTTP 200
```

Step renamed from "run service + healthz" → "run gateway + /v1/models".

## Why

Surfaced by the DOCKER-INSTALL #64 review finding (2026-06-27): the `Dockerfile`
already defaults to `CMD ["charon","gateway","--host","0.0.0.0","--port","8080"]`,
but the smoke still targeted `:8473/healthz` (the old Mode-B service surface).

Two failure modes for the next release:
1. The gateway serves on `:8080`, not `:8473` — the port mapping was wrong.
2. A tokenless `0.0.0.0` bind is rejected (`NonLoopbackBindWithoutToken`) — the
   container would refuse to start at all without a `CHARON_GATEWAY_TOKEN`.

## Decisions

- **Token:** fixed literal `ci-smoke-token` — satisfies the non-loopback-bind guard
  for an ephemeral CI container; no secrets management needed.
- **Health check:** `GET /v1/models` with `Authorization: Bearer` header; gateway
  returns HTTP 200 with an empty model list before any provider is configured.
- **Mode-B smoke dropped:** `/healthz` on `:8473` is the Mode-B service surface,
  which is already exercised by the `pytest` suite in the `gate` job. No second
  container added.
- **Publish gate untouched:** `needs: [gate, image-smoke]` wiring, digest-pinning,
  SLSA provenance, and GHCR push steps are all unchanged.

## Scope check

Only `.github/workflows/release.yml` and `docs/review-log/RELEASE-SMOKE-FIX.md`
(this file) were created/modified — both within the ticket's `owns:`.
