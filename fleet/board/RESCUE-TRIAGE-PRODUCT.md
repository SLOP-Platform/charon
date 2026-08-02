repo: charon
tier: strong
priority: 1
difficulty: 4
work_class: design-review
branch: chore/rescue-triage-product
depends_on:
owns: docs/review-log/RESCUE-TRIAGE-PRODUCT.md
substrate: N/A
substrate-novel: |
  The mechanical half is ADOPTED, not rebuilt: `git cherry` and `git patch-id` answer whether a
  commit already reached master through a squash-merge, `gh pr list --state all --head <branch>`
  answers whether a PR ever existed, and GitHub's own `update-branch` API answers the stale-base
  problem. This ticket writes none of that.
  What no external tool answers is which of three competing variants of ONE security fix is the
  one to keep, or whether a 26-commit branch that forked weeks ago still contributes anything the
  product does not already have. A diff tool reports difference; it cannot report obsolescence.
  That judgement, plus the public-repo constraint that every surviving PR must carry no rig paths,
  is the novel slice, and its output is PR bodies and closure evidence rather than a program.
serial_justified: |
  Fourteen branches in ONE repo whose dispositions are COUPLED: three of them are variants of a
  single fix, and two more are variants of one catalog-seed change. A lane that judged any one of
  those in isolation would open a PR for a variant that a second lane had already superseded.
execution: |
  Off-Claude via fleet-droid.sh, own worktree on the PRODUCT checkout. The only writes are PR
  opens, PR/branch closures, and this ticket's evidence file. Never `--force`, never a raw
  `git push`, never a rebase of another lane's branch.
source: |
  RESCUE-PUSH-TOOL's live sweep, 2026-08-01: 47 local-only branches pushed to origin in one run.
  Fourteen of the surviving PRODUCT branches have no PR of any kind, so nothing on the board or in
  any review queue references them.
note: |
  ## THE STATE THE RESCUE LEFT BEHIND
  Pushing made this work safe from disk loss. It did NOT make it reviewed and it did NOT make it
  visible. Fourteen product branches sit on the remote with no PR against them: no gate has run on
  them, no reviewer has seen them, and the board does not track them.

  ## THE FOURTEEN BRANCHES (product, no PR of any kind)
  1. chore/remove-stdlib-only-prohibition
  2. feat/connect-omp-wsl
  3. feat/cwd-config
  4. feat/diff-cover-mutmut-adopt
  5. feat/gateway-litellm-live-wire
  6. feat/ordering-cost-primary
  7. feat/wire-tool-repair
  8. fix/provider-key-exfil-round6
  9. fix/provider-key-exfil-v2
  10. fix/provider-key-exfil-v2-round5
  11. fix/spend-metric-trustworthy
  12. pr164
  13. sub/ft-catalog-seed-contract-fixtures
  14. sub/ft-catalog-seed-fix-v2

  ## THE BIGGEST SINGLE BODY OF RESCUED WORK
  `feat/cwd-config` IS 26 COMMITS — the largest single body of rescued work in either repo. It
  gets a real read, not a skim, and it is the one branch where "close it as dead" demands the
  strongest evidence. If it is genuinely superseded, prove that per subject area, not in one line.

  ## THE VARIANT CLUSTERS — PICK ONE, CLOSE THE REST
  * `fix/provider-key-exfil-round6`, `fix/provider-key-exfil-v2` and `fix/provider-key-exfil-v2-round5`
    are three variants of ONE fix. Pick the BEST and close the other two with the reason. Opening
    three PRs for one fix is the failure mode. This is a credential-egress surface, so the chosen
    variant must be the most COMPLETE one, never merely the smallest diff.
  * `sub/ft-catalog-seed-contract-fixtures` and `sub/ft-catalog-seed-fix-v2` are two takes on the
    same catalog-seed change; judge them together against what FT-CATALOG-SEED already carries.
  * `pr164` is a branch named after a PR number. Establish what it actually contains and whether
    that PR already landed before doing anything else with it.

  ## DONE CONTRACT — ONE DISPOSITION PER BRANCH, EVIDENCE ON EVERY ONE
  For EACH of the fourteen, answer both questions before choosing:
    a. Is its change ALREADY on master by another route — squash-merged under another name,
       superseded, or reinvented? Prove it with shas, a `git cherry` / `git patch-id` result, or
       the file content on master. "Looks similar" is not evidence.
    b. Does it still CONTRIBUTE anything master lacks today?
  Then exactly one of: OPEN a PR whose body states what the branch delivers, what is already on
  master and what is left; or CLOSE / delete it with the evidence that it is dead.
  CLOSING DEAD WORK WITH EVIDENCE IS AN EQUALLY VALID OUTCOME. Do not resurrect corpses. Fourteen
  PRs is a FAILING result — it would spend the entire review queue on work that may already be on
  master.

  ## TWO CONSTRAINTS SPECIFIC TO THIS REPO
  * PUBLIC REPO. Any PR opened here must pass public-clean: no rig paths (`fleet/...`), no
    internal hostnames, no local absolute paths, no tokens in the branch content or the PR body.
    A branch that only fails public-clean is not dead — strip the leak and open it clean.
  * STALE BASE. These branches forked before a long run of master commits, so expect stale-base
    CI failures. REFRESH via the GitHub `update-branch` API. Do NOT use `gh run rerun`: rerun
    replays against the CACHED merge ref, so it re-runs the same stale merge and reports the same
    failure, which reads as a flaky suite and is not one.

  ## DELIVERABLE
  `docs/review-log/RESCUE-TRIAGE-PRODUCT.md` — one row per branch: branch, commit count, verdict
  (PR-OPENED #N / CLOSED-DEAD / HELD-WITH-REASON) and the evidence it rests on. A verdict with no
  evidence cell is a guess, and guesses are why these branches went unread.

## Dependencies & Sequence

- **depends_on: none.** A read-then-dispose pass over existing remote branches. It builds nothing,
  changes no gate and imports no module, so nothing has to land first.
- **Sequence: NOW, while the rescue is fresh.** Stale branches decay: every master commit widens
  the gap that `update-branch` has to close, and raises the odds someone reinvents the same fix.
- **Concurrency safety — owns-collision: none.** The single owned path is a NEW file named after
  this ticket. No other live ticket owns `docs/review-log/RESCUE-TRIAGE-PRODUCT.md`. Verified
  against the live board before minting.
- **Different REPO from the other two rescue lanes.** This ticket is `repo: charon` (the PRODUCT
  checkout); `RESCUE-TRIAGE-RIG` and `PR-QUEUE-DRIVE` are `repo: charon-private`. Separate trees,
  separate branches, no shared file — they run fully in PARALLEL.
- **Hand-off, not a dependency:** PRs this ticket opens become review-queue input later. That is
  merge-order, not a build prereq.
- **Related, do NOT fold in:** the live `FIX-PROVIDER-KEY-EXFIL` ticket owns the exfil FIX itself.
  This lane only decides WHICH rescued variant survives and opens it for review; it does not
  rewrite the fix, and it must not edit that ticket.
