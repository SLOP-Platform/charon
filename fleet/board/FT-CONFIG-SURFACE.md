repo: charon
tier: strong
difficulty: 2
work_class: refactor
branch: feat/ft-config-surface
depends_on:
owns: src/charon/config/providers.py, tests/test_config_free_tier.py
accept: |
  Give provider config a place to DECLARE a leg's free-tier limits so QuotaTracker can be fed from
  config (today `config/providers.py` add_provider accepts only dollar starting_balance + funding_class;
  there is NO rpd/rpm/tpm/tpd field, so nothing can ever populate the limiter).
  DO (src/charon/config/providers.py):
  - Extend the add_provider / provider schema with an optional `free_tier` block per leg:
    { rpm, rpd, tpm, tpd, weekly_tokens, monthly_tokens } (all optional ints) + `reset` kind
    ("rolling" | "calendar") + optional `reset_anchor` (utc time / weekday / day-of-month). Absent
    block == no limits == unlimited (back-compat: existing configs load unchanged).
  - Validate: reject a negative/non-int limit with a clear error; a `calendar` reset with no anchor
    defaults to UTC-midnight (document it). Emit a normalized dict shaped EXACTLY as QuotaTracker's
    `limits={provider: {...}}` constructor expects (FT-QUOTA-ENGINE owns that shape — match it so
    FT-WIRE can pass it straight through with no adapter).
  - Do NOT touch src/charon/config.py (owned by DELETE-STATIC-RANK/PROVIDER-URL-HELPER) or
    config/keyprobe.py (owned by PROVIDER-PROBE-FIX) — this ticket lives entirely in config/providers.py.
  FAIL-ON-REVERT (tests/test_config_free_tier.py, new): a provider config with a `free_tier` block
  round-trips to the normalized limits dict QuotaTracker consumes; a bad limit is rejected; a config
  with NO free_tier block still loads (unlimited). Revert the schema field → the free_tier config is
  dropped/errors → test fails.
