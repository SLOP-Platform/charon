# BUILD-SERVER-EPHEMERAL-PORT

**Date:** 2026-07-13
**Class:** test-fragility
**Tier:** economy

## Summary

Tests that call `build_server` could bind a fixed port (8080), causing
`OSError: [Errno 98] Address already in use` on the shared 4-LOM runner.

## Change

1. **`gateway.py`**: Added optional `port` keyword-only parameter to `build_server()`
   (default `None` → uses `cfg.port`). When `port=0` is passed, the server binds
   an OS-assigned ephemeral port, avoiding collisions.

2. **`test_module_registry.py`** (new): Tests that:
   - Exercise `_module_inst` for all configured module types
   - Prove `build_server(port=0)` binds ephemerally
   - Run two servers concurrently on port 0 → no collision
   - Pre-bind port 8080 and start ephemeral servers → no error (FAIL-ON-REVERT)
   - Run back-to-back builds with pre-bound port 8080 (GREEN-IS-NOT-PROOF)

## Decision

Threading a `port` param through `build_server` preserves backward compatibility
(default unchanged) while giving tests an explicit override point. The module
registry tests serve as a canary — reverting to a hardcoded port turns the
pre-bound-8080 test RED.
