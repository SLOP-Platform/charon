Wire the engine's tier into gateway-resolved model selection. Canonical tier for this ticket:
**med** (mapped to fleet `sonnet`). Depends on TIER-2 (merged): tier vids are published as
gateway pools and fail over via the request loop. Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Engine consumption" FIRST, plus
`src/charon/adapters/acp.py` (`AcpBackend.dispatch(unit, tier, …)` lines ~138-160, which
already receives the `Tier` but doesn't use it for model selection) and the observing
`GatewayProxy` base-URL wiring.

GOAL: Wire `dispatch`'s `tier` as the requested model id (the tier vid) into the agent
env/observer so the gateway resolves the tier pool; caps stay keyed on the canonical tier.

DESIGN ANCHORS (cite in your review note):
- `AcpBackend.dispatch` already receives the `Tier` but routes through the observing
  `GatewayProxy` without using it for model selection. Wire the TIER VID (canonical
  `low/med/high` string) as the REQUESTED model id into the agent env / observer base-URL so
  the gateway resolves the tier pool and fails over transparently (multi-provider, OpenAI
  engine path — unlike the fleet's Anthropic `claude -p` path).
- `capacity.FixedCap` caps stay keyed on the SAME canonical `low/med/high` string — ONE tier
  vocabulary across engine caps, gateway pools, and fleet ranking. Do NOT introduce a second
  vocabulary or a translation shim.
- Absent `tiers.json` → gateway has no tier vids; the request should degrade exactly as today
  (no regression for setups without tier config).

BUILD:
1. src/charon/adapters/acp.py — EXTEND `dispatch` (and any helper that builds the agent env /
   observer base-URL) to pass the tier vid as the requested model id. Keep caps keyed on the
   canonical tier. Do NOT edit gateway.py, config.py, or capacity.py — import/consume them.
2. tests/test_acp_tier_route.py — proven-red: `dispatch` sends the tier vid as the requested
   model id to the agent/observer; caps remain keyed on the canonical tier; absent tier config
   → today's behavior (no regression).

CONSTRAINTS: own ONLY the files in your board ticket's `owns:` line
(src/charon/adapters/acp.py, tests/test_acp_tier_route.py) — nothing else. acp.py already
exists: EDIT it. Import gateway/config/capacity; do NOT edit them. Same wave as TIER-4/5/6
(disjoint files). If your work needs a file outside `owns:`, STOP and run release.sh with a
one-line reason. Stdlib-only core. Gate green every commit (pytest, ruff, mypy src/charon,
check_boundary, check_version). No secrets. Conventional commits. Write your review note as
`docs/review-log/TIER-7.md` (NEVER the shared `docs/REVIEW-LOG.md`). Commit ALL work on your
branch and STOP — do NOT push, do NOT open a PR, do NOT run submit.sh; the launcher publishes
after you exit.
