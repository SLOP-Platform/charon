repo: charon
tier: economy
priority: 2
difficulty: 2
work_class: greenfield-feature
branch: feat/ft-catalog-seed
depends_on:
owns: src/charon/provider_presets/hosted.py, src/charon/routing_policy/free_tier_catalog.py, tests/test_free_tier_catalog.py
accept: |
  The product cannot read the build-rig FREE-TIER-LIMITS.tsv (product/rig boundary), so it needs its
  OWN shipped seed of known free-tier limits + presets for the free providers it doesn't know yet.
  DO:
  - src/charon/provider_presets/hosted.py: add presets for three free/cheap NON-Anthropic providers:
    GitHub Models (base https://models.inference.ai.azure.com, key_env GITHUB_TOKEN), Featherless.ai
    (its OpenAI-compatible base + key_env; note 32K session-context cap in the preset comment), and
    Ollama.com cloud/turbo free tier (its hosted base + key_env — DISTINCT from the existing LOCAL
    ollama preset; do not touch the local one). OpenAI-compatible shape, matching sibling presets.
  - src/charon/routing_policy/free_tier_catalog.py (NEW): a stdlib data module mapping provider -> known
    free_tier limits in the SAME normalized shape FT-CONFIG-SURFACE emits (rpm/rpd/tpm/tpd/weekly/monthly
    + reset kind). Seed the verified numbers: groq 8B rpd=14400/rpm=30/tpm=6000, openrouter :free
    rpd=1000/rpm=20, cerebras tpd=1_000_000/rpm=5, mistral monthly≈1e9, plus GitHub Models / Featherless /
    Ollama.com placeholders flagged `verified=False` until PRICING-LIMITS-CHECKER confirms them. This is a
    SEED/default source only — the live authority is config (FT-CONFIG-SURFACE) + refresh
    (PRICING-LIMITS-CHECKER); the catalog fills gaps for a leg with no explicit config.
  - Every entry NON-Anthropic (sg-never-anthropic). Mark personal-only free tiers `personal_only=True`.
  FAIL-ON-REVERT (tests/test_free_tier_catalog.py, new): the three new presets are importable/parse; the
  catalog returns groq's 14400 rpd and mistral's monthly cap in the normalized shape; an unknown provider
  returns None (no limits). Revert a preset/seed row → its test fails.
