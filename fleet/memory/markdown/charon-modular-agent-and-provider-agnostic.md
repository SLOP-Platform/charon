---
description: Hard design constraint — Charon must stay modular; the engine is NOT hardcoded to any one agent (e.g. opencode) or LLM provider
metadata: 
name: charon-modular-agent-and-provider-agnostic
node_type: memory
originSessionId: dbc15100-af3f-415f-ae56-66e13a77d57e
type: project
tags: [charon, modularity, provider]
last_referenced: 2026-07-13
---
HARD DESIGN CONSTRAINT (operator, restated 2026-06-27 after a near-miss): Charon must be as
modular as reasonably possible. The production work-engine must NOT be hardcoded to a specific
agent product (e.g. opencode) or a specific LLM provider. It must drive ANY compatible agent the
Charon user prefers — Windows GUI apps AND terminal apps — and ANY provider, as long as it's
compatible with Charon. Same for LLM providers.

**Near-miss that triggered this:** the TIER-7 (engine tier routing) review recommended wiring the
tier vid into `OPENCODE_CONFIG_CONTENT.model` in api.py — i.e. coupling tier resolution to
opencode specifically. WRONG. The agnostic path: the agent points at Charon's OpenAI-compatible
gateway and requests the TIER VID as the model id; the gateway resolves tier -> pool -> provider
failover. Agent selection belongs behind an agent-adapter abstraction, not a hardcoded product.

**How to apply:** any routing/selection/integration design must be checked against "does this lock
Charon to one agent or one provider?" If yes, redesign behind an abstraction. Reinforces
[[charon-production-readiness-mindset]], [[product-vs-build-rig-boundary]],
[[charon-vision-gateway-first]].
