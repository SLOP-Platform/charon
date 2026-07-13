---
description: "replacing the fragile local session-bridge with a durable, push-notify, cross-host coordinator on a neutral box"
metadata: 
name: durable-bridge-rework
node_type: memory
originSessionId: fbcc2b18-3ba9-4057-b3fd-af8c3e6ffb84
type: project
tags: [bridge, session]
last_referenced: 2026-07-13
---
**Goal (operator-driven, 2026-07-06):** the current session-bridge is too fragile — 600s TTL + model-driven heartbeats mean sessions silently expire; it's also pull-only (no notify) and LOCAL-ONLY (AF_UNIX socket + local SQLite). Replace with a **durable, cross-host, push-notify** coordinator.

**Decisions so far:**
- Neutral dedicated **coordinator box = Rocinante (.51), LOCKED** (operator-approved 2026-07-06). Verified an OLD superseded SLOP box, safe to repurpose after backup (see [[rocinante-is-live-slop-prod]]). Decommission sequence approved; config backup underway; komodo/periphery root-check pending (operator).
- Transport leaning SSH-tunnel-to-coordinator; design keeps `$COORDINATOR_HOST` symbolic (real IP only in gitignored `~/.charon/bridge-hosts.env`; public-repo guard). See [[public-repo-no-personal-info]].
- Naming convention enshrined: Charon sessions = **Jedi** names, SLOP = **droid** names, **Grand Master** names (yoda/luke-skywalker/satele-shan) RESERVED for the manager (edit staged in `~/.config/opencode/session-bridge/SESSION.md`, to land with the rework).

**Design iterated v1→v2→v3, each adversarially reviewed:** v1 REWORK → v2 REWORK → v3 SHIP-WITH-FIXES → all closed. Authoritative spec `fleet/DURABLE-BRIDGE-DESIGN-v3.md`. Final model: lease (no PID), allowlist redaction chokepoint (`lease_token` never serialized to peers), persisted per-recipient `seq`, at-least-once ack + `idempotency.py` ledger, per-repo isolation.

**DEPLOYED 2026-07-07 (Phase 0-1 DONE):**
- Product-repo guard on charon master: `1c54ef4` (wire public-clean into gate/CI + populate exceptions) + `cfa3159` (content-keyed fail-safe exceptions) — keeps the coordinator IP out of public commits; gate 6/6 + 1246 pytest + CI green.
- Coordinator LIVE on Roci: systemd daemons `charon-bridge-{charon,mediastack}` (per-repo socket `/run/charon-bridge/*.sock` + DB `/var/lib/charon-bridge/*.db`, Restart=always) from `/opt/charon-bridge/daemon.py`.
- Client tunnel `~/.charon/coordinator-tunnel.sh` (self-healing via `~/.charon/ensure-coordinator-tunnel.sh` hooked into `.bashrc`/`.profile`) → `~/.charon/coordinator-charon.sock`. Real host in uncommitted `~/.charon/bridge-hosts.env`.
- Cutover STAGED: `opencode.json` `BRIDGE_HOST=rocinante` — takes effect on NEXT opencode restart; current sessions unaffected. Cross-host path verified end-to-end. Residual: WSL doesn't auto-start on Windows boot (tunnel returns on first shell after WSL starts).

**Phase 2/3 DEFERRED** → brief `fleet/DURABLE-BRIDGE-PHASE-2-BRIEF.md` (NB3 renewer immortalizes a crashed session's lease, 120s auto-ack loss window, non-destructive nudge reads on restart, wire `idempotency.py`, `status` RPC + `bridge-status` CLI + kill-switch, AGENTS.md G3). **benchmark-v2 SHIPPED** (fleet `f42ea99`/`a4ea41f`).
