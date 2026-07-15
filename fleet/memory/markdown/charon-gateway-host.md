---
description: "Charon gateway runs at http://<COORDINATOR_HOST>:8080 (the .60 box), NOT localhost — stop probing 127.0.0.1:8080"
metadata: 
name: charon-gateway-host
node_type: memory
originSessionId: e2478a55-c53f-48cc-9378-5c328f54aa8f
type: reference
tags: [charon, gate, gateway]
last_referenced: 2026-07-13
---
The running Charon gateway is at **http://<COORDINATOR_HOST>:8080** (deployed on the `.60` box; login/UI at `/charon/login`). It is **NOT** on `localhost:8080` in the manager session.

**Recurring waste:** nearly every session a manager reflexively `curl`s `127.0.0.1:8080` to "check if the gateway is up", gets nothing, and wrongly concludes it's down. It's just the wrong host. Probe `http://<COORDINATOR_HOST>:8080` instead. opencode reaches Charon via its own configured socket-proxy (`~/.config/opencode/charon/`), not that TCP port — so a dead localhost curl says nothing about whether CG jobs work.

Related: [[charon-deploy-drift-lessons]], [[charon-headless-review-loop]].
