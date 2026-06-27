# Review log — DOCKER-INSTALL

Make `docker compose up` / `docker run ghcr.io/slop-platform/charon` a first-class
fresh-install gateway path (no host Python). Built ON the existing Dockerfile /
compose / GHCR scaffolding; did not greenfield.

## Decisions

- **Mount point: `/data`** (not `/config`). Picked the ticket's lead option for a
  clean, gateway-specific config home; used consistently across Dockerfile (`ENV
  CHARON_HOME=/data`, `VOLUME /data`), compose, docs, entrypoint, and healthcheck.
- **Named volume `charon-config:/data`, not a bind.** A bind mount (`./dir:/data`)
  inherits host-uid ownership, so uid 10001 inside the container often can't write
  the `0700` config dir / `0600` secrets.json. A named volume is seeded from the
  image's `/data` (chown'd to 10001), so `setup` / `providers add` write cleanly
  and config persists across restarts. Bring-your-own bind is documented as path (c).
- **Entrypoint embedded in the Dockerfile via a BuildKit `COPY` heredoc**, not a
  separate `docker-entrypoint.sh`. Reason: a standalone script file is NOT in this
  ticket's `owns:`, and the strict ownership rule forbids creating off-list files.
  Embedding keeps it within `Dockerfile` (owned) and adds no image weight. Requires
  BuildKit, declared via the `# syntax=docker/dockerfile:1` directive (BuildKit is
  the default builder on Docker 23+ and on GitHub Actions runners).
- **Entrypoint guards ONLY the gateway path.** It mirrors `gateway.build_server`'s
  `GatewayBindRefused` invariant (non-loopback bind + no token → friendly refusal
  with `openssl rand -hex 16`, `exit 78`/EX_CONFIG) and passes through an implicit
  first arg matching charon's real subcommands — `run land work intake gateway
  providers models tier reset ledger doctor version setup` — as `charon <subcmd>`,
  while anything else (the Mode-B `uvicorn …` command, `sh`, …) is `exec "$@"`'d as a
  raw command, so the Mode-B profile is NOT broken. Token/host are also read from explicit `--token`/`--host` flags as a
  belt-and-braces check; the in-app guard remains the final backstop.
- **Healthcheck**: token-aware `GET /v1/models` via stdlib `urllib` (zero-dep; no
  curl in the slim image). Declared image-level (`HEALTHCHECK`) so `docker run`
  users get it, and mirrored in compose for explicitness.
- **Compose default**: a bare `docker compose up` already targeted `gateway`
  (Mode-B `charon-service` is behind `profile: service`); kept that, added the
  volume, healthcheck, `/data`, and `.env` wiring. Loopback port map retained;
  LAN-widening documented.
- **`.env.example`** added (empty `CHARON_GATEWAY_TOKEN=` + `openssl` hint). Note:
  `.gitignore` already ignores `.env.*`, which matches `.env.example`, so it was
  committed with `git add -f` (cannot edit `.gitignore` — not in `owns:`).

## FLAG for manager follow-up — `release.yml` image-smoke (NOT in my owns:)

`.github/workflows/release.yml`'s `image-smoke` job runs the image with
`-p 127.0.0.1:8473:8473` and curls `/healthz` — that is the **Mode-B service**
path. The image default is now the **gateway** (`:8080`, `GET /v1/models`,
token-gated), so the smoke no longer exercises the default image:
1. it maps `:8473`, but the gateway listens on `:8080`;
2. it curls `/healthz`, but the gateway's health surface is `/v1/models`;
3. it passes no token, so even on `:8080` the gateway would refuse to start.

`release.yml` is intentionally outside this ticket's `owns:`. Recommend a
coordinated follow-up to either (a) point image-smoke at the gateway
(`-p 127.0.0.1:8080:8080`, `-e CHARON_GATEWAY_TOKEN=...`, curl
`/v1/models -H "Authorization: Bearer ..."`), or (b) explicitly run the Mode-B
command in the smoke (`... charon-image uvicorn charon.service.app:app ...`). Did
NOT edit `release.yml`.

## Verification

Docker is NOT available in this build env, so a live `docker build` / `compose up`
could not be run here. Exercised instead:
- Dockerfile reviewed line-by-line; entrypoint heredoc script validated for POSIX
  sh correctness and `set -eu` safety; Mode-B `uvicorn` pass-through traced.
- `docker-compose.yml` is valid YAML (parsed); gateway is the bare-`up` default,
  Mode-B behind its profile.
- No `src/`, `pyproject.toml`, `release.yml`, or `.gitignore` edits — gate
  (pytest/ruff/mypy/boundary/version) is unaffected by these doc/infra files and
  was re-run green.

NOT exercised here (needs Docker): actual `docker build`, `docker compose up`
serving `/v1/models`, healthcheck flip to healthy, live entrypoint refusal. The
launcher / a Docker-capable env should run the Item-7 live checks before merge.
