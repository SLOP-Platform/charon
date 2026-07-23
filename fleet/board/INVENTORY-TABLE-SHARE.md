repo: charon-private
tier: strong
difficulty: 2
work_class: money-path
priority: 1
branch: feat/inventory-table-share
depends_on: INVENTORY-TABLE, DISCOVERY-NORMALIZE
dep-kind: build
owns: fleet/discovery/inventory_writer.py
note: |
  D7 of the DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN §4, operator-approved P1, 2026-07-23). The
  discovery-side WRITER that merges normalized discovery rows into the ONE shared price-tracked-inventory
  table — "one table, two writers." REUSE-FIRST: the table + accessor already exist (INVENTORY-TABLE); this
  ticket only writes discovery's candidate + community-observed columns into it (catalog_refresh + the meter
  own the live/measured columns). No parallel store. [[always-fix-catalog-mismatches]]
accept: |
  Make discovery co-write the shared INVENTORY-TABLE (do NOT fork a second store):
    1. Upsert D2's normalized discovery-inventory.tsv rows into fleet/state/price-tracked-inventory.tsv via
       the INVENTORY-TABLE accessor, keyed on (provider, normalized_model).
    2. **Column partition enforced** — discovery writes ONLY the candidate + community-observed columns
       (source, source_url, funding_class-provisional, community cost/limit, first_seen/last_seen, status);
       it must NOT clobber the live/measured columns catalog_refresh + the meter own.
    3. The meter's observed per-(model,provider) cost SUPERSEDES any community-quoted price once traffic
       exists (ADR-0016 invariant) — discovery's cost columns are cold-start ordering only.
  FAIL-ON-REVERT: a discovery upsert must not overwrite a meter-written live cost column; make it clobber
  -> RED.
scope: |
  The discovery writer that merges normalized rows into the shared price-tracked-inventory table via the
  INVENTORY-TABLE accessor, partitioned to the candidate/community columns only. One table, two writers.
ds: |
  ## Dependencies & sequence
  - depends_on: INVENTORY-TABLE (the shared table + accessor it writes through) + DISCOVERY-NORMALIZE (the
    rows it merges). Both real build deps.
  - coordinate with: PRICE-TRACKED-INVENTORY-AUTOSWAP (owns the table concept); catalog_refresh + meter
    write the measured columns (not this ticket).
  - concurrency: disjoint new file fleet/discovery/inventory_writer.py.
