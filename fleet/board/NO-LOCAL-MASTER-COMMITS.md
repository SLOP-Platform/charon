repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: fix/no-local-master-commits
depends_on: SYNC-SCHEDULE
dep-kind: merge-order
real-dep: |
  real-dep: SYNC-SCHEDULE — MERGE-ORDER only, zero owns overlap. SYNC-SCHEDULE wires the EXISTING
  fleet/sync-checkouts.sh into SessionStart + preflight so local master never drifts stale. It has
  been PR-OPEN ~194h. Land it FIRST: this ticket removes the CAUSE of divergence, SYNC-SCHEDULE
  keeps local current afterwards. Either alone is half the fix.
owns: fleet/board-lock.sh, fleet/tests/board-write-lock.test.sh, fleet/retire-done.sh
serial_justified: |
  ONE invariant — "local master is a pure mirror of origin". The refusal, the ergonomic replacement
  that makes the refusal survivable, and the auto-archive residue that currently blocks the sync are
  the same guarantee. Ship the refusal alone and it gets BOARD_LOCK_BYPASS'd (the manager did exactly
  that this session); ship the ergonomics alone and divergence continues.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Model note: opencode silently falls back to the DEAD gpt-5.4 pool for any model not in
  opencode.json's charon provider list (36 of 2567). Verified listed AND funded 2026-07-31:
  deepseek-v4-pro, gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7, big-pickle.
source: |
  Operator 2026-07-31: "WHY do we keep allowing master and origin to constantly diverge?" — asked
  after watching the manager hit "REFUSING sync: DIVERGED" repeatedly across one session.
note: |
  ## DO NOT TOUCH land.sh's SYNC REFUSAL — IT IS A HARD-WON DATA-LOSS GUARD
  `fleet/board/archive/LAND-SH-SAFE-SYNC.md` (DONE) records WHY land.sh refuses to sync a dirty or
  diverged tree: *"land.sh's step-7 sync HARD-RESET the main checkout and DESTROYED uncommitted
  working-tree changes (a whole session's board bookkeeping wiped, 2026-07-13). It must NEVER
  destroy uncommitted work... Fast-forward only; abort loudly on divergence."*
  The manager nearly proposed a ticket that would have partly reverted this, having not read it
  first. **The refusal is CORRECT.** This ticket removes the divergence upstream so the existing
  FF-only sync always succeeds. Any change that makes the sync destructive is an automatic REJECT.

  ## FACTS (verified 2026-07-31)
  - Measured on the live rig: `behind=0 ahead=0` only AFTER the operator manually ran
    `git reset --hard origin/master`. Before that: repeated `behind=4 ahead=1`.
  - 13 of the last 20 commits on origin/master are PR merges; the manager made 10 board-hygiene
    commits in one session, each committed DIRECTLY onto local master in the main checkout.
  - THE MECHANISM: `board-lock.sh commit` writes onto local master -> a branch is cut from that tip
    -> `land.sh` opens a PR -> GitHub creates a MERGE commit. origin/master then holds the commit
    *wrapped in a merge*; local master holds it *bare*. Two histories for identical content, so
    local is simultaneously ahead and behind. **Divergence by construction, on every board commit.**
  - THE RATCHET: `retire-done.sh` auto-archives tickets on land, dirtying `fleet/board/`, which makes
    land.sh refuse the sync, which leaves the divergence in place for the next land to inherit.
  - The main-checkout guard today enforces only a MESSAGE PREFIX (`land:` or `board-hygiene`), not
    WHERE you are — so ten conforming commits each created divergence.
  - `BOARD_LOCK_BYPASS=1` exists and the manager used it this session. Any refusal added here will
    be bypassed the same way unless the ergonomic path is genuinely easier.

  ## FRAMING (hypothesis — TEST IT, overturn loudly if wrong)
  The manager believes the fix is: refuse board commits in the main checkout, provide a one-command
  worktree-commit-and-land replacement, and stop the auto-archive residue from blocking sync.
  **Unverified**: some main-checkout commits may be genuinely unavoidable (recovery, conflict
  resolution, the archive residue itself). If a blanket refusal is wrong, the answer may be a
  narrow allowlist plus a loud advisory — say so rather than forcing it.

  ## WHAT TO BUILD
  1. **Ergonomics FIRST** — one command that takes a board edit, commits it on a branch in a scratch
     worktree, and lands it. Must be no harder than today's `board-lock.sh commit`, or it will be
     bypassed. Build and prove this BEFORE the refusal.
  2. **Then the refusal** — `board-lock.sh commit` refuses a main-checkout target and prints the
     exact replacement command. **Advisory first, blocking second** — a gate that blocks the
     habitual path on day one gets disabled, and a disabled gate is not a gate.
  3. **Break the ratchet** — auto-archive residue must not leave the main checkout dirty in a way
     that blocks the next sync.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d` fixture repos, offline:
    a. a board commit made via the new path leaves local master FAST-FORWARDABLE (never diverged)
    b. the old path (commit on main-checkout master + land) is DETECTED — reproduce the divergence
       in a fixture and assert the check catches it
    c. ANTI-OVER-BLOCK: a legitimate main-checkout operation still succeeds (name it explicitly)
    d. auto-archive residue does NOT leave the tree in a state that blocks `sync-checkouts.sh`
    e. FAIL-CLOSED: if the check cannot determine which checkout it is in, it refuses rather than
       silently allowing
    f. land.sh's dirty/diverged sync REFUSAL still holds unchanged — red-proof that
       LAND-SH-SAFE-SYNC's guarantee is intact (a dirty fixture's uncommitted + untracked files
       both SURVIVE)
  Then run the real flow: make a board change through the new path, land it, and show
  `behind=0 ahead=0` with no manual reset.

## Dependencies & Sequence
  - Depends on: SYNC-SCHEDULE (merge-order only — land that first; it is built and PR-open).
  - Blocks: nothing, but every session pays a manual `git reset --hard` until it lands — and that
    reset is DENY-LISTED to the manager, so it costs an operator interrupt every time.
  - Related: LAND-SH-SAFE-SYNC (archived, DONE) — its guard must survive intact.
    SHARED-NAMESPACE-CONTENTION (#288) — same "shared mutable state, no isolation" family.

  ## ROOT CAUSE OF THE ARCHIVE RESIDUE — LOCATED AND REPRODUCED 2026-08-04 (manager)
  This ticket already scopes "the auto-archive residue that currently blocks the sync". Here is the
  exact line, so whoever takes it does not have to re-find it.

  `fleet/retire-done.sh` stages archived tickets with:
      [ -f "$dst" ] && ! git ls-files --error-unmatch "$dst" >/dev/null 2>&1 && { mv; git add; } \
        || { mv; echo "(already tracked)"; }

  `$dst` is the DESTINATION under board/archive/ and it is tested BEFORE the `mv`. On a first
  retirement that file does not exist, so `[ -f "$dst" ]` is FALSE and control always falls to the
  else branch — a bare `mv` with NO `git add`. The staging fix the block's own comment promises
  ("stage the new archived files immediately so the tree returns to clean") therefore NEVER RUNS,
  and every retirement leaves the tree dirty. That dirty tree is what blocks sync-checkouts.sh from
  fast-forwarding, which is this ticket's entire subject.

  MEASURED 2026-08-04: one sweep retired OUTCOME-TEST-OWED, TOOL-ENABLE-RATCHET and
  SHELLCHECK-RATCHET; all three printed "(already tracked)" on a FIRST move and all three were left
  UNSTAGED, forcing the manager to hand-land each retirement through worktree-commit-and-land.sh.

  SECOND BUG, same line: the `A && B || C` idiom runs C whenever the LAST command of the B block
  fails, so a failing `git add` silently re-runs `mv` on an already-moved file. Use if/else; the mv
  must happen exactly once.

  FIX: mv FIRST, then test whether `$dst` is tracked, then stage. Keep the "already tracked" message
  honest — it must print only when the file really was already tracked.
  ACCEPTANCE ADDITION: prove it by EXECUTING a real first-time retirement in a fixture and asserting
  the tree is clean afterwards; a first move must report "(staged)", never "(already tracked)".

  NOTE ON SEQUENCING: this ticket depends_on SYNC-SCHEDULE, which has been PR-OPEN ~194h. Until
  that lands, local master keeps going stale even after this fix.
