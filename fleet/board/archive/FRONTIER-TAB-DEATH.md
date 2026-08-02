repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/frontier-tab-death
owns: fleet/preserve-unpushed.sh, fleet/tests/preserve-unpushed.test.sh
serial_justified: One ordering fix in cleanup() plus the step it calls and its fail-on-revert test; splitting them would land a fix with no proof.
substrate: N/A
substrate-novel: |
  N/A because the durability engine is git itself — "does this commit exist anywhere but this
  disk" is `git rev-list --count HEAD --not --remotes`, and preserving it is `git push -u origin
  <branch>`. No durability layer, sync daemon, mirror or backup library is being hand-rolled or
  displaced; there is no third-party candidate to weigh, because the only thing being added is
  WHEN we ask git that question.
  shellcheck — CONSULTED, already adopted and wired, and it has a live EVAL-REGISTRY row for this
  exact class (the `set -e` tab-kill row, 2026-08-01). Re-verified here: `-S warning` is CLEAN on
  both new files. It cannot be the guard — there is no lint rule for "a worktree was torn down
  while its commits existed on one disk only", which is a runtime ordering fact about our own
  stand-down path, not a lint pattern.
  git-worktree hooks and `git maintenance` were the established alternatives considered for
  "preserve before teardown" and rejected on evidence: neither fires at the moment this launcher
  decides to remove a worktree, which is the only moment that matters.
  THE NOVEL SLICE is therefore the ORDERING contract in our own stand-down path: publish this
  ticket's branch, PROVE it reached a remote by re-asking git, then let leak-guard judge.
  In-tree reuse (not substrate, listed for the reviewer): the publish call is the same one
  fleet/rescue-push.sh and the launcher's own submit path already use; the durable record is the
  existing state/needs-push/<id> marker; the recovery path is the existing
  fleet/land-needs-push.sh; fleet/leak-guard.sh is untouched and its predicate is reused verbatim
  so the step and the guard can never disagree.
  `fleet/reuse-check.sh . fleet/preserve-unpushed.sh` -> "No overlaps found."
depends_on:
note: |
  MEASURED 2026-08-01: five frontier tabs died after ONE ticket each, all with the identical
  shape and exit code 1 (tickets GRADE-MODEL-PROVIDER-PAIR, KSF-LOAD-BEARING,
  TOOL-COMPOSITION-LAYER, WORKFLOW-E2E-AUDIT, +1 relaunch):

    [frontier-N] <TICKET>: launcher running the gate (one-shot verification)...
    leak-guard: REFUSING to remove <wt> — 1 commit(s) on HEAD are not on any remote
    (unpushed work). Nothing removed; resolve by hand.
    [frontier-N] cleanup: worktree KEPT: <wt> — leak-guard REFUSED removal.

  Note what is MISSING from that trace: the `launcher gate exit code = N` line. The tab never
  reached it. The killer is fleet-droid.sh:1403 — a RED gate is a non-zero compound command in
  plain statement position under `set -euo pipefail` (:17), so the shell unwinds, the EXIT trap
  (:1050) runs cleanup(), and leak-guard refuses on the way out. That half is
  LAUNCHER-GATE-SETE-KILL (PR #356) and is NOT re-fixed here.

  THIS ticket is the second, independent half. The droid had already COMMITTED. Nothing in the
  launcher ever published the branch, so every one of those tabs left commits on a single disk
  and the manager had to rescue them by hand with `fleet/rescue-push.sh --push`. Landing the
  set -e fix alone would make the tab survive while STILL leaving the work unpublished on any
  other stand-down path (SIGINT, preflight abort, a crash after commit). The launcher was
  manufacturing the exact stranded-work class the session is fixing.

  TIER-INDEPENDENT — the frontier/strong asymmetry is FALSIFIED, not explained. A strong tab has
  since died with the byte-identical shape (strong-4073729 / RELEASE-PRESERVES-WORK), so the
  apparent frontier-only pattern was TIMING: strong tabs simply took longer to reach cleanup.
  There is no tier, model or chain component and no tier-specific handling is built here.
  (Mechanically, every observed death drew a `repo: charon-private` ticket, whose RR_GATE is
  `validate_board.sh` (repo-registry.sh:100) — a WHOLE-BOARD gate, so one ambient RED reds every
  rig-repo ticket at once. That is an amplifier for how OFTEN the gate goes red, not a cause of
  the death, and it is tier-blind: strong-3047201 and strong-710358 carry the identical board RED
  in state/gate-results/.)

  THE LOAD-BEARING SHAPE (strong-4073729, measured):
    WARNING: RELEASE-PRESERVES-WORK left UNCOMMITTED changes — launcher auto-committing.
    ... launcher running the gate (one-shot verification)...
    leak-guard: REFUSING to remove ... — 1 commit(s) on HEAD are not on any remote (unpushed work).
  cleanup() step (1) AUTO-COMMITS what the droid never committed, which MINTS the very unpushed
  commit step (2) then refuses on — the stand-down arms its own refusal. So the stranded-work path
  is reached even when the droid never commits at all, which is why publish-before-cleanup is the
  load-bearing fix and surviving the gate is not sufficient on its own.

accept: |
  - Committed-but-unpushed work on a droid branch is PUBLISHED before the worktree is torn down;
    after the publish, leak-guard has nothing left to refuse on (it is not weakened, it simply
    sees no unpushed commits).
  - A publish that FAILS is non-fatal DATA: the state/needs-push/<id> marker stays live, the
    work stays on disk, leak-guard keeps refusing, and the message names
    `bash fleet/land-needs-push.sh <id>` as the recovery path.
  - The marker is written BEFORE the push (a kill mid-push still leaves the record) and cleared
    only against a RE-READ unpushed count, never on the push's own exit status.
  - A branch with nothing unpushed mints no marker and pushes nothing.
  - fail-on-revert proof: fleet/tests/preserve-unpushed.test.sh (17 assertions) EXTRACTS the
    real cleanup() from fleet-droid.sh and runs the real step against real git fixtures.
    17/17 pass with the fix; removing the cleanup() wire -> 2 FAIL, deleting
    fleet/preserve-unpushed.sh -> hard FAIL, clearing the marker without a proven publish
    -> 8 FAIL.

## Dependencies & Sequence

- **depends_on: (none) — but SEQUENCE BEHIND LAUNCHER-GATE-SETE-KILL (PR #356).** The two are
  the two halves of one class and are independent code paths: #356 stops the tab dying on a RED
  gate (property a), this stops the work being stranded whatever ends the tab (property b).
  Neither subsumes the other; #356 alone would just lose the work more quietly on the paths it
  does not cover, and this alone would preserve work in a tab that still dies.
- **owns-collision note:** the two owned files are new and uncontended. The one-line wire in
  `cleanup()` touches `fleet/fleet-droid.sh`, which LAUNCHER-GATE-SETE-KILL owns. The hunks are
  ~470 lines apart (cleanup() at ~:920 vs the gate block at ~:1400) and merge cleanly, but land
  #356 FIRST and rebase this onto it to keep the file single-writer.
- **Blocks / unblocks:** landing this is what makes any early tab exit non-destructive, so it
  is a prerequisite for trusting that a pool tab can be killed, restarted, or gated RED without
  a human rescue afterwards.
