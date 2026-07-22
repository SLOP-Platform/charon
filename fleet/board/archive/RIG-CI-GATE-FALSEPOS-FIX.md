tier: strong
repo: charon-private
work_class: ci-infra
difficulty: 3
branch: fix/rig-ci-substrate-gate-falsepos
owns: fleet/tests/rig-ci.test.sh, fleet/checks/substrate_first_gate.py, fleet/tests/substrate-first-gate.test.sh, fleet/tests/land-push-ci-gate.test.sh
depends_on:
substrate: N/A
substrate-novel: |
  This repairs the rig's OWN bespoke substrate-first gate and its fail-on-revert harness: an
  owns-collision false-positive that reds any adopt-ticket whose owned wrapper file is named after
  the adopted tool, plus a rig-ci fixture that omitted the gate scripts and false-redded four cases.
  No external linter, YAML tool or framework models "fix the false-positive in our own substrate-first
  gate", so this is the genuinely novel in-house slice with nothing off-the-shelf to adopt instead.

## Dependencies & sequence

No dependencies — a self-contained repair of two pre-existing rig gate bugs on their own files and
tests. Wave: rig-ci hardening. No other ticket writes fleet/tests/rig-ci.test.sh,
fleet/checks/substrate_first_gate.py, fleet/tests/substrate-first-gate.test.sh or
fleet/tests/land-push-ci-gate.test.sh, so it fans out collision-free and lands independently.
