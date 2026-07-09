> ARCHIVED 2026-07-08 — superseded by POOLS-REDESIGN-ADR-v2.md (durable ideas — canonical low/med/high vocab + separate tiers.json — salvaged into its 'Salvaged design ideas' section; the tier mechanics shipped via TIER-1..7/TIER-SELECT)

# DTC — Charon model-tier abstraction (consensus design)
_2026-06-27 debate-to-consensus: 3 stances → adversarial critique → synthesis. Grounded in the real Charon source._

# (1) CONSENSUS DESIGN — "tier = a first-class, gateway-served pool in its own namespace"

The consensus takes **Stance A's** strongest move (a tier IS a cost-ranked gateway pool the gateway already fails over, wired on the existing setup page) but adopts **Stance B's** separate-file namespace to kill Stance A's fatal `pools.json` dual-consumer collision, and resolves every critique. Verified against the real code below.

## Decisions that resolve the critiques

- **One canonical vocabulary, committed: `low/med/high`** (the existing `types.Tier`, `types.py:12-17`). It is already what units carry, what `router._DEFAULT_POLICY` emits (`router.py:18-25`), and what `capacity.FixedCap` keys concurrency on (`capacity.py:76-78`). `opus/sonnet/haiku` and any `frontier/strong/economy` synonyms become **aliases only**. This ends the three-vocabulary sprawl and removes the cap-desync footgun: the web editor edits members/aliases, never the fixed canonical keys, so `FixedCap` caps never silently desync.
- **Tiers live in their own file `tiers.json`, NOT `pools.json`.** This is the central fix to Stance A's deepest correctness bug: `pools.load_pools` is *strict* — `_entry_from_registry` requires an `agent` field (`pools.py:47-59`, raises `PoolConfigError`), and `router.from_charon_dir(secrets.config_dir())` reads that same `pools.json` (`router.py:52-58`). Web-authored models from `config.add_model` never write `agent` (`config.py:215-230`), so overloading `pools.json` would crash the ACP router. Keeping tiers in `tiers.json` leaves the strict loader untouched → backward compatible by construction.
- **Within-tier = cheapest-first is CORRECT, made explicit.** The "semantic inversion" critique is resolved by stating the invariant: *a tier's members are asserted capability-equivalent (all clear the band's bar)*; the gateway's free-first→`cost_rank` stable sort (`gateway.py:92-104`, mirroring `pools.py:91`) then means "the **cheapest live model that meets this capability floor**" — which is the intended product behavior, not an inversion.
- **No silent cross-tier downgrade.** A dry tier returns the upstream's terminal status (clean exhaustion, matching `pools.choose_from_pool`'s "raise rather than degrade", `pools.py:96-113`). Cross-tier *spill* is opt-in **as data** (operator appends a neighbor model to a tier's member list). `order` drives the fleet's ticket-draining `rank()` and optional spill — never an automatic quality drop.
- **The fleet keeps its Anthropic executor; only the engine consumes multi-provider pools.** Critique A is right that `claude -p` speaks the Anthropic Messages API while the gateway is OpenAI-only (`proxy_server.py` forwards `chat/completions`, no `/v1/messages`). So we do **not** route `claude -p` through the gateway. The fleet de-hardwires by resolving tier→*concrete Anthropic model name* from `tiers.json` (a name lookup), while Charon's own ACP/OpenAI engine workers request the **tier vid** from the gateway and get full multi-provider failover. One `tiers.json` feeds both; no undesigned translation shim.

## Data model — `tiers.json` in `secrets.config_dir()` (new, tiny, optional)

```json
{
  "order": ["low", "med", "high"],
  "members": {
    "low":  ["gemini-flash", "haiku"],
    "med":  ["sonnet", "qwen3-coder"],
    "high": ["opus", "deepseek-r1"]
  },
  "aliases": { "opus": "high", "sonnet": "med", "haiku": "low",
               "frontier": "high", "strong": "med", "economy": "low" }
}
```

- `members[tier]` are **model ids already in `models.json`** (reuse the registry: provider, `free`, `cost_rank` — `config.py:215-230`). No new model schema, no DB, no migration runner (HARD REQ #4).
- `order` = capability bands ascending; index = rank (replaces the hardwired `rank()`).
- `aliases` = legacy/synonym → canonical tier (the backward-compat seam).
- **Absent file → legacy behavior** (everything falls back to `opus/sonnet/haiku`). Canonical tier keys are fixed (`low/med/high`); only `members`/`aliases` are operator-editable.

## Where the mapping lives + the resolution contract

| Concern | Lives in | Surface |
|---|---|---|
| Concrete models in a tier, ordered | `tiers.json.members` | web `/charon/tiers`, `charon tier set`, CLI |
| Model defs (provider, `free`, `cost_rank`) | `models.json` (existing) | web `/charon/models`, `charon models` |
| Tier order + legacy aliases | `tiers.json` (`order`,`aliases`) | web `/charon/tiers`, `charon tier init` |

`config.resolve_tier(name) -> canonical` (alias-folded), `config.tier_members(tier) -> [model_id]`, `config.tier_rank(name) -> int`. **Deterministic:** within-tier order = free-first→`cost_rank` stable sort; first non-cooled member wins (`order_by_cooldown` only defers cooled routes, `proxy_server.py:688-695`); `order` is an explicit list (HARD REQ #5).

## Gateway alignment (HARD REQ #2) — tiers compile INTO the existing pool machinery

In `gateway.load_config`, after reading `models.json`/`pools.json`, also read `tiers.json` and feed `members` through the **existing** `_build_routes_and_pools(registry, members, providers_cfg)` (`gateway.py:77-104`), merging the resulting tier vids into `GatewayConfig.pools` and `model_ids`. **Precedence:** an explicit `pools.json` vid wins on name collision (no surprise). Result: each tier is published in `/v1/models` and fails over transparently via the unchanged request loop (`proxy_server.py:470-588`, cools 429/402/503, advances on downgrade). The strict `pools.load_pools`/`router.from_charon_dir` path never sees `tiers.json` → no crash.

## Web-UI surface (HARD REQ #3) + backend API

- **New "Tiers" fieldset** in `_SETUP_HTML` (`proxy_server.py:147` region): rows = canonical tiers from `order`, each with a comma-separated member-id input (reusing the `addPool` pattern, `proxy_server.py:182-185`) and alias chips. Operator types model ids straight from the registry list already rendered on the page. POSTs `{order, members, aliases}` to `/charon/tiers`.
- **Backend:** `config.set_tiers(order, members, aliases)` (atomic `_save`, reuses `config.py:168-175`); a new `"tiers"` branch in `gateway.make_setup_handler` (`gateway.py:190-248`) calling `_reload()` (which recompiles tier pools into the live server via `apply_routes`, `gateway.py:185-188`).
- **Critical omission Stance A missed, fixed here:** add `"/charon/tiers"` to the hardcoded POST allowlist in `proxy_server.py:409-411`, else the POST falls through to chat-completions and 502s. CSRF/Origin guard (`proxy_server.py:414-420`) then covers it for free.
- **Console** (read-only, `proxy_server.py:80-103,738-763`) already renders pools + recent failovers; add a `tier` tag column so tier vids are visually distinct.

## Fleet consumption (preserve `flock` atomicity — HARD REQ #5)

**`claim.sh`** — parse `tiers.json` **ONCE, before `flock 9`** into a bash assoc array; `rank()` becomes a pure-bash array lookup (microseconds) inside the locked loop, never spawning Python under the lock (fixes Stance A's contention regression). Legacy fallback when `tiers.json` is absent:

```bash
declare -A RANK
if out="$(charon tier ranks 2>/dev/null)"; then        # "low 1\nmed 2\nhigh 3\nopus 3 ..." (canonical+aliases)
  while read -r n r; do RANK["$n"]=$r; done <<<"$out"
else RANK=([opus]=3 [sonnet]=2 [haiku]=1); fi           # legacy, unchanged
rank(){ echo "${RANK[$1]:-0}"; }
exec 9>"$LOCK"; flock 9                                  # atomic claim path UNTOUCHED
```

The `flock 9` test-and-set and per-ticket `claims/$id` create (`claim.sh:17,32`) are byte-for-byte unchanged; `tiers.json` is read-only/idempotent → no new lock, no race. `meta tier` still reads the ticket's label; tickets may say `high` or still `opus` (alias-folded).

**`fleet-droid.sh`** — accept canonical **and** legacy tier args, and resolve the concrete launch model from config instead of `MODEL="$TIER"`:

```bash
opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;       # arg allowlist widened
MODEL="$(charon tier resolve "$TIER" --executor anthropic)" || MODEL="$TIER"  # name lookup; legacy fallback
...
claude -p --model "$MODEL" --dangerously-skip-permissions "$prompt"
```

`charon tier resolve <tier> --executor anthropic` returns the cheapest live tier member whose provider is Anthropic-API-runnable (so `claude -p` can execute it); `|| MODEL="$TIER"` keeps half-migrated setups working. No gateway dependency on the fleet path → no Anthropic↔OpenAI shim.

## Engine consumption

`AcpBackend.dispatch(unit, tier, …)` already receives the `Tier` but doesn't use it for model selection (`acp.py:138-160`); the agent routes through the observing `GatewayProxy`. Wire the **tier vid as the requested model id** into the agent env / observer base-URL so the gateway resolves the tier pool and fails over. `capacity.FixedCap` caps stay keyed on the same canonical `low/med/high` string — one tier vocabulary across engine caps, gateway pools, and fleet ranking.

## Failover behavior (summary)

- **A model in a tier is down** → invisible: gateway cools it (429/402/503) and serves the next cheapest *same-tier* member; `X-Charon-Failovers` + console record it.
- **Whole tier dry** → chain exhausted → real terminal upstream status (`proxy_server.py:510-515`) or 502 if empty (`proxy_server.py:461`); the engine reports `EXHAUSTED`, the fleet droid exits non-zero → `release.sh` frees the claim (`fleet-droid.sh:78-80`). No stuck tickets, no silent downgrade.
- **Cross-tier** is the fleet's ticket-draining job (`own → lower` passes, data-backed `rank()`) and/or operator opt-in spill — never automatic.

## Migration path (no flag-day)

1. **Absent `tiers.json`** → `claim.sh` legacy `rank()`, `fleet-droid.sh` legacy `opus/sonnet/haiku`, gateway has no tier vids. Nothing breaks.
2. **`charon tier init`** (CLI + a setup-page button) writes `tiers.json` with `order=[low,med,high]`, the legacy `aliases`, and seeds each tier's `members` with the single matching Anthropic model so **day-one == today**; operator later adds cheaper non-Anthropic members per tier in the web Tiers editor.
3. **Tickets unchanged** — `tier: opus` resolves via `aliases` → `high`. Optional later mechanical rename, never required.

---

# (2) OPTIMIZED CHARON TICKET BREAKDOWN

File-disjoint, ordered; same-wave tickets own disjoint files. Charon paths are absolute under `/home/stack/code/charon/`; fleet paths under `/home/stack/charon-private/fleet/`.

| id | tier | branch | owns (paths) | depends_on | goal |
|---|---|---|---|---|---|
| **TIER-1** | high | `feat/tier-config-store` | `src/charon/config.py`; `tests/test_tier_config.py` | — | Add `load_tiers`/`set_tiers` (atomic `tiers.json` in `config_dir`) + canonical `low/med/high`, `resolve_tier`, `tier_members`, `tier_rank` (alias-folded, legacy fallback). |
| **TIER-2** | high | `feat/gateway-tier-pools` | `src/charon/gateway.py`; `tests/test_gateway_tiers.py` | TIER-1 | In `load_config` compile `tiers.json.members` via existing `_build_routes_and_pools` into `GatewayConfig.pools`/`model_ids` (pools.json wins on collision); add `make_setup_handler` `"tiers"` branch + `_reload`. |
| **TIER-3** | med | `feat/cli-tier` | `src/charon/cli.py` (new `tier` subcommand block); `tests/test_cli_tier.py` | TIER-1 | `charon tier init|set|list|ranks|resolve` — init seeds backward-compat tiers; `resolve --executor anthropic`/`ranks` are the fleet entrypoints. *(Same wave as TIER-2; disjoint files.)* |
| **TIER-4** | high | `feat/tier-web-ui` | `src/charon/proxy_server.py`; `tests/test_setup_tiers.py` | TIER-2 | Add "Tiers" fieldset to `_SETUP_HTML`, add `"/charon/tiers"` to the POST allowlist (`proxy_server.py:409-411`), add `tier` tag column to the console. |
| **TIER-5** | high | `feat/fleet-tier-claim` | `/home/stack/charon-private/fleet/claim.sh` | TIER-3 | Parse tier ranks ONCE before `flock` into a bash assoc array (`charon tier ranks`, legacy fallback); data-backed `rank()`. `flock`/claim path untouched. |
| **TIER-6** | high | `feat/fleet-tier-launch` | `/home/stack/charon-private/fleet/fleet-droid.sh` | TIER-3 | Widen arg allowlist to canonical+legacy tiers; `MODEL=$(charon tier resolve … --executor anthropic)` with `||$TIER` fallback. *(Same wave as TIER-4/5/7; disjoint files.)* |
| **TIER-7** | med | `feat/engine-tier-route` | `src/charon/adapters/acp.py`; `tests/test_acp_tier_route.py` | TIER-2 | Wire `dispatch`'s `tier` as the requested model id (tier vid) into the agent env/observer so the gateway resolves the tier pool; caps stay keyed on canonical tier. *(Same wave as TIER-4/5/6.)* |

**Waves:** A = {TIER-1} · B = {TIER-2, TIER-3} · C = {TIER-4, TIER-5, TIER-6, TIER-7}. Every wave-mate owns disjoint files; the only intra-`gateway.py` work (pool compile + setup handler) is consolidated in TIER-2 so TIER-4 can own `proxy_server.py` alone.