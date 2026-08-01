repo: charon
tier: strong
priority: 0
difficulty: 3
work_class: money-path
branch: fix/catalog-refresh-persist
depends_on: SW-STATIC-LEGS-RETIRE
real-dep: SW-STATIC-LEGS-RETIRE shares src/charon/routing_policy/catalog_refresh.py and is pushed awaiting merge — sequence after it lands
owns: src/charon/routing_policy/catalog_refresh.py, tests/test_catalog_refresh_persist.py
substrate: N/A
substrate-novel: |
  REUSES the refresher that already exists and already works. `routing_policy/catalog_refresh.py`
  already polls every configured provider's OpenAI-compatible `GET /models` on a TTL and already
  has correct failure semantics ("STALE-BUT-USABLE: a provider poll that fails keeps that
  provider's last-good entries"). Nothing about discovery needs building. The novel slice is the
  WRITE-BACK — persisting what it discovers into the catalog the router actually reads.
serial_justified: |
  One write-back path on one existing poller.
source: |
  Operator, 2026-08-01: "CG needs to do regular updates on available models, not just with
  opencode zen/go."
note: |
  ## THE DEFECT — DISCOVERY WORKS, THE WRITE-BACK WAS NEVER BUILT
  Measured on the live 4-LOM gateway:
  - `catalog_refresh.json` = `{"enabled": true, "ttl_s": 21600}` — **33 bytes, config only**.
  - **No catalog cache file exists on /data.** The only artefacts are that config and its backup.
  - `catalog_refresh.py` contains NO reference to `models.json`, `write`, `persist` or `json.dump`.
  - The gateway log shows it IS polling (repeated `catalog refresh: provider 'cline-pass' /models
    poll failed (404) — keeping last-good entries`), so the job runs every 6h as designed.
  Conclusion: **the refresher polls every provider and holds results IN MEMORY ONLY.** Every
  restart discards them, and `/data/models.json` — the file the router reads for `free`,
  `cost_rank` and `enabled` — is never updated.

  ## WHAT THAT COST (all measured 2026-08-01)
  - **opencode-zen rotates its free list and we never noticed.** Live `GET /zen/v1/models` showed
    6 free models; our catalog had `minimax-m3-free` and `qwen3.6-plus-free` (both ROTATED OUT)
    and was missing `laguna-s-2.1-free` and `ling-3.0-flash-free` (both rotated IN and both
    verified routing `provider=direct`).
  - **`free=False` on genuinely free models** (every Zen `*-free`), so free-first ordering skipped
    them and traffic went to paid legs instead.
  - **647 of 859 entries carry no `cost_rank`**, so cost-first ordering is blind to most of the
    catalog. `together` has 270 enabled models and exactly ONE ranked.
  - The manager had to hand-sync Zen's free list and hand-correct `free` flags — a manual fix that
    will rot again within 6 hours [[dynamic-tools-never-on-demand]].

  ## SCOPE
  1. **PERSIST the poll result.** Write discovered `(provider, model)` plus `free`, price/cost
     fields and availability into the catalog the router reads, atomically.
  2. **MERGE, do not clobber.** Operator/manual overrides and `enabled: false` decisions must
     survive a refresh — a provider poll must never silently re-enable something switched off on
     purpose, nor drop a hand-added entry. State the precedence explicitly.
  3. **Handle ROTATION in both directions.** A model that disappears from a provider's `/models`
     must be marked unavailable (not silently left routable); a model that appears must become
     routable. Zen is the proof case: 2 out, 2 in, within days.
  4. **Cover every provider, not just Zen/Go** — the poller already does; the write-back must too.
  5. **Surface the refresh.** Last-refresh time and per-provider status must be visible (a poll
     that has failed for days should be loud, not one log line among thousands — `cline-pass` has
     been 404ing on every cycle and nobody noticed).

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, offline, injected mock provider (the module already supports an injectable poller —
  use it; do NOT hit real networks in tests):
    a. a poll discovering a NEW model persists it, and it SURVIVES a restart. Revert the
       write-back -> RED. **This is the whole defect.**
    b. a model that disappears from a provider's /models is marked unavailable, not left routable.
       (The Zen rotation case.)
    c. `free` and price fields from the poll land in the catalog — a provider-reported free model
       ends up `free: true`. (The `free=False`-on-free-models bug.)
    d. **MERGE-SAFETY (ANTI-OVER-BLOCK)**: an operator `enabled: false` and a hand-added entry
       both SURVIVE a refresh. Revert -> RED. Clobbering operator intent is worse than staleness.
    e. a provider whose poll FAILS keeps its last-good entries (guards the existing
       stale-but-usable behaviour from regressing) AND its failure is surfaced.
  Then dogfood against the live gateway: report models added/removed/re-priced on one real cycle.

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  Reviewer != builder. This writes the data every routing and cost decision reads. The reviewer
  must confirm a bad poll cannot empty or corrupt the catalog, and cannot resurrect a deliberately
  disabled leg.

D&S — Deps & Sequence:
  - Feeds CATALOG-COMPLETENESS (which backfills what is missing) and FREE-TIER-QUOTA-ROUTING
    (which needs accurate `free` flags). This one keeps the catalog TRUE over time; those consume it.
  - Check owns collision on routing_policy/ before starting.

## Bar raised 2026-08-01 (operator: "FULLY tested and wired (dogfood etc)")

This ticket may NOT be marked done on a green unit test. It is the canonical instance of the
rig's dominant failure class — a mechanism that exists and cannot fire — so the proof must be
behavioural, not structural.

REQUIRED, all of them:

1. **PERSISTS.** After a refresh cycle, `models.json` on disk actually changes. Prove it by
   diffing the file before/after, not by asserting the function was called. The current defect is
   precisely that results live in memory and are dropped.

2. **FIRES ON A CADENCE, and the cadence is observable.** Show the 6h poller invoking the persist
   path in a real run. A refresher whose timer never fires is the same bug in a new place.

3. **DOGFOOD — the real test.** Point it at the LIVE gateway catalog and prove it detects a genuine
   change. Two concrete, currently-true cases to use as fixtures:
     * `minimax-m3-free` billed $0.1542 and $0.1009 on 2026-08-01 despite `-free` in its NAME.
       A refresh must surface that its free status no longer matches the id.
     * `deepseek-v3` / `deepseek-r1` are ids that existed once and now match NOTHING among the
       gateway's ~2580 models. A refresh must surface a vanished id, not silently keep it.
   Model NAMES change and free STATUS changes — see MANAGER-OPERATING-RULES.md §14.

4. **PROPAGATES TO EVERY CONSUMER.** Per §14's generalisation: a refresh that updates ONE copy is a
   drift generator, because the copies then disagree and each looks authoritative. Name every
   consumer of catalog data in the PR and show each one sees the update — at minimum
   `models.json`, `pools.json`, the opencode client's declared model map (see
   `fleet/sync-opencode-models.sh`), and `fleet/tier-models.tsv` chains.

5. **FAILS LOUD, never silently stale.** If a provider poll fails, the refresher must say so and
   leave the previous data intact with a visible staleness marker. It must NEVER write a partial
   catalog and never report success on a failed poll — an unreachable provider must not read as
   "this provider now offers nothing".

6. **FAIL-ON-REVERT, externally red-proofed.** Report both counts (green with the fix, RED on
   revert). A test that passes with the persist call removed is worthless.

7. **A GATE, so it cannot rot back.** `fleet/sync-opencode-models.sh --check` already exits 3 when a
   tier chain names a model the client cannot call or the gateway will not route. Wire the
   staleness check into preflight so drift is caught mechanically rather than remembered.

NOT IN SCOPE, and do NOT do it: setting or changing any spend cap. The live meter is fiction in
both directions (gateway reports usage.cost_usd = $0.000226 while opencode reports $1.3372 of real
spend for the same period), and a cap against a fictional number bricks the gateway.
