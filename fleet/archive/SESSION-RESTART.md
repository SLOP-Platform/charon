# Charon Session Restart — 2026-07-01

## One-line bootstrap
Read `/home/stack/charon-private/fleet/HANDOFF-CONTINUE.md`, read `/home/stack/code/charon/AGENTS.md`, run `bash /home/stack/charon-private/fleet/status.sh` and `bash /home/stack/charon-private/fleet/validate_board.sh`, register on the session bridge as `worker`, then tell the operator the state and next action.

## State snapshot
- **Branch:** `feat/global-fallback-provider` (all work accumulated here)
- **PR:** #78 open — 873 passed, all gates clean, ready for operator merge
- **Gateway:** 10.0.1.60:8080 — all 49 models have zen→go failover
- **Session model:** deepseek-v4-pro via opencode-zen → opencode-go failover

## What was built (15+ tickets, 873 tests)
- CONSOLE-PROVIDER-MGMT, OBS-CAPTURE, CLIENT-CONNECT-GUI, ADR-0015
- Routing proxy (routing_proxy.py), FALLBACK-PROVIDER, OBS-UI, WCI-MVP
- CWD-CONFIG (cwd opencode.json renderer — UNBLOCKED ORCH-ROUTE)
- DTC-1 through DTC-8 (gate registry, shared fixtures, meta-tests, charon-gate, arch checker, parametrize, security scanner, test patterns)
- CONNECT-OMP-WSL, SETUP-KEY-UX, PUBLIC-CLEAN-LINT, DOGFOOD
- AGENTS.md Rules 5-8 + session-bridge heartbeat rules

## Key findings
- **CWD opencode.json WORKS** with opencode 1.17.11 acp — confirmed 2026-07-01 (2 proxy hits). Previous tests had bugs (bogus session ID, missing model key).
- **ORCH-ROUTE is now UNBLOCKED** by CWD-CONFIG — can build immediately.
- opencode issue #34638 updated with cwd workaround.

## What's next (in priority order)
1. **ORCH-ROUTE** — build the orchestrator proxy path now that cwd config works. Ticket at `board/ORCH-ROUTE.md`. Owns `api.py`, `agent_launch.py`, `test_agent_launch_routing.py`. The routing_proxy is already built.
2. **WCI-FOLLOWON** — ready, depends on WCI (in PR #78).
3. **Parked tickets:** ACCESS-MODES, ATC, CWD-CONFIG-VERIFY (obsolete), ~10 design-required.

## Useful commands
```
bash /home/stack/charon-private/fleet/status.sh
bash /home/stack/charon-private/fleet/validate_board.sh
gh pr view 78 --repo SLOP-Platform/charon
```
