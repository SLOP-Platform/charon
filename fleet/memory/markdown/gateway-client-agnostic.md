---
description: "Charon Gateway (SG) is CLIENT-agnostic — any OpenAI-compatible client points at it; never hardcode a client. opencode CLI is a fine swappable client; only opencode-Zen/Go the PROVIDER shouldn't be default"
metadata: 
name: gateway-client-agnostic
node_type: memory
originSessionId: fffc7f6f-75c2-4588-b70e-1d3885da5281
type: project
tags: [charon, gate, gateway]
last_referenced: 2026-07-13
---
Operator clarification (2026-07-12), resolving a recurring confusion:

- **"opencode not default" meant the PROVIDER** — OpenCode Zen / Go (`opencode-go`/`opencode-zen`), not the opencode CLI. That provider should not be a default (and is the dead `401` in the deepseek pool — see the exhaustion incident).
- **opencode CLI is just a client** the operator currently uses; it must NOT be hardcoded. Next week could be OhMyPie or anything else.
- **SG (Charon Gateway) is client-agnostic**: an OpenAI-compatible endpoint any client points at. SG never needs to know which client/UI is in use. The client→gateway coupling lives on the client side (client config points at the gateway), never in SG.
- Manager = Claude only. Fleet WORK runs OFF Claude via an agnostic client → the gateway, which does cheapest-usage-provider-first routing with roll-to-next-on-exhaust ([[route-work-to-charon-not-claude]], [[charon-vision-gateway-first]], [[charon-modular-agent-and-provider-agnostic]]).

**Consequence for the rig:** `fleet-droid.sh` currently runs `claude -p --model opus/sonnet/haiku` with no `ANTHROPIC_BASE_URL` → hits Anthropic directly = burns Claude tokens (a leak). `fleet/charon-run.sh` (opencode-CLI → `--model charon/*` → gateway, "zero Claude limit") is the correct off-Claude shape. Fix: droid executes through the gateway via a SWAPPABLE client (e.g. `CHARON_AGENT_CMD`, default = current opencode CLI), never `claude -p` to Anthropic.
