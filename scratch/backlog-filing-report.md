# Backlog Filing Report — HANDOFF-2026-07-08 §3 → durable fleet board tickets

Filed 2026-07-08 by the ticket-filing sub-session. All new tickets staged as `.parked`
(invisible to `validate_board.sh`'s `*.md` glob) so no droid claims them before the manager
gates activation. NOT committed/pushed/activated. Prompt files are path-only (authored at activation).

Authoritative D&S source used: **`scratch/pivot-implementation-plan.md` EXISTS** — its dependency
graph (§1) is used verbatim for the #26/#25/#20/#16/#17/#27 cluster (no PROVISIONAL derivation needed).

## Mapping: backlog # → disposition

| # | Intent | Disposition | Ticket file |
|---|--------|-------------|-------------|
| A2 | Re-ground grades brain on live actuals (pivot day-one enabler; not a numbered backlog item) | **NEW** (flagged) | `BENCH-REGROUND-LIVE.md.parked` |
| #26 | Out-of-band grading (P0 integrity) | **NEW** | `BENCH-OOB-GRADING.md.parked` |
| #20 | Provisional-vs-active scoring (P0 enabler) | **NEW** | `BENCH-PROVISIONAL-SCORING.md.parked` |
| #16 | Aggregate N runs per (model, section) | **NEW** | `BENCH-AGGREGATE-N.md.parked` |
| #17 | Difficulty calibration | **NEW** | `BENCH-DIFFICULTY-CAL.md.parked` |
| #25 | Test-freshness / reds-replay (primary ranking signal) | **NEW** | `BENCH-REDS-REPLAY.md.parked` |
| #27 | Gate #14 assignment on discrimination | **NEW** | `ASSIGN-DISCRIM-GATE.md.parked` |
| #33 | Secret hot-rotation force-refresh | **NEW** (product-touch flagged) | `SECRET-HOTROTATE.md.parked` |
| Pools Phase 1 | tier-collapse + cost/health routing | **COVERED** — see below | (none new) |
| #12 | Cooldown fix-3 | **NEW** (product-touch flagged) | `COOLDOWN-FIX3.md.parked` |
| #30 | Catalog + pricing sync + drift detector | **NEW** (product-touch + dedup flag) | `CATALOG-SYNC-DRIFT.md.parked` |
| #31 | Full-catalog search + curate (blocked on #30) | **NEW** | `CATALOG-SEARCH-CURATE.md.parked` |
| #29 | `-free-zen-model` drift cleanup | **NEW** (live-config/manager task) | `ZEN-DRIFT-CLEANUP.md.parked` |
| #18 | Review 4 low-conf work_class backfills | **NEW** | `WORKCLASS-BACKFILL-REVIEW.md.parked` |
| #19 | Triage 5 pre-existing board reds | **NEW** | `BOARD-REDS-TRIAGE.md.parked` |
| #21/#22/#23 | Provisional capability probes (blocked by #20) | **NEW** (consolidated + needs-input) | `CAP-PROBE-BACKLOG.md.parked` |
| #32 | Add LongCat-2.0 (blocked on signup) | **NEW** (product-touch flagged) | `LONGCAT-PROVIDER.md.parked` |

**16 new ticket files created; 1 backlog item (pools Phase 1) covered by existing tickets.**

## Already-covered (NO duplicate created)

- **Pools-redesign Phase 1 (tier-collapse + cost/health routing)** → covered by the existing live
  cluster: `POOLS-SIMPLIFICATION.md` (replace ~50 per-model pools with sparse overrides + tiers =
  tier-collapse), `COST-RANK-AUTO.md` (auto-derive cost_rank from real pricing + cost_class), and
  `DRAIN-ROUTING.md` (balance/health-aware routing). These already carry the full dep chain
  (SR-5 → SR-5b → COST-RANK-AUTO / DRAIN-ROUTING → POOLS-SIMPLIFICATION). No new ticket filed.
  - **FLAG for manager:** the handoff's "pricing injection point now known" note (models.json lacks
    cost_input/cost_output; populate via an OpenRouter alias-fix or a models.dev import) may or may
    not be fully inside the SR-5/SR-5b capture scope. `CATALOG-SYNC-DRIFT` (#30) also names this
    pricing import. Reconcile ownership of the pricing-source build across SR-5b / COST-RANK-AUTO /
    #30 at activation so it is built once, not thrice.
- **#30 vs MODEL-DISCOVERY.md:** NOT a duplicate. MODEL-DISCOVERY = OUTBOUND `/v1/models` enrichment
  endpoint; #30 = INBOUND catalog sync + drift detector. Adjacent (shared catalog schema), filed
  separately with a cross-ref note in the #30 ticket. No edit made to MODEL-DISCOVERY.

## D&S spine used (from pivot-implementation-plan.md §1, authoritative)

```
BENCH-REGROUND-LIVE (A2, depends_on: none)              ← grades.py/tier_chart.py chain root
   ├─► BENCH-PROVISIONAL-SCORING (#20, enabler)         ← +stage col; chain: grades.py/tier_chart.py
   │       ├─► BENCH-OOB-GRADING (#26, integrity)       ← file-seq after #20 (shares bench.sh/
   │       │        └─► BENCH-REDS-REPLAY (#25)            grade_state.py/model-scorecard.sh); needs Q1
   │       ├─► BENCH-AGGREGATE-N (#16)                  ← chain: grades.py/tier_chart.py
   │       │        └─► BENCH-DIFFICULTY-CAL (#17)        ← +promote.py v2 gate
   │       └─► CAP-PROBE-BACKLOG (#21/22/23)
   └─► ASSIGN-DISCRIM-GATE (#27, depends_on A2 + #16)   ← owns assign.py/selftest.py (disjoint, justified)
```
- **Refinement of the plan's logical parallelism:** pivot §1 runs #20 ∥ #26 in parallel, but they
  share `bench.sh` / `grade_state.py` / `model-scorecard.sh`, so #26 is **file-sequenced after #20**
  (depends_on set; noted in both tickets' scope). Honest D&S over nominal parallelism.
- Independent tickets (no bench-cluster dep): SECRET-HOTROTATE (#33), COOLDOWN-FIX3 (#12),
  CATALOG-SYNC-DRIFT (#30) → CATALOG-SEARCH-CURATE (#31), ZEN-DRIFT-CLEANUP (#29),
  WORKCLASS-BACKFILL-REVIEW (#18), BOARD-REDS-TRIAGE (#19), LONGCAT-PROVIDER (#32).

## Product-boundary flags (build touches src/charon — ticket is rig planning artifact only)

- **SECRET-HOTROTATE (#33)** → `src/charon/secrets.py`
- **COOLDOWN-FIX3 (#12)** → `src/charon/proxy.py`
- **CATALOG-SYNC-DRIFT (#30)** → reads/writes product catalog (`src/charon/config.py` / models.json)
- **LONGCAT-PROVIDER (#32)** → `src/charon/providers.py`
- Pools Phase 1 (covered tickets) already carry product owns.
- Each flagged ticket's scope says: keep the product STANDALONE, no rig/fleet/SLOP import may leak in.
- The **entire bench pivot cluster is RIG-ONLY** (fleet repo) per pivot §9; the single product-boundary
  contact is Phase-2 pools grades-table source (pivot §7), which is downstream and not filed here.

## validate_board.sh result

**RED — but PRE-EXISTING and UNCHANGED by this filing.** Exactly 5 issues, all GUI-SVELTE-BUILD-centered:
1 `missing-prompt: GUI-SVELTE-BUILD`, 4 `owns-collision LIVE` (GUI-SVELTE-BUILD vs COST-RANK-AUTO /
DRAIN-ROUTING / POOLS-SIMPLIFICATION / INC-401-FAILOVER / RFL-2/3/4 / SR-13 / SR-6 on Dockerfile +
config.py + gateway.py + proxy_server.py). Identical before and after filing — the 16 new `.parked`
tickets are invisible to the validator's `*.md` glob, so they added **zero** new reds. These 5 reds are
handed to **BOARD-REDS-TRIAGE (#19)** (they are plausibly the exact "5 pre-existing board reds" that
ticket refers to). Not fixed here (fixing GUI-SVELTE-BUILD sequencing is out of scope + a manager call).

## Items needing manager / operator input

1. **A2 (BENCH-REGROUND-LIVE):** confirm it should be filed/activated as its own ticket (recommended by
   pivot §1; it is the dep-root for the cluster + #27). Filed provisionally.
2. **#21/#22/#23 (CAP-PROBE-BACKLOG):** individual intents were NOT in the handoff (ephemeral board ids)
   — filed as ONE consolidated ticket; recover distinct specs from operator/prior board before build.
   Also carries the **PENDING operator call**: retire generic synthetic sections wholesale vs keep
   purpose-built probes provisionally.
3. **Pricing-source build de-dup:** reconcile the "pricing injection point" across SR-5b /
   COST-RANK-AUTO / #30 (build once).
4. **Operator decisions gating builds** (from pivot §8): Q1 (#26 substrate — top blocker), Q2/Q3 (#25
   corpus + admissibility), Q6 (#27 fall-back-vs-refuse — recommend fall back).
5. **External blockers:** #32 LongCat needs a Meituan signup+key; #31 blocked on #30.
6. **Pre-existing board RED (5 issues, GUI-SVELTE-BUILD):** dispose via #19 / sequence GUI-SVELTE-BUILD.
