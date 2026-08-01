repo: charon-private
tier: strong
priority: 0
difficulty: 1
work_class: routing
branch: fix/broker-bare-tier-legs
owns: fleet/tier-models.tsv
serial_justified: One data file; the whole change is removing provider suffixes from three chains.
substrate: N/A
substrate-novel: |
  Not a build at all — a DATA correction to one rig-local TSV, removing provider pins so the
  gateway's existing broker does the job it is already wired to do. No tool, library or new code is
  involved, so there is nothing to adopt-vs-build.
depends_on:
note: |
  NORTH-STAR ALIGNMENT (operator directive 2026-08-01): "the BROKER, using the model tier list,
  finds a provider that can service the model and gets it to the work." Static provider-pinned
  chain legs are the opposite of that.

  MEASURED 2026-08-01 — 10 of 17 tier-chain legs were provider-PINNED (`-go`, `-ds`, `-groq`),
  which OVERRIDES a broker that already works:

    pinned leg              bare id             broker pool depth
    minimax-m2.5-go      -> minimax-m2.5        2 legs
    deepseek-v4-flash-ds -> deepseek-v4-flash   7 legs (incl. opencode-go)
    deepseek-v4-pro-ds   -> deepseek-v4-pro     4 legs
    gpt-oss-120b-groq    -> gpt-oss-120b        8 legs

  Pinning collapses each of those pools to ONE provider: no failover, no funding-class ordering,
  no cooldown/latency rotation, and no ability for the broker to honour the opencode-Go bundle
  ($10/mo flat, GLM-5.2 + DeepSeek + Kimi + MiMo, $60/mo cap) or the Zen free-only rule. Those are
  cost constraints that belong to POOL MEMBERSHIP, decided per request by the broker — not frozen
  into a tier list.

  CORRECTION RECORDED (this session got it wrong first): `kimi-k2.6` and `minimax-m3-free` were
  initially reported as DEAD legs because they are absent from `/v1/models`. They are NOT dead.
  `proxy_server.py` deliberately hides POOL-ONLY ids (`pool_only = set(srv.pools) - set(srv.routes)`)
  since a pool name is a routing concept, not a billable model. Both return 200 and fail over
  across 5 and 4 provider legs respectively. fleet/OPENCODE-MODEL-LIST-GAP.md had already warned
  that deriving the routable set from /v1/models alone is wrong; sync-opencode-models.sh now unions
  in the pool ids from /charon/status.

  Tier MEMBERSHIP is deliberately unchanged here — no model moves between tiers. Placement is
  governed by the grading/promotion process (see RANKING-PIPELINE-AUDIT.md) and is a separate
  decision.
accept: |
  - Every leg in fleet/tier-models.tsv is a BARE model id — no `-go` / `-ds` / `-ng` / `-or` /
    `-nw` / `-groq` / `-hf` / `-cline` / `-nv` provider suffix.
  - `free-*` ids are NOT stripped (`free-groq`, `free-cerebras`, `deepseek-v4-flash-free` are
    genuine free-tier model ids, not provider pins).
  - De-duplication preserves first-occurrence order, so cheapest-capable-first intent survives.
  - No model is added to or removed from any tier — membership is unchanged.
  - Every resulting id verified to return HTTP 200 from the live gateway before landing.
  - `fleet/sync-opencode-models.sh --check` exits 0 (all chain models declared AND routable).

## Dependencies & Sequence

- **depends_on: (none).** Single data file.
- **Sequence: before any dispatch wave** — every droid/reviewer chain is read from this file, so
  landing it first means the broker (not the tier list) picks providers for all subsequent work.
- **Blocks / unblocks:** unblocks real failover depth on the strong/frontier chains (2-8 legs
  instead of 1) and lets funding-class / cooldown / latency ordering actually apply.
- **owns-collision:** none — `fleet/tier-models.tsv` carries no `owns:` on any other live ticket.
- **Does NOT fix (separate, still open):** cost-based reordering is INERT — `forwarder.py:548`
  guards `order_pool_by_live_cost` on a non-empty live meter, and per-provider spend is never
  populated (live `usage.cost_usd` = $0.000045 across 3.3M tokens in; `remaining_usd` is null for
  all 17 providers). That is FORWARDER-COST-ORDER-FALLBACK / SPEND-METRIC-TRUSTWORTHY.
