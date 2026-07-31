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

  ## PRIOR FORENSICS — verified by session tott-doneeta 2026-07-31 (START HERE; corrects FACTS above)
  Re-measured. **39 REDs, not 40.** Split by marker directory:
    - `state/claims/`    14
    - `state/submitted/`  4
    - `state/done/`      21

  **CORRECTION to the FACTS block above.** It asserts the ticket exists "nor as
  `fleet/state/done/<id>`". That is FALSE for the 21 `done/` orphans — for those the marker IS
  `state/done/<id>`, and every one carries real completion proof, e.g.
  `FLEET-DEMAND-BROKER -> merged:#264`, `BRIDGE-REPLACE-PHASE1 -> merged:3b7d9a5`,
  `CLAIM-INTEGRITY-TOOL-ADOPT -> override:RED-LINE ...`. **These are LANDED work, not residue.**
  Any rule that treats a `done/` marker with merge proof as sweepable is wrong.

  **The "residue from a dropped wave" hypothesis is NOT supported.** For every one of the 39,
  `git log --all -- fleet/board/<id>.md fleet/board/archive/<id>.md` finds the ticket file
  (ever_in_git >= 1 for all 39; 2-6 commits for many). They existed.

  **The disappearance mechanism is a MERGE, not a delete.** Sampled DOGFOOD-GATE,
  FLEET-DEMAND-BROKER, WCI-CONTENTION-TEETH, SECRET-HOTROTATE:
    - the ADD commits (`6e94e0d`, `859e3b9`) and the archive RENAME (`1c974cc`, R100
      `board/ -> board/archive/`) are ALL ancestors of master;
    - the files are absent from master's tree NOW;
    - `git log --full-history --diff-filter=D` finds **ZERO deleting commits**;
    - every commit touching the path under `--full-history` is a **merge commit**.
  A board file added on master, never deleted by any commit, yet absent from master's tree =
  dropped by merge resolution. This is the same divergence-by-construction the handoff already
  root-caused (`board-lock.sh commit` writes bare onto local master; origin wraps the same content
  in a merge; a later merge resolves board state to the side that lacks the file).
  **This is the answer to handoff gate 5b ("what process CREATES a claim whose ticket vanishes")
  and it means a 40th orphan is guaranteed until the merge path stops dropping board files.**

  **`state/claims/` bucket is NOT uniform — do not treat it as one class.** Markers are
  work-leases (`ticket:/session:/worktree:/heartbeat:`). Of the 14:
    - **provably retire-able** — the work LANDED on product master today:
      `DOGFOOD-GATE` (d6267c3), `INERT-STARTUP-CHECK` (6ab6035).
    - **provably work-at-risk** — a live product worktree still holds unlanded commits:
      `SECRET-HOTROTATE`, `SW-IDENTITY-FOLD`, `SW-STATIC-LEGS-RETIRE`,
      `LITELLM-CAPABILITY-ADOPTION`, `PREFLIGHT-GATE-REGISTRY`, `PREFLIGHT-OWNS-ARBITRATE`,
      `RIG-BRANCH-16-DEEPDIVE`, `SW-PHASE0-GRADE-READ`, `BRIDGE-MIGRATE-DROID-CLIENT`,
      `REGISTRY-META-CATALOG`, `LAND-GATE-RIG-SUITE`, `WORK-LEASE-WORKTREE-RESOLVE`
      (cross-check each against `git worktree list` before acting — this list is from the
      2026-07-31 handoff's stranded-work scan, RE-MEASURE it).
  So the classifier needs at least: landed-proof -> retire · unlanded-commits -> work-at-risk ·
  neither -> unknown/fail-closed. **Do not ship a classifier that only looks at `fleet/board/`.**

  **REMAINS OPEN for this ticket (not done by the prior forensics):**
    - per-marker verdict for all 39 (the above is a sample + a bucket count);
    - encoding the rule in `reconcile-stale-claims.sh` with the RED-then-GREEN contract below;
    - whether the merge-drop mechanism should be gated separately (likely a sibling ticket —
      surface it, do not silently widen this one).

  **UNRELATED RED found while doing this (surface, do not fix here):**
  `fleet/claim-jedi-name.sh` dies — `pool file not found: fleet/state/jedi-name-pool.txt`. The
  file was added in `5d42cd5` and is absent from the working tree. Same disappearance shape as the
  board tickets above. Needs its own ticket.

D&S — Deps & Sequence:
  - Depends on: nothing. BLOCKS EVERYTHING — the board is RED until this lands.
  - Do FIRST, before the 2 unlanded commits (a1d9ce8, 60b9a89) and the 4 remaining triage LANDs.
