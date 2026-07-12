# Branch Protection — charon (SLOP-Platform/charon)

## Required status check (operator action item)

The land scripts now REFUSE ON RED locally, but a CI-red merge can still slip through
if the manager's `gh pr merge` runs while CI is pending or flaky. Server-side branch
protection is the belt-and-braces enforcement the droid cannot apply itself.

### Settings to enable (GitHub → Settings → Branches → Add rule)

| Field | Value |
|---|---|
| Branch name pattern | `master` |
| Restrict pushes that create matching branches | ✓ |
| Require status checks to pass before merging | ✓ |
| Require branches to be up to date before merging | ✓ |
| Status checks (exact names — must match CI) | `ruff`, `mypy`, `gate` |
| Require linear history | (optional — off for now) |
| Include administrators | ✓ (enforce for everyone) |

### Exact required-check names

These must match what the CI workflow emits. Verify in the repo's Actions tab; the
check name is the **name of the job/step as shown in the PR's "Checks" panel**:

1. **`ruff`** — the `ruff check` step in `.github/workflows/ci.yml`
2. **`mypy`** — the `mypy` type-check step
3. **`gate`** — the `python3 -m charon.cli gate` step (or the product gate the CI runs)

If the CI workflow uses matrix jobs or custom names, update the three entries above
to match exactly. A mismatch silently disables the protection.

### Why this is needed

`land.sh` and `land-push.sh` now run the gate locally before merge/push, but:
- The manager's `gh pr merge` does not wait for CI to finish unless protection is on.
- A stale or cached local tree can pass the local gate while CI would fail.
- Branch protection makes the server reject the merge until all three checks are green,
  closing the last gap.

### Verification

After enabling:
1. Open a PR with a deliberate ruff error (e.g., unused import).
2. Wait for CI to go red.
3. Try `gh pr merge` — GitHub must reject it with a message naming the failing check.
4. Fix the error, re-push, wait for green, merge — must succeed.
