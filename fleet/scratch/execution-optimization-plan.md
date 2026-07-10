# Execution-Optimization Plan — Charon fleet backlog

Author: WCI/optimization planner sub-session · Date: 2026-07-08
Authority for collisions: `fleet/validate_board.sh` (GREEN, structurally valid) — a shared file in
`owns:` = tickets CANNOT run concurrently. Doctrine applied: `COORDINATOR-DOCTRINE-v2.md`
(right-size model, batch, parallelize owns-disjoint, chain-depth cap 1, must-read gates C1–C7,
adversarial review for core/money-path, background so latency≠slowdown).

**RECOMMEND-ONLY.** Board not edited, nothing launched, nothing committed.

Vehicle rule: touches `src/charon/**` (or product `tests/`, Dockerfile, workflows) → **DROID TAB**
(operator runs `fleet-droid.sh <tier> --wait 3 --retries 10`; model = Claude resolved by
`charon tier resolve <tier> --executor anthropic`, NOT a gateway model). Rig / `fleet/**` /
`capability/**` / `benchmark/**` / board / docs / design / investigation / live-`/data`-config →
**manager SUB-SESSION** (Agent tool, Claude right-sized). `capability/` and `benchmark/` are under
`fleet/` = RIG → sub-session, never a product droid.

Tier→Claude class (interim scorecard mapping, doctrine §STATUS): frontier→Opus-class,
strong→Sonnet-class(high), economy/sonnet→Haiku/Sonnet-class. Droid resolves per-tab.

---

## KEY FRAME (from coordinator correction)

- **PROXY-FAILOVER-FIX is NOT in flight** — the earlier launch hit a now-fixed `fleet-droid.sh`
  arg bug and errored before claiming; nothing was built. It is **Wave-1 READY-TO-LAUNCH**, sole
  owner of `src/charon/proxy_server.py`.
- The **11 rebase-after tickets stay BLOCKED until PROXY-FAILOVER-FIX MERGES**:
  GUI-SVELTE-BUILD, DRAIN-ROUTING, INC-401-FAILOVER, RFL-2, RFL-3, RFL-4, SR-13, SR-6,
  COST-RANK-AUTO, GPT5-POOL-REORDER, POOLS-SIMPLIFICATION. `proxy_server.py` becomes the single
  most-contended file on the board post-merge — it bounds wall-clock (see Critical Path).

---

## 1. ACTIONABLE INVENTORY

### 1a. READY (state=ready) — prompts all exist, verified
| ticket | tier | work_class | owns (key files) | deps | prompt? | vehicle | model | blocked? |
|---|---|---|---|---|---|---|---|---|
| PROXY-FAILOVER-FIX | strong | money-path | proxy_server.py, balance.py, +tests | none (P1 self-contained) | yes | DROID TAB | Claude/strong | **NO — Wave 1** (adversarial review before merge; C2) |
| RFL-5 | frontier | greenfield | context_shaper.py (NEW), test | none | yes | DROID TAB | Claude/frontier (reserve Claude, do NOT gateway) | NO — Wave 1, **adversarial gate** (mutates user content; C3) + design-settled check |
| SR-3 | economy | bugfix | cache.py, test_cache.py | none | yes | DROID TAB | Claude/economy | NO — Wave 1 |
| SR-10 | strong | ci-infra | docker-compose.yml, release.yml, Dockerfile | none | yes | DROID TAB | Claude/strong | NO — Wave 1 (**operator micro-decision**: single image source; RECOMMENDED default = image-only/CI) |
| SR-11 | economy | ci-infra | .github/dependabot.yml | none | yes | DROID TAB | Claude/economy | NO — Wave 1 (trivial) |
| TOOL-REPAIR-MUTATING | economy | bugfix | tool_repair.py, test | none | yes | DROID TAB | Claude/economy | NO — Wave 1 |
| BENCH-REGROUND-LIVE | strong | refactor | capability/grades.py, benchmark/lib/tier_chart.py | none | yes | SUB-SESSION | Claude/Sonnet | NO — Wave 1 (**unblocks whole bench chain**) |
| FRAGILITY-TICKETS | economy | docs | fleet/board/ (authors 4 NEW tickets) | none | yes | SUB-SESSION | Claude/Haiku-Sonnet | NO — Wave 0/1 (expands backlog; serializes board writes) |
| HANDOFF-PIPEFAIL | economy | bugfix | fleet/handoff.sh | none | yes | SUB-SESSION | Claude/Haiku-Sonnet | NO — Wave 1 |
| SR-4 | economy | docs | fleet/SMART-ROUTING.md | none | yes | SUB-SESSION | Claude/Haiku | NO — Wave 1 |
| BENCH-OOB-GRADING | frontier | ci-infra | benchmark/bench.sh, grade_state.py, grader-daemon.py, graders, … | build-after BENCH-PROVISIONAL-SCORING | yes | — | — | **BLOCKED — DO NOT SCHEDULE** (operator Q1 grader substrate not provisioned) |

### 1b. PARKED-BUT-BUILDABLE (deps met, prompt exists, owns-disjoint from Wave-1 product files) — require manager un-park + gate
| ticket | tier | work_class | owns | deps (met?) | prompt? | vehicle | model | note |
|---|---|---|---|---|---|---|---|---|
| SECRET-HOTROTATE | strong | bugfix | secrets.py, test_secrets.py | none ✓ | yes | DROID TAB | Claude/strong | C1 security → strong + independent re-verify (Rule 9); coordinate `/data/rotate-hf.py` on gateway host |
| SR-12 | economy | preset | providers.py, test_providers.py | SR-5 ✓ | yes | DROID TAB | Claude/economy | mechanical preset add (opencode-go/zen), operator-confirmed. **providers.py collision group** — pick ONE of SR-12/LONGCAT/PROVIDER-FLATRATE per wave |
| DTC-6 | strong | tests | test_fence.py, test_failover.py, test_decompose.py | DTC-2,3 ✓ | yes | DROID TAB | Claude/Sonnet | backlog test-parametrization; low priority |
| OHMYPI-ASSESS | strong | research | (none) | none ✓ | yes | SUB-SESSION | Claude/Sonnet | research; **unblocks CONNECT-OMP-WSL** |
| BOARD-REDS-TRIAGE | sonnet | docs | (none) | none ✓ | yes | SUB-SESSION | Claude/Sonnet | board triage |
| WORKCLASS-BACKFILL-REVIEW | sonnet | docs | (none) | none ✓ | yes | SUB-SESSION | Claude/Sonnet | board review |
| FRONTIER-REVIEW-POLICY | economy | docs | fleet/board/FRONTIER-REVIEW-POLICY.md | none ✓ | yes | SUB-SESSION | Claude/Haiku | policy doc |
| CWD-CONFIG-VERIFY | strong | verify | (none) | none ✓ | yes | SUB-SESSION | Claude/Sonnet | verification task |
| ZEN-DRIFT-CLEANUP | sonnet | routing | /data/pools.json, /data/models.json | none ✓ | yes | **MANAGER/SSH** (NOT droid) | manager | live-4-LOM config audit; needs the box |
| COOLDOWN-FIX3 | sonnet | bugfix | proxy.py, test_proxy_downgrade.py | none ✓ | yes | DROID TAB | Claude/Sonnet | **VERIFY not superseded** — master already landed cooldown-clamp-120s (f3a73f2); may be done. Shares proxy.py w/ blocked INC-401/DRAIN → land BEFORE them if still needed |

---

## 2. OWNS-COLLISION GROUPS (concurrency ceilings)

- **`src/charon/proxy_server.py`** (the bottleneck): PROXY-FAILOVER-FIX ‖ INC-401-FAILOVER ‖
  DRAIN-ROUTING ‖ SR-13 ‖ SR-6 ‖ SR-6-Phase2 ‖ RFL-2 ‖ RFL-3 ‖ RFL-4 ‖ GUI-SVELTE-BUILD ‖
  BRIDGE-RELAYFEATURES ‖ UX-POLISH. → **STRICTLY ONE AT A TIME.** PFF holds it in Wave 1; the
  rest serialize behind the merge.
- **`src/charon/proxy.py`**: COOLDOWN-FIX3, INC-401-FAILOVER, DRAIN-ROUTING. (PFF does NOT own
  proxy.py — COOLDOWN-FIX3 can run in Wave 1 alongside PFF.)
- **`src/charon/providers.py`**: SR-12, LONGCAT-PROVIDER, PROVIDER-FLATRATE, SR-5(done). → one per wave.
- **`src/charon/config.py`**: DRAIN, COST-RANK-AUTO, POOLS-SIMPLIFICATION, GUI-SVELTE, CATALOG-SYNC-DRIFT, TIER-RECS, LONGCAT, PROVIDER-FLATRATE. → one per wave (all but CATALOG-SYNC are blocked/parked now).
- **`src/charon/gateway.py`**: DRAIN, COST-RANK-AUTO, POOLS-SIMPLIFICATION, GUI-SVELTE, UX-POLISH. → one per wave (all blocked now).
- **`capability/grades.py` + `benchmark/lib/tier_chart.py`**: BENCH-REGROUND-LIVE, BENCH-PROVISIONAL-SCORING, BENCH-AGGREGATE-N, BENCH-DIFFICULTY-CAL, ASSIGN-DISCRIM-GATE. → **serial bench chain** (parallel to product chain, rig-side sub-sessions).
- **`fleet/board/`**: FRAGILITY-TICKETS owns the whole dir → serializes board-file authoring; keep
  other board-writers (FRONTIER-REVIEW-POLICY, BOARD-REDS-TRIAGE) out of the same instant.
- **`/data/pools.json`**: ZEN-DRIFT-CLEANUP, GPT5-POOL-REORDER, POOLS-SIMPLIFICATION (last two blocked).

Everything in Wave 1 below is **owns-disjoint** — verified against the collision groups.

---

## 3. WAVE SCHEDULE

### WAVE 0 — optional prep (SUB-SESSIONS, run first or fold into Wave 1)
- **FRAGILITY-TICKETS** (sub, Haiku-Sonnet) — authors 4 new board tickets (PROVIDER-PROBE-FIX,
  ACTION-PIN-POLICY, DOCKER-SMOKE-CLEANUP, CI-WORKFLOW-POLICY-GATE). Do FIRST so the backlog is
  complete before scheduling, and so no other board-writer collides.
- **Readiness-gap authoring** (one sub, Sonnet) — author the TBD prompts / finalize PROVISIONAL
  owns for CATALOG-RECONCILE-GPT5, CATALOG-SYNC-DRIFT, CAP-PROBE-BACKLOG, TIER-RECS, DSGN-WRITEBACK
  so they become claimable in later waves (see §6). Pure prep; no product code.

### WAVE 1 — the largest set that can start NOW (deps met, owns-disjoint, unblocked, prompt-ready)
**PARALLEL DROID TABS** (operator opens each; Claude via tier resolve):
1. **PROXY-FAILOVER-FIX** (strong) — sole owner proxy_server.py; **THE critical-path unlock**.
   money-path (C2) → **adversarial review before merge**, Phase-1-only scope (P1 Retry-After + P5 UA).
2. **RFL-5** (frontier) — context_shaper.py NEW; **adversarial gate** (mutates user content, C3),
   reserve Claude. Confirm the per-virtual-key gating design is settled before merge.
3. **SR-3** (economy) — cache.py correctness + hit/miss counters.
4. **TOOL-REPAIR-MUTATING** (economy) — tool_repair.py mutating-gate bugfix.
5. **SR-10** (strong) — deploy hygiene; needs the operator's one-line image-source pick (default image-only).
6. **SECRET-HOTROTATE** (strong) — secrets.py; C1 → strong + re-verify. *(un-park first)*
7. *(capacity permitting)* **SR-11** (economy, dependabot.yml) and/or **SR-12** (economy, providers.py)
   and/or **COOLDOWN-FIX3** (verify-not-superseded) and/or **DTC-6** — all owns-disjoint, low-risk fillers.

**PARALLEL SUB-SESSIONS** (manager Agent tool; Claude right-sized):
- **BENCH-REGROUND-LIVE** (Sonnet) — capability/grades.py + tier_chart.py; **unblocks the bench chain**.
- **HANDOFF-PIPEFAIL** (Haiku-Sonnet) — fleet/handoff.sh pipefail bugfix.
- **SR-4** (Haiku) — SMART-ROUTING.md doc fix.
- **OHMYPI-ASSESS** (Sonnet) — research; **unblocks CONNECT-OMP-WSL**.
- *(fillers)* BOARD-REDS-TRIAGE, WORKCLASS-BACKFILL-REVIEW, FRONTIER-REVIEW-POLICY, CWD-CONFIG-VERIFY.
- **ZEN-DRIFT-CLEANUP** — manager/SSH on the 4-LOM box (not a droid).

### WAVE 2 — unlocked when PROXY-FAILOVER-FIX MERGES (proxy_server.py freed)
`proxy_server.py` is single-owner → **serialize on that file** (droid tabs, one at a time):
- **INC-401-FAILOVER** (strong, proxy.py+proxy_server.py) — first; forks the rest.
- In parallel on OTHER files: **BENCH-PROVISIONAL-SCORING** (sub, after BENCH-REGROUND-LIVE merges —
  bench chain runs concurrently with the product chain the whole time).
- **RFL-3** (proxy_server.py) can interleave with INC-401 only by taking the file *after* INC-401's
  merge — cannot be concurrent.

### WAVE 3 — after INC-401 merges
- **DRAIN-ROUTING** (frontier, money-path, proxy.py+proxy_server.py+gateway.py+config.py) — big one.
- **SR-6** (frontier, translate.py+proxy_server.py) — serialize behind DRAIN on proxy_server.py.
- **GPT5-POOL-REORDER** (manager/SSH, /data/pools.json) — parallel (no proxy_server.py).
- Bench chain: **BENCH-AGGREGATE-N** (sub).

### WAVE 4 — after DRAIN merges
- **COST-RANK-AUTO** (money-path, config.py+gateway.py), **SR-13** (proxy_server.py) — serialize.
- **NANOGPT-PRIMARY-REVIEW** (sub, review DRAIN live).
- Bench: **BENCH-DIFFICULTY-CAL**; **BENCH-OOB-GRADING** *iff operator Q1 answered*; then **BENCH-REDS-REPLAY**, **ASSIGN-DISCRIM-GATE**, **CAP-PROBE-BACKLOG**.

### WAVE 5 — after COST-RANK merges
- **POOLS-SIMPLIFICATION** (gateway.py+config.py+/data/pools.json).
- **RFL-3→RFL-2→RFL-4** (proxy_server.py serial), **GUI-SVELTE-BUILD** (proxy_server.py — huge, serialize),
  **SR-6-Phase2**, **BRIDGE-RELAYFEATURES**, **UX-POLISH** — all contend for proxy_server.py; drain one at a time.

### FINAL — **ATC** (frontier, sub-session, owns nothing) — adversarial audit of all merged work → findings + fix tickets. Runs LAST.

---

## 4. CRITICAL PATH + ROUGH WALL-CLOCK

**Longest dependency chain (product / money-path, all serialized on `proxy_server.py`):**
```
PROXY-FAILOVER-FIX → INC-401-FAILOVER → DRAIN-ROUTING → COST-RANK-AUTO → POOLS-SIMPLIFICATION → ATC(final audit)
```
= **5 sequential build+review+merge cycles + 1 audit.** DRAIN, COST-RANK, PFF are money-path → each
carries an adversarial-review gate (C2/C3, strong model floor). This chain — not the ticket count —
bounds "everything shipped." GUI-SVELTE, RFL-3/2/4, SR-6/Phase2, SR-13, BRIDGE-RELAYFEATURES,
UX-POLISH are NOT on the strict dep path but ALL contend for the same `proxy_server.py`, so they
*extend* wall-clock even though they don't deepen the dependency chain.

**Parallel rig chain (does not gate product):**
`BENCH-REGROUND-LIVE → BENCH-PROVISIONAL-SCORING → BENCH-AGGREGATE-N → BENCH-DIFFICULTY-CAL`
(serialized on capability/grades.py) — 4-deep, runs as sub-sessions alongside the product chain.

**Rough wall-clock (in gated build-cycles, not fake hours):** critical path ≈ **6 serial cycles**;
with one operator gating merges and a sane 4-tab cap, expect the money chain to dominate. Everything
NOT on proxy_server.py (SR-3, SR-10, SR-11, TOOL-REPAIR, SECRET-HOTROTATE, RFL-5, bench chain, all
rig/doc subs) can finish inside the first 1–2 cycles in parallel — the tail is entirely the
proxy_server.py serialization + the money-path review gates.

---

## 5. BLOCKED SET → blocker → exact unblock action (who)

| ticket | blocker | unblock action | who |
|---|---|---|---|
| BENCH-OOB-GRADING | Q1 bench-grader substrate not provisioned; build-after BENCH-PROVISIONAL-SCORING | answer operator Q1 + provision grader substrate; un-park & land BENCH-PROVISIONAL-SCORING; restore `depends_on` | **operator** |
| COORDINATOR-DOCTRINE-ROLLOUT | owns=TBD-CONFIRM + prompt=TBD, parked-for-review | confirm rig injected-rules path + SLOP AGENTS.md target, then author prompt+owns+D&S | **operator** then manager |
| INC-401-FAILOVER | proxy_server.py held by PFF | merge PROXY-FAILOVER-FIX | manager (after merge) |
| DRAIN-ROUTING | PFF + INC-401 (proxy_server.py) | merge PFF then INC-401 | manager |
| COST-RANK-AUTO | PFF + DRAIN-ROUTING | merge DRAIN | manager |
| POOLS-SIMPLIFICATION | PFF + DRAIN + COST-RANK | merge COST-RANK | manager |
| GPT5-POOL-REORDER | PFF + INC-401 | merge INC-401; then manager/SSH on 4-LOM | manager |
| SR-13 | PFF + DRAIN (proxy_server.py) | merge DRAIN | manager |
| SR-6 / SR-6-Phase2 | PFF + INC-401 (proxy_server.py) / SR-6 | merge INC-401 / SR-6 | manager |
| RFL-3 / RFL-2 / RFL-4 | PFF (proxy_server.py); then RFL-3→2→4 chain | merge PFF, then serialize | manager |
| GUI-SVELTE-BUILD | PFF (proxy_server.py) | merge PFF; serialize (large) | manager |
| BRIDGE-RELAYFEATURES | proxy_server.py (BRIDGE-HARDEN dep DONE) | merge PFF + drain the proxy_server.py queue | manager |
| UX-POLISH | proxy_server.py | merge PFF + drain queue | manager |
| BENCH-PROVISIONAL-SCORING (+ AGGREGATE-N, DIFFICULTY-CAL, REDS-REPLAY, CAP-PROBE-BACKLOG) | BENCH-REGROUND-LIVE not merged; capability/grades.py chain | land BENCH-REGROUND-LIVE (Wave 1), then serialize | manager |
| ASSIGN-DISCRIM-GATE | BENCH-REGROUND-LIVE + BENCH-AGGREGATE-N | land both | manager |
| CONNECT-OMP-WSL | OHMYPI-ASSESS research | run OHMYPI-ASSESS (Wave 1 sub) | manager |
| CATALOG-SEARCH-CURATE | CATALOG-SYNC-DRIFT | land CATALOG-SYNC-DRIFT (needs owns finalized) | manager |
| NANOGPT-PRIMARY-REVIEW | DRAIN-ROUTING live | land DRAIN | manager |
| LONGCAT-PROVIDER | external: Meituan LongCat API signup + key | operator signs up + provisions key | **operator** |
| PROVIDER-FLATRATE | no viable target (synthetic.net / apiary dead ends) | operator identifies a real flat-rate provider, else close | **operator** |
| ATC | audits merged waves | run after build waves merge | manager (final) |

---

## 6. READINESS GAPS (prompt=TBD / owns=TBD / PROVISIONAL) — author before claimable
| ticket | gap | what must be authored |
|---|---|---|
| CATALOG-RECONCILE-GPT5 | prompt=TBD | author prompt + `## Dependencies & sequence` section (validator D&S check REDs on un-park without it) |
| COORDINATOR-DOCTRINE-ROLLOUT | prompt=TBD + owns=TBD-CONFIRM | operator confirms rig injected-rules file path + SLOP AGENTS.md target; then author prompt (source = COORDINATOR-DOCTRINE-v2.md) + owns + D&S |
| CATALOG-SYNC-DRIFT | owns PROVISIONAL (tools/catalog_sync.py, config.py) | finalize owns; manager reconciles pricing-source overlap with SR-5b/COST-RANK-AUTO |
| CATALOG-SEARCH-CURATE | owns PROVISIONAL (tools/catalog_curate.py) | finalize owns at activation |
| CAP-PROBE-BACKLOG | owns PROVISIONAL (benchmark/units.tsv, benchmark/probes) | finalize owns; depends on BENCH-PROVISIONAL-SCORING landing |
| TIER-RECS | owns PROVISIONAL (recommend.py NEW, cli.py, config.py) | finalize owns at activation |
| DSGN-WRITEBACK | prompt "authored on activation", owns empty | author prompt + owns at activation |
| DURABLE-BRIDGE-PHASE-2 | owns paths unconfirmed | confirm bridge/ owns paths + add D&S section before un-park |

**Recommendation:** run a single **Wave-0 sub-session** (Sonnet) to author the D&S-compliant prompts
+ finalize the PROVISIONAL owns for CATALOG-RECONCILE-GPT5, CATALOG-SYNC-DRIFT, CAP-PROBE-BACKLOG,
TIER-RECS, DSGN-WRITEBACK. Pure rig authoring, no product code, unblocks later waves cheaply. The two
TBD tickets needing an **operator target confirmation** (COORDINATOR-DOCTRINE-ROLLOUT) cannot be
authored until the operator answers.

---

## 7. RECOMMENDED CONCURRENCY

- **Owns-disjoint ceiling in Wave 1 is high** (every ready ticket is disjoint), so collisions are NOT
  the binding constraint — **operator gating bandwidth + concurrent token burn are.**
- **Recommended: 4 concurrent DROID TABS + 3 concurrent SUB-SESSIONS.**
  - Droid tabs (priority order): (1) PROXY-FAILOVER-FIX [critical path], (2) RFL-5 [adversarial],
    (3) SR-3 or TOOL-REPAIR-MUTATING, (4) SECRET-HOTROTATE or SR-10. Rotate SR-11/SR-12/DTC-6/
    COOLDOWN-FIX3 in as tabs free.
  - Sub-sessions: (1) BENCH-REGROUND-LIVE [unblocks bench chain], (2) HANDOFF-PIPEFAIL, (3) SR-4 /
    OHMYPI-ASSESS. Fold FRAGILITY-TICKETS in as Wave-0 first.
- **Token vs wall-clock tradeoff:** each extra droid tab is a full Claude build session (real tokens)
  + a merge to gate. More tabs shrink wall-clock but pile gating load on one operator and burn tokens
  in parallel. 4+3 is the sweet spot: it saturates the *independent* work in ~1–2 cycles while leaving
  the operator able to give each money-path merge a real (must-read, Rule 10) adversarial review.
  Beyond that, wall-clock is bounded by the proxy_server.py serialization no matter how many tabs open,
  so more concurrency past ~4 product tabs buys little and costs tokens.
- **Doctrine guardrails honored:** money-path/core (PFF, DRAIN, COST-RANK, RFL-5, SECRET-HOTROTATE)
  get the strong-model floor + adversarial review before merge (C1/C2/C3); manager never auto-launches
  a droid (operator opens tabs); chain depth capped (dependent sequences serialized, not chain-delegated);
  all delegations backgrounded.
