repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
priority: 0
branch: feat/merge-drop-ratchet
depends_on:
owns: fleet/checks/board-file-ratchet.sh, fleet/tests/board-file-ratchet.test.sh, fleet/checks/rig-ci-scope.sh
substrate: N/A
substrate-novel: |
  The rule ("a ticket file may leave fleet/board/ ONLY by moving to fleet/board/archive/, or with
  an explicit declared retire") is specific to THIS board's lifecycle and has no off-the-shelf
  owner. REQUIRED FIRST TASK: record a real EVAL-REGISTRY row for the generic PR-diff-policy
  substrates before writing the check — **Danger** (danger-js/danger-ruby, the best-known
  "assert things about a PR's diff" tool) and **Conftest/OPA** (policy over structured input).
  Judge them honestly on fit-without-bending and exit cost, NOT on size. If either fits, WRAP it;
  the check below is the fallback, not the assumed answer. A verdict that is not in EVAL-REGISTRY
  gets paid for twice.
serial_justified: |
  ONE invariant, one enforcement point. The check and its wire into the CI allowlist are the same
  deliverable — an unwired check is the built-but-inert class this ticket exists to prevent.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. Strong chain verified funded 2026-07-31.
source: |
  Measured 2026-07-31 (session tott-doneeta) while clearing ORPHAN-CLAIM-FORENSICS. Operator:
  "I want the merge-drop mechanism fixed now if it's sane and logical."
note: |
  ## THE DEFECT (measured, not theorised)
  NINE board tickets were destroyed and had to be restored by hand from git history this session:
  PREFLIGHT-OWNS-ARBITRATE · SW-STATIC-LEGS-RETIRE · LITELLM-CAPABILITY-ADOPTION ·
  SW-IDENTITY-FOLD · BRIDGE-MIGRATE-DROID-CLIENT · SECRET-HOTROTATE · PREFLIGHT-GATE-REGISTRY ·
  PREFLIGHT-GATE-RUN-HELPER · WCI-CONTENTION-TEETH.

  **The disappearance signature (verify it yourself before building — do not take this on faith):**
    - the ADD commits (`6e94e0d`, `859e3b9`) and the archive RENAME (`1c974cc`, R100
      `board/ -> board/archive/`) are ALL ancestors of master;
    - the files were absent from master's tree;
    - `git log --full-history --diff-filter=D -- <path>` finds **ZERO deleting commits**;
    - every commit touching those paths under `--full-history` is a **MERGE commit**.
  A file added on master, deleted by no commit, yet absent from master's tree = **dropped by merge
  resolution** — a branch carrying a stale or partially-regrouped `fleet/board/` tree was merged
  and its state won. Note `859e3b9`'s own subject: "board regroup interrupted".

  **Blast radius: the board is the fleet's work-memory.** A silently dropped ticket becomes an
  orphan claim marker, which REDs the board, which blocks EVERY land. That is exactly the 39-RED
  full stop this session opened with. **A 10th drop is guaranteed until this is gated.**

  ## THE INVARIANT TO ENFORCE (the ratchet)
  A `fleet/board/*.md` file may leave `fleet/board/` in EXACTLY two ways:
    1. it appears at `fleet/board/archive/<same-name>.md` in the SAME diff (normal retire), or
    2. the commit/PR explicitly declares the retire (e.g. `board-hygiene: retire <ID>`).
  ANY other disappearance — including one produced by a merge resolution — is **RED at the merge
  boundary**. Net ticket count may fall ONLY with a matching archive/ gain or a declared retire.

  ## WHY THE MERGE BOUNDARY IS THE RIGHT FIRING LAYER
  The drop is invisible to every existing check because no COMMIT deletes anything — the loss only
  exists in the merge RESULT. So the check must compare the merge result against both parents, not
  scan a commit's own diff. `fleet/validate_board.sh` cannot see it (it validates the tree it is
  handed, and a board missing a ticket is structurally valid). This is why nothing caught nine
  losses.

  ## SCOPE
  - `fleet/checks/board-file-ratchet.sh` — the check. Compares the post-merge board file set
    against the base, classifies every disappearance, RED on any undeclared drop.
  - Wire it into `fleet/checks/rig-ci-scope.sh`'s allowlist. That file is a DELIBERATE allowlist —
    its line 48 says "NEVER replace this with a `for t in fleet/tests/*.test.sh` sweep" — so the
    wire is an explicit entry, not auto-discovery. An unwired check is inert and fails this ticket.
  - `fleet/tests/board-file-ratchet.test.sh` — hermetic, `mktemp -d`, offline.

  ## OUT OF SCOPE (surface, do not fix here)
  - The DIVERGENCE half of the root cause (bare board commits on local master vs origin's merge-
    wrapped copies) is already owned by **NO-LOCAL-MASTER-COMMITS** (blocked on SYNC-SCHEDULE).
    This ticket makes the LOSS visible; that one stops the divergence being created.
  - Recovering already-lost tickets — done 2026-07-31 in commit `e4e5582`.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. a merge whose result DROPS a board ticket present in the base -> RED naming the ticket.
       **Build this fixture from the REAL signature above** (merge that removes a file no commit
       deleted), not from a plain `git rm` — a `git rm` fixture would pass a check that is blind
       to the actual defect, which is precisely how this shipped.
    b. a normal retire (board/X.md -> board/archive/X.md in the same diff) -> GREEN.
    c. a declared retire without an archive/ move -> GREEN.
    d. ANTI-OVER-BLOCK: a merge that touches no board files at all -> GREEN, and a merge that ADDS
       tickets -> GREEN.
    e. the check is REGISTERED in rig-ci-scope.sh and actually EXECUTES — prove it fires by
       observing it go RED in a real run, not by asserting it is listed.
  Report the RED output verbatim for (a).

D&S — Deps & Sequence:
  - Depends on: nothing. Do it NOW — it is priority 0 and guards the board that gates all landing.
  - Collision: `fleet/checks/rig-ci-scope.sh` is also owned by PLANE-CANARY-REGISTRY (DONE),
    FN-MEMORY-RETIRE-ADOPT (DONE) and HANDOFF-GATE-NONBYPASSABLE (blocked on RECONCILE-WIRING,
    far off). This ticket is sequenced FIRST; HANDOFF-GATE-NONBYPASSABLE carries the dep on it.
  - Pairs with NO-LOCAL-MASTER-COMMITS (creates divergence) — this one DETECTS the loss.
