# Charon

**Charon is two things in one tool:**

1. **A smart LLM endpoint** — a local, OpenAI-compatible API gateway that automatically fails over across your providers. Point any OpenAI client at it and stop babysitting rate limits.
2. **An autonomous coding worker** — point Charon at a repo and a to-do list, and it does the work itself: drives a coding agent through the tasks and opens a pull request for each one.

Most people only need #1.

New here? Start with [getting started](docs/getting-started.md).

---

## Which mode do I want?

| You want… | Use | What Charon is here |
|---|---|---|
| A reliable LLM endpoint for your tools (Cursor, Cline, Aider, opencode, your own app) | **Gateway** | Just the smart model backend. It answers model calls; **your** agent does the work. |
| Charon to autonomously do coding work from a list of tickets | **Orchestrator** | The worker itself. It drives a coding agent through your tasks and opens PRs. |

> In **Gateway** mode, Charon never touches your code or your tickets — it only answers API calls.
> In **Orchestrator** mode, Charon *is* the one doing the coding work.

### Mode A — Gateway (the default, ~80% of users)

```bash
charon setup          # guided: add providers, keys, and models
charon gateway        # serves http://127.0.0.1:8080/v1
```

Point your client's base URL at `http://127.0.0.1:8080/v1`. Full install and setup in [Install](#install) and [Quick start](#quick-start) below.

### Mode B — Orchestrator (opt-in)

```bash
charon intake import my-tasks.md          # turn your to-do list into a plan
charon work --units my-tasks.md.plan.json \
            --repo /path/to/your/repo \
            --backend acp --acp-cmd 'opencode acp'
```

Charon drives a coding agent through each task and opens a PR per task — a human merges. Full details in [Work engine (opt-in)](#work-engine-opt-in) below.

---

## Install

**One-liner (recommended).** The bootstrap installer checks prerequisites
(Python >=3.11, git, pipx), installs anything missing via your OS package manager
(apt / dnf / brew), then installs Charon — with friendly output and a NEXT STEPS
guide at the end:

```bash
curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
# wget alternative:
wget -qO- https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
```

> **NOTE:** the one-liner points at a GitHub **release asset**. Publishing
> `install.sh` as a release asset is a release/deploy step — the URL above is
> **forward-looking until the first release**. Until then, run the script from a
> checkout: `bash install.sh`.

**Cautious? Download → inspect → run.** The installer is short and inspectable:

```bash
curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh -o install.sh
less install.sh        # read it first
bash install.sh        # --help for flags; -y to skip prompts
```

**Already have Python 3.11+ and pipx?** Skip the bootstrap entirely:

```bash
pipx install git+https://github.com/SLOP-Platform/charon      # or: uvx, or pip install
```

### Update

Re-run the one-liner — it detects an existing install, pulls the newest version,
reinstalls cleanly, and **preserves your settings in `~/.charon`**. The bare
`pipx` form works too:

```bash
curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
pipx reinstall charon      # equivalent if you installed via pipx
```

Want a clean slate? `bash install.sh --reinstall` resets `~/.charon` (it backs up
the old config first). Re-running to *update the program* never touches settings —
`charon setup` / `charon reset` are what touch your *settings*.

### Uninstall

```bash
pipx uninstall charon                      # if installed via pipx
rm -rf ~/.charon-venv ~/.local/bin/charon  # if the venv fallback was used
rm -rf ~/.charon                           # optional: also remove your settings
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

A `docker compose up` brings up the gateway as a token-gated, OpenAI-compatible
container with persistent config and **no host Python required**:

```bash
cp .env.example .env                       # set CHARON_GATEWAY_TOKEN (openssl rand -hex 16)
docker compose run --rm gateway setup      # one-time provider/model setup
docker compose up                          # gateway on http://127.0.0.1:8080/v1
```

Full guide — `docker run`, host-local providers, the three setup paths, LAN
exposure, and the optional Mode-B service — in **[docs/docker.md](docs/docker.md)**.

## Work engine (opt-in)

The gateway above is the product. Charon **also** ships a native work-engine — an
**opt-in consumer on the shared core** that never touches the gateway request path
(D001). It turns a unit plan into completed, *proposed* work:
**analyze → decompose → assign to parallel workers → propose-default land → validate.**

```bash
charon work --units plan.json        # run the engine end-to-end; prints a JSON report
```

`--units` takes either an **intake plan** (`charon-intake-plan` JSON, below) or a
consumer units file (TOML/JSON of `{goal, accept, tier, owned_paths}`). Example
consumer units file (`plan.json`):

```json
[
  {
    "goal": "add a greeting function",
    "accept": ["pytest -q", "python -c 'from mymod import greet; greet()'"],
    "tier": "sonnet",
    "owned_paths": ["src/mymod.py", "tests/test_mymod.py"]
  }
]
```

`accept` must be a **list** of shell commands (not a string); each must exit 0 to
pass. The engine
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

This native engine **supersedes the external `<private-rig-repo>/fleet/` dev harness** for real
use — that bash rig is dev-box *build* tooling only (its workers are `claude -p`, not the
product's ACP workers, D003). **Still gated / future:** positive-isolation verification
(D015) that probes host-sensitive paths/egress are unreachable, rather than trusting the
container flag. See [`docs/adr/`](docs/adr/) and [`docs/DECISIONS.md`](docs/DECISIONS.md)
for the full design and decision register.

## License

MIT — see [LICENSE](LICENSE). Design notes and decisions live in [`docs/adr/`](docs/adr/).
