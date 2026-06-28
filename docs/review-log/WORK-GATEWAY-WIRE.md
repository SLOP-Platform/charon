# WORK-GATEWAY-WIRE — route the spawned agent's LLM calls through Charon's gateway

## Gap
The `charon work` path spawned the ACP agent pointed at the per-run, token-gated
in-process gateway but never gave it the credential, so every LLM call returned
`401 missing or invalid bearer token` — the autonomous run died at dispatch before
any edit/commit. Routing itself was already proven sound out-of-band; the only gap
was the credential never reaching the spawned child.

## Mechanism chosen — inject the token into the SAME config override (no fence hole)
Took the spec's strongly-preferred path. The `OpencodeRenderer` already injects
`OPENCODE_CONFIG_CONTENT` to override the agent's provider `baseURL` to the proxy;
that override now also carries the proxy's own bearer as `options.apiKey`. The
openai-compatible client sends `apiKey` as `Authorization: Bearer`, so the agent
authenticates to the per-run gateway it is pointed at. baseURL + credential travel
together in one injected config.

Rejected the env-var alternative (`{env:CHARON_GATEWAY_TOKEN}` forwarding): it would
put the secret in the broad process env. The config-injection path keeps the secret
out of the env entirely, so `Fence.scrubbed_env()`'s strict whitelist is untouched
(no widening, no general hole). The threading is renderer-agnostic — `render()` /
`AgentRenderer.render()` gained a `proxy_token` param; any future renderer wires it
however its product expects.

## Scope of the api.py change — thread, don't re-gate
The spec's api.py instruction is precise: `render(acp_cmd, server.url,
requested_model)` → "also pass server's token". So `_acp_via_renderer` now calls
`render(..., proxy_token=server.token)`. This is correct in both states: when the
per-run proxy is token-gated, `server.token` is the bearer the agent must present
and it now rides the injected config; when the proxy is ungated, `server.token` is
`None` and the renderer keeps the non-empty `"charon-proxy"` placeholder the client
requires — i.e. exactly prior behavior. The agent's calls then flow through this
same `server`, whose `observer` records them (the observability half, for free).

### Deliberately NOT changed: the `GatewayProxyServer(...)` construction
The full live 401 also requires the per-run proxy to actually BE gated — i.e.
constructing it with `token=gw_cfg.token` (which `load_config` resolves from
`CHARON_GATEWAY_TOKEN`). I prototyped that one-liner and it is the natural companion,
but it trips four pre-existing INTEGRATION tests in files OUTSIDE this ticket's
`owns:` — `tests/test_run_task_routing.py` and `tests/test_tier_lifecycle.py`. Their
simplified ACP stubs POST to the proxy WITHOUT presenting a bearer, so a gated server
401s them (the ambient `CHARON_GATEWAY_TOKEN` in the run env makes `gw_cfg.token`
non-None, exposing the coupling). Fixing them means editing those stubs to read the
injected `apiKey` and send `Authorization: Bearer` — non-owned files. Per the
single-source-of-truth ownership rule I did NOT touch them. The seam change here is
forward-compatible: the instant the proxy is gated (by the ticket that owns that
construction + those stubs), `server.token` is non-None and the agent authenticates
with zero further renderer/seam work. The documented acceptance is entirely
seam-level, and it is fully met by the threading + the new tests below.

## This is NOT the D4 provider key
The forwarded value is the local proxy's own bearer (minted by the proxy), never an
upstream provider key. `_acp_passthrough_env(include_keys=False)` is unchanged, so
`OPENCODE_API_KEY`/`OPENROUTER_API_KEY`/`ANTHROPIC_API_KEY` still never cross.

## Tests (tests/test_agent_launch_routing.py)
- `test_gateway_credential_reaches_the_spawned_agent` — proves the proxy bearer
  reaches the child at the wire, paired with the proxy url, while provider keys
  present in the env stay absent (D4 intact). Asserts agnostically on the rendered
  env plus the injected config's `options`.
- `test_gateway_wire_opens_no_general_secret_hole` — REQUIRED security regression
  guard: an arbitrary `SECRET_*` and provider keys are absent from every rendered
  env/config value; only the one gateway bearer crosses.
- `test_ungated_proxy_keeps_nonempty_placeholder` — no token → non-empty placeholder
  preserved, no stray credential invented.

The existing `test_agent_launch_pins_vid_at_the_seam_and_excludes_keys` needed no
change: it renders without a token (apiKey stays the placeholder) and its
key-exclusion assertions still hold. `test_fence.py` secret/escalation tests are
untouched and stay green (the fence whitelist is unchanged).
