# R46-BALANCE-WIRE — review log

**ticket:** R46-BALANCE-WIRE
**date:** 2026-07-13
**status:** authored, tests passing

## Decision / notes

The construction mechanism (`_build_balance_tracker` in `gateway.py:268-281` and
`balance_tracker=cfg.balance_tracker` in `build_server:353`) was already authored
— the code was written ahead of this ticket's activation. The ONLY missing link
was the FAIL-ON-REVERT test suite (`tests/test_balance_wire.py`).

### What was already in place

- `GatewayConfig.balance_tracker` field (gateway.py:143)
- `_build_balance_tracker(providers_cfg)` in `load_config` (gateway.py:245, 268-281)
- `build_server` passes `balance_tracker=cfg.balance_tracker` (gateway.py:353)
- Observer meter wiring for class-3 providers (gateway.py:357-362)
- `GatewayProxyServer` accepts and stores `balance_tracker` (proxy_server.py:502, 587)
- `BalanceTracker.record_spend` connected live in forwarder.py:556-557, :650-651

### What this ticket adds

- `tests/test_balance_wire.py` — FAIL-ON-REVERT test suite:
  1. `test_build_server_non_none_tracker_from_config` — asserts build_server
     forwards a non-None BalanceTracker from config, with correct starting_usd.
     FAIL-ON-REVERT: removing the wiring line makes this RED.
  2. `test_build_server_live_decrement_after_forwarded_cost` — verifies that
     record_spend on the wired tracker actually decrements remaining() for a
     non-class-3 fixed provider.
  3. `test_build_server_observer_wired_for_class3` — verifies the observer meter
     spend source wiring for class-3 drain-then-park providers: remaining()
     returns starting_usd minus observer-metered spend.
  4. `test_build_server_none_tracker_when_config_is_none` — backward-compat:
     build_server does not fabricate a tracker when the config carries None.

### Reviewer checklist (required per ticket)

- [ ] Confirm `build_server` reads the **real provider config** (via
  `_build_balance_tracker(providers_cfg)` in `load_config`, then
  `balance_tracker=cfg.balance_tracker` in `build_server`) — NOT a
  hardcoded/test-only tracker.
- [ ] Confirm the F29 module registry (`_MODULE_SPECS`) is the construction
  site — `load_config` builds modules via the registry loop AND builds the
  balance tracker from the same `providers_cfg` dict.
- [ ] No bespoke adapter for OpenCode Zen added (OPENCODE-GO-USAGE.md §1 —
  anomalyco/opencode#10448 still open, opencode-zen/go are CONFIG-ONLY
  mode:fixed).
