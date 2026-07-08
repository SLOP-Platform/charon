tier: opus
work_class: ci-infra
branch: feat/docker-install
depends_on:
owns: Dockerfile, docker-compose.yml, .dockerignore, docs/docker.md, .env.example, README.md
prompt: /home/stack/charon-private/prompts/docker-install.md
scope: PRODUCTION-READINESS / fresh-install. Make `docker compose up` and
  `docker run ghcr.io/slop-platform/charon` a FIRST-CLASS fresh-install path — a clean,
  token-gated, OpenAI-compatible Charon GATEWAY with PERSISTENT config that needs NO host Python
  (sidesteps the Python-3.11 barrier hit on charon-vm 2026-06-27: Ubuntu 22.04 / Python 3.10 /
  no pip). Build ON the existing Dockerfile / docker-compose.yml / GHCR `release.yml` scaffolding;
  do NOT greenfield. Closes the gaps that block a turnkey container gateway:
  (1) CONFIG PERSISTENCE — image sets `CHARON_STATE_DIR=/work/.charon` (Mode-B service state), but
      the GATEWAY's config dir is `$CHARON_HOME` (secrets.config_dir()), which the image does NOT
      set → gateway config defaults to an UNMOUNTED `~/.charon` and is lost on restart. Set
      `CHARON_HOME=/data` (chown'd to uid 10001), `VOLUME /data`, mount it in compose.
  (2) ENTRYPOINT / TOKEN GUARD — default CMD is `charon gateway --host 0.0.0.0` with NO token;
      `build_server` RAISES `NonLoopbackBindWithoutToken` → raw traceback. Add a small POSIX-sh
      entrypoint that refuses cleanly with a friendly message (mirror the guard; show
      `openssl rand -hex 16`) and reads `CHARON_GATEWAY_TOKEN`, while passing through `setup` /
      `providers add` / other subcommands.
  (3) FIRST-TIME SETUP in a container — support + document three paths; lead with
      `docker compose run --rm gateway setup` writing into the mounted volume.
  (4) HEALTHCHECK — `HEALTHCHECK` on `GET /v1/models` (token-aware, zero-dep urllib).
  (5) COMPOSE — gateway as the default `up` target (Mode-B stays behind `profile: service`),
      loopback port map, config volume, `CHARON_GATEWAY_TOKEN` env + `.env.example`,
      `restart: unless-stopped`, `host.docker.internal`, healthcheck.
  (6) DOCS — bulk in NEW `docs/docker.md`; only a MINIMAL pointer touch in `README.md`
      (collision-aware — keep the edit tiny).
  (7) VERIFY — `docker build` + (if Docker available) `docker compose up` serves `/v1/models`
      with the token; else build + `docker compose config` + config sanity.
note: ACTIVE / claimable. Canonical tier high → fleet `opus` (fresh-install-critical; entrypoint +
  setup design). owns is the docker surface + `docs/docker.md` + `.env.example` + a SINGLE minimal
  `README.md` pointer.
  OWNS-COLLISION CHECK (authoring, 2026-06-27): no ACTIVE ticket owns Dockerfile / docker-compose.yml
  / .dockerignore / docs/docker.md / .env.example. `README.md` is also owned by E7 and FR1 — BOTH
  DONE (state/done/) — so the validator reports an all-done hand-off (INFO), NOT a live collision.
  PROVISIONAL: `.dockerignore` does not yet exist on master (droid may add it); `.env.example` is
  new; the exact `CHARON_HOME` mount point (`/data` vs `/config`) is the droid's call — pick one and
  use it consistently. `release.yml` is INTENTIONALLY NOT owned: its `image-smoke` job
  (`:8473` + `/healthz`, the Mode-B path) does NOT match the gateway default (`:8080` + `/v1/models`,
  token-gated) — the droid FLAGS this in the PR for a coordinated manager follow-up; it must NOT
  edit release.yml without re-scope.
  CONSTRAINTS: product-clean (no SLOP/fleet/rig leak), agent/provider-agnostic, MUST NOT break the
  pip/curl/pipx install or the Mode-B `charon-service` profile, keep the image lean.
