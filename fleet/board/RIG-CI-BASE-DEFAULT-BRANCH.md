repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: fix/rig-ci-base-default-branch
owns: fleet/land-push.sh, fleet/tests/rig-ci-base-default-branch.test.sh
serial_justified: One base-ref selection fault in a single land-push block plus its fail-on-revert test.
substrate: N/A
substrate-novel: |
  This is a POLICY choice inside our own gate, not a capability anyone ships. The change is a
  three-line base-ref selection in fleet/land-push.sh; nothing is being built that a library
  could provide, and no new dependency is introduced.

  Closest external candidates, and why none covers it:
    * `git` itself — already the substrate and used unchanged (`git rev-parse` / the existing
      ref-probe loop). Nothing here re-implements a git primitive, so this is not an
      adopt-vs-build decision at all. Deliberately NOT filed as an EVAL-REGISTRY adoption row:
      git is the VCS the rig runs on, not a candidate under consideration.
    * `gh pr diff` — cannot serve as the base: land-push runs BEFORE any PR exists on a branch's
      first push, so the gate would have no base exactly when it is most needed.
    * `git diff @{upstream}` / any "diff vs tracking branch" convention — that IS the defective
      behaviour being fixed, not an alternative to it.
    * CI diff-scoping tools (dorny/paths-filter, tj-actions/changed-files, pre-commit's
      `--from-ref/--to-ref`) — all take the base ref as an INPUT. They would inherit the same
      wrong base; choosing the base correctly is precisely the part they delegate to the caller.

  The novel slice is the rig-specific invariant: a ticket-OWNERSHIP question must be asked against
  the DEFAULT BRANCH, because that is the only ref where the board lives. No external tool encodes
  "this repo keeps its ticket board on master, so ownership diffs must resolve there."
depends_on:
note: |
  Running-list item 12, previously NO TICKET. Concrete repro captured 2026-08-01 while landing
  LAUNCHER-GATE-SETE-KILL.

  `fleet/land-push.sh:160` picks the diff base for the scoped board check by trying, in order:
      origin/$_DSTG, origin/master, origin/main
  where `$_DSTG` is the DESTINATION BRANCH. For a feature branch that means the branch's own
  remote-tracking ref is preferred.

  Consequence — the gate's verdict depends on whether the branch has been pushed before:
    * FIRST push of a branch: `refs/remotes/origin/<branch>` does not exist -> falls through to
      origin/master -> the full branch diff is checked -> the owning ticket on master IS found ->
      GREEN.
    * SECOND push of the SAME branch: that ref now exists -> the base is the branch's OWN previous
      tip -> the diff is only the incremental commit -> a commit that touches just code emits
      "this change touches CODE owned by NO live board ticket" even though the ticket is on
      master and plainly owns those files. FALSE RED.

  The board/substrate/ownership questions are inherently "does the board on the DEFAULT BRANCH
  cover this change". Answering them against the branch's own previous tip is a category error:
  the board is never in that ref.

  This is the same stale-base fault class as #338 (which fixed land-push's OTHER scope) — the
  handoff's chain defect #1 recorded that `rig-ci-scope.sh`'s substrate check "STILL" had it.
  This is that instance, with a reproduction.

  BLAST RADIUS: every incremental push of every feature branch in the rig. It trains operators to
  reach for `--force` (which bypasses the gate wholesale) to land legitimate work — the exact
  habit FORCE-PUSH-SAFETY-GATE exists to prevent.
accept: |
  - The scoped board check resolves its base to the DEFAULT BRANCH (origin/master, or origin/main
    where that is the default), NOT to the branch's own remote-tracking ref, whenever the
    destination is not itself the default branch.
  - Pushing the same feature branch TWICE yields the SAME board verdict; the second push does not
    invent a "code owned by NO live board ticket" RED for code a master ticket owns.
  - Pushing to master itself is unchanged (base is still origin/master).
  - The existing fail-closed behaviour is preserved: if NO base ref resolves at all, the gate
    still refuses (exit 4) rather than checking zero tickets and reporting GREEN.
  - fail-on-revert proof in fleet/tests/rig-ci-base-default-branch.test.sh, externally red-proofed.

## Dependencies & Sequence

- **depends_on: (none).** Self-contained: one base-selection block in land-push.sh plus its test.
- **Sequence: EARLY.** It gates the ability to land any multi-push branch cleanly, so it should
  land before a wave of tabs starts producing branches that need more than one push.
- **Blocks / unblocks:** unblocks incremental pushes rig-wide; removes the standing incentive to
  reach for `land-push --force`, which is what FORCE-PUSH-SAFETY-GATE (P0) is defending against.
- **owns-collision:** none. `fleet/land-push.sh` carries no `owns:` on any live ticket
  (RELEASE-PRESERVES-WORK, AUTOLAND-DEFAULT-BRANCH-FIX, FORCE-PUSH-SAFETY-GATE, LAND-SH-POSTMORTEM
  and STRANDED-WORK-AUDIT only MENTION it in prose). Verified 2026-08-01 via
  `grep -H '^owns:.*land-push' fleet/board/*.md` = no matches.
