repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: feat/sr-5-pricing-cost-visibility
depends_on:
owns: src/charon/config.py, src/charon/discover.py, src/charon/providers.py
prompt: /home/stack/charon-private/prompts/sr-5.md
scope: W2 (parallel with SR-3/SR-4; disjoint owns from SR-2). Capture pricing on discovered/imported
  models + configurable per-token fallback so usage.cost_usd stops reading 0.0; surface
  unknown-pricing models in status. depends_on EMPTY — board-unblocked. Prereq for SR-7.
