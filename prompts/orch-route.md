# ORCH-ROUTE — route `charon work` through a per-run in-process proxy (orchestrator mode)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `api.py` + `ports/agent_launch.py` (+ test). DISJOINT from every
other backlog ticket → safe to run CONCURRENTLY with all Wave-1 tickets. A fresh Charon can claim it
immediately. NOTE: Step 0 (verify opencode honors the config override) must pass before the build
proceeds — that's an in-ticket gate, not a cross-ticket dependency.

## Why
WORK-GATEWAY-WIRE shipped the gateway-first path: `charon work` forwards `CHARON_GATEWAY_TOKEN` so
the agent uses the standing gateway. The ORCHESTRATOR-mode alternative — `charon work` standing up
its OWN per-run in-process `GatewayProxyServer` (with an observer) and pointing the agent at it via
the renderer's injected `OPENCODE_CONFIG_CONTENT` — gives per-run isolation + in-path telemetry
(the observer records the calls). The plumbing for this (proxy + renderer + `proxy_token` threading)
is already built and PARKED on remote branch `origin/feat/work-gateway-wire` (it was correct but
sat on a code path `charon work` didn't use).

## STEP 0 — resolve the open question FIRST (do not skip)
The 2026-06-27 diagnostic could NOT confirm that `opencode acp` honors the injected
`OPENCODE_CONFIG_CONTENT` override (baseURL→in-process proxy) over its on-disk `opencode.json`.
Verify empirically: stand up a tiny in-process proxy, set `OPENCODE_CONFIG_CONTENT` to point at it,
run `opencode acp`, and confirm the call hits the in-process proxy (its counter moves), NOT the
on-disk-config gateway. **If the override is NOT honored in acp mode, STOP and report** — the
per-run-proxy approach is not viable for opencode and this ticket needs a redesign (note findings).

## What to build (only if Step 0 confirms the override works)
Make `charon work`'s acp path build the per-run proxy + renderer path (cherry-pick/adapt the parked
plumbing): stand up a token-gated `GatewayProxyServer`, mint its token, thread it via
`render(..., proxy_token=server.token)` so the agent authenticates to the in-process proxy and its
observer captures telemetry. Gate behind an explicit `--proxy`/orchestrator flag so the default
stays the gateway-first path (WGW). NEVER on the gateway hot path.

## Acceptance
- Step 0 finding recorded in the review-log.
- With the orchestrator flag, a `charon work` run routes the agent through the in-process proxy (its
  observer records ≥1 call); without the flag, behavior is exactly WGW (standing gateway). Test at
  the seam (mock the proxy/observer). No secrets leaked.

## CONSTRAINTS
Likely owns: `src/charon/api.py`, `src/charon/ports/agent_launch.py`, `tests/test_agent_launch_routing.py`
(reuse the parked branch's diffs). Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/ORCH-ROUTE.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked). Branch `feat/orch-route`. Parked plumbing reference: `origin/feat/work-gateway-wire`.
