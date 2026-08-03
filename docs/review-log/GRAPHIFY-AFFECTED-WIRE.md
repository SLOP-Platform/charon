# GRAPHIFY-AFFECTED-WIRE review log

## Decision: call site is `fleet/reuse-check.sh`, not `fleet/preflight.sh`

Explicitly NOT wiring into preflight.sh despite it being the obvious-looking home.
Eight live tickets already co-own preflight.sh (PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, MARKER-PROOF-MECHANIZE, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE, GATE-INTEGRITY-C, WCI-DEC-FLEET-PREFLIGHT-SH). Claiming it would create 8 merge-order edges making the ticket unclaimable.

fleet/reuse-check.sh is the better fit on merit: TOOL-INVENTORY.md:14 already pairs graphify and reuse-check as the tool-first trigger. The inventory says these belong together. Reuse-check answers "does this already exist?"; blast-radius answers "what does touching it affect?" — two halves of one question asked at the same instant.

Post-PREFLIGHT-GATE-REGISTRY, a one-line preflight row for the same check is a trivial follow-up. That is a strictly better sequence than blocking on it now.

## Design decisions

1. **Read-only**: blast-radius.sh never calls `graphify update`. Freshness is graphify-freshness.sh's job. Duplicating freshness logic here would fork the contract.

2. **Inline Python over helper script**: the original design had a `_blast_radius_py.sh` helper. Simplified to inline Python in a heredoc — fewer files, same behavior.

3. **Three distinct failure modes** (NO_CONNECTIONS / NODE_NOT_FOUND / GRAPH_READ_ERROR) ensure "no answer" and "no impact" are always distinguishable. A tool that says nothing when it knows nothing is how a wired check silently becomes inert.

4. **BLAST_RADIUS=0 env opt-out** preserves the hermetic case: a session that cannot access the graph gets silence, not a confusing skip message that implies failure.

## Test design

The test (26 assertions, all hermetic) uses `run_blast()` helper to run blast-radius.sh against a fixture graph in a single subshell, avoiding the `BLAST_GRAPH=... && bash` subshell-scoping bug where the env var is lost to a nested command substitution.

The R1 revert test creates a reverted reuse-check.sh that emits the same banner text but no real blast-radius output, proving the call-site goes silent after revert.

## Scope check

git diff confirmed only:
- fleet/checks/blast-radius.sh (NEW)
- fleet/reuse-check.sh (modified)
- fleet/tests/blast-radius.test.sh (NEW)
- fleet/TOOL-INVENTORY.md (modified)
- docs/review-log/GRAPHIFY-AFFECTED-WIRE.md (NEW)

No touch of preflight.sh, graphify-freshness.sh, or registry-discovery.sh.
