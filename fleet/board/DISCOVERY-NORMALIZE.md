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
  NON-VACUOUS: a run that normalized ZERO offers must RED (`examined 0 offers`), never report clean.
  RUNNER-REACHABLE: this leg's red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  `fleet/tests/*.test.sh` glob or rig-ci-scope.sh CI_SUITES) — a proof no runner runs is not evidence.
  PUBLISH THE CONTRACT: write the §3c column header + one example row to a committed FIXTURE the
  downstream legs (D3/D4/D7) build against, so none of them has to wait on this module's code.
scope: |
  RawOffer -> normalized §3c inventory row (own discovery-inventory.tsv snapshot), identity via
  _normalize_model_id, funding_class inferred-provisional, adopting FREE-TIER-LIMITS.tsv columns. Merge into
  the shared table is D7 (INVENTORY-TABLE-SHARE), not here.
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-SOURCE-ADAPTERS (real build dep, KEPT — consumes its RawOffer output; there is
    no RawOffer shape to normalize until D1 defines it). D1 is BUILT (feat/discovery-source-adapters,
    PR #219) and UNLANDED: this edge clears by LANDING, not by restructuring the board.
  - feeds: DISCOVERY-DIFF (D3) diffs this snapshot; INVENTORY-TABLE-SHARE (D7) merges these rows into the
    shared price-tracked-inventory table. NEITHER is a board edge on this ticket — see below.
  - UN-BUNDLED 2026-07-24: this ticket was briefly absorbed into a DISCOVERY-PIPELINE mega-ticket. That
    was reverted. D2..D6 own SEVEN DISJOINT new files, so they are five INDEPENDENT tickets that five
    agents can build at once; fusing them into one serial branch traded the whole wall-clock win for
    nothing. Grouping is expressed as one ROADMAP wave (`discovery-leg`) at one priority, NOT as one
    ticket. [[decomposed-by-design-not-reactive]] [[optimize-execution-wallclock-tokens]]
  - reuse: charon.proxy._normalize_model_id; FREE-TIER-LIMITS.tsv columns.
  - concurrency: disjoint new files (normalize.py + its own discovery-inventory.tsv snapshot). Safe to
    build in parallel with D3/D4/D5/D6 — no shared file with any of them.
