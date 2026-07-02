# ORCH-ROUTE — route `charon work` through a per-run in-process proxy (orchestrator mode)

## Dependencies & sequence
**depends_on: CWD-CONFIG — Wave 1 (after CWD-CONFIG lands).** CWD-CONFIG changes the renderer
to write per-run `opencode.json` in cwd instead of the (non-honored) `OPENCODE_CONFIG_CONTENT`
env var. This ticket builds orchestrator mode on top of that fixed renderer.

Owns `api.py` + `ports/agent_launch.py` (+ test). CWD-CONFIG owns `agent_launch.py` —
`depends_on: CWD-CONFIG` orders them correctly (CWD-CONFIG runs first, modifies the renderer;
ORCH-ROUTE builds the orchestrator path on top). No other backlog ticket owns these files.
Safe to run after CWD-CONFIG lands.

## STEP 0 — RESOLVED 2026-06-30
Empirical test (see `docs/review-log/ORCH-ROUTE-STEP-0.md` + 2026-06-30 follow-up):

- `OPENCODE_CONFIG_CONTENT` env var is **NOT honored** by opencode 1.17.11 `acp` mode ✓
- **cwd `opencode.json` IS honored** — custom provider resolved, API calls routed through
  test listener ✓

**Verdict: per-run-proxy routing is viable via cwd `opencode.json`.** CWD-CONFIG implements
this injection mechanism in the renderer. Once it lands, the renderer produces an
`AgentLaunch` whose cwd `opencode.json` points the agent at the per-run proxy.

## Why
WORK-GATEWAY-WIRE shipped the gateway-first path: `charon work` forwards `CHARON_GATEWAY_TOKEN` so
the agent uses the standing gateway. The ORCHESTRATOR-mode alternative — `charon work` standing up
its OWN per-run in-process `GatewayProxyServer` (with an observer) and pointing the agent at it via
the renderer's injected cwd `opencode.json` — gives per-run isolation + in-path telemetry
(the observer records the calls). The plumbing for this (proxy + renderer + `proxy_token` threading)
is already built and PARKED on remote branch `origin/feat/work-gateway-wire` (it was correct but
sat on a code path `charon work` didn't use).

## What to build
Make `charon work`'s acp path build the per-run proxy + renderer path (cherry-pick/adapt the parked
plumbing): stand up a token-gated `GatewayProxyServer`, mint its token, thread it via
`render(..., proxy_token=server.token)` so the agent authenticates to the in-process proxy and its
observer captures telemetry. Gate behind an explicit `--proxy`/orchestrator flag so the default
stays the gateway-first path (WGW). NEVER on the gateway hot path.

The renderer (CWD-CONFIG) already writes per-run `opencode.json` to cwd — this ticket plumbs the
proxy URL and token into that file's provider config.

## Acceptance
- CWD-CONFIG landed (renderer writes cwd `opencode.json`).
- With the orchestrator flag, a `charon work` run routes the agent through the in-process proxy (its
  observer records ≥1 call); without the flag, behavior is exactly WGW (standing gateway). Test at
  the seam (mock the proxy/observer). No secrets leaked.

## CONSTRAINTS
Likely owns: `src/charon/api.py`, `src/charon/ports/agent_launch.py`, `tests/test_agent_launch_routing.py`
(reuse the parked branch's diffs). Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/ORCH-ROUTE.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked). Branch `feat/orch-route`. Parked plumbing reference: `origin/feat/work-gateway-wire`.
