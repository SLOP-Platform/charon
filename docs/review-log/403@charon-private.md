# Review: 403@charon-private
**PR:** fix(gate-integrity): G5 INFLOW BASE lookup broken in git worktrees
**URL:** https://github.com/Nnyan/charon-private/pull/403
**Date:** 2026-08-02T05:30:17Z
**Reviewer:** reviewer-tab-2812490
**Author:** frontier-2788768

## Verdict
NEEDS-REVISION

## Findings
- HIGH — Catastrophic INFLOW misfire when the base ref is unavailable: the new block does `git ls-tree "${BASE_REF:-origin/master}"` and, on any failure, sets `base_unenf=()`, so every pre-existing red-proof suite is classified as NEW and INFLOW reds on all 101 suites. The v2 "worktree fix" only changed `[ -d .git ]` → `[ -e .git ]`; it does not handle a missing/unfetchable `origin/master`, which is the default state of shallow and single-branch CI checkouts (e.g. `actions/checkout` fetches only the PR head). The author's own state doc admits CI sets `RIG_CI_BASE` while the gate reads `BASE_REF` — so in CI the gate will red on day one and get disabled, exactly the fate the ticket warns about. There is no fallback to `HEAD~1` or the merge-base, and the fail direction is wrong for a gate whose base it cannot determine.
- HIGH — The "pre-existing bug fix" is a no-op and the real change is a ratchet loosening: `suites="$(_ci_suites || true)"` is command substitution, which runs in a subshell and captures stdout regardless of any `local suites` inside `_ci_suites`; the rename `suites`→`ci_suites` cannot change behavior, and `_ci_suites()` itself is not touched by this PR. Yet `GI_UNENFORCED_MAX` is raised 88→101 (+13) inside an ENFORCEMENT PR, a direction that a genuine allowlist fix (registered suites no longer counted) could only reduce. The "master accumulated 19 NEW findings" justification contradicts the +13 delta, and the 3 new G3 findings are explicitly NOT added to `GI_BASELINE`, so the claim "gate green on origin/master | 39 findings" is unverifiable — the gate should RED on those 3.
- MED — The primary done-contract ("gate REDs at authoring time") is never asserted via exit code: T19–T23 drive the gate through `_capture`/`run`, which grep output strings but discard `rc` (the function returns `rm`'s status, always 0). A gate that prints "G5 INFLOW"/"G5 BACKLOG" but always exits 0 would pass every new test. The old tests 1–15 check rc via `chk`; the new tests don't, and T24's "fail-on-revert" is a manual note, not a regression test.
- MED — Baseline key contract broken by the rename: the finding key `G5:unenforced-proof-suites` is renamed to `G5:unenforced-proof-ci_suites` and a new key `G5:new-unenforced-proof` is added, while `GI_BASELINE` (mechanically generated, "never transcribe by hand") is left unchanged and still references the old G5 aggregate. If the old key was baselined, the renamed BACKLOG finding is now unbaselined and will red whenever emitted; key renames must regenerate the baseline. The reentrancy comment ("executes exactly ONE external command") is also now false — the gate runs `git ls-tree`, `git show`, `grep`, and `basename`.
- LOW — Robustness/IFS: `for tb in $base_files` word-splits on whitespace, so a BASE test file whose name contains a space is dropped from `base_unenf` and fires a false INFLOW; filenames containing glob metacharacters also break the `case $'\n'"$ci_suites"$'\n'` membership match. The `.test.sh$` grep on ls-tree output and the missing-origin/master case mean the base set is computed silently wrong in several paths, all of which favor RED (gate disablement).

## Fail-on-revert check
Reverting this PR removes the INFLOW gate and returns the floor to 88, allowing new red-proof suites to enter `fleet/tests/` without CI registration — but until the base-ref-availability and floor-contradiction issues are fixed, the current gate is more likely to red-on-everything in CI and be disabled than to catch real inflow.

## Status
Pending Manager dispensation
