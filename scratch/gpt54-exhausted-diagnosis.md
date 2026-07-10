# gpt-5.4 "all providers exhausted" — live diagnosis (READ-ONLY)

Date: 2026-07-08 · Gateway: 4-LOM `charon-gateway-1` · Version: v0.3.6 (build f369b7c) · Up 18h, healthy

## VERDICT (root cause)
The gpt-5.4 pool is **genuinely all-exhausted**: it has exactly two members —
`nanogpt` and `openrouter` — and BOTH are returning **HTTP 402 (insufficient
balance / out of funds)** right now. This is NOT a routing bug that fails to use a
live member; intra-pool failover is working correctly (nanogpt 402 → failed over to
openrouter). It is a **billing/funds exhaustion** of both paid backends for that model.

The ~7h55m / attempt #15 backoff is **owned by the CLIENT (the SLOP/opencode/droid
Build session), not the gateway.** On the all-exhausted path the gateway returns a
plain **HTTP 503 with NO `Retry-After` header**, so the client falls back to its own
exponential backoff, which at attempt #15 lands around 8 hours.

Two independent, real defects compound the impact:
1. **No `Retry-After` on the 503** → the gateway forfeits control of client retry
   cadence, letting the client's exponential schedule balloon to ~8h.
2. **No cross-model / cross-tier substitution** → when gpt-5.4's own pool is dry the
   gateway gives up instead of routing to another capable model (e.g. gpt-5.5,
   claude-*). Confirmed absent in the proxy serve path.

## CONFIDENCE
- Pool is genuinely all-exhausted (both members 402): **HIGH** (live `recent_failovers`
  ring buffer + provider `last_status`).
- Gateway returns 503 with no Retry-After: **HIGH** (source-confirmed, exact code path).
- 8h stall is client-owned exponential backoff: **HIGH** on "gateway did not send it";
  **MEDIUM** on "client exponential doubling to ~8h" (client not directly observed —
  inferred from attempt #15 + gateway sending no Retry-After).
- No cross-model substitution in the serve path: **HIGH** (source-confirmed).

## 1. gpt-5.4 pool state (LIVE)
Pool members (`GET /charon/status` → pools["gpt-5.4"]): **`["nanogpt", "openrouter"]`** (2 members).

Live provider stats (`GET /charon/status` → providers):
| provider   | served | failed | errors | last_status | cost_usd | state now |
|------------|--------|--------|--------|-------------|----------|-----------|
| openrouter | 108    | 15     | 9      | **402**     | 7.46     | out of balance |
| nanogpt    | 12     | 38     | 6      | **402**     | 0.00     | out of balance |
| huggingface| 2      | 0      | 0      | 200         | 0.00     | healthy (not in gpt-5.4 pool) |

`cooldown_seconds` = **`{}`** → NO provider is in an active gateway cooldown right now.
(The v0.3.6 ≤120s clamp means any 402-triggered cooldowns from earlier have already
expired; the providers are not sidelined by cooldown — they are live-returning 402.)

Log/observability evidence — the `recent_failovers` ring buffer (38 entries, all `gpt-5.4`):
- Earlier entries: `nanogpt=402 (insufficient balance) → failed over → openrouter=200`.
  Proves intra-pool failover works and openrouter was the paid backstop.
- **Most recent entries: `nanogpt=402 … ; openrouter=402 ("insufficient balance")`** —
  BOTH members 402 in the same request. `served_by` shows the last-tried provider with
  `status=402` (terminal failure, recorded as an error, not a real serve).

Interpretation: openrouter's balance was carrying gpt-5.4 (108 served, $7.46 spent).
Once openrouter also hit 402, both members of the 2-member pool were exhausted →
gateway synthesized the terminal "all providers exhausted" 503.
(`docker logs` grep for gpt-5.4/402/etc. returned nothing — this build surfaces
per-request upstream detail via the status ring buffer, not stdout logs; the ring
buffer is the authoritative evidence.)

## 2. Layer B — origin of the ~8h backoff
Gateway error-response code path — `proxy_server.py` lines 815-835, the terminal
all-exhausted branch:
```
self._send_resp_headers(503, "application/json", route.label, failovers, False)
self._write(json.dumps({"error": {
    "message": "all providers exhausted",
    "type": "all_providers_exhausted",
    "failover_reasons": [f"{f['provider']}={f['status']}" for f in failovers],
}}).encode())
```
`_send_resp_headers` (lines 483-500) sends ONLY: status, `Content-Type`,
`X-Charon-Provider`, `X-Charon-Failovers`, `X-Charon-Failover-Reasons`, optional
`X-Charon-Downgrade`/`X-Cache-Status`, token cookie. **It never sets `Retry-After`.**

Therefore the gateway returns `503` with **no `Retry-After`**. The 7h55m / attempt #15
is NOT gateway-dictated — it is the **CLIENT's own exponential backoff** (opencode/droid),
which at attempt #15 (doubling from a ~1s base ≈ 2^15 ≈ 9h, with cap/jitter ≈ 7h55m).

**Layer ownership of the 8h stall: the CLIENT.** The three layers stay distinct:
- Gateway-internal routing cooldown (v0.3.6, ≤120s) — currently `{}` (empty), not involved.
- Gateway→client `Retry-After` — **not sent** on this path (the gap).
- Client backoff — **owns the 8h stall.**

## 3. Failover gap (confirm/refute)
**CONFIRMED.** No cross-model or cross-tier substitution happens in the gateway proxy
serve path.
- `chain_for(model)` (`proxy_server.py:1115-1128`) returns ONLY that one model's own
  pool: `if model in self.pools: return list(self.pools[model])`. The serve loop
  (`_ProxyHandler`, lines 771-841) iterates exactly that chain; when the LAST member
  also fails over-eligibly (402/429/503/…) it emits "all providers exhausted" (503).
  There is no step that re-routes to a different model id or a lower/other tier.
- Cross-model failover DOES exist in the codebase — `failover.py` /
  `handoff.py::choose_next_backend` / `router.py` — but those serve the
  **coordinator/engine (orchestrator)** path, not the gateway request-proxy that a
  raw OpenAI client (the SLOP Build session) hits. The gateway proxy only does
  intra-pool, cross-**provider** failover. Cross-**model** substitution is the
  wanted-but-unbuilt feature; refute of any claim that the gateway already does it.

This matches the KNOWN_CONTEXT failover-bug note, refined: the pool DID fail over
across its providers (nanogpt→openrouter worked for a while); the gap is that once the
whole gpt-5.4 pool is dry, nothing substitutes a different capable model.

## 4. Mitigation (PROPOSED — not executed)

### Reversible hot-fix (unstick now)
The stalled Build session is parked on its own ~8h client backoff; the gateway itself
is fine and will retry immediately on the next client request. Fastest paths:
- **Restore balance on a gpt-5.4 backend** — top up **openrouter** (the paid backstop
  that was carrying gpt-5.4) and/or **nanogpt**. As soon as either clears 402, the pool
  serves again. No gateway change needed; no cooldown blocks it (`cooldown_seconds={}`).
- **Kick the client** — the ~8h wait is client-side, so restoring balance alone won't
  wake an already-sleeping session until its timer fires. To resume immediately, the
  stalled Build session must be nudged/restarted so it re-issues the request (which will
  then succeed against the topped-up backend). Restoring funds + restarting the session
  together is the complete unstick.
- (Optional, if a topped-up model differs) point the Build session at a model whose pool
  has funds — e.g. a `-go`/opencode-zen-backed or huggingface-backed model that is not
  balance-exhausted — as a manual, temporary cross-model substitution the operator does
  by hand (the gateway won't do it automatically).

All above are reversible and touch funds/session only — no config/routing rewrite.

### Root fix (durable)
1. **Emit `Retry-After` on the all-exhausted 503** (and on single-upstream 429/402
   relays) so the gateway, not the client's runaway exponential, owns retry cadence —
   e.g. a bounded value tied to the soonest cooled member / a sane default (≤120s), so a
   transient dual-402 can never become an 8h client stall.
2. **Cross-model / cross-tier substitution in the proxy serve path** — when a model's
   own pool is exhausted, fall over to another capable model in the same tier before
   returning 503 (productize the coordinator's `choose_next_backend` semantics into
   `chain_for`/the serve loop). This is the wanted-but-unbuilt feature.
3. **Balance-aware pre-emption** — the balance pollers (`balance.py`, incl.
   `_poll_nanogpt`/`_poll_openrouter`) already know remaining USD; demote a
   balance-exhausted provider proactively instead of discovering 402 per-request, and
   surface a low-balance alert before both members of a 2-member pool go dry.
4. **Widen thin pools** — gpt-5.4 has only 2 paid members; both share the same failure
   mode (funds). Adding a non-balance-gated member (e.g. an opencode-zen/`-go`-served or
   HF-served gpt-5.x variant) removes the single-point dual-402.

## UNVERIFIED
- The exact client (opencode/droid) backoff formula and cap — inferred (gateway sends
  no Retry-After + attempt #15) but the client process was not directly observed.
- Whether openrouter's 402 is a hard zero balance vs. a per-key/per-model spend cap —
  observed as "insufficient balance" 402; underlying account state not queried
  (would require provider dashboards / balance poll, out of read-only-gateway scope).
- Health of pool-eligible providers with no recent traffic (neuralwatt, deepseek, groq,
  cerebras, together, mistral) — keys present and not cooled, but not exercised in the
  observed window, so live 200-health is unconfirmed.
- Timestamps on the `recent_failovers` entries are not exposed in the ring buffer, so
  the precise moment openrouter flipped to 402 is not pinned (ordering is preserved).
