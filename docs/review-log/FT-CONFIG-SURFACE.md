# FT-CONFIG-SURFACE — review-log fragment

## Summary
Extended `charon.config.providers.add_provider` with an optional `free_tier`
block so QuotaTracker can be fed from user config. Added two submodule-local
accessors (`_load_free_tier_limits`, `_free_tier_to_quota_limits`) that
project the persisted block to the exact `QuotaTracker(limits={...})` shape.

## Schema (persisted under `providers.json[name].free_tier`)

```jsonc
{
  "rpm": 60,            // optional int >= 0
  "rpd": 200,           // optional int >= 0
  "tpm": 100000,        // optional int >= 0
  "tpd": 5000000,       // optional int >= 0
  "weekly_tokens": 1e6, // optional int >= 0 (future-facing budget; not consumed by QuotaTracker)
  "monthly_tokens": 4e6,// optional int >= 0 (future-facing budget; not consumed by QuotaTracker)
  "reset": "rolling" | "calendar",  // optional; absence == rolling-default
  "reset_anchor": {                  // optional; depends on `reset`
    "time": "HH:MM",                 // UTC time of day
    "weekday": 0..6,                 // weekly reset
    "day_of_month": 1..31            // monthly reset
  }
}
```

Absent `free_tier` block == unlimited == back-compat (existing configs load
unchanged, no field written, no entry in `_load_free_tier_limits`).

## Validation
* Negative or non-int limits (including `bool`) → `ValueError`.
* Unknown keys → `ValueError`.
* `reset` must be `"rolling"` or `"calendar"`.
* `reset_anchor` requires `reset` to be set.
* `reset_anchor` accepts `"HH:MM"`, weekday name (`mon`..`sun`, also
  `Monday`/etc, case-insensitive), or int `1..31` (day-of-month).
* `calendar` with no anchor → defaults to UTC midnight (anchor field absent
  on disk; documented in the `add_provider` docstring).
* `rolling` with an anchor → anchor silently dropped (rolling windows have
  no calendar boundary).

## QuotaTracker shape (submodule output)

`_load_free_tier_limits()` returns `dict[str, dict[str, int]]` shaped
EXACTLY as `QuotaTracker(limits=...)` expects: only `rpm/rpd/tpm/tpd`
int keys per provider. Weekly/monthly token budgets and reset metadata
are intentionally stripped from the projection — QuotaTracker's
sliding-window model doesn't consume them; they're persisted for the
future billing/external accounting path.

## Design notes / deviations from a quick read of the ticket

* The new accessors are **underscore-prefixed** (`_load_free_tier_limits`,
  `_free_tier_to_quota_limits`). The `charon.config.__init__` facade is
  explicitly owned by DELETE-STATIC-RANK / PROVIDER-URL-HELPER — the
  ticket calls this out as out-of-scope. The facade test
  (`tests/test_config_facade.py::test_facade_re_exports_every_public_submodule_symbol`)
  requires every non-underscore name in any submodule to be re-exported in
  `__init__.py`. Underscore prefixing keeps the contract intact: downstream
  (FT-WIRE) imports directly from the submodule:
  ```python
  from charon.config.providers import _load_free_tier_limits
  ```
  If the facade owner later wants to add the re-exports, it's a trivial
  2-line additive change.
* `add_provider(free_tier=None)` is a back-compat no-op: the field is only
  written when the caller passes a block. This preserves the old
  "merge-into-existing-entry" semantics for the other kwargs (e.g. calling
  `add_provider("x", base_url=...)` doesn't clobber a previously-set
  `free_tier`).

## Verification
* New test file: `tests/test_config_free_tier.py` (23 tests).
  * Round-trip: full block / minimal / merge-into-existing / zero-limit.
  * Back-compat: no block, no kwarg, empty config dir.
  * Validation: negative / non-int / bool / unknown keys / bad reset / bad
    anchor / anchor-without-reset.
  * Anchor shapes: HH:MM / weekday name / day-of-month / garbage / rolling
    ignored / calendar no-anchor defaults to UTC midnight.
  * Projection: strips extras, empty input.
  * FAIL-ON-REVERT: pins the persisted `free_tier` field.
* Full gate green: 1746 tests pass (was 1723; +23 new). ruff clean, mypy
  clean, arch OK, security OK, boundary OK, version check unchanged
  (pre-existing pip editable drift, not introduced by this change).

## Files
* `src/charon/config/providers.py` — extended.
* `tests/test_config_free_tier.py` — new.
