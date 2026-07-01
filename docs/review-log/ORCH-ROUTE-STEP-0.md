# ORCH-ROUTE — Step 0 verification report

**Date:** 2026-06-29
**Ticket:** ORCH-ROUTE (feat/orch-route)

## Step 0 result: NOT HONORED

opencode 1.17.11 `acp` mode does **not** honor the `OPENCODE_CONFIG_CONTENT`
override. A test proxy on a random loopback port received **zero** requests
when opencode acp was launched with `OPENCODE_CONFIG_CONTENT` pointing at it.

Test methodology:
1. Started a tiny TCP-to-HTTP proxy on a random loopback port
2. Set `OPENCODE_CONFIG_CONTENT` to a config with a `charon_probe` provider
   pointing at the proxy
3. Launched `opencode acp`, completed initialize → session/new → session/prompt
4. Counted inbound requests on the proxy socket — **0**

## Impact

The per-run-proxy approach (stand up an in-process `GatewayProxyServer` and
point the agent at it via `OPENCODE_CONFIG_CONTENT`) is **not viable** for
opencode's ACP mode. The override that works for `opencode` (interactive/CLI)
is not consumed by the ACP subprocess.

## Recommended path forward

Per the ORCH-ROUTE prompt:
> If the override is NOT honored in acp mode, STOP and report — the per-run-proxy
> approach is not viable for opencode and this ticket needs a redesign (note findings).

Options:
1. **Redesign ORCH-ROUTE:** use a different mechanism to route ACP agent calls
   through an observer proxy — e.g., inject the config via environment variables
   the opencode ACP reads, or use a different model-provider override path.
2. **Use a different ACP backend:** `omp acp` (oh-my-pi) supports custom
   providers in its config file — may honor the file-based config in ACP mode.
   This would require CHARON-ACP-BACKEND abstraction (already noted in OHMYPI-ASSESS).
3. **Drop the per-run-proxy approach** and stick with the gateway-first model.

## Ticket status

ORCH-ROUTE is **blocked on redesign** until the operator chooses a path.
