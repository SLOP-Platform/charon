# Cline non-streaming envelope — do the eval paths that hit the 5 open pools STREAM?

- **Date:** 2026-07-08
- **Mode:** READ-ONLY investigation
- **Context:** Cline Pass is OpenAI-compatible ONLY when streaming. Non-stream request →
  `{"data":…,"success":true}` (no top-level `choices`), relayed verbatim by
  `proxy_server.py` → breaks a non-streaming OpenAI client. Cline is now the cheap-first
  (cost_rank=1) leg on 5 open pools: glm-5.2, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash,
  minimax-m3(-free). Source of the wiring + the non-stream finding:
  `fleet/scratch/cline-wire-report.md` (STEP 4/5 + the ⚠ manager-attention block).

---

## 1. Benchmark / real-outcomes eval harness — how it calls models

Harness: `fleet/benchmark/` (`bench.sh` + `lib/` + deterministic `graders/`).

**The benchmark does NOT call `/chat/completions` itself.** Its architecture (README.md,
RUN-BENCHMARK.md, bench.sh header):

- The operator picks a model in **opencode** with `/model`, then pastes one prompt telling
  the agent — *which IS the model being benchmarked, running as the opencode agent* — to
  drive `bench.sh` through sections S0–S6.
- **All real model completions happen inside opencode** (the model implements each section's
  coding task with its own tools). `bench.sh` only (a) prepares fixtures/worktrees,
  (b) runs **deterministic graders** (pytest/diff/swap-and-rerun — no model calls), and
  (c) reads cost via `lib/charon_cost.py`, which hits the gateway **status URL**, not
  chat/completions (and therefore never touches the Cline pools).
- Grep confirms: no `curl`/`httpx`/`requests.post` to `chat/completions` anywhere in
  `bench.sh` / `lib/sections.sh`. Legacy `run.sh`/`run-many.sh` are also "paste into an
  opencode tab" drivers — same opencode path, no direct completion call.

=> The benchmark scoring path's real completions ARE the opencode coding path. It streams
(see §2). The only direct-from-bench.sh gateway hit is a non-stream **status** read, which
does not route a completion through the Cline pools.

## 2. Real coding-agent eval path (opencode) — streams?

- opencode is wired to the gateway via `~/.config/opencode/opencode.json` as an
  `@ai-sdk/openai-compatible` provider (baseURL `http://10.0.1.60:8080/v1`). opencode's
  chat loop uses the AI SDK `streamText` path — coding agents SSE-stream by construction.
- Charon's own product code documents this: `proxy_server.py::_extract` (line 337) — *"the
  SSE `data:` chunks for a streamed one (agents like OpenCode stream)"* — and the proxy has
  a dedicated SSE branch (`text/event-stream` / `data:` prefix).
- Live proof already on record: `cline-wire-report.md` STEP 5 drove **all 5 Cline pools
  through the real gateway with the `charon-proxy` UA, streaming** → HTTP 200 via the
  cline-pass leg, 0 failovers, no downgrade, spill intact. The wrapped-envelope breakage
  was reproduced **only** on an explicit non-stream call.

=> Coding path STREAMS: **YES.**

## 3. Any other non-streaming client that would hit the 5 open pools?

- Health checks / `/models` / catalog probes — don't call chat/completions (out of scope).
- `charon_cost.py` — status URL only, not completions.
- droid-harness (`/home/stack/code/droid-harness`) — no direct `chat/completions`/`curl`;
  it launches CLI agents (claude/opencode) which stream ("streaming text only" per its
  IN-TAB-RESTART-DESIGN.md).
- **Minor residual edge (non-scoring, non-fatal):** opencode may issue an auxiliary
  non-stream `generateText` for session-title/summary. If that ever routed to one of the 5
  Cline pools it would get the wrapped body — but it is not the scoring path, is best-effort
  in opencode (a failed title is silently ignored), and the benchmarked model is pinned via
  `/model`. Does not change the verdict; worth a line in the shim ticket.

---

## VERDICT

- **Coding-eval path streams?** YES
- **Benchmark scoring path streams?** YES (its real completions run through opencode =
  streaming; bench.sh itself never routes a completion through the Cline pools — only a
  non-stream *status* read).
- **No non-streaming client routes real completions through the 5 Cline pools.**

### => A — accept Cline as-is, file a shim ticket for later.

**One-sentence reason:** Both eval paths that hit the 5 open pools (the opencode coding
agent AND the benchmark, whose real completions run through that same opencode agent) SSE-
stream, and the only non-stream gateway hit in the harness is a status read that never
touches the Cline pools — so the wrapped-envelope bug is latent; ticket the provider-scoped
unwrap shim for any future non-streaming OpenAI client rather than blocking on it now.
