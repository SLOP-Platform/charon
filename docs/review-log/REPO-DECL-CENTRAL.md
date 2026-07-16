# REPO-DECL-CENTRAL — centralised repo path declarations

**Date:** 2026-07-15
**Status:** implemented

## Summary

Added `PRODUCT_REPO` and `FLEET_REPO` declarations to `fleet/_lib.sh` as the ONE
canonical source of truth for repo paths. Every rig tool that previously hardcoded
the product or fleet repo path now sources `_lib.sh` and uses these variables.

## Changes

- `_lib.sh`: added `PRODUCT_REPO` (default `$CHARON_PRODUCT_REPO`, overridable via
  `CHARON_PRODUCT_REPO`) and `FLEET_REPO` (default `$CHARON_FLEET_REPO`,
  overridable via `CHARON_FLEET_REPO`). Updated `_vm_repo()` to fall back to
  `$PRODUCT_REPO`.
- `handoff.sh`: sources `_lib.sh`; replaced `CHARON_REPO`/`PRIV_REPO` and all
  hardcoded fleet paths with `$PRODUCT_REPO`/`$FLEET_REPO`/`$FLEET`.
- `retire-done.sh`: `CHARON` now reads `$PRODUCT_REPO` (was already sourcing
  `_lib.sh`).
- `handoff-check.sh`: sources `_lib.sh`; `PRIV` reads `$FLEET_REPO`; product repo
  references use `$PRODUCT_REPO`.
- `land-needs-push.sh`: sources `_lib.sh`.
- `tests/repo-decl-central.test.sh`: fail-on-revert test that sets
  `CHARON_PRODUCT_REPO` to a temp path and asserts consumers target it.

## Root cause addressed

The product/fleet split was load-bearing but implicitly coupled — the product path
was redeclared across ~7 rig files with inconsistent names. This was the origin of
the recurring "wrong-repo" bug class (done-merge gate checked the product repo for
fleet tickets; the fleet handoff gate ran product-shaped checks in the fleet repo).
Centralising the declaration removes the whole class.
