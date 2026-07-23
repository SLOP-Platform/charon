repo: charon-private
tier: strong
difficulty: 2
work_class: generalist
priority: 1
branch: feat/discovery-normalize
depends_on: DISCOVERY-SOURCE-ADAPTERS
dep-kind: build
owns: fleet/discovery/normalize.py, fleet/state/discovery-inventory.tsv
note: |
  D2 of the DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN §3a/§3c, operator-approved P1, 2026-07-23).
  RawOffer -> one normalized inventory row per (source, provider, model). REUSE-FIRST: model identity via
  the router's OWN `_normalize_model_id` (charon.proxy) so discovery dedup == router identity; adopt the
  FREE-TIER-LIMITS.tsv column set (no new schema). funding_class INFERRED here is provisional until
  add-provider re-derives it authoritatively. [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  A normalize step turning each RawOffer (from D1) into a §3c inventory row written to
  `fleet/state/discovery-inventory.tsv` (its OWN snapshot; the shared table merge is D7):
    1. Columns = the §3c union (source, source_url, provider, base_url, model_ids, funding_class,
       cost_in/out_usd_mtok, rpd, rpm, tpm, tpd, context_cap, trains_on_data, personal_only,
       exhaustion_signal, first_seen, last_seen, status). No new columns invented.
    2. Model identity via `_normalize_model_id` (reuse verbatim) so a model maps to the same key the
       router uses. Keyed row = (provider, normalized_model).
    3. `funding_class` inferred (1 free / 2 flat-sub / 3 drain-prepaid / 4 PAYG) from cost==0 + trial
       flags; marked PROVISIONAL (add-provider re-derives authoritatively per ADD-PROVIDER gap #2).
    4. status defaults to `candidate`; first_seen/last_seen stamped.
  FAIL-ON-REVERT: two source rows for the same model under different id spellings normalize to ONE key;
  break the _normalize_model_id call -> duplicate keys -> RED.
scope: |
  RawOffer -> normalized §3c inventory row (own discovery-inventory.tsv snapshot), identity via
  _normalize_model_id, funding_class inferred-provisional, adopting FREE-TIER-LIMITS.tsv columns. Merge into
  the shared table is D7 (INVENTORY-TABLE-SHARE), not here.
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-SOURCE-ADAPTERS (real build dep — consumes its RawOffer output).
  - feeds: DISCOVERY-DIFF (D3) diffs this snapshot; INVENTORY-TABLE-SHARE (D7) merges these rows into the
    shared price-tracked-inventory table.
  - reuse: charon.proxy._normalize_model_id; FREE-TIER-LIMITS.tsv columns.
  - concurrency: disjoint new files (normalize.py + its own discovery-inventory.tsv snapshot).
