tier: economy
difficulty: 3
work_class: ci-infra
branch: feat/fn1-memory-store
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/memory/
accept: |
  ADOPT basic-memory (MCP-native, markdown = source of truth, local FastEmbed semantic + full-text) pointed at
  the existing manager `memory/` dir. Compose per fleet/state/MEMORY-DESIGN.md (borrow-not-build).
  - Kill the wholesale SessionStart memory dump; load only a small PINNED core + pull-on-demand via a
    `memory.search` MCP tool, so facts arrive salient AT POINT OF NEED (this is what failed on the merge method).
  - Migrate the ~50 markdown files as-is (add light frontmatter: tags + last_referenced).
  FAIL-ON-REVERT: a test asserts (a) the SessionStart hook no longer cats the full memory set, and (b) `memory.search`
  returns a known fact that is NOT in the pinned core. Revert either → red.
  GREEN-IS-NOT-PROOF: demonstrate real point-of-need retrieval of a fact absent from the pinned core.
scope: Rig-only (manager/session memory). basic-memory is AGPL-3.0 — fine for the internal rig; txtai/MIT is the
  documented swap IF this is ever productized. Store + retrieval is largely solved by basic-memory; the real work is
  the migration + killing the dump.
ds: Now (rig-only). FN2 + FN3 depend on this store existing. Owns a NEW `fleet/memory/` dir → no owns-collision.
