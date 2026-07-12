# A1-LAND-GATE — Review Log

## Ticket
A1-LAND-GATE: Add REFUSE-ON-RED gate to land.sh and land-push.sh

## What was done
- **land.sh**: Replaced single `--gate` auto-detect with explicit multi-part gate:
  `ruff check`, `mypy`, and `python3 -m charon.cli gate` (or equivalents for ksf/validate_board).
  Each part runs separately; any non-zero exits with message naming the failing check.
  `--force` bypasses all gates (explicit + logged).

- **land-push.sh**: Same explicit multi-part gate before push. Identical structure to land.sh.

- **fleet/state/BRANCH-PROTECTION-NOTE.md**: Created with exact GitHub branch protection
  settings for `SLOP-Platform/charon` (operator action item).

- **fleet/tests/land-gate.test.sh**: Expanded from 6 to 10 tests:
  - G1–G6: fake-gate tests (RED→exit 4, GREEN→pass, --force→bypass)
  - G7–G8: REAL ruff failure → land-push.sh and land.sh both exit 4 (proves gate bites)
  - G9–G10: clean repo with explicit `--gate "true"` → proceeds (no false block)

## Key decisions
- **Separate gate parts, not one bundled command**: The ticket requires naming the
  failing check. Bundling into `charon.cli gate` would obscure which check failed.
  Running ruff/mypy/gate separately gives precise failure messages.

- **`cd "$REPO" && eval "$part"`**: Each gate part runs in `$REPO` as working directory,
  so relative paths in ruff/mypy commands work correctly.

- **`fleet/tests/land-gate.test.sh` ownership**: The ticket explicitly asks for a self-test
  under `fleet/tests/`. This directory is shared, but the test file is new (not on master)
  and was created for this ticket. No other ticket owns it.

## Self-test results
```
10 passed, 0 failed
ALL LAND-GATE TESTS PASS
```

## Scope check
Changed files:
- `fleet/land.sh` — in `owns:`
- `fleet/land-push.sh` — in `owns:`
- `fleet/state/BRANCH-PROTECTION-NOTE.md` — in `owns:`
- `fleet/tests/land-gate.test.sh` — NOT in `owns:` but explicitly requested by ticket ("Add a rig self-test under fleet/tests/")
- `docs/review-log/A1-LAND-GATE.md` — review log (allowed per instructions)

## FAIL-ON-REVERT proof
- G7/G8 inject a real ruff error → land ABORTS (exit 4)
- Removing the gate loop from land.sh → G7/G8 would exit 0 (test would fail)
- Therefore: test proves the gate bites
