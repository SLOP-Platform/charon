# ADVREVIEW SALVAGE-GHCACHE — branch review: salvage/preflight-verify-merged-ghcache-wip

**Reviewer:** nomi-sunrider (charon/deepseek-v4-pro), 2026-07-27
**Branch:** `salvage/preflight-verify-merged-ghcache-wip` (6 commits ahead of merge-base, 57 files changed)

---

## VERDICT SUMMARY: **ABANDON**

The useful code change (`pr_number_is_merged` in `gh-cache.sh` + `_lib.sh` delegation) is
**already on master, byte-for-byte identical**. The remainder of the branch is 32 destructive
deletions of live infrastructure (fleet scripts, state docs, active board tickets) that
would nuke ~200KB of active fleet machinery. Nothing useful to salvage — the optimization
landed independently via squash-merge 68efdef or equivalent.

---

## 1. THE DELETIONS ARE REAL, NOT A DIFF ARTIFACT

Per the SOP: three-dot diff (`master...branch`) shows 57 files, +204/-3979.
The two-dot form (`master..branch`) inflates to 2,266 files due to `graphify-out/` JSON
artifacts — a diff artifact from being far behind master. The three-dot form is authoritative.

**32 files the branch would DELETE still EXIST on master:**

| File | Size on master | What it is |
|---|---|---|
| `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` | 53,877 B | Current workloop spike state doc |
| `fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md` | 31,419 B | Reconciliation gate design state |
| `fleet/flow-canary.sh` | 28,537 B | Flow canary script |
| `fleet/tests/flow-canary.test.sh` | 20,568 B | Flow canary test suite |
| `docs/review-log/WORKLOOP-INTEGRITY-STACK-SPIKE.md` | 7,127 B | Spike review log |
| `fleet/board/RECONCILE-WIRING.md` | 7,380 B | Active board ticket |
| `fleet/board/REVIEWER-TAB-POOL.md` | 5,805 B | Active board ticket |
| `fleet/board/RECONCILE-GATE-WIRED.md` | 5,609 B | Active board ticket |
| `fleet/board/RECONCILE-BOARD-PR-DONE.md` | 5,457 B | Active board ticket |
| `fleet/board/RECONCILE-REVIEW-GATE.md` | 5,423 B | Active board ticket |
| `fleet/board/archive/FLOW-CANARY.md` | 5,184 B | Archived ticket |
| `fleet/board/archive/GW-BRIDGE-2-METERING-SPEND.md` | 4,341 B | Archived ticket |
| `fleet/board/PREFLIGHT-VERIFY-MERGED-GHCACHE.md` | 4,094 B | Active board ticket |
| ... | ... | ... |
| **TOTAL** | **~200 KB** | **32 active files** |

Every one of these files is present and live on `origin/master`. The branch's deletions
are correct for the stale tree the branch was based on (the branch diverged before these
files were independently created/recreated on master). Landing it now would delete them
unconditionally.

---

## 2. THE USEFUL CHANGE IS ALREADY ON MASTER

The branch's purpose was to adopt `gh-cache.sh` batched lookups for `_vm_pr_merged` and
`_vm_branch_merged` in `_lib.sh`. Both changes are already identical on master:

### `fleet/gh-cache.sh` — `pr_number_is_merged()` function

```
# pr_number_is_merged <repo-slug> <pr-number> -> 0 if the PR is in the cached merged set, 1 if not.
# Pure local grep against the cached `<branch>\t<pr#>` TSV — ZERO gh calls.
pr_number_is_merged(){
  local slug="$1" pr="$2"; [ -n "$pr" ] || return 1
  _gh_merged_tsv "$slug" | awk -F'\t' -v p="$pr" '$2==p{found=1; exit} END{exit !found}'
}
```

==> IDENTICAL byte-for-byte on `origin/master:fleet/gh-cache.sh` lines 126-130.

### `fleet/_lib.sh` — delegation to gh-cache

Branch replaces per-marker `gh pr view` / `gh pr list --head` calls with:
```
_vm_pr_merged() -> pr_number_is_merged "$slug" "$1"
_vm_branch_merged() -> [ -n "$(branch_merged_pr "$slug" "$1")" ]
```

Plus sources `gh-cache.sh` via guarded `[ -f "$_GH_CACHE_LIB" ] && . "$_GH_CACHE_LIB"`.

==> ALL added lines are present on `origin/master:fleet/_lib.sh`. Verified by grepping
each `+` line from the branch diff against master content — 100% match.

### `docs/review-log/PREFLIGHT-VERIFY-MERGED-GHCACHE.md`

The review log exists independently on master (1,896 B). The branch adds its own version
(+42 lines). Both describe the same change. The master version is authoritative (already
landed); the branch version would conflict on merge but adds nothing new.

---

## 3. TESTS — proven by EXECUTING on master

All relevant test suites pass on master (where equivalent code already lives):

| Test suite | Result | Exit |
|---|---|---|
| `fleet/tests/gh-cache.test.sh` | 8 passed, 0 failed | 0 |
| `fleet/tests/verify-merged-repo-aware.test.sh` | 0 failures (37 checks) | 0 |
| `fleet/tests/done-gate.test.sh` | 33 passed, 0 failed | 0 |

The `gh-cache.test.sh` suite includes explicit coverage of `pr_number_is_merged`:
- Test (e): merged PR number -> exit 0
- Test (f): non-merged PR number -> exit 1
- Test (g): empty PR number -> exit 1
- Test (h): ZERO gh calls (poisoned PATH proof)

All pass. The optimization is working and verified on master.

---

## 4. BRANCH HISTORY: why this is listed as "unlanded"

Commit log shows `salvage(preflight-verify-merged-ghcache-wip)` as 6 commits ahead of
merge-base. But `git log master...branch` lists **hundreds of commits** (the branch
diverged very far back in history). The gh-cache optimization was independently rebuilt
and squash-merged to master (likely as part of another landing sweep). The branch's
commits are now stale — the useful content was recreated rather than cherry-picked.

The branch also carries ~200 board-hygiene commits that were correct at their time
(deleting tickets that HAD been completed) but are now destructive because those tickets
have been recreated or remain active on current master.

---

## 5. REWORK PATH (if operator still wants the performance gain)

The optimization already lives on master. If there were useful board ticket updates
mixed in:

- `fleet/board/GW-BRIDGE-2-METERING-SPEND.md` — branch moved it from `archive/` to
  `board/`, but master already has it in `board/` (not archive). No gain.
- `fleet/board/REVIEWER-DOGFOOD-REDS.md` — branch adds +49 lines; master has a
  different version. Would need manual review.
- `fleet/board/workloop-integrity-stack-spike.md` — branch modifies +34/-31; master
  has a different version. Worth inspecting separately.

None of these are critical enough to risk the 32 deletions.

---

## 6. NO GATE/CHECK ADDED — EXTERNAL RED-PROOF N/A

The branch does not add a new gate, check, or test. It modifies pre-existing plumbing
(`_lib.sh`, `gh-cache.sh`) whose equivalent is already on master and covered by existing
tests. No external red-proof is applicable to an ABANDON verdict.

---

=== SESSION REPORT v1 ===
TICKET:       REVIEW-SALVAGE-GHCACHE
SESSION:      nomi-sunrider | deepseek-v4-pro
STATUS:       DONE
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/ADVREVIEW-SALVAGE-GHCACHE.md
OWNS-OK:      yes
GATE:         n/a — read-only review
TESTS:        gh-cache: 8/0 · verify-merged: 37/0 · done-gate: 33/0 (run on master, equivalent code)
RED-PROOF:    n/a — branch adds no gate/check; equivalent code already proven on master
OBSERVABLE:   MET — diff comparison ran locally within the git repo
RAN:          gh-cache.test.sh (exit 0, 8/8), verify-merged-repo-aware.test.sh (exit 0, 37/0), done-gate.test.sh (exit 0, 33/33)
READ:         pr_number_is_merged identical on master; _lib.sh delegation identical on master; 32 delete-target files confirmed live on master; all + lines in branch _lib.sh/gh-cache.sh verified present on master byte-for-byte
BRIEF-ERRORS: none
BLOCKED-BY:   none
BUDGET:       ok
NEXT:         LAND=0 REWORK=0 ABANDON=1 UNSAFE=0
=== END REPORT ===
