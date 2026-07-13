---
description: The fleet build-rig lives at /build-rig (NOT ~/code) — always use the ABSOLUTE path for HANDOFF/board/scripts
metadata: 
name: fleet-rig-absolute-path
node_type: memory
originSessionId: 6a15dd76-f504-4a39-bf2c-48d8ef5bf755
type: reference
tags: [build-rig, fleet]
last_referenced: 2026-07-13
---
The Charon build-fleet rig — `HANDOFF.md`, `WORKFLOW.md`, `status.sh`/`board.sh`, `board/`, `prompts/`, `DESIGN-QUEUE.md` — lives at **`/build-rig/fleet/`**, i.e. under `~`, **NOT** under `~/code`.

The manager session's working dir is `/repo/charon` (the product repo). So a RELATIVE reference like `build-rig/fleet/HANDOFF.md` resolves to the wrong place (`/repo/charon/build-rig/...`, which doesn't exist) and a fresh session can't find the handoff.

**Always reference the rig by its absolute path**: `/build-rig/fleet/HANDOFF.md`. The bootstrap/new-session one-liner ([[manager-gives-new-session-prompt]]) MUST use the absolute path. The rig is build-infra only and does not ship ([[product-vs-build-rig-boundary]]).
