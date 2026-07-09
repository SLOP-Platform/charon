# DRAIN-ROUTING — Balance-aware drain-before-move routing

## Context
The 2026-07-04 gpt-5.5 incident showed that the gateway routes to providers without
knowing their balance. opencode-zen ($2.99 depleted), OpenRouter (no credits), and
opencode-go (model not in catalog) were all ranked ahead of NanoGPT (working, $12/mo
flat). DRAIN fixes this by making the gateway balance-aware.

## Operator-approved design (2026-07-04 decisions #1-2, #24-29)
- Two mechanisms: (a) poll balance APIs where they exist; (b) operator-configured starting
  balance + auto-decrement via cost_usd for dashboard-only providers.
- Priority: free daily tiers BEFORE prepaid drain balances (free-first-then-drain).
- NanoGPT stays primary unless a specific drain fast-path applies.
- NeuralWatt: HIGH PRIORITY — drain 6kWh limit before 2026-07-22, then PAYG. Narrow
  fast-path first, then fold into broader DRAIN. May update production routing immediately
  after verification.
- OpenRouter: included in same fast-path. Treat as prepaid/drainable ($10 deposit + 1000
  free RPD).

## Implementation

### Phase 1: NeuralWatt/OpenRouter fast-path (narrow, before 7/22)
- Add a `balance` field to providers.json entries (operator-configured starting_balance).
- Add a `balance_api` field for providers with real APIs (OpenRouter /credits).
- In the gateway sort (`gateway.py:109-139`), add a drain-priority tier: providers with a
  positive draining balance get sorted ahead of their normal cost_rank position, but AFTER
  free daily tiers.
- Auto-decrement: on each successful response, subtract cost_usd from the provider's
  balance. At ~0, demote/exclude.
- For NeuralWatt: set starting_balance to the remaining 6kWh equivalent in USD, mark as
  `cost_class: expiring`. For OpenRouter: poll /credits, mark as `cost_class: prepaid`.

### Phase 2: Broad DRAIN (after fast-path is verified)
- Add balance polling for DeepSeek (/user/balance), NanoGPT (/check-balance).
- Generalize the drain-priority tier to all providers with balance data.
- Add a `charon balance show` CLI command to surface current balances.
- Add a `charon balance set --provider X --amount Y` CLI command for dashboard-only
  providers.

## Dependencies & sequence
- depends_on: SR-5b (cost_usd is real and merged), INC-401-FAILOVER (401 fix must land first).
- Phase 1 (NeuralWatt/OpenRouter fast-path) can land independently of Phase 2.

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_proxy.py tests/test_gateway.py -v -q ; ruff
check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
