Make `docker compose up` (and `docker run ghcr.io/slop-platform/charon`) a FIRST-CLASS
fresh-install path for the Charon gateway: a clean, token-gated, OpenAI-compatible gateway with
PERSISTENT config that needs NO host Python (this sidesteps the Python-3.11 barrier hit on
charon-vm 2026-06-27, where Ubuntu 22.04 / Python 3.10 / no-pip blocked the pip/pipx path).
Canonical tier: **high** (fleet `opus`) — fresh-install-critical, involves entrypoint + setup
design. Build ON the EXISTING scaffolding (Dockerfile, docker-compose.yml, release.yml publish to
`ghcr.io/slop-platform/charon`); do NOT greenfield. The PRIMARY target is the GATEWAY, not Mode-B.

READ FIRST (read-only — understand the real code before touching anything; the local checkout may
be stale, prefer reading the repo you are working in fresh):
- `Dockerfile` — base `python:3.12-slim` (BASE_IMAGE build-arg, digest-pinned at release), non-root
  user `charon` (uid 10001), `pip install .[service]`, `CMD ["charon","gateway","--host","0.0.0.0",
  "--port","8080"]`. NOTE it sets `ENV CHARON_STATE_DIR=/work/.charon` and
  `CHARON_CONTAINER_VERIFIED=1` (Mode-B autonomy fence) — `CHARON_STATE_DIR` is the Mode-B SERVICE
  worker state root, NOT the gateway's config dir. It does NOT set `CHARON_HOME`.
- `docker-compose.yml` — two services: `charon-service` (Mode-B, profile `service`, :8473, loopback)
  and `gateway` (build: ., :8080 host-loopback, sets `CHARON_GATEWAY_TOKEN` + `CHARON_HOME=/config`,
  mounts `./charon-config:/config`, `host.docker.internal:host-gateway`, `restart: unless-stopped`).
  The `gateway` service is the model for what we want, but it is NOT the default and has no
  healthcheck or `.env` example.
- `src/charon/secrets.py` → `config_dir()`: `$CHARON_HOME` else `~/.charon` (the gateway's
  providers/models/pools + the 0600 `secrets.json` live HERE). This is the dir that must persist.
- `src/charon/gateway.py` → `_DEFAULT_HOST=127.0.0.1`, `_DEFAULT_PORT=8080`,
  `_TOKEN_ENV="CHARON_GATEWAY_TOKEN"`. `load_config` resolves token from
  `--token`/file/`CHARON_GATEWAY_TOKEN`. `build_server` ENFORCES the invariant: it RAISES
  `NonLoopbackBindWithoutToken` for a non-loopback host with no token. Health surface = aggregated
  `GET /v1/models`; console at `/` and `/charon`; setup page at `/charon/setup`.
- `src/charon/cli.py` → `_cmd_gateway`: applies stored keys to env, defaults config source to
  `config_dir()` so the gateway "just works" after `setup` with no flags.
- `.github/workflows/release.yml` → builds the image and runs `image-smoke`. NOTE (see Item 4): the
  smoke currently maps `127.0.0.1:8473:8473` and curls `/healthz`, which matches the Mode-B SERVICE,
  NOT the default gateway CMD (:8080, `/v1/models`, and now token-gated) — flag this.

DELIVER the 7 items below. Own ONLY the files in `owns:` (see the ticket). Keep the image LEAN.

1. CONFIG PERSISTENCE — make the gateway's config dir a real, persistent volume.
   - In the `Dockerfile` (gateway path) set `ENV CHARON_HOME=/data` (a clean, gateway-specific
     mount point; do NOT overload `/work` or the Mode-B `CHARON_STATE_DIR`), `mkdir`/`chown` it to
     the `charon` user, and declare `VOLUME /data` so providers/keys/models/pools survive restarts
     and are NEVER baked into the image. (Equivalently keep `/config` if you prefer parity with the
     existing compose service — pick ONE and use it consistently across Dockerfile + compose + docs.)
   - In compose, mount a named or bind volume at that path (e.g. `./charon-config:/data`).
   - The 0600 `secrets.json` must land inside the mounted dir with correct ownership for uid 10001;
     verify `charon setup` / `providers add` can write it (dir is `chmod 700` by `set_secret`).

2. GATEWAY ENTRYPOINT — default the container to a token-gated gateway on `0.0.0.0:8080`.
   - Keep `0.0.0.0:8080` as the in-container bind (compose maps host loopback). Token comes from
     `CHARON_GATEWAY_TOKEN` (already wired through `gateway.load_config`).
   - Add a SMALL entrypoint script (POSIX sh, lean) that, before exec'ing the gateway, refuses to
     start a non-loopback bind with NO token and prints a CLEAR, friendly message (mirror the
     in-app `NonLoopbackBindWithoutToken` text + show `openssl rand -hex 16` to make one) instead of
     a raw Python traceback. It must `exec` so signals/PID-1 behave (or pair with tini if already
     present — do not add weight unless needed). The entrypoint must still allow `docker run … setup`
     / `… providers add …` / arbitrary `charon` subcommands to pass through (only guard the gateway
     default path). Default `CMD` stays the gateway.

3. FIRST-TIME SETUP IN A CONTAINER — `charon setup` is interactive; spec + support the realistic
   paths and pick the CLEANEST as the documented default:
   (a) `docker compose run --rm gateway setup` (interactive) writing into the MOUNTED volume — make
       this work end-to-end (the entrypoint must let `setup` through; the volume must be writable).
       This is the recommended default for a fresh user.
   (b) Non-interactive: `providers add` + key via env/secrets for scripted/headless config.
   (c) Bring-your-own: mount a pre-made `~/.charon` (or the volume dir) populated on the host.
   Document all three; lead with (a). Verify the configured gateway then serves models.

4. HEALTHCHECK — add a `HEALTHCHECK` (and/or compose-level healthcheck) hitting the gateway's real
   health surface `GET /v1/models` on `127.0.0.1:8080`, TOKEN-AWARE (pass `?token=$CHARON_GATEWAY_TOKEN`
   or the `Authorization` header) so a gated gateway reports healthy. Use a tool present in the slim
   image (python stdlib `urllib` is a safe zero-dep choice; only assume `curl` if you add it).
   ALSO FLAG (PROVISIONAL — `release.yml` is NOT in your `owns:`): the existing `image-smoke` job
   curls `/healthz` on `:8473`, which is the Mode-B service path and does NOT match the default
   gateway CMD (`:8080` + `/v1/models`, now token-gated) — so the smoke would not exercise the
   gateway image correctly. Surface this clearly in your PR description / a REVIEW note so the
   manager can decide whether to fix `release.yml` in a coordinated follow-up. Do NOT edit
   `release.yml` yourself unless the manager re-scopes your `owns:`.

5. COMPOSE FILE — make `docker compose up` "just work" for the gateway:
   - Make the gateway the natural default `up` target (keep Mode-B `charon-service` behind its
     `profile: ["service"]` so a bare `docker compose up` brings the GATEWAY).
   - Keep host-side port mapping on LOOPBACK by default (`127.0.0.1:8080:8080`); document how to
     widen to the LAN deliberately (still token-gated).
   - The config volume from Item 1, `CHARON_GATEWAY_TOKEN` via env, `restart: unless-stopped`,
     `host.docker.internal:host-gateway` (so host-local providers like LM Studio/Ollama/Jan are
     reachable), and the Item-4 healthcheck.
   - Add a `.env.example` (e.g. `CHARON_GATEWAY_TOKEN=` with a comment to run `openssl rand -hex 16`)
     and reference it from compose; do NOT commit a real token. Ensure `.env` is gitignored.

6. DOCS — a concise "Run with Docker" path. To AVOID README collisions with other install work,
   put the BULK in `docs/docker.md` (new file) covering: quick start (`cp .env.example .env`, set a
   token, `docker compose up`), `docker run ghcr.io/slop-platform/charon` with the volume + token +
   `host.docker.internal` flags, the three setup paths from Item 3, pointing an OpenAI client at
   `http://127.0.0.1:8080/v1` with the token as the API key, the console at `/` `/charon`, and
   widening to the LAN. In `README.md` make only a MINIMAL, collision-aware touch: a SHORT pointer
   to `docs/docker.md` (the existing "Expose it / Docker" section ~L136-150 can host the pointer —
   keep the edit tiny and self-contained so it does not fight other install docs).

7. VERIFY — prove it works:
   - `docker build -t charon:ci .` succeeds.
   - If Docker is available in your env: `docker compose up` (with a test token + a minimal config —
     e.g. a no-key local provider or a mounted pre-made config) serves `GET /v1/models` (200, with
     the token) on `127.0.0.1:8080`; the healthcheck reports healthy; the entrypoint refuses cleanly
     with the friendly message when the token is unset. Tear down with `docker compose down`.
   - If Docker is NOT available: at minimum `docker build` + validate the compose file
     (`docker compose config`) + a config-path sanity check; describe exactly what was and wasn't
     exercised in the PR.

CONSTRAINTS (hard):
- PRODUCT-CLEAN: zero SLOP / fleet / build-rig / runner leakage into the image, compose, or docs.
- AGENT- & PROVIDER-AGNOSTIC: nothing hardcoded to any specific agent (e.g. opencode) or provider;
  the gateway fronts any provider via config.
- MUST NOT break the existing pip/curl/pipx install path or the Mode-B `charon-service` profile.
- Keep the image LEAN (no needless layers/deps; reuse the existing base + `.[service]` install).
- Own ONLY the files listed in `owns:`. The `README.md` touch is a single minimal pointer — do not
  restructure the README. Do NOT touch `release.yml`, `pyproject.toml`, or `src/` unless the
  manager re-scopes you; if a code change in `src/` seems required, STOP and flag it instead.
- Base your branch on `master`, open a DRAFT PR, do not merge.
