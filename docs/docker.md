# Run Charon with Docker

A `docker compose up` (or `docker run ghcr.io/slop-platform/charon`) brings up a
clean, **token-gated, OpenAI-compatible gateway** with **persistent config** and
**no host Python required** — the turnkey fresh-install path when you can't (or
don't want to) use the native `pipx install charon` route.

The container default is the **gateway** (`charon gateway` on `0.0.0.0:8080`),
published to the host's loopback. Provider keys and your model/pool config live
on a persistent `/data` volume; they are never baked into the image.

> The Mode-B fenced service (`charon-service`, ADR-0002 §2.3) is a *separate*,
> optional path — see [Mode-B service](#mode-b-service-optional) at the end.

---

## Prerequisites

Your user must be in the `docker` group, otherwise you'll get a
`permission denied … /var/run/docker.sock` error:

```bash
sudo usermod -aG docker $USER
```

Log out and back in (or start a new login shell with `newgrp docker`) for the
group change to take effect. Alternatively, prefix every `docker compose` /
`docker run` command with `sudo`.

---

## Quick start (compose)

```bash
cp .env.example .env                       # then edit .env:
#   CHARON_GATEWAY_TOKEN=...  (generate one: openssl rand -hex 16)

docker compose run --rm gateway setup      # one-time: configure providers/models
docker compose up                          # gateway on http://127.0.0.1:8080/v1
```

Point any OpenAI client at `http://127.0.0.1:8080/v1` and use the token as the
API key:

```bash
curl -s http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer $CHARON_GATEWAY_TOKEN"
```

The live console is at <http://127.0.0.1:8080/> (also `/charon`); the web setup
page is at `/charon/setup`.

Tear down with `docker compose down` (the `charon-config` volume — your config —
**persists**; add `-v` only if you want to wipe it).

### Why a token?

The gateway binds `0.0.0.0` inside the container and holds your provider keys, so
a non-loopback bind **must** be token-gated (ADR-0005 D5/R8). If
`CHARON_GATEWAY_TOKEN` is unset the entrypoint refuses to start with a clear
message instead of a raw traceback:

```
charon: refusing to start the gateway on a non-loopback host (0.0.0.0) without a token.
  The gateway holds your provider keys, so a non-loopback bind must be token-gated (ADR-0005 D5/R8).
  Generate one and pass it in:

      export CHARON_GATEWAY_TOKEN=$(openssl rand -hex 16)
```

---

## First-time setup — three paths

Config (providers, models, pools, and the `0600` `secrets.json`) lives under
`$CHARON_HOME` = **`/data`** inside the container, on the persistent
`charon-config` volume. Pick whichever fits:

### (a) Interactive setup into the volume — recommended

```bash
docker compose run --rm gateway setup
```

`setup` runs interactively and writes into the mounted `/data` volume, so the
config survives the `--rm` and is there when you `docker compose up`. This is the
cleanest path for a fresh user.

### (b) Non-interactive / scripted

Add providers and keys without the wizard — good for headless/automated setups:

```bash
# add a provider + model (writes config to /data)
docker compose run --rm gateway providers add openrouter --key-env OPENROUTER_API_KEY

# supply the key via the environment (loaded into the gateway at start, never
# written to any committed file)
echo "OPENROUTER_API_KEY=sk-..." >> .env
```

`.env` is gitignored; values flow into the container env and Charon's
`apply_to_env()` makes them available to the matching `key_env`.

A key supplied this way is read-only and **bound to the host its built-in preset
declares** — it is never sent to another host. Keys stored by Charon itself
(`providers add --key`, the setup wizard, the web console) are saved against the
PROVIDER rather than the env-var name, since an env-var name can be shared by
several providers; those are bound to the host they were stored for.

Gateway **start-up** only ever READS this directory, and rotating a key is just
editing `.env` and restarting.

Do **not**, however, mount the config volume `:ro`. By default the config dir is
also the state dir, and several components create and persist files there while
the gateway is *running* — the quality scorer, the balance tracker's auto-park
state, virtual keys, and the policy router. A read-only mount therefore starts
cleanly and then silently loses auto-park state and quality scores, or errors
mid-request. If you want the config genuinely read-only, point state elsewhere
with `--state-dir` and mount only that directory read-write.

Two cases need action after upgrading an existing deployment — both are reported
as a `WARNING:` line on stderr at gateway start, naming the provider:

- a provider whose `base_url` you overrode to something other than its preset
  (a corporate proxy, say) while its key lives only in `.env`. The env key is
  bound to the preset host, so it will not be sent to the overridden one;
- a model entry using `upstream_base` + `key_env` pointing at a host no preset
  claims.

In both cases re-supply the key so it is stored against the provider:

```bash
docker compose run --rm gateway providers add <name> --base-url <your-base> --key sk-...
```

Rolling back to a pre-upgrade image keeps working for keys that were already in
`.env` or in a legacy `{key_env: value}` `secrets.json` entry — neither is ever
removed. A key stored *after* upgrading lives under a `provider:<id>` entry that
an older image does not read, so re-add that provider if you roll back.

### (c) Bring your own config

If you already have a populated `~/.charon` on the host, mount it instead of the
named volume — set the gateway service's volume to `~/.charon:/data` (or copy
your `providers.json` / `models.json` / `pools.json` / `secrets.json` into the
`charon-config` volume). Ensure `secrets.json` is `0600` and the dir is readable
by uid `10001`.

After any of these, `docker compose up` and confirm:

```bash
curl -s http://127.0.0.1:8080/v1/models -H "Authorization: Bearer $CHARON_GATEWAY_TOKEN"
```

---

## Plain `docker run` (no compose)

```bash
docker run --rm -it \
  -p 127.0.0.1:8080:8080 \
  -e CHARON_GATEWAY_TOKEN="$(openssl rand -hex 16)" \
  -v charon-config:/data \
  --add-host host.docker.internal:host-gateway \
  ghcr.io/slop-platform/charon
```

- `-p 127.0.0.1:8080:8080` — publish to host loopback only.
- `-v charon-config:/data` — persistent config (a named volume Docker seeds with
  the correct uid-10001 ownership).
- `--add-host host.docker.internal:host-gateway` — reach host-local providers.

Run setup the same way by overriding the command:

```bash
docker run --rm -it -v charon-config:/data ghcr.io/slop-platform/charon setup
```

The entrypoint passes `setup`, `providers …`, and any other `charon` subcommand
through; only the default gateway path is token-guarded.

---

## Reaching host-local providers

The container's `localhost` is **not** the host. With
`host.docker.internal:host-gateway` in place (compose sets it; `docker run` needs
`--add-host`), set a host-local provider's `base_url` to
`http://host.docker.internal:<port>`:

| Provider  | Host port | base_url                                |
|-----------|-----------|-----------------------------------------|
| LM Studio | 1234      | `http://host.docker.internal:1234/v1`   |
| Ollama    | 11434     | `http://host.docker.internal:11434/v1`  |
| Jan       | 1337      | `http://host.docker.internal:1337/v1`   |

---

## Widening to the LAN

By default the host port maps to loopback (`127.0.0.1:8080:8080`), so only the
host can reach the gateway. To expose it on your LAN — **deliberately**, and still
token-gated — change the compose port mapping to:

```yaml
    ports:
      - "8080:8080"
```

The token is still required (the in-container bind is already `0.0.0.0`), so
clients on the LAN must send `Authorization: Bearer <token>`.

---

## Healthcheck

The image declares a `HEALTHCHECK` (and compose mirrors it) that probes
`GET http://127.0.0.1:8080/v1/models` with the token, using stdlib `urllib` (no
`curl` needed in the slim image). A correctly-configured, token-gated gateway
reports `healthy`:

```bash
docker compose ps          # STATUS shows (healthy) once models are served
```

---

## Mode-B service (optional)

The Mode-B fenced service is a different surface (the privileged agent loop, not
the gateway). It is **not** started by a bare `docker compose up`; bring it up
behind its profile:

```bash
docker compose --profile service up charon-service
```

It serves on `127.0.0.1:8473` and mounts `./work:/work`. See ADR-0002 §2.3.

---

## Notes

- Image base is `python:3.12-slim`; the published image is digest-pinned at
  release (see `docs/SUPPLY-CHAIN.md`).
- The container runs as non-root uid `10001`.
- This path does **not** replace the `pip` / `curl` / `pipx` install or the
  Mode-B profile — it sits alongside them.
