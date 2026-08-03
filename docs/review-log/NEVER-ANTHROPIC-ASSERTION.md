# NEVER-ANTHROPIC-ASSERTION — review/decision log

## Decision: assertion over name-list

The ticket explicitly rejects a hardcoded name list (`claude|opus|sonnet|haiku|fable|anthropic`) as
the enforcement mechanism, because a name list rots. The existing `fleet/checks/no-anthropic-in-sg.sh`
already implements the name-list approach — it is NOT replaced by this assertion; it remains as a
backstop for the "do not put Claude model names in the chain" pattern check.

The assertion is implemented as **provider-resolved**: each model id in each tier chain is resolved
against the live gateway catalog to find its serving provider; if the provider name contains
"anthropic" or "claude", the assertion fails. This survives:
- Catalog refreshes that add new models under existing Anthropic providers
- New aliases for existing Anthropic models
- Provider renames

## Decision: stubbed gateway probe (RESOLVE_PROVIDER_CMD seam)

The live gateway probe (`GET /charon/config`) requires network access and a valid token. For CI
hermeticity, the test exposes `RESOLVE_PROVIDER_CMD` as a shell-command override — the test injects
a stub that simulates provider resolution. This is the same pattern as `LPF_PROBE_CMD` in
`leg-preflight.test.sh` and `CHARON_TIER_RANKS_CMD` in `tier-drift.test.sh`.

## Decision: no edit to validate_board.sh or preflight.sh

The ticket says "run it in CI and in preflight." The gate check (`fleet/checks/no-anthropic-in-sg.sh`)
already exists. Rather than adding a new check to validate_board.sh (which would require edits
outside the ticket's `owns:`), the CI gate is satisfied by this test suite, which runs as part of
`py.test` / `bash fleet/tests/*.test.sh` in the CI pipeline. The preflight wiring is a separate
operator step.

## Fail-on-revert seed case

The test seeds `opencode-zen/claude-opus-4-1` (the live Anthropic model on the opencode-zen provider
that appeared 2026-08-02) into the synthetic strong chain. The stub resolves it to
"anthropic-opencode-zen", triggering a RED. Removing the model from the chain makes it GREEN.
