repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: fix/branch-gate-diff-scope
depends_on:
owns: fleet/land-push.sh, fleet/tests/branch-gate-diff-scope.test.sh
substrate: N/A
substrate-novel: |
  REUSES a principle we already implement. `fleet/checks/rig-ci-scope.sh` states it explicitly:
  "THE load-bearing line of this gate: CI inspects ONLY what the PR touched. Widening this to the
  whole tree re-introduces the false-RED class the fresh-checkout constraint exists to prevent."
  The push/land gate does NOT diff-scope its board check. This ticket applies the existing,
  proven principle to the one gate that lacks it — not a new mechanism.
serial_justified: |
  One scoping rule at one chokepoint plus its proof.
source: |
  Operator, 2026-08-01: "any branch cut before a board fix becomes permanently unpushable — that
  needs to be fixed in a mechanized class way."
note: |
  ## THE DEFECT — A BRANCH IS GATED ON STATE IT DOES NOT OWN
  `land-push.sh` / `land.sh` run `validate_board.sh` **inside the branch's WORKTREE**. The worktree
  carries the board as it was when the branch was cut. So a branch is judged on board state it
  never touched and cannot fix.

  **Consequence: every branch cut before a board fix becomes PERMANENTLY UNPUSHABLE.** Not slow —
  impossible. The branch cannot fix the board (not in its `owns:`), and the gate will not let it
  push. Only a rebase clears it, and rebase is denied to the manager by design.

  ## MEASURED 2026-08-01 — four completed pieces of work, all refused
  | Branch | Commits | Refused with |
  |---|---|---|
  | `fix/loop-guard-reason-wire` | 1 | 3 REDs, none in its own diff |
  | `chore/retire-final-e2e-review` | 2 | 5 REDs, none in its own diff |
  | `fix/shared-namespace-contention` | 1 | stale-board REDs |
  | `feat/deadcode-tools-wire` | 1 | stale-board REDs |
  The RETIRE droid diagnosed it itself: *"Pre-existing 5 REDs involve FAKTORY-REINVESTIGATE/
  FAKTORY-TRIAL duplicate owns, HANDOFF-NAME-ALLOCATOR/SHARED-NAMESPACE-CONTENTION,
  PLANE-CANARY-WIRE/PREFLIGHT-GATE-* — none touches FINAL-E2E-REVIEW.md."* Every one of those was
  ALREADY FIXED on master. The branches were being blocked by history.

  ## THE FIX — DIFF-SCOPE THE BOARD CHECK AT THE PUSH/LAND GATE
  The gate must judge the branch on **what the branch changed**, not on the whole stale tree:
  1. Validate board entries the branch actually TOUCHED (`git diff --name-only <base>...HEAD`
     filtered to `fleet/board/`). A branch touching no board file gets no board-RED.
  2. Where whole-board validity genuinely matters, evaluate it against the **MERGE RESULT** or
     `origin/master` — never the stale worktree copy.
  3. A RED that exists identically on `origin/master` is PRE-EXISTING and must not block a branch
     that did not cause it. Report it (so it is not hidden) but do not refuse the push.

  **Do NOT weaken the gate.** A branch that genuinely breaks the board must still be refused —
  that is the ANTI-OVER-BLOCK case below and it is the whole risk of this change.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture repo + fixture board:
    a. **Reproduce the real case**: a branch touching NO board file, in a worktree whose board has
       a pre-existing RED that also exists on base -> push is ALLOWED, and the pre-existing RED is
       REPORTED not swallowed. Revert the scoping -> RED.
    b. **ANTI-OVER-BLOCK (the load-bearing one)**: a branch that ADDS a board RED not present on
       base is still REFUSED. Revert -> RED. Without this the ticket is a gate-weakening.
    c. a branch that FIXES a pre-existing RED pushes cleanly.
    d. a branch touching board files with a RED in its OWN diff is refused, naming that file.
  Then dogfood: run against the four real stranded branches above and show each result.

D&S — Deps & Sequence:
  - Depends on: nothing. Unblocks 4 completed-but-unpushable branches immediately, and every
    future branch cut before a board fix.
  - Pairs with RELEASE-PRESERVES-WORK (that one stops completed work being un-claimed; this one
    stops it being unpushable). Independent; neither blocks the other.
