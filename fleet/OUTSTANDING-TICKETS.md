# Charon Outstanding Tickets — Consolidated Backlog Review

**Generated 2026-07-04 (revised).** READ-ONLY blast-radius + out-of-box review. No product code touched.
Supersedes the prior 2026-07-03 list. Weighs the NEW context: today we hand-deployed a free/cheap-provider
**routing stack** on the live 4-LOM gateway (manual `cost_rank`/`free` flags in models.json encoding a
draw-down order: free-daily → expiring-credits → persistent-prepaid → metered), promoting NanoGPT
(DeepSeek-V4-Pro flat sub), Groq, Cerebras, NeuralWatt, etc. above opencode-zen.

---

## 0. What the DeepSeek build sessions actually produced (git-verified)

| Assigned | Branch | State | Evidence |
|---|---|---|---|
| **SR-7** | `feat/sr-7-spend-cap-hardening` | ✅ **COMMITTED** (`b45705f`) | drops `cost>0` record guard; records est_cost at 0; adds record to streaming path. +8 LOC proxy_server + 47 LOC test. Clean, coherent. |
| **SR-5b** | `feat/sr-5b-cost-usd-wire` | ⚠ **UNCOMMITTED WIP** in worktree `/home/stack/code/charon-sr-5b` | branch tip == SR-7 commit; `proxy.py` + `proxy_server.py` edited but **never committed**; gate/pytest not verified. |
| **SR-8** | `feat/sr-8-dead-module-decision` | ❌ **NOT STARTED** | branch does not exist. |
| **TIER-SELECT Phase-A** | `feat/tier-select-catalog-a` | ✅ **COMMITTED** (`c4c4189`) | new `model_catalog.py` (150 LOC) + `cli.py` picker + 191 LOC test. |

Net: the SR-7→SR-5b→SR-8 chain session got **1 of 3** done (SR-7), left SR-5b half-built (uncommitted),
never reached SR-8. The parallel TIER-SELECT session finished its Phase-A cleanly. **Two branches carry
un-merged committed work (SR-7, TIER-SELECT-A); one worktree carries uncommitted WIP (SR-5b).**

---

## 1. Verdict table

| Ticket | Built? / status | Relevant? | Verdict | Blast-radius & out-of-box notes |
|---|---|---|---|---|
| **SR-7** | Committed, unmerged | Yes | **DO-NOW** (review+merge) | Small (money-path counter). SR-5b stacks on it — merge together or SR-5b first. |
| **SR-5b** | Uncommitted WIP | **Yes ↑↑** | **DO-NOW** (finish+review) | Money-path, proxy.py hot path. Makes `cost_usd` real → un-blinds spend caps + console. Possible WIP bug (see §2). |
| **TIER-SELECT-A** | Committed, unmerged | Yes ↑ (600+ models) | **DO-NOW** (review+merge) | Low (new module + CLI). Catalog is data-only; verify no vendor branching / fleet strings leaked. |
| **SR-12** (opencode-zen preset) | Parked | Yes ↑ | **DO-NOW** (small) | Trivial preset add; removes the manual base_url band-aid on 4-LOM. opencode-zen/go both now in the draw-down order. |
| **RFL-3** (image/vision exclusion) | Not started | Yes | **DO-NOW / soon** (small) | Low. Mechanical filter over existing `has_images`+`vision` meta; with 600+ mostly text-only models, image→text-only route 400s. High correctness / low effort. |
| **RFL-1** (proactive quota tracking) | Not started | **Yes ↑↑** | **DO-NOW** (module first) | New `quota.py` independent of chain — build+test now; wire into `_handle` later. Free tiers have hard caps (Groq 14.4k RPD, Cerebras 5 RPM, NanoGPT 60M/wk) → pre-flight skip avoids 429+latency thrash. |
| **tool-repair** (`tool_repair.py`) | Not started (only X-POST-EVAL analysis) | **Yes ↑↑** | **DO** (soon) | Medium. Open models (DeepSeek-V4/Kimi) are now PRIMARIES → their tool-schema weakness directly hurts. New module, stdlib, schema-only, OFF-by-default for state-mutating calls. |
| **SR-6 Phase-1** (Anthropic prompt cache) | Not started (design signed) | ↓ (was Yes) | **DEFER** | Low blast radius, design ready. But Anthropic is now a LOW-priority upstream in the draw-down order → cache-saving ROI dropped. Build after the cost/quota wave. |
| **SR-8** (wire 6 dead modules) | Not started (decision cleared) | Partial | **DEFER + RE-SCOPE** | Wire only the 3 free always-on (Observability/RequestInspector/SessionAffinity) first. **Out-of-box: SpeculativeExecutor CONTRADICTS RFL-1** — racing N providers burns N× quota on hard-capped free tiers. Keep speculative+consensus parked until after RFL-1. |
| **SR-13** (GUI session login) | Not started | Low (UX) | **DEFER** | Security-sensitive; no routing relevance. UX/production-readiness wave. Coordinate CHARON_SESSION_KEY with pending secrets rotation. |
| **RFL-2** (chat playground) | Not started | Yes (UX) | **DEFER** | Low. Zero-setup "who served this?" — good production-readiness win, after RFL-1/RFL-3. |
| **RFL-4** (limit editor) | Not started | Yes | **DEFER** | Nothing to edit until RFL-1's limits config exists. After RFL-1. |
| **RFL-5** (context compaction) | Not started | Maybe | **DEFER / EXPERIMENTAL** | Breaks transparent-proxy; opt-in OFF-by-default. Relevant for tiny-ctx free models but risky. Ship module-only when demand appears. |
| **SR-4** (SMART-ROUTING.md doc fix) | Not started | **No — now contradictory** | **CLOSE** (fold into SR-8) | SR-4 documents that speculative/consensus DON'T fire; SR-8 WIRES them so they DO. Doing both is a contradiction — fold the doc correction into whoever wires the modules. |
| **SR-6 Phase-2** (bidi OpenAI↔Anthropic translation) | Parked | No (trigger unfired) | **CLOSE / keep parked** | High blast radius on money-path dispatch + SSE. Revisit-trigger (OpenAI client → Anthropic-only upstream) has not fired. |

---

## 2. Per-ticket detail (non-trivial only)

### SR-5b — finish the money-path multiply (TOP PRIORITY)
Uncommitted WIP in `/home/stack/code/charon-sr-5b` adds `cost_source` to `ProxyObservation`, computes
`cost_usd = tokens_in*cost_input + tokens_out*cost_output` when the provider reports none, adds
`_lookup_pricing` (exact → normalized → final-segment match), and a `_pre_flight_estimate` in
proxy_server.py that replaces the hardcoded `0.0000015` floor. It correctly preserves SR-7's
"record-even-at-0" semantics (feeds computed cost into the same `record`/`check` sites, doesn't reinstate
the guard).
- **BLAST-RADIUS / BUG FLAG:** the diff renames `returned_model=returned` → `returned_model=returned_model`
  and calls `_lookup_pricing(requested_model, expected_model)` — verify `returned_model`/`expected_model`
  are actually bound in `classify()`'s scope (the surrounding code used `returned`/`expected`). If not, this
  is a NameError. **Gate + pytest were never run on this WIP.** Do not merge until a reviewer runs
  `python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q` and confirms the variable binding.
- **Why it jumped in priority:** with the manual draw-down stack live, `cost_usd=0` means the console
  cost column and the universal spend cap are **blind** to every provider that doesn't self-report cost
  (most of them). SR-5b makes those numbers real. It does NOT change routing order (see §3).

### RFL-1 — proactive quota tracking (newly urgent)
The draw-down stack leans on many hard-capped free tiers. Today Charon only learns a provider is
exhausted by **burning a request → 429 → cooldown** (reactive). RFL-1 adds a stdlib sliding-window
per-(provider,model) tracker with pre-flight `can_handle(tokens)`, so a provider that WOULD 429 is skipped
before the call. **Phasing win:** `quota.py` + tests are independent of the proxy_server single-writer
chain — build and unit-test the module now, wire the `_handle` hook in a later proxy_server slot. Pairs
with RFL-4 (hot-edit the limits).

### tool-repair — now a primary-reliability lever
X-POST-EVAL already did the analysis: no tool-call repair layer exists (`response_normalizer` only touches
`message.content` strings, not `tool_calls[].function.arguments`). With NanoGPT DeepSeek-V4-Pro and other
open models now at the TOP of the draw-down order (not just failover fallbacks), their documented
tool-schema-adherence weakness is on the primary path. A stdlib, schema-only, table-driven repair module
(`tool_repair.py`) with per-rule telemetry is the biggest single lever to make the cheap primaries
reliable. **Guardrail:** repair format/schema only, never guess semantic values; OFF-by-default for
state-mutating tool calls.

### SR-8 — re-scope, and mind the quota contradiction
Decision was "WIRE all 6," but the new stack changes the calculus:
- Observability / RequestInspector / SessionAffinity: cheap, always-on, wire freely (SessionAffinity's
  Anthropic-cache-warming value dropped since Anthropic is deprioritized, but pinning is still harmless).
- **SpeculativeExecutor + ConsensusRouter: keep OFF/parked.** Racing or cross-verifying across N providers
  multiplies spend AND **burns N× the free-tier quota RFL-1 is trying to conserve** — directly at odds
  with the draw-down design. Only revisit speculative *after* RFL-1 lands, and only to race genuinely-free
  providers with quota headroom.

### SR-6 — de-prioritized by the new stack
Design is signed and Phase-1 is low-risk, but it only saves money on **Anthropic-wire** routes, and the
draw-down order now pushes Anthropic to the bottom (used rarely). The saving is real but small in the new
regime. Build it after the cost/quota/reliability wave, not before.

---

## 3. Out-of-box findings the routing stack surfaces

1. **Cost-ranked failover ALREADY works — by hand.** `pools.py` sorts every tier `(not free, cost_rank)`
   (free-first, then cheapest) at chain-build time, and `_handle` builds the cost-ranked chain before
   `order_by_cooldown`. So today's manual `cost_rank`/`free` flags ARE honored by routing. SR-5b does NOT
   enable cost-ranked failover (a common misconception) — that already exists. What is still **manual** is
   (a) the `cost_rank` numbers + `free` flags themselves, and (b) `cost_usd=0` blinding the caps/console.
   SR-5b fixes only (b).
2. **NEW IDEA — auto-derive `cost_rank` from captured pricing (the real automation of today's hand-work).**
   SR-5 already captures per-token pricing; nothing derives `cost_rank` from it, so the draw-down order is
   still typed in by hand. A small ticket ("compile `cost_rank` from `cost_input+cost_output`, keep `free`
   and manual overrides winning") would AUTOMATE exactly what we did manually today. This is the
   highest-leverage salvageable idea and **no existing ticket covers it** — recommend creating it.
3. **Draw-down tiers ≠ a single `cost_rank` scalar.** The hand-built order encodes *classes*
   (free-daily / expiring-credits / persistent-prepaid / metered), not just price. Consider a small
   `cost_class` enum feeding the sort ahead of raw `cost_rank`, so "use the expiring credits before the
   prepaid balance" is expressible — pure price ranking can't say that.
4. **Speculative execution vs free quotas** (see SR-8) — a latent contradiction if SR-8 wires it naively.
5. **Per-(model×provider) identity** (X-POST-EVAL C5) — same model id behaves differently per upstream;
   ties into the SR-1 double-bill root cause. Ensure quality_scorer / quota (RFL-1) / repair rules key on
   the full (model, provider) tuple, not the bare model id.

---

## 4. Recommended next 3–5 actions (ranked)

1. **Finish + review + merge the money-path pair: SR-5b then SR-7.** Run the gate on the SR-5b WIP, fix
   the likely `returned_model`/`expected_model` binding bug, confirm pytest green, then merge SR-7+SR-5b
   together. This un-blinds spend caps and the console cost column for the live stack. *(DO-NOW)*
2. **Review + merge TIER-SELECT-A, and land SR-12 (opencode-zen preset).** Both small, both ship
   production-readiness value; SR-12 kills the 4-LOM band-aid. *(DO-NOW)*
3. **Create + build "auto-cost_rank from pricing" (new ticket) + RFL-1 quota module.** These two together
   automate the manual draw-down order (ranking) and add pre-flight cap awareness (thrash avoidance) —
   the direct automation of everything we did by hand today. Build both as chain-independent modules
   first, wire later. *(DO-NOW / DO-NEXT)*
4. **Build tool-repair (`tool_repair.py`), stdlib, schema-only, off-by-default.** Makes the now-primary
   open models (DeepSeek-V4 etc.) reliable. *(DO — soon)*
5. **CLOSE SR-4 and keep SR-6-Phase-2 parked; DEFER SR-6-Phase-1, SR-8 (re-scoped to 3 free modules),
   SR-13, RFL-2/4/5.** Fold SR-4's doc correction into the eventual SR-8 wiring. *(housekeeping)*

**Do RFL-3 (image/vision exclusion) opportunistically** — it's a small, high-correctness filter and slots
into any proxy_server slot.
