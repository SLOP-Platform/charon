# BRANCH-TICKET-MAP — prior-art verdict (agen-kolar, 2026-07-24)

## VERDICT: `feat/work-lease-gate` is ALREADY LANDED ON MASTER, and is PARTIAL.
DO NOT rebuild it. DO NOT try to "land" it either — there is nothing to land.

Execution evidence:
- `git -C <TICKET-MAP-GATE wt @ origin/master 9055478> log --oneline -- fleet/work-lease.sh`
  returns exactly `e6eacea` and `6463b0f`. Both prior-art commits ARE master.
- `git diff --stat feat/work-lease-gate -- fleet/work-lease.sh fleet/tests/work-lease.test.sh
  fleet/hooks/ fleet/fleet-droid.sh` => only `fleet/hooks/session-start.sh | 9 +++`.
  The branch is 98 commits BEHIND master and carries no unique work worth landing.
  => The branch is a stale leftover. It should be DELETED, not landed.

## What the landed prior art actually does (verified by reading + running master's code)
- DISPATCH gate = "no SECOND builder on the same TICKET" (`acquire`/`dispatch` conflict branch).
  That is double-claim closure. It is NOT branch->ticket mapping enforcement.
- COMMIT gate = `cmd_pre_commit` refuses an unmapped worktree branch. This is the LATE refusal
  that cost four agents their finished work.
- `git rev-parse --git-common-dir` was used ONLY in `_hook_targets` (where to install hooks).
  It was NEVER used for the claims store.

## The two gaps it LEAVES (both reproduced by execution)
1. SPLIT CLAIMS STORE — still open. `WORK-LEASE-WORKTREE-RESOLVE` accept-1 was NOT satisfied by
   `5d951e8`. Proof run against the live rig:
     $ cd /home/stack/charon-private-wt/TICKET-MAP-GATE
     $ bash fleet/work-lease.sh acquire ZZ-PROOF-TICKET      -> rc=0 "leased"
     $ ls /home/stack/charon-private/fleet/state/claims/ZZ-PROOF-TICKET -> No such file
     $ bash /home/stack/charon-private/fleet/work-lease.sh check ZZ-PROOF-TICKET
                                                             -> "NO-LEASE" rc=1
   i.e. acquire SUCCEEDS and the hook still REFUSES. Root cause: `fleet/state/*` is .gitignored,
   so every linked worktree gets its own empty `state/claims/`, and `CLAIMS` was derived from
   `$FLEET` (the *running copy's* dir) instead of the git common dir.
2. NO CREATION-TIME ENFORCEMENT — nothing anywhere refuses an unmapped branch at worktree/branch
   creation. `fleet-droid.sh` only did `work-lease.sh bind ... || true` AFTER the worktree existed.

## What I built to close them (branch feat/branch-ticket-map-gate, TICKET-MAP-GATE worktree)
Extends existing files only — no new script (anti-accretion honoured).
- `fleet/work-lease.sh`
  * `_state_root()` resolves the claims store + lock from
    `git rev-parse --path-format=absolute --git-common-dir` (fallback: relative form, then
    `$FLEET` when not in a repo, so hermetic tests are unaffected). ONE store for main + all
    worktrees. Overridable via `WORK_LEASE_STATE_ROOT` for tests.
  * `branch_to_ticket [branch]` now takes an OPTIONAL branch arg (creation time has no HEAD yet)
    and searches BOTH the local `board/` and the shared (common-dir) `board/` — fixes stale-board
    false refusals in old worktrees without regressing sub-authored tickets.
  * `board_reachable()` — fail-closed precondition (no readable board => refuse).
  * NEW subcommand `guard-branch <branch> [context]` — the CREATION gate. rc 1 + loud stderr on:
    unmapped branch, blank branch, unreadable board. `WORK_LEASE_BYPASS` deliberately NOT honoured.
- `fleet/fleet-droid.sh` — dispatch loop now calls `work-lease.sh guard-branch "$branch"`
  immediately after reading the ticket's `branch:` field and BEFORE `p0_worktree_setup`
  (guard line 375 < create line 408). On refusal it releases the claim and moves on: no worktree,
  no model launch, zero wasted build.
- `fleet/tests/work-lease.test.sh` — extended (not a new file; matches gate.sh's `*.test.sh` glob)
  with assertions 11-17: mapped branch ALLOWED (non-vacuous), unmapped REFUSED + loud, blank
  REFUSED, no-board REFUSED, fleet-droid WIRED before creation + releases on refusal, and a REAL
  git repo + REAL linked worktree proving a worktree-side acquire writes the MAIN store and the
  main-side script (what the hook resolves to) agrees.

## Red-proof (executed, exit codes)
- All 25 assertions GREEN, exit 0.
- R4 revert `STATE_ROOT="$FLEET"`               -> 16,17 FAIL, exit 1
- R2 revert `cmd_guard_branch { return 0 }`     -> 12,13,14 FAIL, exit 1
- R3 revert: delete guard-branch call in droid  -> 15,15b FAIL, exit 1
- Live: `guard-branch` REFUSES (rc 1) feat/fixture-bypass-gate,
  salvage/preflight-verify-merged-ghcache-wip, feat/substrate-first-gate-v2,
  feat/work-lease-gate, feat/branch-ticket-map-gate — i.e. every one of the stranded branches
  would have been refused at creation.
- shellcheck -S warning on the 3 changed files: clean (only pre-existing SC2034 in fleet-droid.sh).
- `fleet/gate.sh`: 68 passed, 9 failed (pre-existing; the only named FAIL is PROMOTION-GATE
  selftest drift: UNIFIED-PLANE-CANARY-FRAMEWORK priority='9' not 0..5). Not touched.

## REMAINING (next session)
- A board ticket carrying `branch: feat/branch-ticket-map-gate` still does not exist (another sub
  owns fleet/board/*). Until it lands, this branch is itself unmapped.
- UNCOVERED PATH: a manager/subagent running bare `git worktree add` is still not gated — there is
  no scripted entry point for it. `leak_worktree_setup` was deliberately NOT gated: tests
  (leak-guard-salvage, worktree-leak-guard, test_droid_reap, dogfood-eval-guard) and
  benchmark/dogfood-eval.sh drive it with intentionally non-ticket branches, so a hard refusal
  there would break them. Options for next session: (a) a sanctioned `fleet/new-worktree.sh`
  wrapper that calls `guard-branch`, or (b) a `reference-transaction` hook (can actually ABORT
  branch creation, but fires on every ref update — high blast radius, needs careful scoping).
  `post-checkout` cannot refuse (git ignores its exit status) — advisory only.
- 10 stranded unmapped branches still need tickets or deletion (unchanged by this work).
