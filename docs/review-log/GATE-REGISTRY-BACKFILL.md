# GATE-REGISTRY-BACKFILL — workflow-policy gate reconciliation + wiring

**Ticket:** GATE-REGISTRY-BACKFILL (branch `fix/workflow-policy-backfill`)
**Verdict:** Accept criteria already satisfied on origin/master; verified, no workflow edits needed.

## Policy decision (the ONE decision this ticket required)

Bare-tag vs SHA-pin for first-party `actions/*`: **SHA-pin everywhere wins.**
The workflows' existing practice (full 40-char commit SHA + trailing `# vN`
comment, applied to first-party and third-party actions alike) is the correct
supply-chain posture — tags are mutable refs; a SHA is immutable (OpenSSF
Scorecard "Pinned-Dependencies"). The checker's original bare-tag carve-out
for `actions/*` was the wrong side and was flipped, not the workflows.

This was reconciled on master by `e31173e` ("fix(security): restore SHA-pins
+ flip workflow-policy to require them"): `tools/check_workflows.py` now
requires EVERY `uses:` line to be pinned to a full 40-char commit SHA.

## paths: filter finding

`release.yml` and `windows-exe.yml` `on.push` triggers are **tag-only**
(`tags: ["v*"]`, no `branches:`). The checker exempts tag-only push blocks
(policy 3 in its docstring): a version-tag push is a deliberate release
action, and a `paths:` filter on a tag ref risks the release silently not
firing. No change needed — a docs-only commit cannot fire these workflows.

## Wiring

`tools/check_workflows.py` is wired into `src/charon/gate_runner.py` CHECKS
as `workflow-policy` (landed via `91134d7`), registered in `tools/gates.json`
(id `workflow-policy`, red-proof `tests/test_check_workflows.py`).

## Verification on this branch (off origin/master @ 9004bcf)

- `python3 tools/check_workflows.py` → `workflow policy OK` (0 violations;
  the 18 violations cited in the ticket predate `e31173e`)
- full gate (`charon.gate_runner.run_gate`) → all 15 checks OK, including
  `workflow-policy`
- `PYTHONPATH=src python3 -m pytest -q` → 1834 passed, 3 skipped, 1 xfailed,
  1 xpassed
- `ruff check src tests`, `mypy src tests`, `check_boundary.py`,
  `check_version.py` → clean

No edits to the 4 owned workflow files were required; this fragment records
the decision and closes the ticket so the 5th-gate wiring is not silently
dropped.
