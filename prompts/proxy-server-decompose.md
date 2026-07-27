# PROXY-SERVER-DECOMPOSE — split the proxy_server.py god-file into 4 modules behind a facade

You are decomposing `src/charon/proxy_server.py` (~1229 lines, the live money-path serving
core) into 4 new modules behind a slim facade. This is a **behavior-preserving refactor**:
**verbatim moves only, NO logic change in any move commit.** The goal is to let the ~9
tickets that all edit this one file stop serializing and split into 2 parallel module-lanes
(routing ‖ console).

Grounding: `fleet/scratch/proxy-decomposition-analysis.md` (§2 seams, §3 owns-map, §4
blast-radius). Read the actual file first; the line ranges below are approximate anchors, not
gospel — move by cohesive unit, re-locate if the file has drifted.

## Own ONLY these files
- `src/charon/proxy_server.py` (slimmed + facade re-exports)
- `src/charon/proxy_console_assets.py` (NEW)
- `src/charon/proxy_response.py` (NEW)
- `src/charon/console_router.py` (NEW)
- `src/charon/forwarder.py` (NEW)
- `tests/test_check_arch.py` (add the 4 new modules to `_ENGINE_FORBIDDEN`)

Do not touch any other file. Product must ship **STANDALONE** — no fleet/SLOP/rig dependency
may leak into product code.

## The seams (what moves where)

| # | New module | Source seam | Approx lines | Content |
|---|---|---|---|---|
| A | `proxy_console_assets.py` | Console asset constants | ~83–332 | `_CONSOLE_HTML`, `_WORK_HTML`, `_SETUP_HTML` — ~250 lines of pure static HTML data, zero logic |
| B | `proxy_response.py` | Response/pricing helpers | ~335–394 | `_extract`, `_pre_flight_estimate`, `_pre_flight_pricing` — module-level pure functions |
| E | `console_router.py` | Control-plane dispatch | ~551–686 | first half of `_handle`: loopback guard, token gate, `/v1/models`, `/charon/status`, `/charon/cost`, console HTML, `/charon/setup` + config POST-writes (CSRF), `/charon/work`. Expose `try_handle_control_plane(handler, srv) -> bool` (True = request fully served) |
| F+D | `forwarder.py` | Data-plane failover loop + request build | F ~688–982, D ~502–549 | second half of `_handle` (body read, session id, `chain_for`, spend cap, guardrails, cache, `order_by_cooldown`, quality routing, the `for route in ordered` loop: non-200 / 200-nonstream / 200-stream branches, downgrade detection, exhaustion synth, caching, spend record) **plus** `_build_upstream_req` (header filter, UA normalization, model rewrite, body normalization, /v1 strip, key injection). Expose `forward_with_failover(handler, srv, ...)` |

### Stays on `proxy_server.py` (do NOT move)
- **Seam G — `GatewayProxyServer`** (~985–1229): routing state (pools/routes, `_cooldown` +
  **`_cooldown_lock`**, stats, snapshot) and its methods `route_for`, `apply_routes`,
  `chain_for`, `order_by_cooldown`, `set_cooldown`, `note_request`, `status_snapshot`, `url`,
  `serve_in_thread`. **`_cooldown_lock` guards `chain_for`/`order_by_cooldown`/`set_cooldown`/
  `apply_routes` as a unit — keep them together on the class. forwarder.py calls them through
  `srv`; it NEVER re-implements locking.**
- **Seam C — shared HTTP substrate** on the `_ProxyHandler` shell: `_json`, `_html`,
  `_authorized`, `_maybe_set_token_cookie`, `_write`, `_drain`, `_send_resp_headers`. Both
  planes call these; they stay on the handler and are passed the handler instance.

### `_handle` collapses to
```
loopback / token gate
if console_router.try_handle_control_plane(handler, srv):
    return
forwarder.forward_with_failover(handler, srv, ...)
```

## Facade (MANDATORY — this is how the suite stays green)
`proxy_server.py` MUST re-export the public import surface so all 13 importing test files
resolve with **zero import edits**. Re-export at least:
`GatewayProxyServer`, `UpstreamRoute`, `_CONSOLE_HTML`, `_SETUP_HTML`, `_WORK_HTML`,
`_extract`, `_pre_flight_estimate`.
(e.g. `from charon.proxy_console_assets import _CONSOLE_HTML, _SETUP_HTML, _WORK_HTML` etc.,
at module top of proxy_server.py.) If a test imports a moved symbol from `charon.proxy_server`
and it fails, the facade is incomplete — fix the re-export, do not edit the test's import.

## Arch guard (REQUIRED, not optional)
`tests/test_check_arch.py` has `_ENGINE_FORBIDDEN` containing `"proxy_server"` (engine may not
import it; it may not import engine/vendor). **Add all 4 new module names**
(`proxy_console_assets`, `proxy_response`, `console_router`, `forwarder`) to `_ENGINE_FORBIDDEN`,
or the engine-import boundary silently weakens.

## Staging — 4 behavior-preserving verbatim-move commits (hardest last)
Do them in this order, running the **full suite green after EACH commit**:
`PYTHONPATH=src python3 -m pytest -q`

1. **commit 1** — extract `proxy_console_assets.py` (A). LOW risk. + facade re-exports. Suite green.
2. **commit 2** — extract `proxy_response.py` (B). LOW risk. + facade re-exports. Suite green.
3. **commit 3** — extract `console_router.py` (E). LOW risk (control-plane, off the money path).
   `_handle` now delegates the first half to `try_handle_control_plane`. Suite green.
4. **commit 4** — extract `forwarder.py` (F + D). **HIGH RISK — the money-path failover loop with
   SR-1/SR-2/DTC scar tissue (double-bill / downgrade regressions).** Verbatim move, zero logic
   change. `_handle` now delegates the proxy path to `forward_with_failover`. Add the 4 modules
   to `_ENGINE_FORBIDDEN` in this commit (or commit 1, your call — but it must be in the PR).
   Suite green. **This step gets an adversarial review** (money-path framing).

**Behavior-preserving constraint (hard):** a move commit may relocate code and add facade
re-exports / delegating calls ONLY. **No logic change, no refactor-while-moving, no "small
cleanup" may ride along in a move commit.** If you find a real bug mid-move, note it for a
SEPARATE follow-up ticket — do not fix it inside a move commit.

After the moves, rebase PFF Phase-1's small header/outbound diff on top (trivial) if it has
landed.

## Dependencies & sequence
- **depends_on: PROXY-FAILOVER-FIX.** PFF Phase-1 (Retry-After + outbound UA — header/outbound
  only, the active bleed-stopper) holds `proxy_server.py` and must land FIRST on the current
  file; this decompose then rebases PFF's small diff after PFF merges. Both own
  `proxy_server.py` → a **hard single-owner-file sequence**, not merge-order-only.
- **Wave:** this is Wave B. Wave A = PFF Phase-1 (+ off-file: INC-401 already CLOSED, COOLDOWN-FIX3
  proxy.py audit). Wave C (unlocked BY this decompose) = 2 parallel lanes: routing (forwarder.py:
  PFF-P2 → DRAIN → SR-6, RFL-3 peel) ‖ console (console_router.py: SR-13, RFL-2, RFL-4).
- **Concurrency safety:** single owner holds `proxy_server.py` for the duration (serial, one
  module per commit). Confirm NO other proxy_server.py ticket is in-flight when this activates.
  PFF Phase-2 (money-path cross-tier substitution) lands AFTER this decompose, into forwarder.py.
- **Do NOT** parallelize the 4 move commits — they are strictly serial on the same file.

## Acceptance
- `PYTHONPATH=src python3 -m pytest -q` — full suite GREEN after each of the 4 commits (not just
  at the end).
- Public import surface resolves unchanged from `charon.proxy_server` (facade).
- `tests/test_check_arch.py` passes with the 4 new modules in `_ENGINE_FORBIDDEN`.
- No logic change in any move commit (reviewable as pure code motion + facade + delegation).

## LAST STEP (required)
Commit your work and report the final commit SHA.

Do NOT push or merge.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
