tier: economy
work_class: bugfix
branch: feat/sr-3-cache-correctness-stats
depends_on:
owns: src/charon/cache.py, tests/test_cache.py
prompt: /home/stack/charon-private/prompts/sr-3.md
scope: W2 (parallel with SR-4/SR-5; disjoint owns from SR-2). Cache correctness (keep exact-SHA-256
  keying) + hit/miss counters surfaced via CLI/status. depends_on EMPTY — board-unblocked.
