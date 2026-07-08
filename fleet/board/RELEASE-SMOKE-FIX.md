tier: sonnet
work_class: ci-infra
branch: feat/release-smoke-fix
depends_on:
owns: .github/workflows/release.yml
prompt: /home/stack/charon-private/prompts/release-smoke-fix.md
scope: CI / release pipeline. The release workflow's `image-smoke` job still does the OLD Mode-B
  smoke (`docker run -p 127.0.0.1:8473:8473` + `curl http://127.0.0.1:8473/healthz`), but the
  published image's DEFAULT is now the token-gated GATEWAY: master's Dockerfile ends with
  `EXPOSE 8080` + `CMD ["charon","gateway","--host","0.0.0.0","--port","8080"]`, health =
  `GET /v1/models` (token-gated), and a tokenless `0.0.0.0` bind is REFUSED
  (`NonLoopbackBindWithoutToken`). So the next release's `image-smoke` would FAIL. Fix: run the
  image with a `CHARON_GATEWAY_TOKEN`, curl `http://localhost:8080/v1/models` with the
  `Authorization: Bearer` header, assert HTTP 200 (gateway returns 200 with an empty model list
  pre-config). Drop or properly re-target the stale `:8473`/`/healthz` Mode-B smoke. Minimal change
  to `release.yml`; do NOT touch the gate/publish jobs or break the publish gate.
note: ACTIVE / claimable. Surfaced by the DOCKER-INSTALL (#64) review finding (2026-06-27): the
  DOCKER-INSTALL droid FLAGGED that `release.yml` `image-smoke` (`:8473` + `/healthz`, Mode-B path)
  does not match the gateway default (`:8080` + `/v1/models`, token-gated) and intentionally did
  NOT edit release.yml (out of its owns) — this ticket is that coordinated follow-up.
  OWNS-COLLISION CHECK (authoring, 2026-06-27): `.github/workflows/release.yml` is owned by NO
  other ACTIVE ticket. DOCKER-INSTALL.md explicitly does NOT own release.yml (it lists
  Dockerfile/docker-compose.yml/.dockerignore/docs/docker.md/.env.example/README.md). CI1 (the
  CI_RUNNER var ticket) touched release.yml's `runs-on` but is DONE (state/done/) — all-done
  hand-off, not a live collision. No depends_on: the master Dockerfile ALREADY defaults to the
  gateway on :8080, so this fix stands alone and does not need DOCKER-INSTALL to merge first
  (it is compatible whether or not DOCKER-INSTALL later adds an entrypoint/token guard, since the
  smoke passes the token through the env either way).
  CONSTRAINTS: product-clean (no SLOP/fleet/rig leak), agent/provider-agnostic, minimal diff to
  release.yml only, must NOT break the digest-pinned publish + SLSA provenance steps.
