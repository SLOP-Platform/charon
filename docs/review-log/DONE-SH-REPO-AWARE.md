# DONE-SH-REPO-AWARE review

## Change
`fleet/done.sh`: read `repo:` field from board file, map to GitHub slug, use
for `gh pr list` merged-PR lookup instead of hardcoded product repo.

## Files changed
- `fleet/done.sh` — repo-aware slug mapping (lines 71-80)
- `fleet/tests/done-gate.test.sh` — G4 tests (repo-aware + product fallback)

## Test verification
- `bash fleet/tests/done-gate.test.sh` — 33/33 pass
