# PFF-P1 adversarial review — feat/proxy-failover-p1 @ 2bed305

Verdict: **FIX** (P1 money-path is SHIP-clean; P5 has a real onboarding gap). Confidence: HIGH.

## Money-path (P1) — CLEAN, no defects found
1. **No behavioral change beyond header.** Diff touches only 7 src files. `_send_resp_headers`
   gained `retry_after: int|None = None`; all pre-existing callers (200/502/cache — lines
   766/803/909/938/960) omit it → byte-identical output. Only the two intended sites emit it:
   terminal 503 (proxy_server.py:837-839) and the 402/429/503 relay (856-857). `retry_after_hint`
   only READS `_cooldown` under `_cooldown_lock` — no routing/cooldown/spend mutation. Spend
   recording (`note_request`) unchanged. VERIFIED.
2. **Retry-After clamp correct in every edge case.** `retry_after_hint` (proxy_server.py:1170-1176):
   past-expiry members filtered by `> now` (no negatives), empty/none-cooled → `default_cooldown`
   (60), output `int(max(1.0, min(soonest, max_cooldown_s)))` with max_cooldown_s=120 → always
   [1,120]. Relay clamp (853-855) `min(obs.retry_after or default_cooldown, max_cooldown_s)`
   re-bounds upstream `Retry-After: 3420` → 120 (not passed through). Suppressed on 400/401/403
   (`else None`) and the emitter guards `if retry_after and retry_after > 0`, so a 0/negative
   upstream value is dropped rather than emitted. Never 0/negative/>120. VERIFIED.
4. **UA-as-IP gotcha — SAFE.** check_security.py `_IP_REGEX` = `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`.
   `Chrome/125.0.6422.113` does NOT match (the 4-digit `6422` breaks the `\d{1,3}` dotted-quad;
   `537.36`/`10.0` are only 2 groups). Base64 secret regex needs a 40+ contiguous `[A-Za-z0-9+/]`
   run — BROWSER_UA's longest is `AppleWebKit/537.36` broken by the `.` (<40). No false-positive.

## P5 gap — the FIX (does not regress, but undercuts P5's own goal)
5. **MISSED outbound provider-probe paths still send a non-browser UA** — the exact CF-1010
   failure class P5 targets, on the provider-ONBOARDING path:
   - `src/charon/config.py:442` `_VALIDATE_UA = "charon-proxy/0.1"` → used by
     `validate_provider_key` (real GET /models + POST /chat/completions probe). Adding a
     groq/cerebras/together key (the very providers P5 exists to unblock) 403s "1010" →
     key reported INVALID → provider never onboarded. Directly defeats P5.
   - `src/charon/cli.py:395` and `src/charon/cli.py:591` — key/base probes, still `charon-proxy/0.1`.
   - `src/charon/speculative_execution.py:116` and `src/charon/routing_proxy.py:98` — build
     upstream POSTs with NO User-Agent → urllib injects `Python-urllib/*` (a `_BANNED_UA_PREFIXES`
     value) → CF-1010. Both were NAMED in the design's own sweep list (§2 P5) yet left untouched.
   These are incompleteness, not regressions (all were already non-browser), so P1 can ship;
   but P5 is not "done" until these fold onto `BROWSER_UA`.
   Minimal fix: `_VALIDATE_UA = BROWSER_UA` (config.py), the two cli.py literals → BROWSER_UA,
   and add `req.add_header("User-Agent", BROWSER_UA)` in speculative_execution/_build_request +
   routing_proxy handler. (observability.py webhook/langfuse correctly left alone — operator's
   own sink, not a provider.)

## Residual risk (accept, not a blocker)
3. **Browser-UA rejection.** Flipping to a browser UA is design-live-verified to flip
   groq/cerebras/together 403→200. Nonzero risk that some SDK-expecting API prefers a client UA,
   but no such provider identified in the swept modules; the pre-change non-browser UA was the
   confirmed-worse state. Accept per design; watch in prod.
