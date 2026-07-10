# Designed-Not-Built — Work-Composition Concurrency Plan

Filed 2026-07-09 by the WCI designed-work planning sub-session. Method: `fleet/WCI-METHOD.md`
(dedup -> contention axis -> decompose-or-serialize -> collision-free waves). Optimized for zero
bottlenecks / max concurrency / min wall-clock / never two writers per file per wave.

---

## 0. STATE RECONCILIATION (WCI Step 1 — dedup first; the single biggest optimization)

The contention detector still lists **stale ownership**: `proxy_server.py` shows 26 "owners" but
**most are DONE** (SR-2, SR-5b, SR-6, SR-7, SR-8, TIER-SELECT, RFL-1, SR-13, MODEL-DISCOVERY,
REQUEST-NORMALIZER, INC-401-FAILOVER, PROXY-SERVER-DECOMPOSE, **PROXY-FAILOVER-FIX**). Grounding
against `git log` + `state/done/` changes the picture completely:

- **PROXY-FAILOVER-FIX (Phase 1) is MERGED** — every `rebase-after: PROXY-FAILOVER-FIX` gate
  (DRAIN-ROUTING, COST-RANK-AUTO, POOLS-SIMPLIFICATION, RFL-2, RFL-4) is now CLEAR.
- **SR-5b is MERGED** — `cost_usd` is real per attempt; the whole SR/proxy chain is done.
- **PROXY-SERVER-DECOMPOSE is MERGED** — `proxy_server.py` already split into `console_router.py`,
  `proxy_console_assets.py`, `proxy_response.py` (now ~725 lines, not the old god-file).
- **`cost_rank` auto-derive PARTIALLY LANDED** — SR-6 shipped `pools.derived_cost_rank`
  (gateway.py:150 sorts by `(not free, derived_cost_rank(spec))`). COST-RANK-AUTO's remaining work is
  the **cost_class enum + deriving from METER's per-(model,provider) grain**, not "add derivation".

**In flight right now (Wave 0 — manager review+push, NOT to be re-created):**
`BILLING-EST-COST-FIX` (submitted, forwarder.py — THE cost-accuracy enabler), `NORMALIZE-CASE-QUANT-FIX`
(submitted, proxy.py — unblocks the NeuralWatt/credit legs), `TEST-HARDEN-CONTRACT` (submitted);
claimed: `CI-WORKFLOW-POLICY-GATE`, `RFL-5`.

**Contradiction reconciled (flag for manager confirmation, per `adversarial-review-must-not-silently-
override-operator`):** METER's ticket says *"rebase-after DRAIN-ROUTING/COST-RANK cluster"* while
COST-RANK/FREE-TIER/POOLS say *"consumes METER"*. That circular note is a STALE shared-file artifact
from when DRAIN was expected to write proxy.py first. The task framing ("METER = THE enabler / hub")
resolves it: **METER lands FIRST**, then the actuators consume it. This plan schedules METER-first and
flags it for the manager rather than silently editing METER's ticket.

---

## 1. DEPENDENCY GRAPH (real deps, not assumed)

```
Wave 0 (in flight):  BILLING-EST-COST-FIX ─┐   NORMALIZE-CASE-QUANT-FIX ─┐
                                            │                            │
proxy.py chain:          NORMALIZE ─▶ OPENROUTER-FLAKINESS-FIX ─▶ METER ─▶ DRAIN-ROUTING ─┐
                                                          (BILLING ─────▶ METER)          │
gateway.py chain:  CAPABILITY-ENGINE ······(gateway.py free until)······▶ DRAIN-ROUTING ──┤
                                                                                          │
                                          DRAIN-ROUTING ─▶ COST-RANK-AUTO ─▶ POOLS-SIMPLIFICATION
                                                        └▶ COST-RANK-AUTO ─▶ FREE-TIER-QUOTA-SPILL
                                          METER + DRAIN ─────────────────▶ DRAIN-THEN-PARK
proxy_server.py chain:  RFL-2 ─▶ RFL-4 ─▶ (DRAIN-ROUTING) ─▶ PFF-P2
balance.py chain:       METER ─▶ DRAIN-THEN-PARK
```

Legend: `─▶` = real build/correctness dep OR single-writer shared-file hand-off (both force order).

**Hub:** METER-MODEL-PROVIDER (sensor) feeds COST-RANK-AUTO, FREE-TIER-QUOTA-SPILL, DRAIN-THEN-PARK,
and the pools grades table. **True roots that need nothing new:** CAPABILITY-ENGINE, RFL-2 (after
Wave-0 pushes).

**Real vs assumed deps (audited):**
- DRAIN-ROUTING hard-deps only SR-5b (DONE). It is ordered after METER here for **METER-first
  reconciliation + shared proxy.py**, not a code dep — but METER-first is the deliberate choice.
- COST-RANK-AUTO real-deps DRAIN (cost_class enum) + METER (metered cost). FREE-TIER real-deps
  COST-RANK (cost_class). POOLS real-deps DRAIN + COST-RANK. DRAIN-THEN-PARK real-deps METER + DRAIN.
- PFF-P2: Phase-1 prereq already merged; only a proxy_server.py single-writer hand-off remains
  (owns trimmed to proxy_server.py so it does NOT block on the gateway.py chain).
- RFL-4 real-deps RFL-2 (proxy_server.py) + RFL-1 (DONE, quota tracker exists).

---

## 2. CRITICAL PATH (the wall-clock floor)

```
BILLING-EST-COST-FIX ─▶ METER ─▶ DRAIN-ROUTING ─▶ COST-RANK-AUTO ─▶ FREE-TIER-QUOTA-SPILL ─▶ DRAIN-THEN-PARK
   (Wave 0)             (W2)        (W3)              (W4)                (W6)                    (W7)
```
**7 sequential slots.** The floor is set by the **METER -> DRAIN -> COST-RANK real dependency chain**
(sense -> decide -> act), NOT by file contention. This is the key finding for the god-file decision (§3):
decomposing gateway.py cannot lower this floor because the steps depend on each other's *semantics*.

**Can start NOW, in parallel with in-flight Wave-1 / off the critical path:**
- **CAPABILITY-ENGINE** (providers/config/gateway.py) — needs nothing; land it while gateway.py is cold.
- **RFL-2 -> RFL-4** (proxy_server.py) — the console frontend chain is fully disjoint from the cost
  chain; it runs entirely in parallel and never touches the critical path.
- **OPENROUTER-FLAKINESS-FIX** (proxy.py) — bleed-stopper, right after NORMALIZE.

---

## 3. FILE-CONTENTION ANALYSIS & GOD-FILE DECISION

Live feature set ownership (post-dedup, DONE tickets removed):

| God-file | Live feature owners | Nature |
|---|---|---|
| **gateway.py** | CAPABILITY, DRAIN, COST-RANK, POOLS, FREE-TIER, DRAIN-THEN-PARK | mixed: serial chain + filters |
| **config.py** | CAPABILITY, DRAIN, COST-RANK, POOLS | mostly the serial chain |
| **proxy.py** | NORMALIZE(flight), OPENROUTER, METER, DRAIN | serial single-writer chain |
| **proxy_server.py** | RFL-2, RFL-4, DRAIN, PFF-P2 | serial single-writer chain |
| **balance.py** | METER, DRAIN-THEN-PARK | serial (METER then park) |

**DECISION: DO NOT decompose gateway.py now. Serialize single-writer-per-wave.** Rationale
(WCI-METHOD Step 3 "keep genuinely-coupled money-path serial; don't force-split to parallelize"):
1. The dominant gateway.py collisions (DRAIN -> COST-RANK -> POOLS) are a **genuine serial money-path
   dependency chain** — decomposition cannot parallelize them (semantic deps, not just file deps).
2. The remaining gateway.py writers (CAPABILITY, FREE-TIER, DRAIN-THEN-PARK) are only 3 lanes and are
   cheaply handled single-writer-per-wave (CAPABILITY lands EARLY while gateway.py is cold).
3. The critical-path floor (§2) is the METER->DRAIN->COST-RANK real chain, so a decompose would **not
   lower wall-clock** — while being a money-path-risky refactor.

Instead the collision metric is turned into a **tracked refactor trigger**: `GATEWAY-ROUTING-DECOMPOSE`
is filed PARKED as a documented future lever (extract an eligibility-filter registry + ordering call
into `routing_policy.py`), to build ONLY IF >= 2 more logically-independent gateway.py features arrive
after this batch. This mechanizes WCI Step 3 without a premature split.

**Concurrency is bought elsewhere, for free:** proxy.py, proxy_server.py, gateway.py/config.py, and
balance.py are FOUR disjoint axes. Early waves run 2-3 disjoint lanes across them (see §4). PFF-P2's
owns were **trimmed to proxy_server.py** (it only READS gateway._tier_pools/tiers.json) so it stays
off the gateway.py chain and can run concurrently with COST-RANK-AUTO.

**FOLD candidate (manager decision):** FREE-TIER-QUOTA-SPILL and DRAIN-THEN-PARK are two faces of ONE
resource-availability eligibility mechanism (mark-unavailable + skip/spill; class-1 quota vs class-3
balance-zero) sharing the same gateway.py skip surface + switch-at-boundary timing. Folding them into
one eligibility ticket removes a serial gateway.py wave and gives one reviewed money-path surface.
Flagged on the DRAIN-THEN-PARK ticket; kept separate here pending the manager's call.

---

## 4. COLLISION-FREE WAVES

Each lane = one droid. No two lanes in a wave write the same file. Recommended model per
`subsession-model-and-token-policy` (right-sized, not biggest).

### WAVE 0 — IN FLIGHT (manager review + push; not new)
`BILLING-EST-COST-FIX` · `NORMALIZE-CASE-QUANT-FIX` · `TEST-HARDEN-CONTRACT` (+claimed
`CI-WORKFLOW-POLICY-GATE`, `RFL-5`). Money-path (BILLING/NORMALIZE) = adversarial review before push.

### WAVE 1 — start after Wave-0 pushes (3 disjoint lanes)
| Lane | Ticket | Owns | Model | Accept (fail-on-revert) |
|---|---|---|---|---|
| A | **OPENROUTER-FLAKINESS-FIX** | proxy.py, tests/test_proxy_openrouter_wrap.py | strong | wrapped `error.metadata.raw` body -> DROP -> failover FIRES |
| B | **CAPABILITY-ENGINE** | providers.py, config.py, gateway.py, tests/test_capability_gating.py | strong | over-context / saturated leg SKIPPED (spill), not dispatched |
| C | **RFL-2** (console chat playground) | proxy_server.py, tests/test_chat_playground.py | strong | `/chat` served, shows which provider/model answered |
D&S: A after NORMALIZE (proxy.py); B independent (gateway.py cold); C after any pending
proxy_server.py (none). All owns-disjoint.

### WAVE 2 — (2 lanes)
| Lane | Ticket | Owns | Model | Accept |
|---|---|---|---|---|
| A | **METER-MODEL-PROVIDER** (hub) | proxy.py, balance.py, (new usage_meter.py), tests/test_meter_model_provider.py | strong | per-(model,provider) in/out tokens + cost recorded & readable |
| B | **RFL-4** (editable limits) | proxy_server.py, tests/test_limit_editor.py | strong | inline RPM/TPM/RPD edit applies without restart |
D&S: A after OPENROUTER (proxy.py) + BILLING (real cost); B after RFL-2 (proxy_server.py). Disjoint.

### WAVE 3 — DRAIN-ROUTING SOLO (monopolizes 4 files)
| Ticket | Owns | Model | Accept |
|---|---|---|---|
| **DRAIN-ROUTING** | proxy.py, proxy_server.py, gateway.py, config.py, tests/test_proxy.py, tests/test_gateway.py | frontier | free-first then drain-order; balance-poll + auto-decrement; NeuralWatt/OpenRouter fast-path |
Genuinely-coupled money-path unit (operator wants the priority chain designed as one). It collides
with every other axis, so it runs alone. ADVERSARIAL review.

### WAVE 4 — (2 lanes)
| Lane | Ticket | Owns | Model | Accept |
|---|---|---|---|---|
| A | **COST-RANK-AUTO** | config.py, gateway.py, tests/test_gateway.py | strong spec + frontier impl | cost_class enum + cost_rank=f(cost_in,cost_out); gpt-5.5 no longer tied at 1000 |
| B | **PFF-P2** (cross-model sub, default OFF) | proxy_server.py, tests/test_pff_p2_substitution.py | frontier | flag ON substitutes same-tier sibling + announces; OFF = 503 as today |
D&S: A after DRAIN (cost_class); B after DRAIN (proxy_server.py). Disjoint (PFF-P2 owns trimmed to
proxy_server.py). ADVERSARIAL review both.

### WAVE 5 — POOLS-SIMPLIFICATION (gateway.py single-writer)
| Ticket | Owns | Model | Accept |
|---|---|---|---|
| **POOLS-SIMPLIFICATION** | gateway.py, config.py, tests/test_gateway.py, /data/pools.json | economy build + manager migration | ~50 pools -> sparse overrides; route snapshots for auto/deepseek-v4-pro/gpt-5.5/*-free preserved |

### WAVE 6 — FREE-TIER-QUOTA-SPILL (gateway.py single-writer)
| Ticket | Owns | Model | Accept |
|---|---|---|---|
| **FREE-TIER-QUOTA-SPILL** | quota.py, gateway.py, tests/test_quota_spill.py | strong spec + frontier impl | exhausted free tier = unavailable (skip+spill at task boundary), not a hard error |

### WAVE 7 — DRAIN-THEN-PARK (gateway.py single-writer) — OR fold into Wave 6
| Ticket | Owns | Model | Accept |
|---|---|---|---|
| **DRAIN-THEN-PARK** | balance.py, gateway.py, tests/test_drain_then_park.py | frontier | class-3 auto-park at $0 + re-arm on top-up; SOLE-LEG GUARD never orphans a pool |
ADVERSARIAL review (safety guard). If folded with FREE-TIER (§3), this becomes part of Wave 6.

### GATED TRACK B — bench pivot (runs FULLY PARALLEL to all product waves; rig-only, disjoint owns)
Do NOT put in the product concurrency waves. Blocked on operator answers, not on product code.
- **BENCH-OOB-GRADING (#26)** — gated on operator **Q1** (grader substrate: separate unix user
  [recommended] / root+sudo / second host). P0 integrity. owns: benchmark/* + preflight.sh etc.
- **BENCH-REDS-REPLAY (#25)** — depends BENCH-OOB-GRADING (+ BENCH-PROVISIONAL-SCORING, DONE); gated
  on **Q2/Q3**. owns: reds.tsv, benchmark/reds-replay.tsv, benchmark/reds_replay.
Once Q1-Q3 are answered these run on their own track, concurrent with the product waves above.

---

## 5. TICKET SET — numbered <-> named mapping

**Created this session (5 new, staged as `.md.parked` — manager un-parks to activate; invisible to
`validate_board` collision checks by design, visible to `wci-contention`):**

| # | Ticket | Kind | Wave | Owns (product) |
|---|---|---|---|---|
| T1 | **OPENROUTER-FLAKINESS-FIX** | bugfix (drain-blocker) | 1 | proxy.py |
| T2 | **CAPABILITY-ENGINE** | routing (max_context/max_concurrency) | 1 | providers.py, config.py, gateway.py |
| T3 | **PFF-P2** | money-path (cross-model sub, default off) | 4 | proxy_server.py |
| T4 | **DRAIN-THEN-PARK** | money-path (funding-class lifecycle) | 7 | balance.py, gateway.py |
| T5 | **GATEWAY-ROUTING-DECOMPOSE** | refactor (future lever, non-scheduled) | — | gateway.py, routing_policy.py |

**Existing tickets scheduled (already staged `.md.parked` on the board — un-park per wave; NOT
re-created, NOT edited):** METER-MODEL-PROVIDER (W2), DRAIN-ROUTING (W3), COST-RANK-AUTO (W4),
POOLS-SIMPLIFICATION (W5), FREE-TIER-QUOTA-SPILL (W6), RFL-2 (W1), RFL-4 (W2), BENCH-OOB-GRADING &
BENCH-REDS-REPLAY (Gated Track B).

**Verification after creation:**
- `wci-contention.sh` — the 5 new tickets appear as owners on their god-files (confirmed).
- `validate_board.sh` — **no new RED introduced.** Pre-existing REDs (NOT caused by this session, flag
  to manager): 6 `orphan-marker` (done markers whose board files were parked/removed: SR-13,
  PROXY-SERVER-DECOMPOSE, BENCH-PROVISIONAL-SCORING, SR-6, BENCH-AGGREGATE-N, BENCH-REGROUND-LIVE) and
  1 `uncommitted-work: dirty tracked file src/charon/proxy.py` in the PRODUCT tree (a prior session
  exited without committing; this planning session never touched product source). Both should be
  cleaned before launching Wave 1.

---

## 6. WALL-CLOCK SUMMARY
- Critical path = 7 serial slots (BILLING->METER->DRAIN->COST-RANK->FREE-TIER->DRAIN-THEN-PARK).
- Waves 1-2 run 2-3 disjoint lanes each (proxy.py / gateway.py / proxy_server.py / balance.py axes).
- RFL-2->RFL-4 + Gated Track B run fully off the critical path.
- Biggest single-wave serializer = DRAIN-ROUTING (owns 4 files); keep it coupled (money-path design
  integrity), it is on the critical path regardless.
- Two manager levers to shorten further: (a) FOLD FREE-TIER-QUOTA-SPILL + DRAIN-THEN-PARK (removes a
  wave); (b) leave GATEWAY-ROUTING-DECOMPOSE parked unless the trigger fires.
