# DEAD-GATEWAY-MODULES — Confirmation Ruling

**Session:** galen-marek (minimax-m3-together)
**Ticket:** DEAD-GATEWAY-MODULES
**Repo:** charon
**Investigation-only:** No product code touched. Verdict produced; operator disposes.
**Construction site (read-only):** `src/charon/gateway.py:73-114` (`_MODULE_SPECS`), instantiation at `:274-275`, attribute plumbing at `src/charon/proxy_server.py:562-586`.

## Method

**Verified by RUNNING:**
- `graphify update /home/stack/code/charon --force` — rebuilt graph (7751 nodes, 14951 edges, 413 communities).
- `tools/check_inert_code.py` — full output reviewed (66 dead symbols in disposition file, none of the six).

**Verified by READING:**
- `git -C /home/stack/code/charon show HEAD:src/charon/gateway.py | sed -n '40..360'` — construction site.
- `git -C /home/stack/code/charon show HEAD:src/charon/proxy_server.py | sed -n '480..600'` — attribute plumbing.
- `git -C /home/stack/code/charon show HEAD:src/charon/forwarder.py | sed -n '200..770'` — the request-path code that calls `srv.<attr>`.
- `grep` over `src/charon/` for every method on each module (`.inspect`, `.pin/.resolve/.touch/.clear`, `.export/.get_metrics/.increment`, `.execute/.run/.dispatch`, `.verify`, `.resolve/.create/.list_keys/.revoke`).
- `grep` over `src/charon/api.py`, `src/charon/proxy_console_assets.py`, `src/charon/console_router.py`, `src/charon/console_work.py` for any consumer.
- `grep` over `docs/`, `fleet/`, `README.md`, `tools/inert-code-disposition.json` for any claim or disposition.

## Verdicts

For each: `LIVE` / `INERT-RETIRE` / `INERT-WIRE`.

| Module | attr on cfg/srv | Verdict | Evidence (file:line) |
|---|---|---|---|
| `RequestInspector` | `request_inspector` | **INERT-RETIRE** | Constructed `gateway.py:89`; stored at `proxy_server.py:577`. Zero method calls on it (`grep 'request_inspector\.'` returns only the assignment sites). Hot path (`forwarder.py`) never references it. No docs/console claim this behaviour exists. Unit tests at `tests/test_request_inspector.py` exercise only the class, never through `GatewayProxyServer`/`forward_with_failover`. Removing it: nothing changes. |
| `SessionAffinity` | `session_affinity` | **INERT-RETIRE** | Constructed `gateway.py:91`; stored at `proxy_server.py:578`. Zero method calls (`grep 'session_affinity\.'` returns only assignment sites). No `X-Charon-Session` reads use it; no docs/console claim. Unit tests at `tests/test_session_affinity.py` exercise the class only. Removing it: nothing changes. |
| `Observability` | `observability` | **INERT-RETIRE** | Constructed `gateway.py:81`; stored at `proxy_server.py:574`. Zero method calls (`grep 'observability\.'` empty). `GatewayProxy` (the `observer` actually used in `forwarder.py`) is a different class — `src/charon/proxy.py:368`. No `/metrics` endpoint exists; `api.py` does not expose it; `proxy_console_assets.py` does not reference it. No docs/console claim. Removing it: nothing changes. |
| `SpeculativeExecutor` | `speculative_executor` | **INERT-RETIRE** (with caveat) | opt-in (`gateway.py:92-95`). With no `speculative.json {"enabled": true}` on disk (none found anywhere in tree), `_module_inst` returns `None` (`gateway.py:340`), so `self.speculative_executor` is `None`. Even when present, zero method calls (`grep 'speculative_executor\.'` empty). Caveat: `docs/REVIEW-LOG.md:1171-1229` describes a "DESTIFF-SPECULATIVE" class-fix that refactored the executor; this is historical/operator-narrative, not a live user-facing claim. Removing it: nothing changes on the wire. |
| `ConsensusRouter` | `consensus_router` | **INERT-RETIRE** | opt-in (`gateway.py:96-100`). With no `consensus.json {"enabled": true}` (none found), instance is `None`. Zero method calls (`grep 'consensus_router\.'` empty). `docs/PLAN-tier1.md:126` explicitly says "Consensus is a port + no-op pass-through in Tier 1; real cross-model review is Tier 3" — i.e., the docs document that consensus is intentionally not wired in Tier 1, matching what the code does. Removing it: nothing changes. |
| `VirtualKeyManager` | `virtual_key_manager` | **INERT-RETIRE** | Constructed `gateway.py:101-103`; stored at `proxy_server.py:581`. Zero method calls (`grep 'virtual_key_manager\.'` and `grep 'vkeys\.'` and `grep 'virtual_keys\.'` empty). Auth path at `proxy_server.py:246-251` uses Bearer token only — never resolves a virtual key. No admin/console endpoint exposes vkeys (no `/vkeys`, no handler in `api.py`, `proxy_console_assets.py`). `docs/docker.md:117` mentions "virtual keys" only as a file mounted alongside other state — not a live-claim. Removing it: nothing changes. |

## No `INERT-WIRE` candidates

The operator's concern was that `SpeculativeExecutor`, `ConsensusRouter`, and `SessionAffinity` describe routing behaviour someone may believe is live. I found **no user-visible claim** in:
- docs/`GATEWAY-PROGRAM.md`, `GUI-API-SURFACE.md`, `README.md` — no mention of these as features.
- `proxy_console_assets.py` / `console_router.py` / `console_work.py` — no exposure.
- `api.py` — no endpoint for them.
- `inert-code-disposition.json` — no existing triage row for them.

The `tools/check_inert_code.py` output does NOT flag any of the six (it sees the `_MODULE_SPECS` registration and treats them as reachable). But reachability-via-registry ≠ reachability-on-the-request-path, which is the question the operator asked.

## Why this is not a false-retire pattern

The risk the prompt named — "zero grep is not evidence" — applies to symbols where dynamic dispatch or aliasing might hide call sites. These six are NOT in that category:
- `forwarder.py` (the only place a request reaches a module) is the file that has been audited to wire `srv.spend_limiter`, `srv.guardrails`, `srv.semantic_cache`, `srv.observer`, `srv.quality_scorer`, `srv.note_request` — and **does not wire any of these six**. I read every `srv.*` access in `forwarder.py` (lines 200-770).
- `proxy_server.py:562-586` is purely structural — populates `self.<attr> = self.modules.get(<attr>)` for each ModuleSpec — and nothing else in `proxy_server.py` uses them.
- The `__getattr__` on `GatewayConfig` (`gateway.py:156-163`) is only a backward-compat accessor for tests that import `cfg.guardrails` etc. — those same tests are also absent for the six modules.

## Files verified to NOT be modified

- `src/charon/gateway.py` — only read.
- `src/charon/proxy_server.py` — only read.
- `src/charon/forwarder.py` — only read.
- No git operations performed in `/home/stack/code/charon` (read-only checkout per prompt).

## Heartbeat

session-bridge_register + heartbeat maintained throughout.