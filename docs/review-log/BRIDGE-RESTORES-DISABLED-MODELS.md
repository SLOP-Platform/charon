# BRIDGE-RESTORES-DISABLED-MODELS — fix review

## Bug
`bind()` snapshots static routes/pools into `self._base` at startup. On every `bridge()`
cycle, `bridge()` reads from `self._base` — a stale snapshot. When the operator uses
web-setup to disable a model, `gateway._reload()` calls `server.apply_routes()` with the
updated state, removing it from `server.routes`. The next bridge cycle reads from
`self._base` (which still contains the model) and restores it via `setdefault`, so the
operator's disable does not persist until a full restart.

## Fix
`bridge()` now reads live state from `self._server` (the live router) on every call, rather
than from `self._base`. Operator hot-reloads (`apply_routes`) are preserved across bridge
cycles. `self._base` from `bind()` is kept for reference doc but is not read in the
hot path.

## Why `catalog_refresh.py` and not `gateway.py`
`gateway._reload()` is correctly implemented — it calls `server.apply_routes()` with the
correct new state. The bug is that `bridge()` then overwrites that correct state with the
stale `_base` snapshot. The fix belongs at the bridge site.

## Static baseline preserved
`setdefault` still means hand-authored routes/pools always win over discovery. The
layering order is unchanged; only the source of the baseline changes (live state instead
of startup snapshot).

## PR #211 relationship
PR #211's "propagates to EVERY consumer" bar is only partial until this lands.
Once this fix is merged, the bridge respects operator disables, completing the contract.
