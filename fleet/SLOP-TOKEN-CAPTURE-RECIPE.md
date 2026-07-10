# RECIPE — Capture a SLOP session's token/$ use through Charon

Goal: measure the token & $ spend of the SLOP session running **DeepSeek-V4-Pro**
through the Charon gateway bridge (`http://10.0.1.60:8080`).

## What the gateway exposes TODAY (no new build)
- **`cumulative_usage()`** — GLOBAL counter: `tokens_in`, `tokens_out`, `cost_usd`
  (from provider-reported `prompt_tokens`/`completion_tokens`/`cost`). All traffic, not per-session.
- **`/charon/cost` console panel** — per-PROVIDER counters (`served_by` label → served / failed / cost),
  maintained by `note_request()` (proxy_server.py:655). Global & cumulative, broken down by provider.
- **Per-(model,provider) meter** (`feat/meter-model-provider`, merging now) — finer `(model,provider) → $`,
  but EMPTY under real traffic until the Wave-2 caller-wiring (`provider=route.label`) lands.
- **Provider dashboards** — the serving provider's own usage page (e.g. opencode-Go), out-of-band.

Gap: **no per-SESSION attribution today.** The SLOP session's spend lands under whichever
provider served `deepseek-v4-pro`, mixed with any other `deepseek-v4-pro` traffic on that provider.

## METHOD A — snapshot-delta (works NOW, best when SLOP is the only DeepSeek traffic)
1. Ensure no other `deepseek-v4-pro` traffic is running (our review jobs primary on glm-5.2 and only
   fail over to deepseek-v4-pro if glm exhausts — so normally deepseek-v4-pro ≈ the SLOP session).
2. Snapshot BEFORE the session (or window): open `http://10.0.1.60:8080/charon/cost` and record the
   row for the provider serving deepseek-v4-pro (served count + cost) and the global `cost_usd`.
3. Run / continue the SLOP session.
4. Snapshot AFTER; **delta = that session's tokens & $**.
Cross-check the delta against the serving provider's own dashboard for the same window.

## METHOD B — durable, exact (after meter Wave-1 merge + a small Wave-2 wire)
1. Merge `feat/meter-model-provider` (in progress).
2. Wave-2: wire `provider=route.label` into the `forwarder.py` record()/observe() sites (the deferred
   step the reviews flagged) → `all_model_provider_costs()` then reports real `(deepseek-v4-pro, <provider>) → $`.
3. For TRUE per-session isolation, add a lightweight **session tag** (a header or key the SLOP client
   sends) carried into the meter key — small ticket, turns Method A's "isolate by quiet window" into
   "read the tagged row directly." → candidate ticket: `METER-SESSION-TAG`.

## RECOMMENDATION
- Right now: use **Method A** (snapshot the `/charon/cost` deepseek-v4-pro provider row before/after),
  keeping other Charon jobs off deepseek-v4-pro during the window.
- Prioritize the **meter merge + Wave-2 provider wiring** to make Method B exact; then decide whether
  the per-session tag is worth a small ticket for ongoing SLOP-session accounting.
