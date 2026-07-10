# Build session — #17: balance tracker module (DRAIN before move — module only)

You are a Charon build session (strong coder). Repo: `/home/stack/code/charon`.

## MANDATORY isolation (Fleet-Droid process — no exceptions)
1. `git worktree add /home/stack/code/charon-balance -b feat/balance-drain master`
2. Register on the session-bridge (repo:"charon"), claim this ticket, announce you OWN NEW file `src/charon/balance.py` + its tests. Work ONLY in `charon-balance`. Do NOT touch `proxy_server.py` or `gateway.py` — the routing wire-up is a DEFERRED follow-up.

## Scope — standalone module + clean API (no proxy wiring)
Goal: Charon should DRAIN a provider's prepaid balance before moving off it, so balances don't rot. Build the tracker; wiring comes later.
- NEW `src/charon/balance.py`. Two balance sources:
  1. **Poll adapters** where a provider exposes a balance API: DeepSeek `GET /user/balance`, OpenRouter `GET /api/v1/credits`, NanoGPT `POST /api/check-balance`. A small per-provider adapter returning remaining USD (or None if unsupported).
  2. **Spend-tracking** for dashboard-only providers (opencode-zen, Together, NeuralWatt): an operator-configured starting balance, decremented by `record_spend(provider, usd)` using the real `cost_usd` (SR-5b).
- Clean public API: `remaining(provider) -> float|None`, `record_spend(provider, usd)`, `should_drain(provider) -> bool` (positive balance → route-first), `is_drained(provider, floor=0.0) -> bool` (≈0 → demote/skip).
- Stdlib-only, thread-safe (`threading.Lock`), config-driven, OFF/inert unless configured. Per-reason counters like `quota.py`/`tool_repair.py`. Follow `response_normalizer.py` style.
- Tests (hermetic, injectable clock/http): config'd-balance decrement crosses to drained at ~0; unconfigured provider is inert; poll-adapter parse; drain/skip transitions.

## Gate + finish
Run BOTH `python3 -m charon.cli gate` AND `PYTHONPATH=src python3 -m pytest -q`. Commit to `feat/balance-drain`. **DO NOT push/PR** — Claude review + operator gate. Report branch + test counts + the public API. No fleet/SLOP/personal strings in `src/`. **D&S:** owns NEW balance.py only — fully disjoint from #6, #5, #19. Proxy wiring = later ticket.
