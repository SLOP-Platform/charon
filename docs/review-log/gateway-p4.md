## 2026-06-26 — Gateway P4: stdlib web console (visibility)

- **Change under review:** a self-contained console on the gateway server itself
  (not FastAPI) so it bundles into the Windows `.exe` (operator decision: ship BOTH
  the stdlib gateway console AND the existing FastAPI Ledger dashboard).
- **Surface:** `GET /` → a zero-external-asset HTML page (polls `/charon/status` every
  2 s); `GET /charon/status` → JSON `{pools, providers, cooldown_seconds, usage,
  recent_failovers}`. Both are gateway-mode only and behind the **same token gate**
  (verified live: 401 without token). Per-provider served/failed/cost accounting was
  folded into `note_request` (one place, called on every exit path) so the hot loop
  gains no new branches; a `status_snapshot()` assembles the view.
- **No secret exposure:** the snapshot exposes provider **labels** (host netloc),
  counts, cost, cooldown seconds, and pool ordering — never `api_key`, `key_env`, or a
  full upstream base/path. The console escapes all interpolated values (no XSS) and
  loads nothing external (zero egress, like the read-only dashboard).
- **Proofs:** `test_gateway_failover.py::test_console_and_status_endpoints` — after a
  429→200 failover, the console HTML is self-contained + titled, and the status JSON
  reports the pool, the served provider (served>0) vs the failed one (failed>0), the
  billed cost (0.02, served only), and the recorded failover. **Live-smoked:** token
  gate (401 without token), cooldown surfaced (5 s from a `Retry-After`), 2.4 KB page.
- **Gate:** 137 passed, ruff clean, mypy clean (29 files), boundary OK, version OK.
- **Independent review — verdict PASS** (no secret/topology leak; both endpoints
  token-gated + gateway-mode-only; every HTML sink escaped; the upstream-influenced
  `reason` field isn't even rendered; no P1–P3 regression). Three LOW fixes applied:
  (1) `note_request` counts a provider as **served only on 200**; terminal failures/
  relayed errors now increment a distinct `errors` counter (console no longer
  overstates health). (2) `esc()` hardened to also escape `"`/`'` (safe regardless of
  future sink). (3) `UpstreamRoute.label` uses `host[:port]` not `netloc`, so any
  `user:pass@` in a misconfigured base can never surface in a header/console.
