# TIER-4 — Tiers web-UI surface (DTC HARD REQ #3)

Canonical tier for this ticket: **high** (fleet `opus`). Depends on TIER-2 (merged):
the `"tiers"` branch in `gateway.make_setup_handler` + `config.set_tiers` already exist;
this ticket only adds the operator-facing surface that POSTs to that backend.

## Changes (proxy_server.py — owned; EDIT in place)

- **Tiers fieldset** in `_SETUP_HTML` (after the Failover-pool fieldset). Rows are the
  canonical tiers `low/med/high` (= `config.CANONICAL_TIERS`, the `order`), each a
  comma-separated member-id input reusing the `addPool` parse pattern, plus an aliases
  input (`name=tier, …`). `setTiers()` POSTs `{order, members, aliases}` to `/charon/tiers`.
  `order` is the fixed canonical permutation `['low','med','high']` because `set_tiers`
  requires exactly the canonical set; the operator types member ids straight from the
  registry list already rendered on the page.
- **POST allowlist** (`proxy_server.py` ~409–411): added `"/charon/tiers"`. **Critical —
  Stance A missed this:** without it the POST falls through to the chat-completions forward
  path and 502s. The existing CSRF/Origin + Host-rebinding guard (414–420) then covers the
  new endpoint for free (verified by `test_tiers_post_keeps_csrf_origin_guard`).
- **Console tier tag column** (read-only, `_CONSOLE_HTML`): the Pools table gains a `tier`
  column. Detection is client-side against the canonical set `['low','med','high']` — tier
  pool vids are *always* a subset of those names (`set_tiers` enforces canonical `order`;
  `_tier_pools` keys pools by the canonical tier name). This keeps the change **display-only**
  and avoids touching `status_snapshot`/failover logic or the gateway. Added a `.tier` badge
  style.

## Scope / boundary

- Owned files only: `src/charon/proxy_server.py`, `tests/test_setup_tiers.py`. No edit to
  `gateway.py` (TIER-2 handler) or `config.py` (TIER-1 `set_tiers`) — the surface only POSTs.
- No backend persist/reload added here (that is TIER-2's `"tiers"` handler + `_reload`).
- Privileged core stays stdlib-only; no new imports in `proxy_server.py`. Client-side
  canonical-name detection avoided a `config.load_tiers()` read on the 2s status hot path.

## Tests (tests/test_setup_tiers.py)

- `…renders_tiers_fieldset_with_member_inputs` — fieldset + a member input per canonical tier.
- `…console_renders_tier_tag_column` — `<th>tier` header + `class=tier` badge present.
- `…tiers_in_post_allowlist_does_not_fall_through` — POST `/charon/tiers` returns 200 (handled
  by TIER-2), not a 502 fall-through; persists `aliases` via the backend. Proven-red: without
  the allowlist entry this POST falls through and does not 200.
- `…tiers_post_keeps_csrf_origin_guard` — cross-origin POST refused (403).

Full gate green: 517 pytest, ruff, mypy, check_boundary, check_version.
