# Charon "gateway-first" — Droid Robot Mode work order

**Status:** plan ready, not started. Hand the prompt below to a Droid Robot Mode
session pinned to `/home/stack/code/charon`, branch `gateway-mode`. Keep it
SEPARATE from the SLOP Droid work (different repo). See memory
`charon-vision-gateway-first` for the why.

> ⚠️ **NOTE:** this file itself contains internal paths + `ticket #1318` —
> **sanitize it before ever committing it** (it is intentionally left untracked).

---

## PRE-WORK: public-repo hygiene audit (operator-requested 2026-06-26, DEFERRED)

The repo is PUBLIC and currently exposes internal development meta / infra (no
real secrets — no API keys, no SSH private key; IPs are private `10.x`). Operator
wants strangers to NOT see this. **Do this audit before/alongside the gateway
work.** Findings (already located — don't re-discover):

- **`docs/HANDOFF.md`** — internal operational runbook, NOT product docs. Leaks
  `charon-vm`/`10.0.3.91`, `~/.ssh/charon_vm`, runner `10.0.1.60`, ssh alias
  `mediastack`, user `stack`, `ticket #1318`, "COLLISION GUARD", provider key env
  *names*+location (`~/.profile`), `/home/stack/...` paths, gh user `Nnyan`.
  → **Relocate out of the public repo** (delete from git, keep a private copy) or
  fully sanitize. Note: it's the methodology/grounding source for this work, so
  preserve a private copy.
- **`docs/REVIEW-LOG.md`** — internal adversarial-review log; references
  `charon-vm`, `mediastack`, `ticket #1318`, `4-LOM`. → relocate or sanitize.
- **`.github/workflows/*.yml` + `.github/actionlint.yaml`** — comments name the
  "mediastack session" / "COLLISION GUARD" / ticket. → trim the prose comments;
  KEEP the functional `4-lom` label.
- **`docs/adr/0002-...md`** line ~50 — `~/.ssh/mediastack` reference. → sanitize.
- Lower-risk: `PLAN-tier*` local paths; `slop`/`mediastack` strings in
  boundary-check docs are FUNCTIONAL (the import guard forbids those names) — keep.
- KEEP public: ADRs, PLANs (sans local paths), SUPPLY-CHAIN, README.

**Caveat:** scrubbing the working tree stops future exposure only; the content is
in git history since `e99d3cc`. A full purge needs a history rewrite + force-push
(disruptive on a public repo). Operator's call — pragmatic scrub-going-forward is
likely enough given no real secrets. CONFIRM with operator before any history
rewrite or before deleting HANDOFF.md.

## Vision (one paragraph)

Charon = a SOLO-dev, local, OpenAI-compatible **gateway** that fronts many
LLM/agent providers (OpenCode Zen ✓, OpenRouter, NanoGPT, ZAI, local LM Studio/
Jan/Ollama) with **visible, cost-ranked failover**, so when one provider hits a
session/rate cap the next serves transparently. Any OpenAI-compatible Windows
client (Cursor, Cline, Aider, Chatbox, Jan, AnythingLLM, Msty, …) points at
`http://localhost:<port>/v1`. The existing autonomous orchestrator (`charon run`:
Ledger + executable acceptance + fence, drives ACP agents) becomes an **opt-in
feature** sharing the same provider/failover core. ~80% of the gateway already
exists as `src/charon/proxy_server.py` `GatewayProxyServer` (pure stdlib → runs
natively on Windows).

## Recommended model + effort (set in Droid; the prompt is model-agnostic)

Droid runs whatever model is selected in its settings — pick it there.
- **P0 (ADR/design) & P2 (failover/security):** Claude Opus 4.8 at `xhigh` effort
  (or Claude Fable 5 for max rigor). Do NOT downgrade here.
- **P1, P3, P4, P6:** Opus 4.8 at `high`.
- **P5 (Windows packaging, mechanical):** a faster/cheaper model is fine.

## Windows packaging decision

Single self-contained `.exe` (PyInstaller) that starts the gateway + opens a
local web console; `charon.toml` config; built on the free `windows-latest`
GitHub runner (does NOT touch the Linux `[self-hosted, 4-lom]` CI). Tray app is a
stretch goal.

---

## THE DROID PROMPT (copy-paste into a fresh Droid Robot Mode session)

```
You are an autonomous engineer building the "gateway-first" evolution of Charon.
Work ONLY in the repository at /home/stack/code/charon. Do NOT touch any other
repo (notably /home/stack/code/slop or anything SLOP-related) — a separate Droid
owns that. All your work goes on a dedicated branch.

== CONTEXT ==
Charon is a thin orchestrator that drives coding agents over ACP and keeps a
vendor-neutral Work Ledger. It already contains, in src/charon/proxy_server.py, a
`GatewayProxyServer`: "a loopback OpenAI-compatible proxy in front of one or many
upstreams" with multi-provider routes, 429/402 + silent-downgrade detection,
server-side key holding, and SSE streaming. The core is pure stdlib (cross-platform,
runs on Windows). Read these first: README.md, docs/adr/*, docs/PLAN-tier2.md,
docs/REVIEW-LOG.md, docs/SUPPLY-CHAIN.md, src/charon/proxy.py,
src/charon/proxy_server.py, src/charon/service/app.py, src/charon/router.py,
src/charon/pools.py, src/charon/cli.py, src/charon/api.py.

== VISION (build toward this) ==
Charon = a SOLO-dev, local, OpenAI-compatible GATEWAY that fronts many LLM/agent
providers with VISIBLE, cost-ranked failover, so when one provider hits a session/
rate cap the next provider serves transparently. Any OpenAI-compatible client
(Cursor, Cline, Aider, Chatbox, Jan, AnythingLLM, Msty, LM Studio, …) points at
http://localhost:<port>/v1 and just works. The existing autonomous orchestrator
(`charon run`: Ledger + executable acceptance + fence, driving ACP agents like
OpenCode) becomes an OPT-IN feature on top of the SAME provider/failover core.
Gateway is the PRIORITY; orchestrator is a toggle, must keep working.

== METHODOLOGY (this repo's house rules — follow exactly) ==
- Plan-before-code: open each phase with an ADR/design note and an ADVERSARIAL
  self-review, reconciled in docs/REVIEW-LOG.md, BEFORE writing implementation.
- Keep the test gate GREEN at every commit (pytest, ruff check, mypy src/charon,
  python3 tools/check_boundary.py src, python3 tools/check_version.py). Run with
  bare `pytest` (CI uses the console script).
- Core stays STDLIB-ONLY; any new dependency goes behind a pyproject optional-
  extra, never in the privileged core. Never log or echo provider API keys.
  Loopback bind by default; non-loopback requires explicit opt-in + a token.
- Commit per increment with conventional-commit messages. Work on branch
  `gateway-mode`; push it and open a DRAFT PR to master. DO NOT merge to master —
  leave that to the operator. CI runs on a self-hosted Linux runner [self-hosted,
  4-lom]; the Windows .exe build must use a SEPARATE workflow on `windows-latest`
  (the repo is public, so those minutes are free) and must NOT change the Linux CI.

== PHASES (ship in order; each ends green + committed + REVIEW-LOG updated) ==
P0  ADR-0005 "Gateway-first Charon" + adversarial review: two modes sharing one
    provider/failover core; security posture; failover semantics; packaging choice.
P1  `charon gateway` standalone long-lived command. Implement /v1/chat/completions
    (stream + non-stream) and /v1/models (aggregated) on GatewayProxyServer. Config
    from a provider-registry file. Loopback default + optional bearer token.
P2  Transparent failover IN the gateway request path: on 429/402/Retry-After or a
    silent model-downgrade, retry the next provider in the cost-ranked pool within
    the same client request and return the first success. Emit a structured
    failover event log; add X-Charon-Provider and X-Charon-Failovers response
    headers. Failover MUST be visible.
P3  Provider registry + presets: an abstraction (base URL, key_env, cost metadata,
    model map, quirks) with presets for OpenRouter, NanoGPT, ZAI (OpenCode Zen is
    already wired as the `opencode-go` upstream). Add local upstreams (LM Studio /
    Jan / Ollama, OpenAI-compatible localhost). Editable cost-rank ordering
    (default free → cheap → paid).
P4  Web console (visibility): extend the existing read-only dashboard into a
    gateway console — live request stream, per-provider usage/cost/failover/health,
    pool config view. Keep it loopback + token-gated.
P5  Windows packaging: PyInstaller single-file .exe that starts the gateway and
    opens the console; a charon.toml config + first-run helper. Add a separate
    `windows-latest` GitHub workflow that builds and uploads the .exe artifact.
P6  Orchestrator as opt-in: ensure `charon run` (ACP + Ledger + acceptance + fence)
    keeps working on the SHARED provider/failover core; document it as the autonomy
    toggle in README.

== DELIVERABLES PER PHASE ==
Code + tests (incl. a TestClient/round-trip where applicable) + docs (README +
ADR/PLAN) + a REVIEW-LOG entry. Stop and summarize after P0 and confirm the design
direction before mass implementation. Report blockers instead of guessing about
external provider quirks; where a real provider key is absent, prove the contract
with a mock upstream (the repo already uses this pattern).

Begin with P0: read the listed files, create branch `gateway-mode`, write
ADR-0005 with an adversarial review, reconcile it in REVIEW-LOG, then pause for
operator confirmation.
```
