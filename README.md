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

## Work engine (opt-in)

The gateway above is the product. Charon **also** ships a native work-engine — an
**opt-in consumer on the shared core** that never touches the gateway request path
(D001). It turns a unit plan into completed, *proposed* work:
**analyze → decompose → assign to parallel workers → propose-default land → validate.**

```bash
charon work --units plan.json        # run the engine end-to-end; prints a JSON report
```

`--units` takes either an **intake plan** (`charon-intake-plan` JSON, below) or a
consumer units file (TOML/JSON of `{goal, accept, tier, owned_paths}`). The engine
builds a durable board, assigns each unit to a warm **ACP** worker honoring
`depends_on` waves and disjoint file-ownership, and drives every unit through the same
fenced `coordinator.run` the single-unit path uses — there is no second, unfenced
dispatch path. Workers default to a `mock` backend; pass `--backend acp --acp-cmd
'opencode acp'` for a real agent.

**Propose-default, not auto-merge.** Completed units pass through the `land` gate
(diff-scope guard, always-hold sensitive paths, executable acceptance, `gitleaks`) and
Charon **opens a PR per unit — a human merges** (D006). Batch auto-land (ADR-0012) is
built but stays **gated**: `charon work` reports proposals only. The engine adds
concurrency, not new trust.

**Sandbox policy (D013).** `--sandbox` selects the worker posture:

| Posture | Meaning |
|---|---|
| `hybrid` *(default)* | host for trusted own-repo work behind the autonomy gate; container for L2+/untrusted |
| `container` | require a verified Mode-B container (`CHARON_CONTAINER_VERIFIED=1`) for every rung |
| `host` | host allowed; a loud override is still required for L2+ |

The **container is the trust boundary** (D012) — the per-unit fence escape-scan is
best-effort, not a boundary. Per-unit autonomy defaults to **L1** (keep + land
changes); **L2+ requires the Mode-B container**. Per-tier concurrency uses a fixed
conservative cap by default; **AIMD adaptive capacity is opt-in/gated** (`--capacity-policy aimd`, D007).

### Intake — from a messy work-list to a plan

Intake is the non-coder front door: it reads a markdown work-item list **as data** and
emits a rule-abiding ticket plan (file-disjoint, tier-tagged, collision-free waves, plus
a top-level product acceptance).

- **Phase 1 (human-reviewed, default).** Intake analyzes input and emits a plan *proposal*
  a human approves or edits. It never runs an acceptance command, spawns a unit, or lands —
  there is no code path from input text to execution. Feed the approved plan to `charon work`.
- **Phase 2 (autonomous, opt-in, default OFF).** `autonomous_intake(..., enabled=True)`
  decomposes and runs without a per-plan human gate. It is **off by default**; even when
  enabled a confidence gate stands between decompose and run, and on low confidence,
  propose-only items, or scope explosion it **falls back to the Phase-1 proposal** rather
  than running blind. Cost/runaway are bounded by a unit cap + shared budget.

For a single goal without a plan, `charon run --goal … --accept …` drives one unit (or the
`Triage→Plan→Implement→Review→Validate→Close` role-DAG with `--decompose`); it defaults to
**L0 (proposes changes, applies nothing)**.

This native engine **supersedes the external `charon-private/fleet/` dev harness** for real
use — that bash rig is dev-box *build* tooling only (its workers are `claude -p`, not the
product's ACP workers, D003). **Still gated / future:** positive-isolation verification
(D015) that probes host-sensitive paths/egress are unreachable, rather than trusting the
container flag. See [`docs/adr/`](docs/adr/) and [`docs/DECISIONS.md`](docs/DECISIONS.md)
for the full design and decision register.

## License

MIT — see [LICENSE](LICENSE). Design notes and decisions live in [`docs/adr/`](docs/adr/).
