repo: charon-private
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: feat/inventory-table
depends_on:
serial_justified: coupled data-primitive — the KS29 accessor script and its one canonical TSV are a single surface (the accessor defines the schema the TSV instantiates; splitting them would hand "write the schema" and "write the file it describes" to two agents). One table, one accessor.
owns: fleet/inventory-table.sh, fleet/state/price-tracked-inventory.tsv
note: |
  FOUNDATION ticket for the self-maintaining-supply lens (operator-approved P1, 2026-07-23). The shared
  price-tracked inventory SPINE that BOTH the discovery leg (DISCOVERY-* / D1-D7) and the drift leg
  (R17 / PRICING-LIMITS-CHECK-SH) consume — "one table, two writers" (FREE-PROVIDER-DISCOVERY-DESIGN §4).
  COMPOSE, do not invent a new schema: adopt the column union already defined in fleet/state/
  FREE-TIER-LIMITS.tsv + the design §3c row. Reuse-first per [[no-rig-as-product-adopt-dont-handroll]]
  [[always-fix-catalog-mismatches]]. Builds FIRST — every D-ticket that writes/reads the shared table
  sequences after this.
accept: |
  A registry-driven inventory table (KS29 data-row primitive) so adding/dropping a provider-offer is a
  DATA row, not code. Deliver:
    1. **Canonical file** `fleet/state/price-tracked-inventory.tsv` with the §3c column union (NO new
       invention — union of the existing FREE-TIER-LIMITS.tsv schema):
       `source, source_url, provider, base_url, model_ids, funding_class, cost_in_usd_mtok,
        cost_out_usd_mtok, rpd, rpm, tpm, tpd, context_cap, trains_on_data, personal_only,
        exhaustion_signal, first_seen, last_seen, status`. `status ∈ {candidate, reviewing, approved,
        rejected, configured, gone}`.
    2. **Accessor** `fleet/inventory-table.sh` — init / read / upsert-row / list-by-status, keyed on
       `(provider, normalized_model)`. Model identity via the router's OWN `_normalize_model_id`
       (charon.proxy) so inventory dedup == router identity (reuse verbatim; do NOT re-implement).
    3. **Writer partition documented** in-file: discovery writes candidate + community-observed columns;
       catalog_refresh + the meter write live/measured columns. No parallel store.
    4. Seed from the operator's 2026-07-23 inventory rows (synthetic/trae/HF/nous/grok/mistral/zai/
       cerebras/deepinfra/deepseek/together/groq/morph + plan tiers + funding class).
  FAIL-ON-REVERT: upsert a row then read it back keyed on (provider, normalized_model); corrupt the
  key-normalization -> read misses -> RED.
scope: |
  Build the shared price-tracked inventory table (KS29 primitive): one canonical TSV (§3c column union,
  no new schema) + a stdlib accessor keyed on router-identity. Foundation both the discovery and drift
  legs consume. Compose the existing FREE-TIER-LIMITS.tsv columns + _normalize_model_id; do not rebuild.
ds: |
  ## Dependencies & sequence
  - depends_on: (none) — this is the FOUNDATION; it builds first.
  - consumed by: DISCOVERY-NORMALIZE (writes candidate rows via INVENTORY-TABLE-SHARE), R17/
    PRICING-LIMITS-CHECK-SH (drift columns), SINGLE-LEG-AUTOSWAP (reads per-model coverage).
  - reuse: FREE-TIER-LIMITS.tsv column schema; charon.proxy._normalize_model_id for key identity.
  - concurrency: disjoint new files (fleet/inventory-table.sh + its TSV) — no other live ticket owns them.
