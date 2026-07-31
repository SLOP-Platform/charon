repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: fix/orphan-claim-forensics
depends_on:
owns: fleet/reconcile-stale-claims.sh, fleet/tests/reconcile-stale-claims.test.sh
serial_justified: |
  ONE question — "what is a claim whose ticket no longer exists anywhere, and what is safe to do
  with it". The forensics and the reconciler change are the same deliverable: a rule derived
  without being encoded leaves the next session sweeping by hand, and a rule encoded without the
  forensics is a guess about 39 pieces of possibly-live work.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Model note: opencode silently falls back to the DEAD gpt-5.4 pool for any model not in
  opencode.json's charon provider list (36 of 2567). Verified funded 2026-07-31: deepseek-v4-pro,
  gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7, big-pickle.
source: |
  Found 2026-07-31 when fixing 4 pre-existing repo: REDs UNMASKED 39 orphan-marker REDs that had
  been hidden behind them. This ticket BLOCKS the board (40 REDs) and therefore blocks all landing.
note: |
  ## FACTS (verified 2026-07-31)
  - `fleet/validate_board.sh` reports **39 `orphan-marker` REDs**: entries in
    `fleet/state/claims/` matching NO board ticket.
  - These were INVISIBLE until 4 `repo-missing`/`repo-owns-inconsistent` REDs were fixed
    (commit 60b9a89). Fixing REDs unmasked more REDs — the board was never at 0.
  - Verified: for these orphans the ticket exists **neither** in `fleet/board/`, **nor** in
    `fleet/board/archive/`, **nor** as `fleet/state/done/<id>`. A sweep for archived-or-done
    cleared **0** of them.
  - `fleet/reconcile-stale-claims.sh --apply` (landed today, PR #273) ran: retired 2,
    **HELD 15 unmerged** (correctly fail-closed), and does not classify this orphan case at all.
  - The board CANNOT reach 0 RED until this is resolved, so `land.sh` refuses every land.

  ## FRAMING (hypothesis — TEST IT, overturn loudly if wrong)
  The manager suspects these are residue from tickets renamed, retired without archiving, or minted
  in a wave that was later dropped. **UNVERIFIED.** They could equally represent REAL abandoned
  work whose ticket was deleted while a branch still exists. **Do not sweep them.** Deleting a
  claim marker you cannot account for is how work gets destroyed
  [[investigate-and-backup-before-data-loss]].

  ## WHAT TO DO
  1. **Forensics first.** For EACH of the 39: does a branch/worktree exist? Unlanded commits? Does
     git history show the ticket ever existing (it may have been renamed or archived-then-deleted)?
     Bucket: `residue-safe-to-clear` · `work-at-risk` · `unknown`.
  2. **Then encode the rule** in `reconcile-stale-claims.sh` so this class is classified, not
     ignored. Fail closed: `unknown` is NEVER auto-cleared.
  3. Report the count per bucket and the names in `work-at-risk`.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. orphan whose ticket never existed AND has no branch/commits -> classified residue
    b. orphan WITH unlanded commits or a dirty worktree -> `work-at-risk`, NEVER auto-cleared
    c. orphan whose state cannot be determined -> `unknown`, fail closed
    d. ANTI-OVER-BLOCK: a normal live claim is still untouched
  Then run against the real fleet and show the board reaching 0 RED, or say precisely why not.

D&S — Deps & Sequence:
  - Depends on: nothing. BLOCKS EVERYTHING — the board is RED until this lands.
  - Do FIRST, before the 2 unlanded commits (a1d9ce8, 60b9a89) and the 4 remaining triage LANDs.
