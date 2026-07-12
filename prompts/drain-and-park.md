# BRIEF — DRAIN-AND-PARK (folded money-path build)

Folds three tickets that all co-own `gateway.py`+`balance.py` (cannot run in parallel) into ONE sequenced build: **METER-Wave2** (balance sensor) → **DRAIN-ROUTING** (drain-priority + exclude-at-0) → **DRAIN-THEN-PARK** (park/re-arm + sole-leg guard).

**Repo:** /home/stack/code/charon · NEW branch **`feat/drain-and-park`** off latest `origin/master`. Commit. **Do NOT push. Do NOT merge. Do NOT open a PR.**
**Class:** money-path, design-sensitive. **Adversarial review of the sole-leg guard is MANDATORY before any merge** (a regression there orphans a pool).

## RECONCILIATION — read first (already-done vs gap)
- **DONE + merged (do NOT rebuild):** the per-(model,provider) **observer meter** (`GatewayProxy._model_provider_cost`, proxy.py) is live — fed real `usage.cost_usd` (forwarder.py:447) and read by cheapest-first routing via `order_pool_by_live_cost` (forwarder.py:291-306). **Cost-ranking is closed. Leave it alone.**
- **Reference inputs (read, do NOT overwrite):** `prompts/drain-routing.md`, `prompts/meter-model-provider.md`, and the ticket `scope:` blocks in `/home/stack/charon-private/fleet/board/DRAIN-ROUTING.md.parked` + `DRAIN-THEN-PARK.md.parked` — those scope blocks are AUTHORITATIVE for operator decisions (#2 free-first-then-drain, #24-29 NeuralWatt/OpenRouter fast-path, sole-leg guard).
- **The gap you build:** the remaining-BALANCE dimension (starting_credit − spend → drain-priority → park-at-0 → re-arm), which nothing does yet.

## ANTI-SPRAWL design constraints (hard)
- Remaining balance = **`starting_balance` (from config) − provider spend from the EXISTING observer meter** (sum `all_model_provider_costs()` per provider). **Do NOT stand up a parallel per-provider decrement ledger** — one spend source, not two.
- Reuse `BalanceTracker`'s existing **poll adapters** (deepseek `/user/balance`, openrouter `/credits`, nanogpt `/check-balance`) with a TTL cache (default 5 min) where a balance API exists; else fall back to `starting_balance − metered spend`.

## Build — internal sequence
1. **Config surface** (src/charon/config.py, `add_provider` ~L194-213 + load ~L177): add optional per-provider `providers.json` fields — `funding_class` (1=free-recurring, 2=flat-sub, 3=drain-then-park finite prepaid, 4=PAYG), `starting_balance` (USD), `mode` (`poll`|`fixed`), and poll `base_url`/`key_env`/`ttl`. Persist + reload; backward-compat (absent fields → provider inert, current behavior).
2. **Balance sensor** (src/charon/gateway.py `load_config` ~L185-208 + src/charon/balance.py): construct `BalanceTracker(config=…)` from `providers_cfg` and assign `GatewayConfig(balance_tracker=…)` (the one field left unset; already flows to the server via gateway.py:329 → proxy_server.py:567). Implement `remaining(provider)` per the anti-sprawl rule above.
3. **Drain routing** (gateway.py / proxy.py eligibility): order by funding class — **free-daily (1) FIRST, then drain finite credit (3), then flat (2), then PAYG (4)** (operator #2 free-first-then-drain; interim flat-before-credit only while credit legs are blocked, per ticket). Positive draining balance → top drain-priority within class; at ~0 → **pre-flight skip / exclude** (no fail-churn).
4. **Park lifecycle** (gateway.py / balance.py): a class-3 provider whose balance hits ~0 → **AUTO-PARK** (mark unavailable; routing skips it). **RE-ARM** to active on top-up (expose a console toggle surface). **HARD SAFETY — SOLE-LEG GUARD (non-negotiable):** never auto-park a provider that is the ONLY remaining leg of ANY pool — check pool membership before parking; if last leg, keep it (alert), never orphan the pool.

## Acceptance (FAIL-ON-REVERT)
- `tests/test_drain_then_park.py`: (1) class-3 provider at ~0 is auto-parked AND re-arms when topped up; (2) SOLE-LEG GUARD — a provider that is the only leg of a pool is NEVER parked. Reverting either invariant must fail its assertion.
- `tests/test_gateway.py`: `load_config` builds a non-None `cfg.balance_tracker` from provider config.
- Ordering tests (extend `tests/test_proxy.py` / add drain-routing test): free-first-then-drain, exclude-at-0.

## PROOF — green is NOT proof (real-traffic probe, the real deliverable)
Boot the gateway (`PYTHONPATH=src python3 -m charon.cli gateway --state-dir <tmp> --port <p>`; the `charon` shim is broken — use the module form). Configure a **fixed-mode class-3** provider with a small `starting_balance`. Drive real `/v1/chat/completions` requests until its balance → ~0; show it **AUTO-PARKS**, routing **skips** it, and there is **no fail-churn**; then top it up and show **re-arm**. Separately show a pool where the target is the **sole leg** is **NOT** parked. Paste the real before/after balances + routing decisions.

## LAST STEP (required)
- FULL gate (NOT pytest alone): `PYTHONPATH=src python3 -m charon.cli gate; echo $?` → must exit **0**.
- Commit all work on `feat/drain-and-park`; report the SHA.
- **Do NOT push. Do NOT merge. Do NOT open a PR.** (separate line, deliberate.)
- Write `/home/stack/charon-private/fleet/state/overnight/DRAIN-AND-PARK-REPORT.md`: diff summary, the real-traffic park/re-arm before/after, the sole-leg-guard proof, gate exit code, SHA. **Flag explicitly that the sole-leg guard needs adversarial review before merge.**
- Print `PACKET: fleet/state/overnight/DRAIN-AND-PARK-REPORT.md` + an ≤8-line honest summary. Real outputs only — never a fabricated SUCCESS line.
