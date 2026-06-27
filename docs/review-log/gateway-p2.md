## 2026-06-26 — Gateway P2: transparent in-request failover

- **Change under review:** in-request failover across a cost-ranked pool, on the
  existing `GatewayProxyServer`. New: `chain_for`/`order_by_cooldown`/`set_cooldown`/
  `note_request` + a provider-keyed cooldown and a bounded failover-event log;
  `GatewayProxy` split into pure `classify` + `record(count_usage)`; `gateway.py`
  builds pools from `charon.toml [pools]` or `.charon/pools.json` (free-first sorted).
- **Failover semantics (ADR R1/R6/R7/R10):** on 429/402/503/404, `Retry-After`, a
  silent downgrade, or an unreachable provider, the next pool member serves **within
  the same client request**; **400/401/403 are returned immediately** (never failed
  over — R6, don't burn money / mask bad requests). 1-element chains never fail over
  (exact pre-P2 single-upstream behavior — all prior proxy tests still green).
- **R10 fixes folded in:** R10a — `count_usage=False` for discarded attempts, so a
  failed-over response's tokens/cost are **not** billed (live-proven: only the served
  provider's 0.02 counted). R10b — each attempt rebuilds the body from the ORIGINAL
  request with that provider's `upstream_model` (proven: A got `ma`, B got `mb`).
  R10c — cooldown is **provider-keyed** (upstream_base) with `Retry-After`/default
  expiry, distinct from the model-keyed per-run `_exhausted`.
- **Streaming (R1):** pre-body status failover is transparent (no bytes sent);
  silent-downgrade is detected by buffering the SSE head until `model` appears (capped
  at 64 KiB) and failed over pre-commit, or surfaced via `X-Charon-Downgrade` if
  already committed. Non-streaming is fully buffered then classified.
- **Visibility (D3):** `X-Charon-Provider`, `X-Charon-Failovers` (count = providers
  moved PAST, not the served one), `X-Charon-Failover-Reasons`, `X-Charon-Downgrade`;
  + an in-memory ring buffer and optional JSONL log.
- **Security (P1 review fixes baked in):** path-only upstream URL (no `?token=` leak),
  bind guard in `build_server`, body-size cap.
- **Proofs:** `tests/test_gateway_failover.py` — 429 failover + visibility headers;
  downgrade failover with NO double-count; client-error NOT failed over; unreachable
  failover; whole-pool-exhausted relays the real last error. Plus a cost-ranked-pool
  config test. **Live-smoked** end-to-end through a real `charon.toml` pool.
- **Gate:** 126 passed, ruff clean, mypy clean (28 files), boundary OK, version OK.
- **Adversarial review:** the failover state machine (the critical surface) is being
  sent to an independent reviewer per the operator's standing instruction.
