## 2026-06-26 — Gateway P1 security review (independent) — reconciled

Independent read-only reviewer attacked the P1 token gate / loopback guard / forward
path. Verdict: needs fixes (1 HIGH, 2 MED, 2 LOW). All accepted; fixed under P2's
forward rewrite (same code path).

- **[HIGH] `?token=` forwarded to the upstream → gateway-token leak.** `self.path`
  (with query) was concatenated onto `upstream_base`, so a client authing via
  `?token=` sent that bearer to every provider's access logs. **Fix:** build the
  upstream URL from `urlsplit(self.path).path` only — the client query is never
  forwarded (`_build_upstream_req`). Header-form auth was already safe
  (`authorization` ∈ `_SKIP_HEADERS`).
- **[MED] `build_server` bound the socket without the loopback guard.** A direct
  caller (e.g. P4 console) could bind exposed+untokened. **Fix:** moved the
  refuse-non-loopback-without-token check INTO `build_server` (raises
  `GatewayBindRefused`); `run` translates it to exit 2. Guard now holds at bind time
  for every caller.
- **[MED] Unbounded request-body read (memory DoS).** **Fix:** `max_body_bytes`
  (default 10 MiB) → `413` over the cap.
- **[LOW] Empty-string token silently UNGATED on loopback.** **Fix:** `run` warns
  when `CHARON_GATEWAY_TOKEN` is set but empty.
- **[LOW] `str(exc)` echoed to client on upstream error.** **Fix:** the failover
  path returns a generic "upstream unreachable" message; no exception string leaked.
- **Verified-correct by the reviewer (kept):** token gate covers all paths before
  forwarding; constant-time compare fails closed; `/v1/models` is id-only; provider
  keys are header-injected and never logged/echoed; bare-proxy defaults unchanged.
