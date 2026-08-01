repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/rescue-push-tool
owns: fleet/rescue-push.sh, fleet/tests/rescue-push.test.sh
serial_justified: |
  One sweep script plus its fail-on-revert suite. There is no second lane here — the whole point
  is that ONE tool owns the whole at-risk-branch classification, because every hand-typed variant
  so far has covered a DIFFERENT subset and each one silently left commits behind.
substrate: N/A
substrate-novel: |
  Checked four external candidates and three in-tree ones before writing a line. None covers the
  job, and the reason is the same in every case — they all handle the EASY half and abort on the
  half that actually loses work.
  git push --all origin (plain git, no install) genuinely covers the two simple shapes: a branch
  with no upstream and a branch ahead of its upstream both get published. What it does NOT do is
  the DIVERGED shape, and diverged is exactly where commits die. git rejects a non-fast-forward
  ref and moves on; the operator is then left with two options git itself offers, force (destroys
  the remote side) or merge by hand (not something a sweep may decide). It also fans out over
  every local ref including backup/*, sets no upstream, and has no dry-run that reports WHICH
  branches carry at-risk commits and how many.
  git-extras 7.1.0 is packaged and installable but ships no push-all-branches subcommand at all;
  its git-sync is a single-branch reset-to-remote helper that DISCARDS local commits, which is the
  precise opposite of a rescue. Rejected on merit, not on dependency cost.
  Forge CLIs (gh and equivalents) operate on PRs and remote refs. They have no notion of a local
  branch that has never been published, so the entire no-upstream class is invisible to them.
  In-tree, land-push.sh and land.sh are SINGLE-BRANCH LANDING paths — they gate, push, open a PR
  and merge ONE named branch. push-verify.sh is a prove-the-push library that a caller sources; it
  never enumerates anything. None of the three sweeps.
  The closest relative is fleet/checks/stranded-work.sh, and the distinction is the whole answer:
  stranded-work.sh DETECTS the class and its header states as a hard invariant that it must never
  gain an apply mode. This tool is the ACTING half that detection was deliberately kept out of.
  So the novel slice is the at-risk CLASSIFICATION across both repos plus the diverged-to-parallel
  rescue-ref policy — additive, never forcing, losing nothing on either side and leaving the merge
  decision to a human. That policy exists in no tool we found.
source: |
  PRIORITY-TODO.md section L — 96 commits on 47 local-only branches existed only on this box, and
  the fix for it was itself stranded. Measured live 2026-08-01: 47 branches rescued on the first
  run, then 50 MORE that the first narrow version had missed, then 4 diverged branches rescued to
  parallel refs. 0 lost.
note: |
  ## THE CLASS — WORK THAT EXISTS ON EXACTLY ONE DISK
  Every session ends with branches that were never published. Section L measured 96 such commits
  across 47 branches in a single sweep. The class recurs not because anyone forgets it matters but
  because the sweep is RETYPED BY HAND each time, and each hand-typed version covers a different
  subset. The first cut of this very tool queried only branches with NO upstream and therefore
  missed 50 branches that were simply AHEAD of an upstream — one of them 25 commits ahead.

  ## THE THREE SHAPES, AND WHY ALL THREE MUST BE IN ONE TOOL
  1. NO UPSTREAM — commits measured against origin/master. Invisible to any upstream-relative
     query. This is the class the narrow first version covered.
  2. AHEAD OF UPSTREAM — commits measured against the tracked upstream ref. This is the class the
     narrow first version MISSED, and it was the larger of the two.
  3. DIVERGED — local carries commits the remote lacks AND the remote carries commits local lacks.
     A plain push is rejected non-fast-forward. This is where a hand-typed sweep reaches for
     --force and destroys the remote side.
  A tool that covers two of three is how the class survived this long. Covering all three in one
  enumeration is the point.

  ## THE SAFETY PROPERTY — NEVER FORCE A DIVERGED BRANCH
  On a non-fast-forward rejection the tool pushes the local tip to a PARALLEL ref under rescue/*.
  That is purely additive — nothing on either side is overwritten, both histories survive, and the
  merge decision is left to a human at leisure. Rescue first, triage later. A rescue tool that can
  destroy the thing it is rescuing is not a rescue tool. This property is the one that MUST have a
  test, because it is the one whose violation is unrecoverable.

  ## SCOPE
  1. Enumerate every local branch in both tracked repos and classify it into the three shapes.
  2. Read-only by default. Mutation only under an explicit --push flag.
  3. Never delete, prune, rewrite or force. The only mutations are a normal push and a parallel
     rescue-ref push.
  4. Report per-branch: the shape, the commit count at risk, and the outcome. A silent failure
     sends the operator back to raw git push, which is deny-listed for manager sessions, so a
     failure must say WHY.
  5. Skip backup/* refs, which are snapshots and not work.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED
  Hermetic tests against throwaway local repos with a local bare remote. No network.
    a. NO-UPSTREAM branch carrying commits is detected and pushed. Revert the no-upstream arm to
       RED.
    b. AHEAD-OF-UPSTREAM branch carrying commits is detected and pushed. Revert the upstream arm
       to RED. This is the arm the first version missed, so it is the regression that matters.
    c. DIVERGED branch is rescued to a parallel rescue/BRANCH ref. Revert to RED.
    d. SAFETY, the critical one — a diverged branch is NEVER force-pushed. Assert the remote tip
       of the ORIGINAL branch is UNCHANGED after the run, and that the local-only commit is
       reachable from rescue/BRANCH instead. A test that only checks the rescue ref exists would
       still pass a tool that force-pushed first and rescued second.
    e. Dry run mutates nothing. Every remote ref is byte-identical before and after.
    f. A branch with nothing at risk is not touched at all.
  Report both counts, green with the tool intact and RED on each revert. A test that passes with
  the rescue arm removed is worthless.

  ## WHY PRIORITY 0
  Section L ranks this above the gate that would prevent it, because unpushed commits are the only
  failure on the board whose cost is UNRECOVERABLE. A missing gate lets a defect land; a lost disk
  loses the work outright.

## Dependencies & Sequence

- **depends_on: none.** This tool reads git refs and pushes. It imports no fleet module, sources
  no library and invokes no gate, so nothing has to land first.
- **Sequence: NOW, ahead of the detection-side work.** The rescue half is worthless after the fact
  and the tool is currently itself stranded — it exists only as a staged file in one checkout,
  which is the exact failure it was written to end.
- **Relationship to `fleet/checks/stranded-work.sh` (PR #361) — sibling, NOT a dependency.** That
  file DETECTS the stranded classes and its header forbids it ever gaining an apply mode. This one
  ACTS. Neither imports the other, so they can land in either order and are not a merge conflict.
- **owns-collision: none.** `fleet/rescue-push.sh` and `fleet/tests/rescue-push.test.sh` are both
  NEW paths owned by no other live ticket. Verified against the live board before claiming.
- **Blocks / unblocks:** unblocks a mechanical session-close sweep, which removes the standing
  need to hand-audit branches at every handoff.
- **Related, do NOT fold in:** `SESSION-END-GATE-REPAIR` (the session-end script self-blocks
  before its work-loss check) and any branch-reaper work. Both touch adjacent problems; this
  ticket is the push sweep only.
