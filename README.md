# Charon

**A local, OpenAI-compatible gateway with visible, cost-ranked failover.** Point any
OpenAI client at `http://localhost:8080/v1`; when one provider hits a rate or credit
cap, the next serves automatically — same request, no waiting, no lost work.

- Works with any OpenAI-compatible client (Cursor, Cline, Aider, Codex, Jan,
  LM Studio, Msty, …) — "if it takes an OpenAI base URL, it's supported."
- Holds your provider keys server-side (never sent to the client); ranks providers
  free-first / cheapest-first.
- Failover is **visible**: `X-Charon-*` response headers + a live local console.

## Install

```bash
pipx install git+https://github.com/SLOP-Platform/charon      # or: uvx, or pip install
```

## Quick start

```bash
charon setup          # guided: add providers + keys, models, a failover pool
charon gateway        # serves http://127.0.0.1:8080/v1   (console at http://127.0.0.1:8080/)
```

Then set your client's **base URL** to `http://127.0.0.1:8080/v1`.

## Providers & keys

```bash
charon providers list                                  # presets + which keys are set
charon providers add openrouter                        # prompts for the key (not echoed)
charon providers add my-llm --base-url https://host/v1 # ANY OpenAI-compatible provider
charon models import openrouter [--free-only]          # add the provider's whole catalog
```

Presets: `openrouter, nanogpt, zai, deepseek, chutes, groq, together, mistral,
opencode-zen, opencode-go, lmstudio, jan, ollama, local`. Keys are stored `0600` in
`~/.charon/secrets.json` (`%APPDATA%\charon` on Windows) — never in config, never in
the repo. Prefer a browser? Open `http://127.0.0.1:8080/charon/setup`.

## Connect a client

| Setting | Value |
|---|---|
| **Base URL** / endpoint | `http://127.0.0.1:8080/v1` (`localhost` also works) |
| **API key** | the gateway token if set, else **any non-empty value** |
| **Model** | a served id (`GET /v1/models`) or a pool name like `auto` (failover) |

- **Cursor** → Settings → Models → *Override OpenAI Base URL*.
- **Cline / Roo** → Provider = *OpenAI Compatible* → Base URL + key + model.
- **Aider** → `--openai-api-base http://127.0.0.1:8080/v1 --openai-api-key <token>`.
- **Codex CLI** → `OPENAI_BASE_URL=http://127.0.0.1:8080/v1`.
- **OpenCode / Jan / LM Studio / Msty / Chatbox** → add a custom OpenAI provider = the URL above.

*Windows/WSL2:* `http://127.0.0.1:8080` usually works; if not, run `charon gateway
--host 0.0.0.0` (with a token) and use `http://<wsl-ip>:8080/v1`.

## Failover

Put providers in a **pool** and Charon fails over automatically — on
429/402/503/`Retry-After`/silent-downgrade/unreachable it serves the next provider
**within the same request** (a 400/401/403 is returned as-is, never failed over).
Configure via `charon setup`, the web form, or a `charon.toml`:

```toml
[gateway]
port = 8080
# token = "..."          # required to bind a non-loopback host

[providers.openrouter]
key_env = "OPENROUTER_API_KEY"

[models."qwen-free"]
provider       = "openrouter"
upstream_model = "qwen/qwen-2.5-coder:free"
free = true

[pools]
auto = ["qwen-free", "kimi"]   # free-first; clients request model "auto"
```

Run with `charon gateway --config charon.toml`. Every response carries
`X-Charon-Provider` and `X-Charon-Failovers`; the console at `/` shows live
per-provider usage, cost, and health.

## Expose it / Docker

By default, `docker compose up` starts the gateway:

```bash
# Generate a token to hold your provider keys
CHARON_GATEWAY_TOKEN=$(openssl rand -hex 16) docker compose up gateway
```

In the container, local providers' `base_url` should point to `host.docker.internal:<port>`
(the container's `localhost` isn't the host's). Image: `ghcr.io/slop-platform/charon:v0.2.0`.

To run the service container instead (Mode-B orchestrator, optional):
```bash
docker compose --profile service up charon-service
```

## Autonomous mode (optional)

Charon also has an opt-in orchestrator — `charon run` drives coding agents over ACP
to an executable acceptance check. It defaults to **L0 (proposes changes, applies
nothing)**; higher autonomy applies diffs and should run in the Mode-B container. See
[`docs/adr/`](docs/adr/) for the design.

## License

MIT — see [LICENSE](LICENSE). Design notes and decisions live in [`docs/adr/`](docs/adr/).
