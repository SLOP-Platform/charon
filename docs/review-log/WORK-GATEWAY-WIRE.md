# WORK-GATEWAY-WIRE — forward the gateway credential to the `charon work` agent

## Problem
`charon work --backend acp` built a bare `AcpBackend` via `_acp_passthrough_env()`,
which forwarded only `HOME/PATH/XDG_*` + provider `*_API_KEY`s — never
`CHARON_GATEWAY_TOKEN`. The spawned `opencode acp` reads its standing `charon`
provider apiKey from `{env:CHARON_GATEWAY_TOKEN}`, which resolved empty in the
child → every LLM call `401 missing or invalid bearer token`.

## Decision (operator, gateway-first)
Forward the single standing-gateway credential into the spawned agent's env on the
bare path. The per-run in-process proxy approach is deferred (parked on remote
`feat/work-gateway-wire`) and intentionally NOT pulled in here.

## Implementation
Added `CHARON_GATEWAY_TOKEN` to `_ACP_KEY_PASSTHROUGH` in
`src/charon/ports/agent_launch.py`. Placement is the whole point of the invariant:

- **Bare `charon work` acp path** (`api.py:375`, `_acp_passthrough_env()` default
  `include_keys=True`) — the token IS forwarded; the agent talks to the standing
  Charon gateway it is configured for and legitimately needs that bearer.
- **Renderer / per-run-proxy path** (`include_keys=False`, `OpencodeRenderer`) —
  the token is excluded with the provider keys; the proxy supplies its own
  credential, so the standing token must not bleed in (D4-aligned).
- Forwarded **only when set** — the dict-comp in `_acp_passthrough_env` skips
  absent vars, so no empty/placeholder value is ever injected.
- The fence whitelist (`fence.py` `_ENV_ALLOW`) is **untouched**: the credential
  rides `passthrough_env`, merged over the scrubbed env at `adapters/acp.py:72`,
  not a fence hole.

Agent-agnostic: only an env var is forwarded; no opencode specifics added.

## Tests (`tests/test_agent_launch_routing.py`)
- `test_bare_path_forwards_gateway_token_when_set` — present on `include_keys=True`.
- `test_bare_path_omits_gateway_token_when_unset` — absent when unset (no placeholder).
- `test_bare_path_forwards_only_the_gateway_token_no_general_hole` — security guard:
  `SECRET_*` / arbitrary vars stay absent; only the gateway token crosses.
- `test_renderer_path_does_not_force_forward_gateway_token` — proxy path excludes it
  (mirrors `test_agent_launch_pins_vid_at_the_seam_and_excludes_keys`).
- Existing seam/fence secret-leak tests stay GREEN unchanged.
