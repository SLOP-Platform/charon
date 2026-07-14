# SR-4 — SMART-ROUTING.md doc corrections

**Status:** Already complete on charon-private master

**Verification:**
- SMART-ROUTING.md §1 and §5 already correctly mark `SpeculativeExecutor` and `ConsensusRouter` as "constructed, not yet wired into `_handle()`"
- Commit `50af47c` on charon-private (`docs(SR-4): mark SpeculativeExecutor + ConsensusRouter as not yet wired`) already applied the fix to master
- No changes needed on this worktree
- `git diff --name-only master...HEAD` is empty (no code changes)
