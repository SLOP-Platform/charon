# Adversarial review — PROXY-SERVER-DECOMPOSE (branch `feat/proxy-server-decompose`)

Reviewer: read-only adversarial sub-session · Date: 2026-07-08
Scope: behavior-preserving verbatim split of the money-path proxy god-file into 4 modules.
Method: mechanical byte-diff of every moved region against `master` (normalizing only the
declared mechanical transforms), facade/arch/import-cycle checks, full test suite.

## VERDICT: **SHIP**

The decomposition is a genuine verbatim move. Every money-path line reproduces byte-for-byte
after the exactly-declared mechanical transforms. No logic rode along. Full suite green.

---

## Evidence (mechanical, not eyeball)

**1. Forwarder money-path loop (commit c566853) — the critical one.**
`forward_with_failover` body diffed against master `_handle` data-plane (699–1002),
normalized `self.`→`handler.` + 8-space dedent. **Only two differences, both expected:**
- the declared call-site rewrite `handler._build_upstream_req(srv,…)` → `_build_upstream_req(handler, srv,…)` (forwarder.py:90)
- a trailing blank line.
Spend `record`/`note_request`, `count_usage` flags (True on served, False on non-200/unreachable/downgrade-discard),
exhaustion synth + `retry_after=srv.retry_after_hint(ordered)`, `relay_retry_after` clamp,
per-route `bj["model"]`/`expected`/`okey`, cache-suppression on downgrade/truncation — all identical.

**2. `_build_upstream_req` (D)** — byte-identical to master 513–561 modulo `self.`→`handler.`
and the `self,`→`handler,` signature (only a trailing blank line otherwise). Query-string drop,
UA normalization, key injection, /v1 strip, stream_options — unchanged.

**3. Seam G integrity.** forwarder.py imports NO `threading` and defines no lock. It reaches
`chain_for`/`order_by_cooldown`/`set_cooldown`/`retry_after_hint` ONLY via `srv.` — never
re-implements or copies the `_cooldown_lock`. All routing state + lock stayed on GatewayProxyServer.

**4. Control-plane (E, 404a0c6)** — master 588–697 == console_router body, modulo `self.`→`handler.`,
each `return`→`return True`, plus a terminal `return False`. Byte-identical otherwise. New slim
`_handle` preserves the loopback guard / token gate / `?token=` cookie-set in the SAME ORDER before
delegating (`if console_router.try_handle_control_plane(...): return` then `forwarder.forward_with_failover(...)`).

**5. Response helpers (B, cd3bf5b)** — `_extract`/`_pre_flight_estimate`/`_pre_flight_pricing`
byte-identical to master 338–397. `_normalize_model_id` now imported directly from `.proxy` (same source).

**6. HTML assets (A, 42cea99)** — removed block == added module (minus docstring), verbatim incl. the
leading `# Self-contained gateway console` comment.

**7. Facade / module-state.** `_SKIP_HEADERS`/`_DEFAULT_UA`/`_BANNED_UA_PREFIXES`/`_STREAM_HEAD_CAP`/
`BROWSER_UA`/`_normalize_request_messages` moved fully OUT of proxy_server — no duplication, no two
sources of truth. Facade re-exports (`_CONSOLE_HTML`,`_SETUP_HTML`,`_WORK_HTML`,`_extract`,
`_pre_flight_estimate`, plus in-file `GatewayProxyServer`/`UpstreamRoute`) resolve; no test imports a
moved-but-non-reexported symbol. All 7 shared handler helpers (`_json`/`_html`/`_authorized`/
`_maybe_set_token_cookie`/`_write`/`_drain`/`_send_resp_headers`) remain on `_ProxyHandler`.

**8. Arch boundary + cycle.** All 4 modules added to `_ENGINE_FORBIDDEN` (tools/check_arch.py) +
asserted (tests/test_check_arch.py). `tools/check_arch.py` passes (no circular-import / layer violation).
No runtime cycle: `proxy.py` does not import `proxy_server`; `UpstreamRoute`/`GatewayProxyServer`
appear only in string annotations under `from __future__ import annotations`.

**9. Tests.** Full suite **1261 passed**; targeted money-path set (test_proxy_server,
test_proxy_downgrade, test_gateway_failover, test_check_arch) **74 passed**. Import smoke + facade OK.

---

## Non-blocking notes (negligible)
- The `_ENGINE_FORBIDDEN` entries + their test assertions both land in the *forwarder* commit
  (c566853), not the per-module commits. Internally consistent (assertion and entry move together),
  and the PR merges as a unit, so the final state is correct. Only matters if someone bisects and
  runs a single intermediate commit in isolation — not a merge blocker.
- `_WORK_HTML` is re-exported defensively though no current test imports it — harmless.

## Confidence: HIGH
Byte-diff of the entire moved money path + full green suite + arch pass. A hidden `self`→`srv`
mis-binding or dropped billing side-effect would have shown in the normalized diff or the failover/
downgrade tests; neither did.
