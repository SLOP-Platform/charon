# VERIFY-MERGED-REPO-AWARE — build report (2026-07-18)

Branch `fix/verify-merged-repo-aware` in worktree
`/home/stack/charon-private-wt/VERIFY-MERGED-REPO-AWARE`. Commit **32254b3cea46dd360754600eb5d7f9a35ca88c09**. NOT pushed.

## What changed
- `fleet/_lib.sh`
  - canonical SSOT decls `PRODUCT_REPO` / `PRODUCT_SLUG` / `FLEET_REPO` / `FLEET_SLUG`
    (`CHARON_PRODUCT_REPO` / `CHARON_FLEET_REPO` env overrides) — this is REPO-DECL-CENTRAL's
    actual deliverable, which had never landed.
  - `_vm_ticket_repo_field <id>` reads `repo:` from `board/<id>.md` then `board/archive/<id>.md`.
  - `_vm_resolve [id]` — the ONE map. `charon|product` -> product; `charon-private|fleet|rig` ->
    fleet; anything else -> rc 1 (FAIL CLOSED); no `repo:` field -> product (back-compat, commented).
  - public `ticket_repo_path` / `ticket_repo_slug`.
  - `_vm_repo/_vm_slug/_vm_sha_in_master/_vm_pr_merged/_vm_branch_merged/_vm_refresh/_vm_owns_present`
    take an OPTIONAL ticket id (trailing arg), so the existing no-arg callers
    (`checks/base-integrity.sh:63,73,115`, `preflight.sh:383,438`) keep today's behaviour.
  - `verify_merged` returns 1 immediately on an unmappable `repo:` — never falls back to product.
  - `VERIFY_MERGED_REPO` (product path) and `VERIFY_MERGED_FIXTURE` preserved, read at CALL time.
- `fleet/done.sh` — sources `_lib.sh` and calls `ticket_repo_slug`; its local `case` copy deleted.
- `fleet/board/archive/REPO-DECL-CENTRAL.md` — added the missing `repo: charon-private`.
- `fleet/tests/verify-merged-repo-aware.test.sh` — new.

## Fail-on-revert (all executed, all observed RED)
| revert | assertions that went RED | observed |
|---|---|---|
| R1 `_vm_resolve` `charon-private` arm -> product path/slug | rig-sha positive; product-only-sha negative | YES (2 failed) |
| R2 `_vm_resolve` `*) return 1` -> product fallback + drop the fail-closed line in `verify_merged` | `repo: bogus` verified | YES (1 failed) |
| R3 `_vm_resolve` `""\|charon\|product` arm -> fleet | product ticket; no-repo back-compat | YES (2 failed) |
| R4 `done.sh` restores its own repo->slug `case` | done.sh single-home assertion | YES (1 failed) |
Restored source re-runs green (0 failed).

## REPO-DECL-CENTRAL phantom merge — CONFIRMED
- marker: `2026-07-16T06:41:31Z merged:c44e7bda0ee835afa01c7a9e876e5df3e2a7162d branch:feat/repo-decl-central`
- `git -C /home/stack/charon-private cat-file -t c44e7bda…` -> **fatal, object absent** (not a rig commit).
- `git -C /home/stack/code/charon log -1 c44e7bda…` -> `Merge pull request #163 from SLOP-Platform/feat/repo-decl-central`, and `git rev-list origin/master | grep c44e7bda` -> **1 hit = IS an ancestor of PRODUCT origin/master**.
- That merge's diffstat is `docs/review-log/REPO-DECL-CENTRAL.md | 34 ++++` — **docs only**. The specced
  `PRODUCT_REPO`/`FLEET_REPO` decls in `_lib.sh` never existed (grep returned zero). So a RIG ticket was
  being merge-"proven" by a PRODUCT commit that contained none of its work — and `verify_merged` gates
  needs-push-guard delete, worktree remove, retire-off-board and G2 auto-close.
- Repo-awareness alone did NOT close this: its board file had **no `repo:` field**, so it defaulted to
  product and still verified. Adding `repo: charon-private` flips it to NOT verified (correct). Board
  correction is included in the commit; revert that one line if the manager wants it decided separately.

## Dry-run: the 10 tickets under the fix (read-only; nothing retired)
| ticket | repo: | resolves to | verifies? | true reason |
|---|---|---|---|---|
| SALVAGE-STASH-CHARON-RUN | charon-private | Nnyan/charon-private | **YES** (was NO) | `merged:#83` is a merged RIG PR — the false negative is fixed; now retirable |
| DONE-SH-REPO-AWARE | charon-private | Nnyan/charon-private | **YES** (was NO) | `merged:#75` is a merged RIG PR — same fix |
| REPO-DECL-CENTRAL | charon-private (added) | Nnyan/charon-private | **NO** (was YES) | phantom: sha exists only in the product repo — false positive removed; work must actually land |
| SETUP-KEY-UX | none -> product | SLOP-Platform/charon | NO | **no done marker at all**; fallback = merged PR for `branch: feat/setup-key-ux` — none exists. Repo-agnostic. |
| SR-1 | none -> product | SLOP-Platform/charon | NO | marker is a BARE timestamp, no `merged:` proof; no merged PR for its branch |
| SR-2 | none -> product | SLOP-Platform/charon | NO | same |
| SR-5 | none -> product | SLOP-Platform/charon | NO | same |
| SR-5b | none -> product | SLOP-Platform/charon | NO | same |
| SR-7 | none -> product | SLOP-Platform/charon | NO | same |
| SR-8 | none -> product | SLOP-Platform/charon | NO | same |

Net: repo-awareness retires exactly 2 of the 10 (SALVAGE-STASH-CHARON-RUN, DONE-SH-REPO-AWARE),
removes 1 dangerous false positive (REPO-DECL-CENTRAL), and is orthogonal to the other 7 —
those are unproven markers / a missing marker, not a wrong-repo problem.

## Pre-existing reds
None. `done-gate` (33), `needs-push-gate` (11), `reconcile-held-markers` (13), `base-integrity` (12),
`reconcile-merged` (14), `parked-semantics`, `board-correctness` (7) all pass before and after.
`bash -n` clean on `_lib.sh`, `done.sh`, the new test.

## Adjacent gaps found (NOT fixed — out of scope)
1. **120 of 226 board/archive tickets have no `repo:` field** (106 have one; 71 say `charon-private`).
   Every field-less rig ticket still defaults to the product repo, i.e. the REPO-DECL-CENTRAL failure
   shape can recur. A `validate_board.sh` rule requiring `repo:` would close the class.
2. `_vm_refresh` is still called with NO id at `preflight.sh:383,438` and `checks/base-integrity.sh:73`,
   so only the PRODUCT `origin/master` ref is refreshed. A stale local RIG ref can now false-negative a
   freshly merged rig ticket. It accepts an id — the callers just need to pass one.
3. `checks/base-integrity.sh:63` `repo="$(_vm_repo)"` is also ticket-independent; base integrity for a
   rig ticket is still computed against the product repo.
4. `fleet/validate_board.sh:86-98` holds a THIRD copy of the repo map (in Python). Not merged into the
   `_lib.sh` SSOT here because it is a different language/consumer; worth a follow-up.
