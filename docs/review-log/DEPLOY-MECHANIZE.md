# Review: DEPLOY-MECHANIZE
**Ticket:** DEPLOY-MECHANIZE (repo: charon-private, branch: feat/deploy-mechanize)
**Date:** 2026-08-04
**Session:** strong-2764845 (deepseek-v4-flash-ds)

## What was built (owns scope only)
- `fleet/checks/deploy-drift.sh` — deploy-drift detector. Compares THREE things (the ticket's rule,
  not two): the RUNNING container image, the compose PIN, and the latest published v* release;
  plus the named commits on master not in the deployed version. Verdicts: GREEN(0) when all three
  agree and master is within budget; RED(1) naming the evidence (BEHIND / downgrade hazard /
  ahead-count, with the undeployed commits listed) ; UNKNOWN(2) — never a false green — when any
  input cannot be read (host unreachable, empty lookup, no charon pin, missing product repo,
  deployed tag not a known ref). Every external read is bounded (timeout) and env-overridable.
- `fleet/tests/deploy-drift.test.sh` — hermetic, offline FAIL-ON-REVERT red-proof (24 assertions).
  Uses a local fixture git product repo + env-command overrides for the two ssh lookups; exercises
  the real script's own override seams, not a fixture bypass.

## Observed proofs (executed, not asserted)
- LIVE host (acceptance a): ran the real check against the deploy host. Reports the real deployed
  version: `RUNNING=v0.6.2 PINNED=v0.6.2 LATEST=v0.6.2 AHEAD=0` → GREEN, rc=0.
- Seeded RED (acceptance b + c): overrode RUNNING to v0.6.1 against the live latest — goes RED
  (rc=1), names the deploy lag AND the compose-pin mismatch, and lists the 16 undeployed commits
  including `1d675bc ... (D-012)`. So "D-012 is not deployed" is legible without reading git.
- Hermetic test suite: 24 passed, 0 failed (each assertion's RED path seeded + GREEN control).
- shellcheck: both files are clean under `-o all` (full rule surface); `shellcheck-ratchet.sh check`
  reports clean (no (file, SC-code) pair exceeds baseline — the two new files add zero findings).
- `bash -n` clean on both files.

## Out of owns (explicitly NOT done here)
The ticket's acceptance (d) status-board tile, (e) CI_SUITES allowlist entry in
`fleet/checks/rig-ci-scope.sh`, and the 20-min cron wiring live OUTSIDE this ticket's `owns:`
line (fleet/checks/deploy-drift.sh + fleet/tests/deploy-drift.test.sh only). Those files belong
to other tickets; per ownership rules they were not touched. The detector + red-proof are the
unit that makes the wiring ticket meaningful — the wiring must call this script and read
`DEPLOY-DRIFT: RUNNING= PINNED= LATEST= AHEAD=` + VERDICT/exit code. Until the rig-ci-scope.sh
allowlist entry lands, the red-proof suite will not execute in CI (the status-board honesty rule
will therefore render this gate UNPROVEN, which is correct — it must not render GREEN).

## Note on the product-repo dependency
The detector reads the deployed tag and compose pin from the deploy host (docker inspect + grep
over ssh), and the latest tag / master-ahead commits from the product repo checkout
(`CHARON_PRODUCT_REPO`, default `/home/stack/code/charon`). It does NOT need the deploy host to
have a git checkout — which is the whole point (the host pulls immutable images).
