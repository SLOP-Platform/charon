# HANDOFF-PIPEFAIL — Fix the handoff.sh gate-masking bug

## Context
handoff.sh lines 59-60 run gates under `2>&1 | tail -3 || true`. This is the exact `| tail`
+ `set -e` masking pattern that handoff gotcha #14 warns about. The `|| true` defeats
`pipefail` and makes gate output non-fatal — a red gate (VERSION DRIFT, failing pytest) is
silently swallowed.

## Fix (build-rig, fleet repo)
In `/home/stack/charon-private/fleet/handoff.sh`, fix lines 59-60. Options:
(a) Capture the gate's own exit code before tail:
```bash
PYTHONPATH=src python3 -m pytest -q --no-header 2>&1 | tail -3 ; pytest_rc=${PIPESTATUS[0]}
ruff check src tests 2>&1 | tail -3 ; ruff_rc=${PIPESTATUS[0]}
[ $pytest_rc -ne 0 ] && echo "WARNING: pytest failed (rc=$pytest_rc)"
[ $ruff_rc -ne 0 ] && echo "WARNING: ruff failed (rc=$ruff_rc)"
```
(b) Drop `|| true` and let pipefail fail the script. (May be too aggressive for a
    handoff-generation script that should still produce output on gate failure.)
(c) Use `set -o pipefail` on those lines without `|| true`, but wrap in a subshell to
    avoid killing the whole script.

Recommended: (a) — capture exit codes, report warnings, don't kill the script (handoff.sh
should still generate output even if gates are red, but the output must NOT hide the
failure).

## Dependencies & sequence
No depends_on. Build-rig fix, not product.

## Gate
`bash /home/stack/charon-private/fleet/handoff.sh 2>&1 | grep -q "version OK\|VERSION DRIFT\|passed"`
