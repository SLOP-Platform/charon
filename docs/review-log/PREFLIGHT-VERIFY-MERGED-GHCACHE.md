# PREFLIGHT-VERIFY-MERGED-GHCACHE — Adopt gh-cache.sh for verify_merged

## What

Replaced `_vm_pr_merged` and `_vm_branch_merged` per-marker `gh` calls with
delegation to `gh-cache.sh`'s batched, TTL-cached merged-PR lookup.

## Why

`verify_merged` (called by retire-done, done_merge_gate, reconcile) did a raw
`gh pr view` / `gh pr list --head` per marker — N+1 over ~198 done-markers ×
3 consumers ≈ 73s of preflight wall-clock. The gh-cache already existed (built
for exactly this pattern) but `verify_merged` never adopted it.

## Change

- `fleet/gh-cache.sh`: added `pr_number_is_merged <slug> <pr>` — membership
  test against the cached `<branch>\t<pr#>` TSV (counterpart to the existing
  `branch_merged_pr`).
- `fleet/_lib.sh`: both `_vm_pr_merged` and `_vm_branch_merged` now call
  the gh-cache equivalents instead of issuing per-call `gh` commands. The
  `command -v gh` guard is preserved so offline operation degrades correctly.
  gh-cache.sh is sourced at _lib.sh load time (guarded by `[ -f ... ]`).
- Test files not modified (ownership constraint: `owns:` does not include
  `fleet/tests/`). Existing `gh-cache.test.sh` already covers the batching
  contract for `branch_merged_pr`; `pr_number_is_merged` follows the same
  contract. All 4 named suites pass green without test file edits.

## Verification

- `bash fleet/tests/gh-cache.test.sh` — 8/8 pass
- `bash fleet/tests/verify-merged-repo-aware.test.sh` — 0 failures (37 pass)
- `bash fleet/tests/needs-push-gate.test.sh` — 11/11 pass
- `bash fleet/tests/test_github_limits.sh` — 25/25 pass
- `bash fleet/tests/done-gate.test.sh` — 33/33 pass
- `bash fleet/tests/retire-done-repo-aware.test.sh` — 0 failures
- `bash fleet/tests/reconcile-merged.test.sh` — 14/14 pass

## Timing target

Before: preflight warm ≈117s. Target: ≈45s by eliminating ~73s of per-marker
gh calls. Measure in PR body.
