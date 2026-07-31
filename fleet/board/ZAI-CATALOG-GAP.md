repo: charon
tier: strong
difficulty: 2
work_class: routing
priority: 0
branch: feat/zai-catalog-gap
depends_on:
owns: src/charon/discover.py, src/charon/model_catalog.py, tests/test_zai_catalog.py
serial_justified: |
  ONE capability question: "which GLM legs does the funded zai provider actually serve, and are they
  in the catalog". The discovery pass and the catalog entries it produces are the same deliverable —
  adding entries without discovery is guesswork, and discovering without recording changes nothing.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Use a VERIFIED-FUNDED leg — see the outage note below. Own worktree.
source: |
  Found 2026-07-31 while diagnosing an "all providers exhausted" failure on glm-5.2 / kimi-k2.6.
  Operator approved (rec 2 of 3).
note: |
  ## THE GAP (measured, verified — confirm, do not re-derive)
  `zai` (https://api.z.ai/api/paas/v4) has `[key SET]`, is FUNDED, and is VERIFIED WORKING:
  a live request to `glm-4.7-flash-zai` returned `finish_reason=stop`, content `"Ok."` on
  2026-07-31. It is a first-party GLM provider.

  But the catalog carries only TWO zai entries — `glm-4.5-flash-zai`, `glm-4.7-flash-zai`
  (both `flash`). There is NO `glm-5.2-zai`, no `glm-5.1-zai`, no `glm-5-zai`.

  Meanwhile EVERY other GLM leg is dead: `opencode-zen` and `opencode-go` are `enabled:false`;
  `-or` (openrouter) 402; `-nw` (neuralwatt) 402; `-ng` (nanogpt) weekly-capped; `-cline` 429
  monthly cap; `-hf` monthly credits depleted.

  So a funded first-party GLM provider is sitting idle while the GLM family reads as fully
  offline. That is free capacity routing cannot see.

  ## WHAT TO DO
  1. Run a real DISCOVERY pass against zai — `charon discover` is the owned tool for this; do NOT
     hand-maintain a model list. Establish which GLM models z.ai actually serves on this key
     (glm-5.2? glm-5? only flash tiers?). **UNVERIFIED so far: whether z.ai serves glm-5.2 at all
     on our plan.** If it does not, that is a legitimate and valuable NEGATIVE result — record it
     and stop; do not invent entries.
  2. For each GLM model zai genuinely serves, add the catalog leg with correct `upstream_model`
     and `cost_rank`.
  3. Prove each added leg with a REAL completion through the gateway (not a /models listing):
     paste the request and the response `finish_reason`.

  ## THE DEEPER FINDING — REPORT, DO NOT FIX HERE
  There is **no git-side catalog SSOT**. `models.json` exists only as live state on the 4-LOM
  `/data` volume; a search of the product repo found no providers/models manifest. The standing
  decision "config SSOT = git manifest" is DECIDED BUT NOT EXECUTED. That means this ticket's
  changes are a LIVE-CONFIG mutation with no reviewable git artifact — the same class as
  `[[charon-deploy-drift-lessons]]` (deployed image != source).
  Record this in your report as a blocking-class finding and propose the SSOT ticket.
  Do NOT attempt the SSOT migration inside this ticket — it is a separate, larger change.

  ## GUARDS
  - **Back up `/data/models.json` before any live mutation** and prove the backup exists
    [[investigate-and-backup-before-data-loss]].
  - Do NOT enable legs you have not proven with a real completion. A catalogued-but-dead leg is
    exactly the defect that produced this ticket.
  - Do NOT touch the `enabled:false` opencode-zen / opencode-go entries — whether those should be
    re-enabled is a funding decision for the operator (pending item #14), not a routing fix.
  - **Model selection for your own session:** GLM and Kimi are OFFLINE. Verified-funded legs as of
    2026-07-31: `deepseek-v4-pro`, `minimax-m3-together`, `devstral-2512`, `gemini-2.5-pro`.

  ## DONE CONTRACT
  - Discovery output showing what zai actually serves (real command + real output).
  - Either: new catalog legs, each proven with a real gateway completion — or a documented
    negative result explaining why no leg was added.
  - A regression test asserting the catalog contains no leg that cannot be reached.
  - The SSOT finding written up with a proposed follow-up ticket.

D&S — Deps & Sequence:
  - Depends on: nothing. zai is funded and live today.
  - Blocks: nothing directly, but it is the cheapest path to restoring ANY GLM capability while
    pending item #14 (funding) is unresolved.
  - Related: `POOLS-SIMPLIFICATION` (parked) — the six-separate-entries-per-model structure that
    prevents `glm-5.2` failing over to any sibling leg. This ticket ADDS a leg; that ticket makes
    legs reachable from one name. They are complementary, not overlapping: disjoint `owns:`.
