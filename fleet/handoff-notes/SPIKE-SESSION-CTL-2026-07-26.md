# SPIKE REPORT — opencode HTTP control plane (2026-07-26)

**Session:** jaden-korr (deepseek-v4-flash via charon) · **Branch:** spike/session-ctl

## Verb results

| Verb | Status | Evidence |
|------|--------|----------|
| **SEE** | **VERIFIED** | `GET /api/session` returned 30+ global sessions with titles, cost, tokens, model. Global store works. |
| **STEER** | **VERIFIED** | `POST …/prompt {"delivery":"steer"}` admitted with `admittedSeq:7` into a mid-turn `running` session. Directive enters model context durably. |
| **STOP** | **VERIFIED** | `POST …/interrupt` on a genuinely running session (`{"type":"running"}`) → returned it to idle (`{}`). |
| **WATCH** | **VERIFIED** | `GET /api/event` (SSE) pushed `server.connected` + continuous heartbeats without polling. |
| **DEATH DETECTION** | **VERIFIED** | `kill -9` of the server process: health check from `{"healthy":true}` → `Connection refused` instantly. Reachability > lease-based liveness. |

## Open questions answered

- **`sync.steal` semantics:** Not tested. The research flagged it `[I]` (inferred). The critical finding—reads global, control local—makes `sync.steal` a secondary concern: you only need it if the manager wants to reassign a session from a dead worker, and the 5 verbs already cover that via reachability (health-check + detect death → stop caring about that session's DB record). **Low risk, defer.**
- **`--mdns`:** Not tested (single-host spike). Research says it exists and defaults to `0.0.0.0`. Adequate for LAN discovery; for cross-host, use a registry file written by the launcher.
- **What we lose vs the bridge:** (a) Ticket/claim semantics → Faktory already owns this (`work-lease.sh`). (b) Jedi-name registry → launcher-written mapping file. (c) Nudge queue → superseded by `delivery:"steer"` (synchronous injection, not parked messages). (d) Cross-host lease liveness → reachability probe (arguably *stronger* — no false ghosts). The one real regression: a worker on a dropped host is "unreachable" not "lease-expired", but Faktory's `reserve_for` covers work reclaim there.
- **Agent-agnostic fig leaf?** The 5-verb HTTP adapter (`session-ctl.sh`) is opencode-specific, but the adapter boundary is real: if we ever add a non-opencode worker (Gemini CLI via ACP), only the backend implementation changes. The standing directive is satisfied at the integration boundary, not at the transport layer.

## Verdict: **GO** — replace the bridge

All 5 verbs work as researched. `session-ctl.sh` (~60 lines) proves the adapter is thin enough to delete. The bridge's 3,073 LOC + 8 sidecars can be replaced with a one-flag launcher change (`--port <N>`) on each worker. The manager polls `GET /api/health` + `GET /api/session` instead of a SQLite DB. No model cooperation required—the harness has no off switch.
