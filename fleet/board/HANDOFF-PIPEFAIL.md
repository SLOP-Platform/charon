tier: economy
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/handoff-pipefail
depends_on:
owns: /home/stack/charon-private/fleet/handoff.sh
accept: bash /home/stack/charon-private/fleet/handoff.sh 2>&1 | grep -q "version OK\|VERSION DRIFT\|passed"
prompt: /home/stack/charon-private/prompts/handoff-pipefail.md
scope: BUG 2 of handoff gotcha #14. handoff.sh lines 59-60 run gates under
  `2>&1 | tail -3 || true` — this is the exact `| tail` + `set -e` masking pattern the
  handoff warns about. Even though handoff.sh has `set -euo pipefail` at line 14, the
  `|| true` on those lines defeats the pipefail and makes the gate output non-fatal. A red
  gate (VERSION DRIFT, failing pytest) is silently swallowed. Fix: either (a) capture the
  gate's own exit code before tail: `pytest ... ; pytest_rc=$? ; ... | tail -3 ; exit $pytest_rc`,
  or (b) drop the `|| true` and let pipefail fail the handoff script on a red gate, or
  (c) use `set -o pipefail` explicitly on those lines without `|| true`. Build-rig fix,
  not product. Suggested agent: glm-5.2 (economy) — one-line shell fix.
