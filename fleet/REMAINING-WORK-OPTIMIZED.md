# Charon Remaining Work — Optimized Work-Composition Plan (WCI pass)

READ-ONLY analysis. No code changed. Generated 2026-07-03 against `feat/prod-install`.

Merged already (per git log on `feat/prod-install`): **SR-1, SR-2, SR-3, SR-5, SR-10, SR-11**.
This plan covers everything still open: **SR-4, SR-6, SR-7, SR-8, SR-5b, SR-13, TIER-SELECT**.

---

## 1. Ticket inventory (owns / deps / gate / size)

| Ticket | Owns (product files) | depends_on (LOGIC after de-dup) | Gate | Size | Model |
|---|---|---|---|---|---|
| **SR-4** | `fleet/SMART-ROUTING.md` (doc, non-product) | — | none | S | DeepSeek |
| **TIER-SELECT-A** *(split)* | `model_catalog.py` (NEW), `cli.py`, `tests/test_model_catalog.py` | — | none | M | DeepSeek |
| **SR-7** | `spend_limits.py`, `proxy_server.py` | — (SR-2, SR-5 merged) | none | S–M | Claude |
| **SR-5b** | `proxy.py`, `proxy_server.py` | — (SR-2, SR-5 merged) | none | M | Claude |
| **TIER-SELECT-B** *(split)* | `proxy_server.py`, `gateway.py`, `tests/test_tier_select.py` | TIER-SELECT-A | none | S–M | DeepSeek* |
| **SR-6** | `translate.py` (NEW), `proxy_server.py` | — (SR-2 merged) | **DESIGN** | L | Claude |
| **SR-8** | `proxy_server.py` + 6 modules (`consensus`, `speculative_execution`, `request_inspector`, `session_affinity`, `virtual_keys`, `observability`) | — (SR-2 merged) | **DECISION** | M | Claude |
| **SR-13** | `proxy_server.py`, `cli.py` | (tail of proxy_server.py chain) | none | L | Claude |

\* TIER-SELECT-B touches the shared critical `proxy_server.py` (UI edit only, no money/auth logic).
DeepSeek is fine if it rebases carefully onto the post-chain file; escalate to Claude if the rebase is non-trivial.

**Key finding — the board `depends_on` fields overstate the real graph.** Almost every SR
`depends_on` on `proxy_server.py` is labelled `real-dep: … single-owner file` — i.e. it is a
**shared-file serialization constraint, NOT a logic prerequisite**. Once you separate the two, the
logic graph is shallow and the only true bottleneck is that six tickets want to write one file.

---

## 2. Dependency + collision graph

### Logic dependencies (genuine build/correctness prereqs)
```
SR-5 (merged) ──► SR-5b   (SR-5b multiplies the pricing SR-5 captured)
SR-5 (merged) ──► SR-7    (SR-7 estimate uses SR-5 pricing)
TIER-SELECT-A ──► TIER-SELECT-B  (web renders the catalog module A creates)
```
That is the *entire* real logic graph. Everything else is file contention.

### File-collision graph — `src/charon/proxy_server.py` (the ONE bottleneck)
Six remaining tickets all write `proxy_server.py`, forcing a single-writer chain:
```
SR-7 · SR-5b · TIER-SELECT-B · SR-6 · SR-8 · SR-13     (any order, but one at a time)
```
Secondary shared file: `cli.py` — owned by **TIER-SELECT-A** and **SR-13** (serialize: A before 13).

### The critical path
The **`proxy_server.py` single-writer chain is the critical path** — 6 sequential edits, wall-clock ≈
sum of those 6 tickets. No reordering removes it; the only lever is to **shrink what sits on it**
(re-scope) and **stop gated tickets from stalling the ungated ones** (reorder).

---

## 3. What is genuinely parallel vs. only looks independent

- **Genuinely parallel (disjoint owns, deps met, ungated):** SR-4, TIER-SELECT-A, and the *head* of
  the proxy_server.py chain (one of SR-7). These 3 can run at once from a cold start.
- **Looks independent but is NOT:** SR-5b, SR-6, SR-8, TIER-SELECT-B, SR-13 all *look* unblocked
  (their logic deps are merged) but **collide on `proxy_server.py`** — they must go one at a time.
- **Gated, so off the immediate path:** SR-6 (design), SR-8 (decision) — but their **non-code
  deliverables (design note / recommendation) are draftable NOW in parallel**, off any owned file.

---

## 4. Optimized wave plan

### Wave R0 — buildable NOW, fully concurrent (3 build + 2 prep)
| Lane | Ticket | Model | Rationale |
|---|---|---|---|
| build | **SR-4** | DeepSeek | Doc-only, disjoint fleet doc, zero code risk. |
| build | **TIER-SELECT-A** | DeepSeek | Pure stdlib DATA + CLI picker; well-specced; OFF the proxy_server.py critical path (the whole point of the split). |
| build | **SR-7** | Claude | Head of the proxy_server.py chain; deps (SR-2/SR-5) merged; money-path → Claude. Start the critical path immediately. |
| prep | **SR-6 design note** | Claude | Draft provider-detection / breakpoint-placement / streaming note for operator sign-off. Collapses gate latency; touches no owned file. |
| prep | **SR-8 recommendation** | Claude | Draft per-module wire/remove/leave-marked recommendation for sign-off. Touches no owned file. |

All three build lanes have disjoint owns (`SMART-ROUTING.md` / `model_catalog.py`+`cli.py` /
`spend_limits.py`+`proxy_server.py`) → zero collision. The two prep lanes write design docs only.

### Wave R1 — proxy_server.py chain, ungated-first (serial, by readiness)
Run in this order; each merges before the next starts (single writer of `proxy_server.py`):

1. **SR-5b** (Claude) — money-path multiply. **Place immediately after SR-7** so the two
   spend-limiter call-site editors are adjacent (see §5 hazard). Deps merged; ungated.
2. **TIER-SELECT-B** (DeepSeek*) — web picker; needs TIER-SELECT-A done (from R0) + a
   proxy_server.py slot. **Not logically after SR-8** — pull it ahead of the gated tickets so it
   never waits on a sign-off.
3. **SR-6** (Claude) — *slots in the moment its design note is signed.* New `translate.py` +
   `_build_upstream_req` wiring.
4. **SR-8** (Claude) — *slots in the moment its recommendation is signed.* Keep it **before SR-13**
   so SR-13 refactors the final `_handle()`.
5. **SR-13** (Claude) — auth/session refactor of `_handle()`; **tail of the chain** so it rebases
   onto the final file and onto TIER-SELECT-A's `cli.py`. Security-sensitive → Claude.

> Scheduling rule: the chain is a token. Whoever's turn it is AND is unblocked writes next. If SR-6/SR-8
> sign-offs are slow, R1 proceeds SR-5b → TIER-SELECT-B → SR-13 without them, and the two gated
> tickets drop in whenever cleared (SR-8 before SR-13; if SR-13 already merged, SR-8 just rebases).

### Wave R2 — blocked on operator (see §6)
SR-6 and SR-8 code, until their notes are signed.

---

## 5. Re-scoping / outside-the-box proposals

**① SPLIT TIER-SELECT (biggest concurrency win — the prompt already sanctions it).**
The prompt's "Optional phasing" splits cleanly:
- **TIER-SELECT-A** = `model_catalog.py` (NEW) + `cli.py` picker + `test_model_catalog.py`,
  `depends_on: EMPTY`. Runs in **Wave R0**, in parallel, entirely OFF the proxy_server.py critical path.
- **TIER-SELECT-B** = `proxy_server.py` web fieldset + `gateway.py` catalog action +
  `test_tier_select.py`, depends only on A.
This moves the largest mechanical chunk (curated catalog + CLI) off the bottleneck and shrinks the
critical-path node to a small web edit. Net: one big serial node becomes one parallel node + one small
serial node.

**② REORDER the proxy_server.py chain: ungated-first, gates drop in on sign-off.**
The board hard-codes `SR-6 → SR-7 → SR-8 → TIER-SELECT → SR-5b → SR-13`, but SR-6/SR-8's position is
arbitrary (shared-file only). Leading with the **design-gated SR-6** stalls the *entire* file behind
an operator sign-off. Put **ungated SR-7 → SR-5b → TIER-SELECT-B → SR-13** first, and let SR-6/SR-8
slot in whenever cleared. The high-value money-path fix (the `cost_usd = 0` double-bill root cause)
then ships **without waiting on any gate.**

**③ DRAFT the gate deliverables now (in R0), in parallel.** SR-6 (design note) and SR-8
(recommendation) are both "write → sign-off → build." The write halves touch no owned code and can be
produced concurrently in R0 and handed to the operator, collapsing gate latency so R2 is short.

**④ REDUNDANCY / CONTRADICTION — SR-7 vs SR-5b share the exact same call sites.** Confirmed in source:
both edit `proxy_server.py:659-662` (pre-flight `spend_limiter.check(est_cost)`) and `:801-802`
(`if … cost > 0: spend_limiter.record(cost)`). SR-7 wants to **drop the `cost>0` guard** (record an
estimate even at 0); SR-5b wants to **change what `cost` is** (computed from stored pricing). If SR-5b
lands far after SR-7 (as the board sequences it, after TIER-SELECT) it can **silently regress SR-7's
"record even when 0"** semantics. **Fix:** sequence SR-5b **immediately after SR-7** (done in R1), and
add a cross-note to SR-5b: "preserve SR-7's always-record-estimate behavior; do not reinstate the
`cost>0` guard." Consider merging the two call-site edits into one ticket if a single agent takes both.

---

## 6. BLOCKED-on-operator — exactly what each gate needs

- **SR-6 (DESIGN-GATED).** Needs an operator-signed design note covering: (a) provider detection —
  how a request is identified as Anthropic-bound (by route/provider, NOT a hardcoded model list);
  (b) `cache_control` breakpoint placement — where the marker goes so the cached prefix stays
  byte-identical across turns; (c) streaming behavior. *Draftable now (R0 prep lane).*
- **SR-8 (DECISION-GATED).** Needs operator sign-off on a per-module **wire / remove / leave-marked**
  recommendation for the six constructed-but-dead modules (consensus, speculative_execution,
  request_inspector, session_affinity, virtual_keys, observability). Constraint: if speculative or
  consensus are wired, they MUST be opt-in + OFF by default (spend multipliers). *Draftable now (R0
  prep lane).*
- **Coordination flags (not blockers, but sequence hazards):**
  - **SR-13 ↔ token→secrets.json rotation:** `CHARON_SESSION_KEY` rides in `secrets.json`; single
    writer must not collide with the pending token rotation. Land SR-13 after the rotation or
    coordinate the one secrets writer.
  - **SR-6 / SR-13 follow-on owns:** both designs also touch `secrets.py` / `gateway.py` (out of the
    scoped owns) — coordinate as follow-ons, don't write them in these tickets.
  - **cli.py:** TIER-SELECT-A writes it before SR-13 (already the R1 tail order).

---

## 7. Model-assignment summary
- **DeepSeek V4 Pro** (well-specced, mechanical/data): SR-4, TIER-SELECT-A, TIER-SELECT-B.
- **Claude** (money-path / security / design-sensitive): SR-7, SR-5b, SR-6, SR-8, SR-13, plus both R0
  prep drafts (SR-6 design note, SR-8 recommendation).
