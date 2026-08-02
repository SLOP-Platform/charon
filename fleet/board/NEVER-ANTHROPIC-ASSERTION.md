repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: feat/never-anthropic-assertion
depends_on:
owns: fleet/tests/never-anthropic-chain.test.sh, docs/review-log/NEVER-ANTHROPIC-ASSERTION.md
serial_justified: |
  One assertion over one file. Nothing to split.
substrate: N/A
substrate-novel: |
  No tool adopted. The rule already exists as doctrine; what is missing is a MECHANICAL check.
  The novel slice is asserting a routing invariant that survives catalog refreshes.
accept: |
  STANDING HARD RULE: SG NEVER routes via Claude/Anthropic. It is on record as a rule that KEEPS
  REGRESSING — which is the definition of a rule that needs a gate rather than a reminder.
  NEW EXPOSURE MEASURED 2026-08-02: the `opencode-zen` provider is LIVE on the gateway and serves
  60 models INCLUDING `opencode-zen/claude-opus-4-1`, `opencode-zen/claude-fable-5`,
  `opencode-zen/claude-haiku-4-5`. No tier chain in fleet/tier-models.tsv contains them TODAY, so
  we are clean — but they are now reachable through a configured provider, which is exactly the
  setup for a silent regression the next time a chain is edited or a catalog refresh reshuffles
  pools.
  Done contract:
  1. Assert that NO tier chain in fleet/tier-models.tsv may contain an Anthropic-SERVED model,
     however it is spelled — match on the resolved provider/model, not on a hardcoded name list.
     A name list rots the moment a provider renames or a new alias appears; the catalog is LIVE
     DATA (doctrine sec.14).
  2. Run it in CI and in preflight, so an edit that introduces one REDs before it can land.
  3. FAIL LOUD naming the offending chain entry and which provider serves it.
  4. Fail-on-revert: seed a chain containing an Anthropic-served model and prove the assertion
     REDs; remove the assertion and prove it passes. Report both verbatim.
  5. Prefer the ASSERTION over an exclusion list at the pool layer — an exclusion list must be
     maintained, an assertion cannot silently stop being true.

## Dependencies & Sequence

P0 by risk-of-silent-regression, tiny by size (one test). No inbound deps. Should land early —
it is cheap, and it converts a doctrine that has already regressed more than once into something
mechanical.
