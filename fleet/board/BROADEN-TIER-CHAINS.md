repo: charon-private
tier: strong
difficulty: 2
work_class: routing
branch: feat/broaden-tier-chains
owns: fleet/tier-models.tsv, fleet/tests/test_tier_chain_breadth.sh
depends_on:
note: |
  The tier failover chains (tier-models.tsv) only span 2 providers (nanogpt's model ids + zai's glm-5.2),
  even though the GATEWAY keys 11 providers. So a nanogpt outage COLLAPSES every tier (economy = 100%
  nanogpt). Broaden each tier's chain to fail over ACROSS providers — add cheapest-capable models served by
  the other keyed gateway providers (deepseek, groq, together, openrouter, opencode-zen, mistral) so a
  single-provider outage doesn't kill a tier. Keep cheapest-strongest ordering per tier.
accept: |
  - Each tier chain in tier-models.tsv spans >=3 DISTINCT gateway providers (not just nanogpt+zai); ordering stays cheapest-strongest.
  - Every model id in the chains is served by a provider that is KEYED on the gateway (verify against the gateway provider list; no dead links).
  - fleet/tests/test_tier_chain_breadth.sh asserts >=3 distinct providers per tier + no unkeyed-provider models.
