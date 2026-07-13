# PINNED CORE — always-on directives loaded at every session start.
# These are the critical facts that every manager session needs at startup.
# Pull-on-demand: use `memory.search <query>` for anything not listed here.

## Build methodology
- Build Charon via the fleet rig: `fleet-droid.sh <tier> --wait 3 --retries 10`
- Autonomous tier-by-tier building with adversarial review/DTC gating every decision
- Do NOT revert to bare `claude --bg` — route sub-work to Charon (opencode→self-hosted-runner)

## Key standing facts
- Charon gateway is at http://<COORDINATOR_HOST>:8080 (NOT localhost)
- Fleet rig lives at /build-rig (absolute path)
- Public repos (charon/mediastack) — never commit tokens/IPs/hostnames/paths
- Gate green proves nothing unless it EXECUTED — verify N checks ran
- Deploy drift pattern: config/secrets/state → /data volume (SR-10 D024)
- Session-bridge: register on board (repo:charon), heartbeat via board() < 600s TTL
- Product vs build-rig boundary: Charon ships standalone; rig never ships

## Recurring failure patterns
- Catalog/routing/config mismatches → always fix on sight
- Pre-existing reds → investigate+fix, never dismiss as "unrelated"
- Silent downgrade → model-id normalization via rsplit(final segment)
- Green-is-not-proof → verify the gate actually ran, not just CI color
- Model self-report lies → log false claims, verify branch diff, never trust SUCCESS line

## Retrieve on demand
For everything else, use `memory.search` — facts arrive salient at point of need.
