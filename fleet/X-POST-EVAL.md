# X-POST-EVAL — Ahmad Awais "make DeepSeek V4 outperform Opus 4.7" thread

**Source:** https://x.com/MrAhmadAwais/status/2050956678502420612 (Ahmad Awais / @CommandCodeAI)
**Retrieval note:** x.com and r.jina.ai both returned 401 (not directly fetchable). Content reconstructed from WebSearch snippets of the original tweet + a follow-up tweet (2051377695389589935, Kimi K2.6), a talk ("Making DeepSeek v4 outperform Opus 4.7 with Taste"), and a third-party summary (summify.io). Confidence: **high** on the core claims (consistent across ≥3 secondary sources); **medium** on exact numbers (author's own figures, unverified).
**Date:** 2026-07-03 · READ-ONLY research, no code changed.

---

## 1. What the post actually claims

Thesis: *"open model bad at tool calling" is almost always a harness problem, not a model problem.* Awais says they made **DeepSeek V4 Pro beat Opus 4.7 6/10 times** on their internal eval, and turned DeepSeek V4 Flash from "unusable" into "competitive," by fixing the **agent harness** — not the model. Claims to have studied "hundreds of billions of tokens" through CommandCode (their open-source AI CLI).

Concrete methods described:

- **C1 — Validate-then-repair tool calls (the headline).** When an open model emits a malformed tool call (JSON string where an array is expected, `null`/empty-object for optional params, schema mismatch), the harness doesn't just bounce the provider error back. It **first repairs the call** to a valid form, executes it, and **also feeds a "repair hint"** back to the model so the next call is correct. Metaphor: "teaching someone to drive — first prevent the accident, then explain how to avoid it."
- **C2 — Repair library grown like DB migrations.** ~3,200 LOC initially → "16,000 repair variations," each a small rule targeting one recurring failure pattern, accumulated empirically from observed traffic. Applied across DeepSeek, Kimi, MiniMax.
- **C3 — Claimed failure rate.** "50–60 tool-call failures per billion tokens" from schema mismatches before repair; near-zero repeat failures after the first repair+hint.
- **C4 — Gateway provider-capability flag negotiation.** Requests ask the gateway for `zeroDataRetention: true` and `disallowPromptTraining: true`. These are **request-level all-or-nothing per upstream**. If any provider in the whitelist (`order`) lacks a flag, the gateway hard-fails (`NoNonTrainingProvidersError`) and the request dies. Their fix (`buildGatewayOptions`): **drop each flag independently** based on whether *anyone* in the whitelist lacks it, so the request proceeds under the **intersection** of guarantees the candidate providers actually support (e.g. novita = no-training but not ZDR; fireworks = ZDR but not no-training).
- **C5 — Same model ID, different results by upstream.** DeepSeek V4 Pro scored differently on their eval depending on which upstream the gateway picked for the *same* logical model — routing/provider identity materially changes agentic performance.
- **C6 — "Taste" / skill files.** User preferences stored as version-controlled markdown "taste files" in the git repo, injected as context, so the agent learns developer patterns transparently (no opaque fine-tune, no stale data). This is a product feature, tangential to the harness thesis.

---

## 2. Critical evaluation

| # | Claim | Sound? | Novel? | Verdict |
|---|-------|--------|--------|---------|
| C1 | Validate-then-repair tool calls + repair hint | **Yes** | Partially | The single strongest, most transferable idea. Repairing arguments against the declared JSON schema and returning a corrective hint is well-grounded: open models fail on *formatting/schema adherence* more than on *intent*, so a deterministic repair layer recovers real capability. Not truly novel — constrained decoding, grammar-based sampling (llama.cpp GBNF, Outlines), and OpenAI/Anthropic tool-schema coercion all attack this — but doing it **post-hoc at the gateway across arbitrary providers**, with a hint loop, is a legitimately useful packaging. |
| C2 | 16,000 repair variations, migration-style | Plausible but **hype-flavored** | No | "16,000 variations" is almost certainly parameter/permutation counting, not 16,000 hand-written rules — treat as marketing. The *pattern* (a small, growing, testable rule set keyed by failure signature) is sound and maintainable. The number is not evidence of anything; ignore it. |
| C3 | 50–60 failures/billion tokens; 6/10 vs Opus | **Unverified** | — | Author's own numbers, no methodology, no public eval. "6/10 wins" on an undisclosed in-house eval is a coin-flip dressed as a win and is exactly the kind of claim a vendor makes to sell a CLI. Directionally believable (harness fixes do lift weak-formatter models); quantitatively **not evidence**. Don't repeat the numbers as fact. |
| C4 | Per-flag independent capability negotiation | **Yes — genuinely good** | Somewhat | This is real, non-obvious systems engineering. Treating privacy/compliance guarantees (ZDR, no-training) as an **all-or-nothing intersection over the candidate set** and degrading each flag independently rather than hard-failing the whole request is a correct and underappreciated pattern for a multi-provider gateway. The subtle risk they gloss over: silently *dropping* a privacy flag to make a request succeed can violate a user's compliance expectation — degradation must be **observable and policy-gated**, not silent. |
| C5 | Same model ID ≠ same behavior across upstreams | **Yes — important** | No (but under-appreciated) | Correct and directly relevant to any failover gateway. Different upstreams for the "same" model differ in quantization, tokenizer/template, tool-format, context limit, and sampling defaults. This validates per-(model×provider) treatment rather than per-model. |
| C6 | "Taste" markdown skill files | Sound, mundane | No | Just version-controlled system-prompt/context injection (à la `CLAUDE.md`, cursor rules). Fine, but it's product UX, not a gateway technique. Low relevance to Charon-as-gateway. |

**Overall:** The thread is a vendor pitch for CommandCode, so discount the numbers and the "6/10 beats Opus" framing. But stripped of hype, **two claims are technically sound and directly on-point for a failover gateway** (C1 tool-repair, C4 capability-flag intersection), and one is a good design principle Charon should already honor (C5).

---

## 3. Applicability to Charon / DeepSeek V4

**Current Charon state (verified in `src/charon/`):** There is **no tool-call repair or validation layer**. The only `tool_calls` reference in source is `request_inspector.py:17` merely *detecting* their presence for routing hints. `response_normalizer.py` operates on `choices[0].message.content` **strings** (STRIP_BOILERPLATE / FIX_JSON / STANDARDIZE_MD) — it does **not** touch `message.tool_calls[].function.arguments`. So C1 addresses a real, currently-empty seam. Charon already has provider failover, `quality_scorer`, `guardrails`, `spend_limits`, `discover`, and the tracked `ADOPT-GATEWAY-FEATURES.md` roadmap.

### Ranked incorporation ideas

**#1 — Tool-call repair/validation module (from C1). HIGH value, MEDIUM effort.**
New `src/charon/tool_repair.py` sitting on the response path, symmetric to `response_normalizer` but operating on `choices[].message.tool_calls[].function.arguments`. For each tool call:
1. Parse `arguments` (JSON); if the model wrapped an object/array in a JSON *string*, unwrap it.
2. Validate against the request's declared tool `parameters` JSON-schema (the schema is already in the request body — no network needed, stays stdlib-only per Charon's module conventions).
3. Apply a small, ordered, table-driven rule set for the common open-model failure patterns: string-encoded-JSON → parsed; `null`/`{}` for absent optional params → omit the key; single object where array expected → wrap; type coercion (`"true"`→`true`, numeric strings). Each rule = one testable function keyed by failure signature (Charon-scale: a couple dozen rules, **not** 16,000 — call out that number as hype in the ADR).
4. Opt-in **repair-hint injection**: on repair, optionally append a system/tool message so the *next* turn self-corrects.
- **Why it fits Charon:** deterministic, stdlib-only, per-response, matches the existing normalizer pattern and the "make weak/cheap providers usable → cheaper failover" thesis. This is the biggest lever for DeepSeek V4 specifically (its documented weak spot is tool-schema adherence, not reasoning).
- **Effort:** ~1 ticket. Repair engine + rule table + tests (~300–500 LOC + fixtures). Wire as an opt-in stage in `proxy_server.py` after the normalizer. **Emit an observability counter per repair** (which rule fired, which model×provider) — that telemetry is itself valuable for routing.
- **Caveat:** must be **config-gated and off by default for tool calls that mutate state** — silently "repairing" a wrong argument can execute the wrong action. Repair only *format/schema* violations, never guess *semantic* values.

**#2 — Capability-flag intersection in provider selection (from C4). MEDIUM value, LOW–MEDIUM effort.**
If/when Charon exposes privacy/compliance requirements (no-train, zero-data-retention, region), model provider capabilities as a matrix and, when a request asks for flags, compute the **intersection over the candidate providers in the failover order** rather than hard-failing if one lacks a flag — but surface any dropped flag as an **observable, policy-gated** event (log + response header/metadata), never silently. Ties into the existing `guardrails`/`policy_router` seam.
- **Effort:** small if a provider-capabilities field already exists in config; medium if the schema must be added. Mostly config + selection logic + tests.
- **Honest flag:** only worth it once Charon actually has compliance-sensitive users. For a solo-dev local gateway this is **lower priority than #1** — park it as a design note, don't build yet.

**#3 — Per-(model × provider) identity, not per-model (from C5). LOW effort, mostly a principle/audit.**
Confirms Charon should treat `deepseek-v4-pro@fireworks` and `deepseek-v4-pro@novita` as distinct routing targets (distinct quality scores, tool-format quirks, context limits). **Directly relevant to the tracked silent-downgrade bug** (namespaced-id 200s discarded/refetched, double-billing opencode-zen): both stem from collapsing model identity across providers. Action: an audit pass to ensure `quality_scorer`/`discover`/routing key on the full (model, provider) tuple, and that the repair-rule table (#1) can be scoped per-provider.
- **Effort:** audit + possibly a keying fix; folds into existing bug work.

### Does NOT apply / not worth it
- **C2's "16,000 variations":** ignore the number. Adopt the *pattern* (small growing rule table) at Charon scale only.
- **C3's benchmark numbers ("6/10 beats Opus", "50–60/billion"):** unverified vendor marketing — do not cite as fact anywhere in Charon docs.
- **C6 "taste files":** product/UX feature (versioned context injection), not a gateway mechanism. Charon-as-gateway shouldn't own user-preference storage; if relevant at all it belongs to the work-engine/agent layer, and only as opt-in context — low priority.

---

## 4. Bottom line

The thread is a CommandCode sales pitch — discount the "6/10 beats Opus 4.7" numbers. But two ideas are technically sound and land on a real gap in Charon:

1. **Tool-call validate-then-repair** (`tool_repair.py`) — the top recommendation. Deterministic, stdlib-only, fits the existing normalizer pattern, and is the single biggest lever to make cheap/open providers (esp. DeepSeek V4) reliable enough to fail over to. **~1 ticket, medium effort.** Build it schema-only, config-gated, off-by-default for state-mutating calls, with per-rule telemetry.
2. **Per-flag capability intersection** in provider selection — correct pattern, but **park until Charon has compliance-sensitive users**; when built, degradation must be observable, never silent.
3. **Per-(model×provider) identity** — a principle Charon should already enforce; ties directly into the known silent-downgrade/double-bill bug. Fold into that bug's audit.
