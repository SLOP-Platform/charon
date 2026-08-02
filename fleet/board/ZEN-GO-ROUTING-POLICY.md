repo: charon
tier: strong
priority: 0
difficulty: 3
work_class: routing
branch: feat/zen-go-routing-policy
depends_on:
depends_on: WCI-DEC-SRC-CHARON-PROVIDERS-PY
owns: src/charon/providers.py, src/charon/provider_presets/opencode.py, src/charon/routing_policy/__init__.py, tests/test_zen_go_routing_policy.py, docs/review-log/ZEN-GO-ROUTING-POLICY.md
owns_widened: |
  WIDENED 2026-08-02. The ticket owned ONLY its review-log, but a droid had already written +58
  lines of real implementation for it into the PRODUCT MAIN CHECKOUT (the leak-guard class) plus
  an untracked tests/test_zen_go_routing_policy.py. That work was therefore owned by NO ticket,
  which made it both unlandable and invisible to every ownership gate — it surfaced only as three
  `uncommitted-work` REDs in validate_board.sh. Widening owns is what makes the existing work
  landable onto feat/zen-go-routing-policy instead of being stashed or discarded.
serial_justified: |
  One policy over two provider entries with one shared enforcement point. Splitting it lands half
  a policy, which is indistinguishable from none.
substrate: N/A
substrate-novel: |
  No tool adopted. Provider config and pool construction already exist; what is missing is the
  CONSTRAINT and its assertion. The novel slice is encoding an operator routing decision as a
  mechanical invariant instead of a remembered convention.
accept: |
  OPERATOR DECISION (stated 2026-08-02, made in an EARLIER session and never written down):
    * `opencode-zen`  -> **FREE models ONLY**
    * `opencode-go`   -> **specific, VERY CHEAP models only**
  MEASURED 2026-08-02 — the decision is NOT ENFORCED anywhere:
    - `/data/providers.json` supports only `base_url`, `funding_class`, `key_env`, `strip_v1`.
      There is NO allowlist / free-only / model-filter mechanism at the provider layer.
    - `opencode-zen` serves **60 models**, INCLUDING PAID ONES: `opencode-zen/claude-opus-4-1`,
      `opencode-zen/claude-fable-5`, `opencode-zen/claude-haiku-4-5`. Paid Claude models on a
      free-only provider violates the decision AND brushes the standing HARD rule that SG never
      routes via Claude/Anthropic.
    - `opencode-zen` carries NO `funding_class` at all, so it is not even classified; `opencode-go`
      has `funding_class: 2`.
  THE INFORMATION-LOSS SHAPE: this decision survived only in a previous session's memory. Had the
  operator not restated it, the next catalog refresh could have routed paid work through a
  provider intended for free traffic and nothing would have objected. Record the DECISION in the
  repo, not just the enforcement.
  Done contract:
  1. Encode the constraint where pools are built: zen admits ONLY models whose live catalog entry
     says free; go admits ONLY the named cheap set. Catalog is LIVE DATA (doctrine sec.14) — re-read
     free status EVERY cycle, never seed once. Verified today: `minimax-m3-free` BILLED \$0.1542
     despite `-free` in its name, so the NAME is not evidence of free — the catalog field is, and
     even that rots.
  2. Give `opencode-zen` a `funding_class` so it is classified like every other provider.
  3. FAIL LOUD when a model would be admitted that violates the policy — name the model, the
     provider and which half of the policy it breaks. Do not silently drop it: a silent drop makes
     a routing policy indistinguishable from a broken provider.
  4. Fail-on-revert: seed a paid model into the zen pool and prove admission REDs; remove the
     constraint and prove it passes.
  5. Cross-check with `NEVER-ANTHROPIC-ASSERTION` — that ticket forbids Anthropic-served models in
     any TIER CHAIN (all providers); this one constrains what each of these two PROVIDERS may
     serve at all. Related, not duplicate: neither subsumes the other.

## Dependencies & Sequence

P0 — money-path and it touches a HARD rule. No inbound deps. Land alongside
NEVER-ANTHROPIC-ASSERTION (tiny, one test); together they close both the provider-admission and
the chain-selection paths. Feeds the cost work: a provider intended for free traffic that silently
serves paid models makes every cost-per-task number wrong at the source.
