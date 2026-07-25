repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: fix/board-write-lock
owns: fleet/board-lock.sh, fleet/tests/board-write-lock.test.sh, fleet/hooks/pre-commit, fleet/retire-done.sh
depends_on: WORK-LEASE-WORKTREE-RESOLVE
real-dep: WORK-LEASE-WORKTREE-RESOLVE owns fleet/hooks/pre-commit (and fleet/work-lease.sh, which
  this ticket deliberately does NOT touch for exactly that reason). This ticket adds ONE dispatch
  line to fleet/hooks/pre-commit, so it is a shared-file HAND-OFF and must land after it. Not a
  logical prereq — a serialization of two writers on one file (BRIEF-PREAMBLE §9).
priority-justification: |
  P0 by the CG ladder — this is an active data-loss defect, not a hardening want. On 2026-07-24 it
  cost work TWICE in one day: (a) a sub's bare `git commit` swept another lane's staged
  `git mv board/X.md board/archive/X.md` out of the SHARED main-checkout index; (b) master was
  rebased under a live sub whose uncommitted WIP was then stashed+dropped by another lane and
  recovered only from a dangling commit. Board serialization today is an UNENFORCED CONVENTION
  ("you are the only board writer"), which is precisely the failure class.
serial_justified: ONE mechanism, not three surfaces. fleet/board-lock.sh is the lock; fleet/hooks/pre-commit is the single line that makes it ENFORCED rather than advisory; fleet/retire-done.sh is the producer of the staged residue the lock exists to stop being swept. Split any of them off and the remainder is inert or unenforced — a lock nobody must call is exactly the unenforced convention this ticket replaces.
source: operator directive 2026-07-24 (two board-write losses in one day)
note: |
  ROOT CLASS: shared mutable state with concurrent writers and NO lock. The rig already owns the
  answer — `flock` on fleet/state/lock, used by claim.sh:207, work-lease.sh, lease-enqueue.sh,
  review-pool.sh, sync-checkouts.sh — and board mutation is the ONE place it is not applied.
  The crux is that sub-sessions mutate fleet/board/*.md and fleet/state/ROADMAP.tsv by DIRECT FILE
  WRITE, not through a script, so there is nothing to flock. The choke point is therefore the
  COMMIT (the moment a board edit becomes shared state), enforced by the pre-commit hook that
  work-lease.sh already auto-installs into the git-common-dir (covers main checkout AND every
  linked worktree). [[board-writes-must-be-locked]]
scope: |
  Turn board mutation from an unenforced convention into a mechanized, fail-closed, locked
  choke point: fleet/board-lock.sh (ONE lock — reuses fleet/state/lock, forks no second lock),
  a pathspec-limited commit, master-moved detection, and pre-commit REFUSAL of any board-touching
  commit that did not come through it.
accept: |
  - fleet/board-lock.sh {acquire|release|status|steal|commit|pre-commit|paths}: every read-modify-
    write of the holder record runs under `flock -w N` on fleet/state/lock (the SAME lock file
    claim.sh uses). FAIL CLOSED: if the flock cannot be taken within the bound, REFUSE the write —
    never proceed unlocked.
  - PATHSPEC-LIMITED COMMIT (the concrete defect): `board-lock.sh commit` must use
    `git commit --only -- <paths>`, never a bare `git commit`. A bare `git commit` takes the WHOLE
    index and is what swept another lane's staged rename.
  - MASTER-MOVED DETECTION: the holder record pins the HEAD sha at acquire; commit REFUSES (loud,
    naming both shas) if HEAD moved under the holder rather than silently proceeding.
  - ENFORCEMENT, not request: fleet/hooks/pre-commit chains `board-lock.sh pre-commit`, which
    REFUSES any commit staging fleet/board/** or fleet/state/ROADMAP.tsv unless it carries the
    live holder token minted by `board-lock.sh commit`. An agent's own `git add`+`git commit` on a
    board file is refused with the exact command to use instead.
  - STALE LOCK: bounded by BOARD_LOCK_STALE_S (default 900s). A stale hold whose holder PID is DEAD
    is reclaimed LOUDLY (banner + append to state/board-lock.log) so the fleet can never deadlock;
    a stale hold whose holder is still ALIVE is REFUSED and requires an explicit
    `board-lock.sh steal <session> --force` — never silently stealable.
  - fleet/retire-done.sh must not leave a staged `git mv` sitting in the SHARED main-checkout index
    for another lane's commit to sweep: either commit the rename through board-lock.sh or perform a
    plain filesystem mv. (Producer side of the same defect.)
  - fail-on-revert test fleet/tests/board-write-lock.test.sh (matched by fleet/gate.sh's *.test.sh
    glob, hermetic under mktemp -d): TWO CONCURRENT WRITERS — one must block or refuse, and the
    LOSER must neither corrupt nor silently lose content; both exit codes asserted. Plus: bare
    board `git commit` REFUSED by the hook; `--only` scoping proven by asserting a foreign staged
    path is NOT swept into the board commit; master-moved REFUSED; flock-unavailable REFUSED
    (fail-closed); stale+dead reclaimed loudly; stale+alive refused. Revert each mechanism => RED.
  - bash fleet/validate_board.sh GREEN.
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder).
ds: |
  ## Dependencies & sequence
  Wave-1, P0. One dep (WORK-LEASE-WORKTREE-RESOLVE) and it is a SHARED-FILE HAND-OFF on
  fleet/hooks/pre-commit, not a build prereq — see real-dep. Everything else this ticket owns is
  new or uncontended (fleet/board-lock.sh, fleet/tests/board-write-lock.test.sh new;
  fleet/retire-done.sh unowned by any live ticket, verified by grep over fleet/board/*.md).
  DELIBERATELY OUT OF SCOPE (contended files, follow-up tickets required, do NOT fold in):
    * fleet/work-lease.sh — the natural host for these subcommands. Owned AND under live edit by
      WORK-LEASE-WORKTREE-RESOLVE (state/claims marker present; branch fix/work-lease-worktree-
      resolve @5d951e8 carries +57/-8 in work-lease.sh, with hunks at BOTH ends of cmd_pre_commit
      and in cmd_install/cmd_ensure — i.e. exactly the regions a board-lock subcommand needs).
      Two writers on one file is forbidden (BRIEF-PREAMBLE §9). Follow-up: fold board-lock.sh's
      subcommands into work-lease.sh once that branch lands, so the rig carries ONE lease script.
    * fleet/land.sh:341-342 — `git add "${LAND_STAGE[@]}" && git commit -q -m ...`. LAND-DIRTY-SCOPE
      scoped the `git add` but left the `git commit` BARE, so it still takes the whole index. This
      is the SAME class and the actual sweeper in failure (a). Owned by HANDOFF-GATE-NONBYPASSABLE
      and RECONCILE-WIRING. Fix is one line: `git commit -q --only -m "$MSG" -- "${LAND_PATHS[@]}"`.
    * fleet/checks/rig-ci-scope.sh CI_SUITES registration for the new test — owned by
      HANDOFF-GATE-NONBYPASSABLE. The test IS reachable now via fleet/gate.sh's *.test.sh glob.
