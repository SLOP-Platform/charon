# Gateway tier pools (DTC tier-abstraction, HARD REQ #2)

Compile `tiers.json.members` INTO the gateway's existing pool machinery so each tier is
published in `/v1/models` and fails over via the unchanged request loop. No new routing path.

## Design anchors (DTC §"Gateway alignment (HARD REQ #2)")

- **Tiers read from `tiers.json`, never `pools.json`.** Tier members are read via the tier config store's
  `config.load_tiers()` (separate store), so the strict `pools.load_pools` /
  `router.from_charon_dir` path never sees web-authored tier data (which has no `agent`
  field and would crash the ACP router, `pools.py:47-59`).
- **Reuse `_build_routes_and_pools` unchanged.** `load_config` feeds `tiers.members`
  (`{tier: [model_id,…]}`) through the SAME compiler used for `pools.json`. Within-tier order
  is therefore free-first→`cost_rank` stable sort — not reimplemented (mirrors `pools.py:91`).
- **pools.json WINS on name collision.** Tier vids are merged with `dict.setdefault`, so an
  explicit `pools.json` vid is never silently overridden (no surprise).
- **Absent file → behavior unchanged.** `config.load_tiers()` returns the legacy default
  (`high=[opus] med=[sonnet] low=[haiku]`) when `tiers.json` is absent; those bare Anthropic
  ids are not in a normal gateway registry, so they compile to zero tier pools → no tier vids.
  (If a registry literally contains a model named `opus`, the legacy `high` pool appears — the
  intended legacy mapping, not a regression.)

## Setup handler

A new `"tiers"` branch in `make_setup_handler` calls `config.set_tiers(order, members, aliases)`
then `_reload()`, which recompiles tier pools into the live server via `apply_routes` — same
hot-reload path as `pools`/`models`. The POST allowlist + web fieldset belong to the tiers web-UI work
(`proxy_server.py`), untouched here.

## Scope

Owned files only: `src/charon/gateway.py`, `tests/test_gateway_tiers.py`. `config.py` /
`proxy_server.py` unchanged.
