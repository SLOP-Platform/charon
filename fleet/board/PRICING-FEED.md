repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: design-review
branch: eval/pricing-feed
depends_on:
owns: fleet/state/PRICING-FEED.md, docs/review-log/PRICING-FEED.md
serial_justified: |
  One comparison across one candidate set, producing one precedence order. Split across tabs,
  each lane would register verdicts derived from a different snapshot of the same feeds, and
  disagreement between them would be indistinguishable from the real cross-source disagreement
  this evaluation exists to detect.
substrate: N/A
substrate-novel: |
  This ticket IS the substrate evaluation — it exists to pick which external pricing sources we
  adopt and in what precedence. Nothing is built beyond the derived store and its precedence
  rule. Candidates are all third-party feeds; the novel slice is the corroboration policy.
accept: |
  MINTED 2026-08-02 to stop an information loss already flagged as the HIGHEST on the board.
  fleet/MODEL-ROLE-EVALUATION.md records PRICING-FEED as "NOT-STARTED as a ticket — PARTIALLY
  ABSORBED. Highest information-loss risk on this list." Its operator inputs exist ONLY in
  fleet/SESSION-HANDOFF-satele-shan.md:104-110 and nowhere else in the repo. That handoff has now
  aged through three sessions. This ticket moves them into the board before they are lost.
  OPERATOR INPUTS TO PRESERVE VERBATIM:
   (a) pricepertoken.com ships a **Price-Per-Token MCP** — live pricing + benchmarks, ~3 lines to
       wire.
   (b) **MCP-first is the preferred integration shape — check EVERY candidate for one.**
   (c) For EXTERNAL reference data prefer **multiple corroborating sources over SSOT**.
       Disagreement between feeds is ITSELF A SIGNAL. SSOT applies to data we OWN and is a
       category error for facts we OBSERVE. Multiple sources -> ONE derived store with a
       DECLARED PRECEDENCE.
   Selection criterion: API-addressable vs webpage-only.
  CANDIDATES — EVAL-REGISTRY currently has ZERO rows for any of these (grep-confirmed):
    benchlm.ai · pricepertoken.com (MCP) · whatllm.org · cheahjs/free-llm-api-resources ·
    12britz/awesome-free-models · TokenWatch (github.com/WyrdWerk/tokenwatch — already verified
    live: 993 models, 863KB pricing.json, no auth, 2-hourly cron, de-aggregates OpenRouter,
    covers OpenCode Go) · LiteLLM model_prices_and_context_window.json (the ONLY existing row:
    LiteLLM-as-data-source, ADOPT, 2026-07-12).
  Done contract:
  1. Evaluate each by CODE and by a LIVE FETCH, not by its marketing page. Record API-addressable
     vs webpage-only, refresh cadence, auth requirement, and licence.
  2. Check EVERY candidate for an MCP interface first (operator input b).
  3. Land a row per candidate in fleet/state/EVAL-REGISTRY.md. **HARD RULE: verdicts land in the
     registry, never in a handoff note** — violating it is exactly how this ticket was lost.
  4. Produce the DERIVED STORE design: multiple sources, declared precedence, and an explicit
     DISAGREEMENT SIGNAL (two feeds differing on a price is a finding to surface, not an average
     to take).
  5. Cross-check a sample against provider-reported cost. A feed that disagrees with what we were
     actually billed is evidence about the FEED, not about the bill.
  6. Feed the result to PRICE-REFRESHER (fallback price path) and SPEND-METRIC-TRUSTWORTHY
     (cost per ACCEPTED task). Price data informs routing; it never decides it alone, because
     quality is a model x provider property — see GRADE-MODEL-PROVIDER-PAIR.

## Dependencies & Sequence

P0 by information-loss risk, not by size. No inbound deps. Must land its EVAL-REGISTRY rows
BEFORE PRICE-REFRESHER commits to a single feed, or that ticket hard-codes a source this
evaluation was supposed to choose. Runs concurrently with the cost tickets (disjoint owns);
they consume its verdicts.
