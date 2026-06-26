# Charon

**A local, OpenAI-compatible gateway that fronts many LLM providers with
visible, cost-ranked failover.** Point any OpenAI-compatible client at
`http://localhost:<port>/v1`; when one provider hits a rate/credit cap, the next
provider serves **transparently, within the same request** — no waiting on
resets, no lost work.

Charon holds your provider keys server-side (never sent to the client), ranks
providers **free-first / cheapest-first**, and fails over on
429/402/503/`Retry-After`/silent-downgrade/unreachable — with every failover
**visible** in `X-Charon-*` response headers and a live local console. Any
OpenAI-compatible client works: Cursor, Cline, Aider, Chatbox, Jan, LM Studio,
Msty, … "If it takes an OpenAI base URL, it's supported."

> Named for the ferryman who carries across the boundary — here, carrying a
> request from an exhausted provider to the next.

Charon also ships an **opt-in autonomous orchestrator** (`charon run`) that drives
coding agents over [ACP](https://agentclientprotocol.com) with a vendor-neutral
Work Ledger, on the **same** provider/failover core — see
[Advanced: autonomous mode](#advanced-autonomous-mode-charon-run) below.

**[→ jump to the Gateway quickstart](#gateway-the-main-event)**

## Install (Mode A — standalone)

```bash
# isolated, on PATH (recommended)
pipx install git+https://github.com/SLOP-Platform/charon

# or for development
git clone https://github.com/SLOP-Platform/charon && cd charon
pip install -e '.[dev]'
```

## Gateway (the main event)

Point any OpenAI-compatible client (Cursor, Cline, Aider, Chatbox, Jan, LM Studio,
…) at `http://127.0.0.1:8080/v1` and Charon fronts your providers. The gateway is
pure-stdlib, holds your provider keys server-side (never sent to the client), and
binds **loopback by default** — a non-loopback bind refuses to start without a token.

First, store your provider keys (kept in a **0600 user-local file**, never in the repo
— `~/.charon/secrets.json`, or `%APPDATA%\charon` on Windows; loaded into the env at
start):

```bash
charon providers list                 # presets + which keys are set
charon providers add openrouter       # prompts for the key WITHOUT echoing it
charon providers test openrouter      # probe the base URL resolves (verify a preset)
```

Then run the gateway:

```bash
# from a charon.toml (providers/models + bind/token), or from .charon/models.json
charon gateway --config charon.toml
charon gateway --state-dir .charon --port 8080

# expose on a LAN (must set a token — the gateway holds your keys)
CHARON_GATEWAY_TOKEN=$(openssl rand -hex 16) charon gateway --host 0.0.0.0
```

### Point a client at Charon

Every OpenAI-compatible client (desktop or CLI) has three settings — set them the
same way everywhere:

| Setting (named various things) | Value |
|---|---|
| **Base URL** / API base / endpoint / "OpenAI base URL" | `http://127.0.0.1:8080/v1` (use `localhost` if the app prefers it — both work) |
| **API key** | If the gateway is token-gated, your **`CHARON_GATEWAY_TOKEN`**; if it's the ungated loopback default, **any non-empty value** (apps require *something*) |
| **Model** | a model id Charon serves — see `GET /v1/models`, the console, or a pool name like `auto` (which gives failover) |

The rule: **if it accepts an OpenAI-compatible base URL, point it at
`http://127.0.0.1:8080/v1`.** A few common ones:

- **Cursor** → Settings → Models → enable *Override OpenAI Base URL* → the URL above;
  put the key/model in the same panel.
- **Cline / Roo (VS Code)** → API Provider = *OpenAI Compatible* → Base URL + key + model.
- **Aider** → `aider --openai-api-base http://127.0.0.1:8080/v1 --openai-api-key <token> --model <id>`
  (or env `OPENAI_API_BASE` / `OPENAI_API_KEY`).
- **Codex CLI** → `OPENAI_BASE_URL=http://127.0.0.1:8080/v1 OPENAI_API_KEY=<token>`.
- **OpenCode** → add a custom provider with `baseURL` = the URL above.
- **Jan / LM Studio / Msty / Chatbox / AnythingLLM** → add a *custom OpenAI-compatible*
  provider/endpoint = the URL above; key as a above.

**Windows + WSL2:** if Charon runs inside WSL2 and the client is a Windows app,
`http://127.0.0.1:8080` usually works (WSL2 forwards localhost). If a client can't
reach it, run the gateway with `--host 0.0.0.0` **+ a token** and point the client at
`http://<wsl-ip>:8080/v1` (`hostname -I` in WSL gives the IP). The token then goes in
the client's API-key field.

### Run the gateway in Docker (optional)

For the everyday **local** gateway, native install (above) is simpler — it reaches
host-local model servers directly and needs no token on loopback. Docker is for a
**shared / always-on / VPS** gateway:

```bash
export CHARON_GATEWAY_TOKEN=$(openssl rand -hex 16)
docker compose --profile gateway up gateway        # builds from source
# clients → http://127.0.0.1:8080/v1, API key = the token
```

Caveats inside a container: a **token is required** (it binds `0.0.0.0`); set
**local** providers' `base_url` to `host.docker.internal:<port>` (the compose adds
that host) since the container's `localhost` is not the host's. (`v0.2.0`+ is the
first image with the gateway; the compose `build: .`s from source by default.)

`charon.toml` (one schema, mirrors `.charon/models.json` field names):

```toml
[gateway]
host = "127.0.0.1"
port = 8080
# token = "..."   # or $CHARON_GATEWAY_TOKEN; required for a non-loopback host

[models."kimi-k2.7-code"]
upstream_base   = "https://opencode.ai/zen/go/v1"
key_env         = "OPENCODE_GO_KEY"   # env var holding the upstream key
# upstream_model = "..."              # real upstream id, if it differs
```

Define a `[pools]` table (a virtual model id → an ordered set of providers) and the
gateway does **transparent, visible, cost-ranked failover** (P2): when a provider
returns 429/402/503, a `Retry-After`, a silent model-downgrade, or is unreachable,
the next provider in the pool serves **within the same request**. A client/auth error
(400/401/403) is returned immediately — never failed over. Every response carries
`X-Charon-Provider` (who served it) and `X-Charon-Failovers` (how many were skipped,
and why); failover events are logged for the console.

```toml
[pools]
auto = ["qwen-free", "kimi-k2.7-code"]   # ordered free-first / cheapest-first
```

**Provider presets** save repeating base URLs: a model references a `provider`, and
the base URL + quirks come from a built-in preset — `opencode-go`, `openrouter`,
`nanogpt`, `zai`, `deepseek`, `chutes`, `groq`, `together`, `mistral`, plus local
(`lmstudio`, `jan`, `ollama`, `local`). You only supply the key. **Any other
OpenAI-compatible provider works too** — just give a base URL:

```bash
charon providers add chatllm --base-url https://your-provider/v1   # then enter the key
```

`charon providers add <preset>` / `charon setup` persist the provider to
`~/.charon/`, so the gateway picks it up with no hand-edited config.

```toml
[providers.openrouter]
key_env = "OPENROUTER_API_KEY"           # base_url comes from the preset

[providers.lmstudio]
base_url = "http://localhost:1234/v1"    # local server, no key

[models."qwen-free"]
provider       = "openrouter"
upstream_model = "qwen/qwen-2.5-coder:free"
free = true

[models."local-coder"]
provider       = "lmstudio"
upstream_model = "qwen2.5-coder-7b"
```

**Web console** (P4): the gateway serves a self-contained console at
`http://127.0.0.1:<port>/` (zero external assets, same loopback + token gate) — live
per-provider served/failed/cost, cooldown/health, the pool config, and a recent-
failover stream. JSON at `/charon/status`. A richer FastAPI dashboard for the
orchestrator's Work Ledger also ships (`python -m charon.service`).


## Advanced: autonomous mode (charon run)

Everything above is the gateway. This is the **opt-in** autonomous orchestrator — it drives coding agents over ACP with a vendor-neutral Work Ledger, on the same provider/failover core. Skip it if you only want the gateway.

### Honest disclosure (autonomous mode)

**The gateway is a passive proxy** — it forwards requests and holds keys; it does
not execute agents or apply changes. The disclosure below applies only to the
**opt-in orchestrator** (`charon run`): a **control plane** that at autonomy ≥ L1
spawns CLI coding agents and can apply their diffs **unattended**. If you only use
the gateway, none of this applies. For `charon run`, treat it accordingly:

- The **default autonomy is L0 (propose-only)** — nothing is applied.
- Per-backend **OS-level isolation is the container (Mode B)**, not the in-process
  fence. The fence hardens the subprocess env and *detects* worktree escapes, but
  a determined local agent process is only truly bounded by the container. **Do
  not run unattended (L2/L3) outside the container on a machine you care about.**
- **Scope:** Charon runs goals with **executable acceptance** (a command that
  exits 0 == done). Prose-only goals ("make it nicer") are out of scope by
  design — `remaining` must be machine-decidable.
- **Sunset clause:** this is a tactical bridge. As frontier agents grow native
  cross-vendor continuity, Charon's coordinator becomes removable — and your
  Work Ledger is just git + JSON, so it outlives Charon.


### Run a goal

```bash
# Run a goal against a built-in mock backend, in an auto-created sandbox repo.
# (proves the loop with no live agent; nothing applied at the default L0)
charon run --goal "create hello" --accept "test -f hello.txt" --backend mock --autonomy L1

# Inspect the derived ledger state (verified / remaining are re-derived from disk)
charon ledger <task-id>

# Tier-0: probe a REAL ACP agent for usage/resume fidelity before trusting it
charon doctor --backend-cmd "claude-code acp"
```


## What it builds vs. integrates

| Concern | Charon | Why |
|---|---|---|
| Coordinator loop | **build** (thin) | the glue nobody owns |
| Work Ledger | **build** | the gap |
| Cross-vendor handoff | **build** | ACP doesn't cross vendors |
| Fence / autonomy ladder | **build** (thin) | trust boundary |
| Execution | **integrate** (ACP client) | standardized |
| Routing/fallback | **integrate** (OpenAI-compat gateway, Tier 2+) | commodity |
| Consensus reviewer | **integrate** (cross-model review, Tier 3) | exists |

## Architecture

```
CLI / Python API / HTTP service   ← the three stable public surfaces
            │
   Coordinator (loop authority)
   ├── Work Ledger  (ONE per task — sole progress truth; INV-1)
   ├── Fence + autonomy ladder (L0–L3, default-deny)
   ├── Router (static policy in Tier 1; gateway in Tier 2+)
   └── AgentBackend port ── MockBackend (proof) · AcpBackend (real, stdio/NDJSON)
```

See [`docs/adr/`](docs/adr/) for the decisions (ADR-0001 architecture, ADR-0002
project boundary, ADR-0003 plane detail) and [`docs/REVIEW-LOG.md`](docs/REVIEW-LOG.md)
for the adversarial review of the build plan and its reconciliation.

## Status

**Tier 1:** standalone repo, CLI, CI, the continuity core (Ledger, fence, ports),
proven end-to-end on the mock backend; real ACP adapter shipped to-spec (validate
with `charon doctor`).

**Tier 2a** (this release): **multi-backend cross-vendor handoff**, proven
end-to-end across two mock vendors — exhaustion (H4) routes to a *different*
backend (H6), which rehydrates `remaining` from the ledger+disk alone (H3) and
finishes without replaying committed work (H5). The proof is deliberately
adversarial, not a happy path: a **lying** backend's forged "done" claim does not
survive the vendor boundary, and `lkg` never advances past an unverified commit
(INV-2). Routing stays a static native policy; the network gateway is gated on
[`docs/SUPPLY-CHAIN.md`](docs/SUPPLY-CHAIN.md) before it may enter the privileged
loop. The Mode-B container is built and health-checked in CI.

**Honest scope of the handoff proof:** what is proven is the *vendor-agnostic
contract* (the portable unit is files+ledger, not a vendor session). **Live**
ACP-to-ACP handoff needs two real ACP agents (not in this env) and stays gated
behind `charon doctor`.

**Tier 2b:** GHCR image-publish path (release-triggered, gated on tests, base
digest-pinned at release, SLSA provenance) + the web surface made honestly
read-only (it returns `501` rather than running the privileged loop in-process —
ADR-0002 §2.3). The live `POST /v1/runs` web/worker split is the recorded design
of record, built *with* its Tier-3 SLOP consumer (see
[`docs/PLAN-tier2.md`](docs/PLAN-tier2.md) §8).

**Web Ledger dashboard (read-only).** A minimal, single-operator web view of the
Work Ledger — project/run list, a run view (progress/cost/handoffs/checkpoints),
and a routing-config pane. Run it:

```
pip install 'charon[service]'
CHARON_SERVICE_TOKEN=$(openssl rand -hex 16) python -m charon.service   # http://127.0.0.1:8001
```

It is **read-only** (no run launch — `POST /v1/runs` is `501` by design),
**token-gated** (`CHARON_SERVICE_TOKEN`; the entrypoint refuses a non-loopback
bind without one), and serves **self-contained HTML with no external assets**
(zero egress). The container is the security boundary (INV-B4); for a VPS, front
it with a reverse proxy + HTTPS. Watch-the-agent-work (live diffs/stream) stays
CLI/TUI by design (ADR-0004 D7).

**Tier 3** (this release): **Ledger-native cost & budget accounting.** Each
checkpoint records a usage span (`tokens_in/out`, `cost_usd`, `latency_ms`);
cumulative spend is **derived** from the ledger (like progress), so it survives a
cross-vendor handoff and a reload without resetting (H3-for-cost). A
`--max-cost-usd` / `--max-tokens` cap stops a run *before* exceeding it — "always
working" never means "unbounded cost." Live token/cost come from real ACP
`session/usage` (gated on `charon doctor`); the mock proves the accounting
contract. *(Re-scoped from a consensus gate after adversarial review found the
gate's only consumer is L2 — built in Tier 4 with it; see
[`docs/REVIEW-LOG.md`](docs/REVIEW-LOG.md).)*

**Tier 4** (this release): autonomy **L2 (apply-with-consensus)** + the consensus
gate. At L2 a completed unit is applied only if a configured reviewer passes; a
**block, an error, or no reviewer all fail _closed_** (`blocked-consensus`, lkg
unchanged). L1 never consults the reviewer (unchanged); **L3** (full-auto) applies
regardless but records the verdict. **L2+ is refused outside the Mode-B
container** (`Fence.assert_environment` — set `CHARON_CONTAINER_VERIFIED=1` inside
it, or opt out loudly), enforcing ADR-0002 §2.3 in code, not just docs.

> **Consensus is _not_ a security boundary.** The reviewer is an automated check
> (an LLM, behind the gateway) that can be wrong or gamed. L2 consensus is
> *additive quality insurance* on top of executable acceptance — not a human
> review and not a security audit. For security-sensitive code, require human
> review outside Charon.

**Parallel independent units (PERF-4) are deferred** — adversarial review found
the thin design unsafe as drafted (escape-scan races on shared worktree parents,
a shared-budget overspend race, sticky backend subprocess state) and no consumer
needs the throughput yet. The binding fixes for when it is built are recorded in
[`docs/PLAN-tier4.md`](docs/PLAN-tier4.md) §6. The live web/worker service + GHCR
publish-on-tag land with the Tier-3 SLOP adapter (SLOP-side).

To configure multiple vendors from the CLI:

```bash
charon run --goal "..." --accept "test -f ok.txt" --backend mock-a,mock-b --autonomy L1
```

## License

MIT.
