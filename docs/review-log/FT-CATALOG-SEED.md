# FT-CATALOG-SEED — free-tier catalog seed + 3 hosted presets

## What landed

A SHIPPED seed of known free-tier rate limits and three new hosted
presets for the free providers the product has not yet been taught
by the build-rig's FREE-TIER-LIMITS.tsv.

- `src/charon/provider_presets/hosted.py` — added `github_models`,
  `featherless`, `ollama_cloud`. The local `ollama` preset in
  `local.py` is intentionally NOT touched.
- `src/charon/routing_policy/free_tier_catalog.py` (new) — stdlib
  data module. `FREE_TIER_CATALOG` plus `get_limits()` /
  `providers()` accessors. No network, no refresh loop, no
  `providers.json` writes.
- `tests/test_free_tier_catalog.py` (new) — FAIL-ON-REVERT coverage
  for every new preset, every seeded row, the unknown-returns-None
  contract, the defensive-copy contract, and the shape-parity with
  `quota.QuotaTracker`.

## Authority order (the load-bearing design decision)

1. Live limits refreshed by PRICING-LIMITS-CHECKER.
2. Explicit config (FT-CONFIG-SURFACE).
3. THIS SEED — fills the gap for a leg with no config and no fresh
   refresh.

The seed is the LOWEST tier. Operators can always win by adding
`[providers.<name>]` overrides; the rig can always win by writing
back through PRICING-LIMITS-CHECKER. The seed only matters for the
cold-start / unconfigured case.

## sg-never-anthropic

The seed never includes `anthropic`. The free-tier rules
(personal_only, free route silent downgrades) only apply to vendors
that actually have a free tier — Anthropic has none. A guard test
(`test_no_anthropic_entry_in_seed`) enforces this; a future ticket
that wants to add an Anthropic entry will have to think about it.

## Why the new providers are `verified=False`

The three new hosted presets are in the catalog as **placeholders**
with `verified=False`. The known numbers (groq 14,400 rpd / 30 rpm /
6,000 tpm; openrouter :free 1,000 rpd / 20 rpm; cerebras 1M tpd /
5 rpm; mistral ~1e9/month) are pinned to a specific verified source
— the test names the literal value so a future rig refresh that
mismatches will flip the test red and force a re-check. The
placeholder rows carry the same normalized shape (every key present,
values explicitly `None`) so a future PRICING-LIMITS-CHECKER can
fill them without schema work.

## Why `ollama_cloud` is distinct from `ollama`

The local `ollama` preset (`local.py`, `http://localhost:11434/v1`,
no key) is the gateway's user-owns-their-GPU path — rate limits
would be a footgun on a developer laptop. The new `ollama_cloud`
preset is the hosted free/turbo tier at `https://ollama.com/v1`,
key-required, and a legitimately different rate-limit profile.
Conflating them would either cripple local dev (false skips) or
remove the bound on the cloud tier (no skips). `ollama` is
intentionally absent from `FREE_TIER_CATALOG`; `ollama_cloud` is
present (placeholder, unverified).

## Why a separate module, not extending `providers.py`

`providers.py` is the registry resolver (base_url/key_env → wire
call). The catalog is a config-shaped data module consumed by the
quota tracker / future refreshers. Keeping them apart means:

- The seed has zero runtime cost when unused (the `quota.QuotaTracker`
  accepts a `dict` from anywhere; the seed is only read when called).
- The seed can evolve (add new fields like `reset`/`weekly`/`monthly`)
  without touching the wire resolver.
- Tests can pin the seed independently of the registry.

## Schema shape (per-provider dict)

```
rpm / rpd / tpm / tpd / weekly / monthly: int | None
reset:    "rolling" | "calendar" | "weekly" | "monthly"
verified: bool
personal_only: bool
note: str
```

Every key is present (None = "we don't track this window") — the
quota tracker and FT-CONFIG-SURFACE consumers iterate the same
keys, and a missing key is a shape bug, not a "no limit" signal.

## Out of scope (intentionally)

- Anthropic entry (sg-never-anthropic).
- Local ollama entry (no limits, no point).
- Any config-side wiring (the seed is a pure data module; the
  consumer that merges it into the live limits dict is a separate
  ticket — likely FT-CONFIG-SURFACE).
- Refresh logic (PRICING-LIMITS-CHECKER is its own ticket).
