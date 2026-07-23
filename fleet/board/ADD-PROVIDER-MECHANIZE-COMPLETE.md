repo: charon-private
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: feat/add-provider-mechanize-complete
depends_on:
serial_justified: coupled add-flow — add-provider.sh and add-provider-interactive.sh share the same provider-add path (key handling, models import, funding_class, verify); the cost+funding_class+routable-verify logic spans both. One surface, not two.
owns: fleet/add-provider.sh, fleet/add-provider-interactive.sh
work_class_note: |
  Operator directive (2026-07-23): "adding a new provider needs to be mechanized where it looks at the
  models available, the costs, then puts it into the right places and makes sure it's wired/ready/available
  properly and completely." ENHANCE the EXISTING mechanization (fleet/add-provider.sh from ADD-PROVIDER-
  MECHANIZE) — do NOT rebuild. It already does: secure-key-via-stdin → `providers add --base-url` → `models
  import` → `providers test` → restart → `/v1/models` verify (idempotent). Close the gaps below so a
  provider-add is COMPLETE. [[no-rig-as-product-adopt-dont-handroll]] [[always-fix-catalog-mismatches]]
  [[latency-is-a-failure-class]]
accept: |
  Enhance fleet/add-provider.sh (+ add-provider-interactive.sh) so ONE command makes a provider fully
  wired/ready/available. Close these specific gaps (each is a real deficiency found this session):
    1. **COSTS (real, not cost_rank):** today `models import` sets a cost_rank but NOT live $/Mtok pricing.
       Populate real per-model input/output pricing by REUSING the existing CG pricing-refresh mechanism
       (PRICE-REFRESHER `src/charon/routing_policy/price_refresher.py` / `fleet/pricing-limits-check.sh` /
       `provider-pricing-limits.tsv`) — do NOT hand-roll a new price source. If pricing for a provider isn't
       in the refresh source, fetch it and feed the refresh mechanism so the regular cycle keeps it fresh.
    2. **funding_class auto-set:** the add flow does NOT set funding_class, so a freshly-added provider is
       unclassified → sorts BELOW the paid floor → never routed (the exact inert-pool bug hit this session).
       `config.add_provider()` supports funding_class but the CLI has NO `--funding-class` flag. Wire it
       (product `src/charon/cli.py providers add` — cross-repo sub-item; coordinate/land there) and have
       add-provider.sh require/pass a funding-class (1 free / 3 drain-prepaid / 2 flat-sub / 4 PAYG).
    3. **COMPLETE availability verification:** model-VISIBLE (`/v1/models`) is not the same as ROUTABLE.
       Add a real end-to-end check: a live completion actually RESOLVES to the new provider's model(s), and
       record the provider's rate-limits/quota into the free_tier_catalog (the foreman-flagged NIM gap).
       Fail-loud + roll back if a model imports but can't actually serve.
    4. **Fix the two known bugs (foreman-flagged):** (a) `providers test` (step 4) falsely reports FAILED
       for a non-preset provider added with `--base-url` though it succeeds; (b) add-provider-interactive.sh
       ECHOES the key — switch to getpass / `read -rs` (secrets ratchet — [[security-is-a-ratchet-gate]]).
  PROVE IT: fail-on-revert test(s) covering funding_class-set, real-cost-populated, and routable-not-just-
  visible. Dogfood by (re)adding one real provider end-to-end and showing it routes + has costs + a class.
  COMPLETION SELF-CHECK: if an added provider can be unclassified, cost-less, or visible-but-unroutable, or
  either bug remains, INCOMPLETE.
scope: |
  Make `fleet/add-provider.sh` a COMPLETE mechanized add: discover models (exists) + populate REAL costs via
  the existing pricing-refresh cycle + auto-set funding_class (wire the missing CLI flag) + verify routable-
  not-just-visible + record rate-limits + fix the test-false-FAIL and key-echo bugs. Enhance, don't rebuild.
ds: |
  ## Dependencies & sequence
  - depends_on: (none to start). owns fleet/add-provider*.sh — no other live ticket owns them (checked).
  - CROSS-REPO sub-item: the `--funding-class` CLI flag lives in product `src/charon/cli.py` (config API
    already supports it) — land that slice in the product repo and consume it here. Flag if it must be a
    separate product ticket.
  - REUSE-FIRST: costs come from the existing PRICE-REFRESHER / pricing-limits refresh cycle — do not add a
    second price source (see PROVIDER-BEST-INVESTIGATION.md's refresh-mechanism finding when it lands).
