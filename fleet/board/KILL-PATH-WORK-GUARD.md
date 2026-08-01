repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: fix/kill-path-work-guard
owns: fleet/stop-worker.sh, fleet/reap-orphans.sh, fleet/kill-guard.sh, fleet/tests/kill-path-work-guard.test.sh
serial_justified: One guard plus the kill paths that must call it; landing the guard without wiring every path leaves the unguarded path as the one that loses work.
substrate: N/A
substrate-novel: |
  Nothing external applies. This asks "does THIS worktree hold uncommitted or unpushed work, and is
  it attributable to the droid I am about to kill" — a question about the rig's own worktree/claim
  topology. `git status --porcelain` is the primitive and is used directly; there is no library to
  adopt for the policy of refusing a kill.
depends_on: STOP-WORKER-GRACEFUL-EXIT
note: |
  OPERATOR DIRECTIVE 2026-08-01, verbatim: **"all/any droid kill paths MUST have a mechanized check
  for work that reviews and commits."**

  MEASURED THE SAME DAY, during this session's own close-out — this is not hypothetical:
    * A killed CATALOG-REFRESH-PERSIST droid left **+222/-40 uncommitted lines** in
      `src/charon/routing_policy/catalog_refresh.py`. It was found ONLY because the operator asked
      for a manual sync check afterwards. Rescued to
      `fleet/state/RESCUE-catalog-refresh-persist-WIP.patch`.
    * `fleet/state/OPERATOR-ACTIONS.md` held SEVEN escalations (#21-27) as an uncommitted local
      edit and would have been lost in the same sweep.

  THE GAP, verified: three kill paths exist — `fleet/stop-worker.sh`, `fleet/reap-orphans.sh`,
  `fleet/branch-reaper.sh` — and `grep -c 'status --porcelain|git diff|commit' fleet/stop-worker.sh`
  = **0**. Every kill path is BLIND to work in progress. Ad-hoc `kill`/`pkill` from a manager
  session (what this session used) is a fourth, entirely unguarded path.

  WHY A CLOSE-GATE IS NOT ENOUGH: a droid killed mid-ticket never reaches any close ceremony, and
  the manager may kill it without ever running a sweep. The check must live AT THE KILL, in the one
  place every path funnels through.
accept: |
  - A single `fleet/kill-guard.sh <worktree|pid>` that, BEFORE any signal is sent:
      * detects uncommitted tracked changes, untracked files matching the ticket's `owns:`,
        unpushed commits, and stashes in the target worktree;
      * REFUSES the kill (non-zero, loud, naming the files) when work is found;
      * offers/does the safe capture — commit on the ticket branch, or write a tracked rescue patch
        under `fleet/state/` — before allowing the kill to proceed.
  - EVERY kill path calls it: `stop-worker.sh`, `reap-orphans.sh`, `branch-reaper.sh`. A path that
    does not call it is the path that will lose the work.
  - An explicit, LOGGED override (`KILL_GUARD_BYPASS=1`) for a genuinely wedged process — loud and
    audited, never silent, never the default.
  - Fail CLOSED: if the guard cannot determine worktree state (path gone, git error), it REFUSES
    rather than assuming clean. An unknown state is not an empty state.
  - Manager-initiated ad-hoc kills are covered too: document the guard in
    MANAGER-OPERATING-RULES.md so `kill`/`pkill` on a droid is never issued bare, and add it to
    TOOL-INVENTORY.md's trigger index under "about to stop a tab/worker".
  - fail-on-revert tests: seed a dirty worktree -> kill REFUSES; clean worktree -> kill proceeds;
    bypass honoured and logged; unreachable worktree -> refuses. Externally red-proof, report both
    counts.

## SWEEPS MUST BE MECHANIZED — operator, 2026-08-01

*"your sweeps must be mechanized to be the ones that find things."*

Proven the same day, twice over:
- The manager hand-composed a work-loss sweep checking only "ahead of upstream". It found 1 branch.
  **It missed 47 local-only branches carrying 96 commits** — a whole loss class, invisible to that
  query shape. Only a second, differently-shaped hand query found them.
- Meanwhile **`validate_board.sh` ALREADY HAS the check** and reported it unprompted:
  `RED uncommitted-work: dirty tracked file '...catalog_refresh.py' — a session exited without
  committing.` The mechanized detector existed, was correct, and was simply not run AS the sweep.

**THE RULE:** a work-loss sweep must be a TOOL that is RUN, never a query composed in the moment.
An ad-hoc query encodes only the loss class its author happened to remember — which is why the
class that keeps costing us is the one nobody thinks to type.

Therefore this ticket must ALSO:
- Expose the guard as a standalone sweep (`fleet/kill-guard.sh --sweep`) covering EVERY loss class
  in one invocation: dirty tracked · untracked-matching-owns · unpushed commits · **branches with
  NO upstream at all** · stashes · detached HEADs — across BOTH repos and all worktrees.
- Reuse `validate_board.sh`'s existing `uncommitted-work` detector rather than writing a second
  one. Two detectors that disagree is worse than one that is incomplete.
- Be the thing `preflight.sh` and the session-close path CALL, so no session has to remember the
  query shape.
- The truncated-path bug in that RED is now its OWN ticket, VALIDATE-BOARD-PATH-TRUNCATION — a
  prose footnote inside another P0 was estimated at ~20% odds of ever being actioned.

## ENFORCE IT — block hand-written sweeps (operator-approved 2026-08-01)

Mechanizing the sweep is not enough if a session can still hand-compose one and miss a loss class.
Add a `PreToolUse[Bash]` hook (the mechanism ALREADY works on this box — the board-lock, work-lease
and dangerous-`rm` guards all blocked this session today) that REFUSES ad-hoc sweep shapes:
`git status --porcelain` inside a loop · `for w in .../charon*wt*` · `git for-each-ref … refs/heads`
· `rev-list --count origin/…` · bare `kill`/`pkill` targeting a droid.

**Every refusal MUST NAME THE APPROVED TOOL.** A bare "denied" sends the session hunting for a
workaround — that is precisely how `--force` habits form. The message should read:
*"Work-loss sweeps are mechanized — run `fleet/kill-guard.sh --sweep`. Composing your own query
encodes only the loss classes you remembered; that is how 96 commits were missed on 2026-08-01."*

HONEST LIMITS, state them in the implementation: the hook matches a command STRING, not intent, so
it will false-positive on legitimate one-off `git status` calls and a determined session can
rephrase around it. It raises the cost of the wrong path and makes the right one the default — it
is not a proof. That is still the right trade: today's failure was not defiance, it was the manager
not remembering the tool existed.

## Dependencies & Sequence

- **depends_on: (none).**
- **Sequence: HIGH — same lane as the §L work-loss root class.** It is the missing half: §L's gate
  catches loss at session close or on a cadence; this catches it at the moment of the kill, which is
  when it actually happens.
- **Blocks / unblocks:** makes tab teardown safe, which is a precondition for running many tabs
  aggressively — the throughput model this fleet depends on.
- **owns-collision:** `fleet/stop-worker.sh` is also owned by STOP-WORKER-GRACEFUL-EXIT — this
  ticket now `depends_on` it and rebases onto its landed version. `fleet/kill-guard.sh` and the test
  are new files.
