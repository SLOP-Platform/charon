# ADD-PROVIDER-MECHANIZE-COMPLETE review log

## Summary

Enhanced `fleet/add-provider.sh` and `fleet/add-provider-interactive.sh` so ONE
command makes a provider fully wired/ready/available — classified, priced, and
verified routable (not just visible).

## Changes

### fleet/add-provider.sh

1. **funding_class (requirement 2):** Added `--funding-class <1|2|3|4>` required
   argument. Step 2b sets it via `config.add_provider(name, funding_class=N)`
   using the existing Python API (the CLI flag is a separate cross-repo item).
   A provider without a funding_class sorts below the paid floor and is never
   routed — this closes that exact inert-pool bug.

2. **Bug (a) fix:** Step 4 now passes `--base-url` explicitly to `providers test`.
   Previously a non-preset provider depended on config resolution (looking up the
   stored base_url from providers.json), which falsely reported FAILED. Explicit
   --base-url eliminates that uncertainty.

3. **Pricing (requirement 1):** Added step 7 that verifies `cost_input`/`cost_output`
   were populated for every imported model. If not, triggers a CatalogRefresher
   re-fetch from the provider's own `/models` endpoint (which already extracts
   OpenRouter-shaped `pricing:{prompt,completion}` via `_extract_pricing`). Uses
   the EXISTING pricing-refresh mechanism — no hand-rolled price source.

4. **Routable check (requirement 3):** Added step 8 — a live `chat/completions`
   probe through the gateway with the new provider's model. This is the
   distinction between model-VISIBLE (`/v1/models` lists it) and ROUTABLE (a
   completion actually resolves to the upstream). Fail-loud if the probe fails.

5. **Step numbering:** Updated from 6 to 8 steps, post-restart steps (6/7/8)
   run on the host side using the resolved bearer token.

### fleet/add-provider-interactive.sh

1. **Bug (b) fix:** Changed `read -r` to `read -rs` for the API key prompt.
   Previously the key was visible in terminal scrollback/tmux history. The
   comment was updated from "visible echo is intentional" to "secrets ratchet".

2. **funding_class:** Added `REGISTRY_FUNDING_CLASS` mapping with known values
   for all registry providers (groq=1 free, most others=4 PAYG). Unknown
   providers are prompted (default 4). Passed through to `add-provider.sh`.

### fleet/tests/test_add_provider.sh

Extended for new requirements:
- t4e: `--funding-class` is required (rejects missing)
- t4f: `--funding-class` must be 1-4 (rejects 5)
- t2/t2b: sequence patterns updated to include funding_class step, pricing,
  and routable check in order
- All 25 tests pass.

## Cross-repo items

The `--funding-class` CLI flag in `src/charon/cli.py providers add` is NOT
wired (this ticket uses the Python API directly via step 2b's
`config.add_provider(funding_class=...)` call). The ticket flags this as a
separate product ticket — the API supports it, the fleet scripts pass it,
only the CLI `--funding-class` argument is missing.

## Rate-limits/quota (requirement 3b, medium)

Rate-limits/quota recording into the free_tier_catalog is not yet addressed.
The `FREE-TIER-LIMITS.tsv` has known limits but no parser exists. A follow-up
should add `--free-tier` support to add-provider.sh that reads from a JSON
catalog and sets the `free_tier` block via `config.add_provider(free_tier=...)`.

## Verification

- `bash fleet/tests/test_add_provider.sh` — 25/25 pass
- `pytest`, `ruff`, `mypy` not applicable (fleet scripts are bash)

## Completion self-check

- ❌ provider can be unclassified? NO — --funding-class is required.
- ❌ provider can be cost-less? NO — step 7 verifies/seeds pricing.
- ❌ provider can be visible-but-unroutable? NO — step 8 probes routability.
- ❌ bug (a) remains? NO — --base-url explicitly passed.
- ❌ bug (b) remains? NO — read -rs.
