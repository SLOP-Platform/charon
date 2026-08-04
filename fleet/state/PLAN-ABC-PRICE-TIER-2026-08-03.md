# PLAN A→B→C — price feed → provider caps → tier-candidate routing

**Status: DOCUMENTED, ON HOLD** (operator, 2026-08-03: "document your ABC plan and hold for
now — I want you to consider an alternative"). A was launched in tab `PRICEFEED` :4150 and
INTERRUPTED at operator request. Worktree + branch preserved, nothing committed.

---

## 0 — The measured facts this plan rests on (do not re-derive)

All measured 2026-08-03 against the live gateway (`build_sha=9659998d`) and shipped source.

| # | fact | evidence |
|---|---|---|
| F1 | **10 of 861** registry entries have `cost_input`. The other 851 get `derived_cost_rank`'s neutral `1000` fallback → **cost-first ordering is inoperative for ~99% of the catalog**. | `cost_rank.py:88-90`; `/data/models.json` on the gateway |
| F2 | **Zero of 90** `opencode-*` registry entries are priced. | same |
| F3 | `catalog_refresh.py` is WIRED and enabled (`{"enabled":true,"ttl_s":21600}`) and its docstring promises per-(provider,model) price from `/models` polls — but yields none, because most providers' `/models` carry no pricing. | `gateway.py:86-89`, `catalog_refresh.py:1-30`, `/data/catalog_refresh.json` |
| F4 | **OpenRouter** `/api/v1/models` returns pricing for **338/338**. **models.dev/api.json** (public, no key) covers **178 providers / 6020 models / 5613 priced**, including `opencode-go` and `opencode` (zen). | live fetch |
| F5 | **17 of 17** of our providers are covered by models.dev. Alias map is 4 entries: `opencode-zen→opencode`, `google-aistudio→google`, `nanogpt→nano-gpt`, `together→togetherai`. `togetherai` = 34/34 priced. | live fetch (operator corrected the `together` miss) |
| F6 | models.dev reproduces the operator's own price list exactly: `deepseek-v4-flash`/`mimo-v2.5` $0.14, `hy3` $0.14, `minimax-m3`/`m2.7`/`m2.5` $0.30, `deepseek-v4-pro` $0.435, `kimi-k2.5`+ $0.50-$3. | live fetch |
| F7 | **4380 pools; 3846 (87.8%) are single-member** — no failover possible at all. 534 (12.2%) have ≥2 legs. 29 list the same provider twice (fake redundancy). | `/charon/status` |
| F8 | There is **no per-provider model allowlist mechanism**, by explicit design: *"discovery is the sole source of membership"* — so `opencode-go` carries 42 models (10 Anthropic, incl. `gpt-5.5-pro-go`) and `opencode-zen` 48 (10 Anthropic). | `routing_policy/__init__.py:165-167` |
| F9 | **Tier routing is built but starved**: `tier_pools()` compiles `tiers.json`, and **`/data/tiers.json` does not exist** on the gateway → no tier ids → inert. The fleet instead hand-maintains tier chains in the rig's `tier-models.tsv` using **provider-pinned** ids (`deepseek-v4-pro-ds`, `minimax-m2.5-go`, `gpt-oss-120b-groq`), violating the standing NEVER-PIN-A-PROVIDER rule in the rig's own config. | `routing_policy/__init__.py:211-225`; `fleet/env-registry.sh:118-133` |
| F10 | **7 providers are parked** and persisted (`/data/balance_park.json`): `cline-pass huggingface nanogpt neuralwatt opencode-go opencode-zen openrouter`. Park **works**; the never-strand fallback (`forwarder.py:481-487`) restores the FULL chain incl. parked legs when every leg of a pool is parked, which is why parked providers still serve. **Corrects the sifo-dyas handoff §4.1/§7b**, which recorded park as a no-op and `/charon/status` as having no `parked` field — both false. | `forwarder.py:443-487`, `/data/balance_park.json`, live probes |
| F11 | Park is a **one-way door** for 5 of the 7: auto-unpark only fires when a balance poll returns >0, and only `deepseek`/`openrouter`/`nanogpt` have poll adapters. `huggingface neuralwatt cline-pass opencode-go opencode-zen` can **never** re-arm. | `balance.py:134-137`, `:322-327` |

**Why this recurs every session:** no mechanism can encode "this provider may only serve these
models" (F8) and there is no price to rank by (F1) → opencode drains → a session hand-parks it →
the park persists with no re-arm path (F11) → pools lose live legs → the never-strand fallback
routes to whatever answers (F10) → the next session sees openrouter serving everything and
concludes the broker is broken. Self-reinforcing, once per session.

---

## 1 — The plan

### A — models.dev as a price source behind the existing seam
Add a price source to `catalog_refresh.py` through its **already-injectable** `ListModelsFn`
seam (`:51`, injected `:145-151`); `_PRICE_KEYS` (`:54`) already carries price into
`model_pricing` (`:187`, `:236`). Convert models.dev's USD-per-1M to per-token and prove the
conversion in a test. 4-entry alias map (F5). Honor the module's existing STALE-BUT-USABLE
contract; never touch the hot path.

- **Hard requirements:** no hand-typed prices (a price table is an automatic reject — the point is
  that a tool supplies them); **fail loud on missing price** (a counter + log, never a silent
  neutral rank — missing-price-is-invisible is the defect that hid F1 for weeks).
- **Acceptance = dogfood, not a green unit test:** assert the priced-entry count goes from ~10 to
  >1000 against a fixture of the live `models.json`, printing before/after.
- **Effort: one tab, a few hours. ~150 LOC + ~100 test.** Confidence HIGH — seam is injectable,
  coverage verified 17/17, `tests/test_catalog_refresh.py` is the pattern.
- **Delivers on its own:** cost-first ordering starts working for ~5,600 model-provider pairs.
  Does **not** require B or C.

### B — provider caps as predicates over A's data
The operator's rule is derivable from F6, not a list to maintain:
- `opencode-go`: admit where `cost.input ≤ 0.30`
- `opencode-zen`: admit where `cost.input == 0` (free only)

Implement as a predicate at the existing admission filter (`routing_policy/__init__.py:199`) plus
per-provider policy. **Must fail loud when a price is missing** — otherwise an unpriced model is
silently admitted, which is the same class of bug as A's.
- **Effort: one tab, a few hours. ~100 LOC + tests.** Confidence HIGH. Gated on A being trusted.

### C — tier-candidate routing (ADR FIRST)
**One concept: a candidate = (model, provider, price, grade, funding state).** A tier is a
predicate over candidates; a request names a tier; the broker sorts by real price and walks
candidates. Provider caps are predicates on the same data. Model-by-name survives as an explicit
escape hatch for evals/reproducibility.

Deletes: the 4380-entry pool map, the bare-vs-`-go` id fragmentation (PR #442 exists only to
collapse spellings — unnecessary once identity isn't the routing key), `_is_sole_leg` /
`_has_live_sibling`, and the never-strand-into-parked fallback (F10). All are artifacts of
model-identity-as-pool-key.

- **Blast radius (measured):** 62 call sites across 18 modules read `.pools`/`chain_for`;
  **43 of 151 test files (28%)** encode pool semantics; `forwarder.py` is 934 LOC on the money path.
- **Safe shape:** parallel candidate path behind a flag → dogfood against the live gateway →
  cut over → delete the pool map.
- **Effort: ADR one tab / half a session. Build 3-5 waves / several sessions — this is the SOFT
  number**, dominated by migrating 43 test files, not by the selection logic (which is small).
  The ADR is what turns 3-5 into a real number.
- **Honest costs:** (1) a tier predicate must include capability — context/output limits,
  tool-calling, vision — or cheap-first routes work to a model that cannot do it (models.dev
  carries limits; grades come from the scorecard); (2) an OpenAI-compatible caller asking for
  `minimax-m2.5` and getting something else is a real semantic change — tier aliases
  (`charon/strong`) keep it explicit; (3) routing-core rewrite ⇒ dogfood gate, not a quick land.

### Sequencing / holds
- Order **A → B → C**, ADR for C before building it (operator-approved 2026-08-03).
- **Do NOT re-arm the 7 parked providers (F10) until B exists** — re-arming restores cheap legs
  but re-opens the opencode drain.
- Adjacent and urgent, not part of A/B/C: `claude-opus-5`/`claude-sonnet-5` pools already list
  `opencode-zen`, and both opencode providers carry 10 Claude models each (F8). The HARD
  never-Anthropic rule is currently held by nothing but the absence of a tier chain naming them.
  `NEVER-ANTHROPIC-ASSERTION` is ticketed and UNBUILT. **C makes this worse before better** —
  a price-ranked candidate pool over all providers can surface an Anthropic-served model that no
  hand-written chain would have named. The assertion must land before C cuts over.

---

## 2 — State of the hold

- Tab `PRICEFEED` :4150, model `deepseek-v4-pro`, session `ses_034d4957fffekDZbEPewOVc29H` —
  launched with the full A brief, then **INTERRUPTED** on operator instruction. Nothing committed.
- Worktree `/home/stack/charon-wt/PRICE-FEED-MODELSDEV`, branch `feat/price-feed-modelsdev`
  (at `54e0dc8`, clean) — **preserved so A can resume without re-setup.**
- No ticket minted yet for A/B/C; if the alternative supersedes this plan, none is needed.
