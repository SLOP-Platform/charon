---
description: "Charon's product vision (clarified 2026-06-26) — a SOLO-dev, local, OpenAI-compatible failover GATEWAY any Windows client points at; autonomous orchestrator is an opt-in feature on top."
metadata: 
name: charon-vision-gateway-first
node_type: memory
originSessionId: 57e20449-d31c-42de-a683-0ba521791c9c
type: project
tags: [charon, gate, gateway, vision]
last_referenced: 2026-07-13
---
**Vision pivot, operator-clarified 2026-06-26.** The earlier "single-operator
Linux CLI" framing was NOT what the operator wanted. Correct vision:

- **Solo dev, single user** — NOT multi-tenant / concurrent clients. "Support many
  Windows clients" = broad *compatibility*, not concurrency.
- **Charon = a local OpenAI-compatible GATEWAY** that fronts many LLM/agent
  **providers** with **visible, cost-ranked failover**, so when one provider/agent
  hits a session/rate cap, work continues on another transparently. The whole
  point: stop waiting on Claude Code session limits by spreading across providers.
- **Any OpenAI-compatible client** points at `http://localhost:<port>/v1` — Cursor,
  Cline, Aider, Chatbox, Jan, AnythingLLM, LobeHub, Msty, Nanocoder, LM Studio,
  etc. Rule: "if it accepts an OpenAI-compatible base URL, it's supported."
- **Autonomous orchestrator** (the current `charon run`: Ledger + executable
  acceptance + fence, drives ACP agents like OpenCode) becomes an **opt-in feature
  the user turns ON**, sharing the same provider/failover core. Gateway is PRIORITY.

**Key realization:** this is ~80% built. `src/charon/proxy_server.py`
`GatewayProxyServer` is already "a loopback OpenAI-compatible proxy in front of one
or many upstreams" (multi-provider routes, 429/402 + silent-downgrade detection,
key-holding, SSE) and is **pure stdlib → runs natively on Windows**. Gaps: run it
**standalone always-on** (`charon gateway`), do **transparent in-request failover**
(today the coordinator switches models, not the gateway), provider **presets**, a
**web console** for visibility, and **Windows packaging**.

**Operator answers (2026-06-26):** (1) gateway priority, orchestrator = toggle.
(2) auto-failover ordering optional to expose, but failover MUST be **VISIBLE** to
the user. (3) packaging = "easy to use" → recommended single Windows `.exe`
(PyInstaller) + local web console, tray app as stretch. (4) OpenCode Zen already
wired (the `opencode-go` upstream, https://opencode.ai/zen/go/v1); add OpenRouter,
NanoGPT, ZAI, then local (LM Studio/Jan/Ollama) by bang-for-buck.

Execution plan + the full Droid prompt are saved in
**`docs/GATEWAY-DROID-PROMPT.md`** (phases P0–P6, per-phase model/effort rec,
Windows-.exe packaging). Hand it to a **Droid Robot Mode** session on a dedicated
`gateway-mode` branch, kept SEPARATE from the SLOP Droid work (different repo).
Not started as of 2026-06-26. See [[charon-project-state]],
[[charon-build-methodology]], [[charon-hosting-and-runner]].

**Vision EXTENSION, operator-clarified 2026-06-26 (later).** Charon is NOT just the
gateway (route model calls). It is a **work engine**: *analyze* incoming work →
*decompose* it → *assign* pieces to **multiple parallel workers**
(models/sessions/droids — "whatever you want to call it"; worker type is an impl
detail) so work runs **concurrently, safely, and MUCH faster** instead of serially.
Gateway = the substrate that makes N parallel workers sustainable; analyze-decompose-
assign = the product value. This RESOLVES the threads-vs-fleet fork (DTC lens C/D
2026-06-26) toward **fleet/multi-worker as core**, not merely opt-in. Implication:
the cross-process worker-coordination substrate (assignment + atomic claim/lease +
worker liveness + safe result-landing) is REAL substrate to build NATIVE over PERF-4's
PID-lock/ledger/SharedBudget — NOT the bash harness ([[droid-robot-mode-harness]]
stays a sibling/reference). Co-equal constraint: "much faster" rides ON the fence +
Mode-B container + L0–L3 ladder (parallel multiplies blast radius), never around them.
The one true OUT: per-worker session-loop glue (context-exhaustion relaunch) is the
worker's job, not Charon's.

**Reconciled into ADRs (2026-06-26):** **ADR-0007** (parallel work engine; Proposed) —
after a 3-lens adversarial review, shrunk to a thin honest first increment (per-unit git
worktree off base, **consumer-supplied units**, **propose-default** gated landing); two
operator-approved calls overturned on the evidence (ephemeral→policy D7; auto-land→
propose-default D4/D5); the engine (board/claim/scheduler, new backend port,
auto-decompose, adaptive capacity, scanner matrix) **deferred behind explicit tripwires
D10**; plus **D12 end-product Validator** role (quality gate, NOT a trust boundary).
**ADR-0008** (Proposed/deferred skeleton) — the **intake→ticket-plan pipeline** (the
non-coder front door: induct messy input → analyze → rule-abiding tickets), two-phase
(human-reviewed plan sooner; autonomous behind D10-C), with a fixed failure contract.
Decisions live in docs/adr/0007 + 0008 + REVIEW-LOG.

**⚠ CORRECTION (2026-06-26, later): the "deferred behind tripwires" reconciliation above
DILUTED an explicit operator decision.** The operator wants the work-engine OWNED NATIVE,
SOONER — exactly the "fleet/multi-worker as core, build the substrate native" decision in
the paragraph above. ADR-0007's adversarial review inverted that into "engine deferred,
maybe never," and it was wrongly recorded as settled. Authoritative decision now lives in
[[charon-own-work-engine]]; ADR-0007 framing to be amended from "deferred" → "native, on
the roadmap, sooner." See [[adversarial-review-must-not-silently-override-operator]].
