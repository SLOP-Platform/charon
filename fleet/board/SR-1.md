tier: strong
branch: feat/sr-1-namespace-downgrade-fix
depends_on:
owns: src/charon/proxy.py, tests/test_proxy_downgrade.py
prompt: /home/stack/charon-private/prompts/sr-1.md
scope: P0 — fix the namespaced-id false-downgrade double-bill. Ships ALONE as Wave 1 (W1) ahead of
  everything else; the whole SR series builds on this classify() correction. depends_on EMPTY —
  board-unblocked, no disjoint-owns dep to justify.
