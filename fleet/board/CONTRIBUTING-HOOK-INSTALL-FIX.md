repo: charon
tier: economy
difficulty: 1
priority: 1
work_class: docs
branch: docs/contributing-hook-install
owns: CONTRIBUTING.md
depends_on:
dep-kind:
state: BUILT + STAGED, NOT COMMITTED. The fix exists on branch docs/contributing-hook-install; the
  commit was correctly REFUSED by the work-lease hook because no board ticket carried that
  `branch:` field. This ticket is that mapping. The sub did NOT bypass — that was the right call.
source: Session 2026-07-24. Observed by execution: the product's public-clean guard was found INERT
  for an unknown period today, and the documented install instruction is why.
priority_justification: P:1 (PRIORITY-LADDER "attached CG work") — deliberately NOT filed as routine
  docs. The documentation itself is what disabled a PUBLIC-repo security guard: following
  CONTRIBUTING.md step 3 as written silently turned off the check that keeps internal IPs,
  /home/stack paths, hostnames and secrets out of the public repo, and it was off for an unknown
  period. Not P:0 — the guard is being restored in the same session, nothing is leaking right now,
  and the change is two lines of markdown that drain in minutes. [[security-is-a-ratchet-gate]]
work_class_note: docs — but the defect class is security. The artifact edited is markdown; the
  consequence of the current wording is an inert public-repo guard.
note: |
  THE DEFECT. CONTRIBUTING.md step 3 documents the hook install as:

      git config core.hooksPath tools/hooks

  `core.hooksPath` WHOLESALE-REPLACES the hook directory. Every hook not present under
  `tools/hooks` — including the repo's public-clean pre-commit guard — stops running, silently,
  with no error and no output. A contributor who follows the documented step correctly ends up with
  the guard disabled and no way to notice. That is exactly what happened today.
  WHY IT MATTERS HERE SPECIFICALLY: this is the PUBLIC repo. The public-clean guard is what blocks
  internal IPs, `/home/stack` absolute paths, internal hostnames and secrets from being committed
  into it [[public-repo-no-personal-info]] [[no-hardcoded-cross-boundary-paths]]. A silently-inert
  guard on a public repo is the highest-consequence version of "it looked wired"
  [[gates-must-actually-run]].
  THE FIX (already written on the branch): replace the `core.hooksPath` instruction with a SYMLINK
  install into `.git/hooks/` — which ADDS the repo's hooks without evicting anything already
  installed — plus an explicit warning that `core.hooksPath` replaces the hook directory wholesale
  and must not be used for this repo.
accept: |
  A. CONTRIBUTING.md step 3 no longer instructs `git config core.hooksPath …`. It installs the
     repo's hooks by SYMLINK into `.git/hooks/`, and the instruction is copy-pasteable verbatim
     [[always-give-exact-command]].
  B. An explicit WARNING is present, in the same step, stating that `core.hooksPath` replaces the
     hook directory wholesale and therefore disables the public-clean guard — naming the guard and
     naming the consequence (internal IPs / /home/stack paths / hostnames / secrets reaching a
     PUBLIC repo). A reader who already ran the old command must be able to tell from this text that
     they need to undo it, and how.
  C. NON-VACUOUS / FAIL-ON-REVERT — the proof is that the guard actually RUNS after following the
     documented steps, not that the markdown reads well:
     1. In a scratch clone, follow the NEW step 3 verbatim, then attempt to commit a file containing
        a seeded internal path (e.g. a `/home/stack/...` string) => the public-clean guard REFUSES
        the commit. Paste the refusal.
     2. Same scratch clone, follow the OLD step 3 (`core.hooksPath tools/hooks`) instead => the same
        seeded commit is ACCEPTED, demonstrating the guard is inert. This is the fail-on-revert
        evidence: revert the doc and the guard stops firing.
     3. A commit with NO seeded violation still succeeds under the new step (the fix must not make
        every commit refuse — a guard that blocks everything is as useless as one that blocks
        nothing).
     Run these in a SCRATCH clone. Do NOT re-point the live checkout's hooks to test this.
  D. Report whether any commit already landed on the public repo while the guard was inert, and if
     the scan is inconclusive say so plainly rather than asserting clean
     [[never-ignore-preexisting-issues]] [[document-model-self-report-lies]].
  E. The product gate stays green: `python3 -m charon.cli gate` (or the repo's documented gate
     command) passes on the branch.
scope: |
  PRODUCT repo (/home/stack/code/charon), documentation only — `CONTRIBUTING.md` and nothing else.
  Does NOT change the hooks themselves, does NOT change the public-clean guard's logic, and does NOT
  touch the rig. If the investigation in C/D shows the guard's own logic is also weak, that is a
  SEPARATE product ticket — hand it back, do not widen this one.
serial_justified: One markdown step plus its warning plus the executed proof that the documented
  steps leave the guard ARMED. There is nothing to fan out to — the proof is the whole point and it
  exercises the same two lines.
ds: |
  ## Dependencies & sequence
  depends_on: (none) — CLAIMABLE NOW. `CONTRIBUTING.md` in the PRODUCT repo is owned by no other
  live board ticket (verified 2026-07-24 against every `owns:` line). The work is already written
  and staged on branch docs/contributing-hook-install; this ticket exists so the work-lease hook can
  map that branch to a ticket, which is what refused the commit.
  UNBLOCKS: the pending commit on docs/contributing-hook-install. Land early — it is minutes of work
  and it re-arms a public-repo security guard.
  RELATED, NOT BLOCKING: WORK-LEASE-WORKTREE-RESOLVE fixes the lease gate's OWN path-resolution
  defect; this ticket is the ticket-mapping the hook demanded, not a fix to the hook.
  CONCURRENCY-SAFETY: work from the existing docs/contributing-hook-install checkout — git will
  refuse a second checkout of the same branch [[one-checkout-one-agent]]. Test the hook behaviour in
  a SCRATCH clone only; never re-point the live .git/hooks mid-session.
