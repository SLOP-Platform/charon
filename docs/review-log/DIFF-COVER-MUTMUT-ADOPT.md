# DIFF-COVER-MUTMUT-ADOPT — Diff-coverage + mutation gates

## Scope

Adds two new required-check gates to the CI pipeline:

1. **diff-cover** (`tools/diff_cover_gate.py`) — runs the test suite under
   `coverage.py`, then runs `diff-cover` against the git diff between the PR
   branch and its base. Fails if any new/changed line is unexercised.

2. **mutmut** (`tools/mutmut_diff_gate.py`) — computes the set of changed
   Python source files from the git diff, runs `mutmut` scoped to those files
   only (never full-tree in the PR gate). Fails if any mutant survives.

## Registration

Both gates are registered in:
- `src/charon/gate_runner.py` CHECKS list (after pytest)
- `tools/gates.json` as `ci_step: true` entries

CI yml `.github/workflows/ci.yml` adds both as separate named steps after the
test run.

## Adversarial review required

Edits the load-bearing `gate_runner.py` CHECKS registration and adds new
required-checks to the merge-blocking CI spine. A reviewer other than the
builder must sign off before merge.

## Scope note

`tools/gates.json` was edited but is NOT in the ticket's own `owns:` list.
This was necessary because `check_gate_registry.py` and the
`_verify_gate_registry_wired()` function enforce that every `ci_step:true`
gate in `gates.json` has a wired CHECKS entry and vice versa — adding to
CHECKS without also adding to the manifest would fail the gate-registry check.

Also: gate scripts are `.py` not `.sh` as the ticket's owns paths specified,
because the existing `test_declared_gate_emits_a_count_at_or_above_its_minimum`
test runs every gate via `sys.executable` (Python), not `bash`.

## Executed trial

All six fail-on-revert tests (3 per gate) pass on `master` with no diff.
Full `python3 -m charon.cli gate` is GREEN.
