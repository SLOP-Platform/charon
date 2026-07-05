tier: economy
branch: feat/sr-4-smart-routing-doc-fix
depends_on:
owns: /home/stack/charon-private/fleet/SMART-ROUTING.md
prompt: /home/stack/charon-private/prompts/sr-4.md
scope: W2 (parallel with SR-3/SR-5). DOC-ONLY — corrects SMART-ROUTING.md §1/§5 to stop claiming
  SpeculativeExecutor + ConsensusRouter fire in _handle() (they are constructed, never invoked).
  Touches NO product code; owns a fleet doc, disjoint from all other SR tickets. depends_on EMPTY.
