repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
priority: 0
branch: feat/fixture-bypass-gate
depends_on:
owns: fleet/checks/fixture-bypass.sh, fleet/checks/gate-integrity.sh, fleet/tests/fixture-bypass.test.sh, fleet/tests/gate-integrity.test.sh
substrate: N/A
substrate-novel: |
  RETROACTIVE ticket for work already BUILT and pushed (3 commits on feat/fixture-bypass-gate,
  +1,146 lines). The substrate question is recorded here for the record rather than to gate a
  build that already happened: "does this gate assert anything real, or is it green over a path
  no test runs" is a meta-invariant over OUR gate set, keyed to our own registry and preflight
  wiring. Generic SAST/lint tools (semgrep, ruff, bandit — all already adopted here) test PRODUCT
  code; none can answer whether one of OUR gates is structurally incapable of failing.
serial_justified: |
  Already built as one unit; ticket minted retroactively to match. The two gates share the same
  meta-invariant and the same registry/preflight wiring.
source: |
  Minted 2026-07-31 (session tott-doneeta) during GATE 2. The handoff flagged this branch as
  "⚠ HAS NO BOARD TICKET. Mint one first or land.sh refuses." Confirmed: no ticket exists in
  fleet/board/, fleet/board/archive/, or ANYWHERE in git history — unlike the 9 tickets destroyed
  by merge resolution, this one was never created at all.
note: |
  ## WHAT IS ALREADY BUILT (verified on origin/feat/fixture-bypass-gate)
  Three commits, +1,146/-2 across 7 files:
    - `fleet/checks/fixture-bypass.sh` (+230) — mechanizes the FIXTURE-BYPASS class:
      "green over a path no test runs".
    - `fleet/checks/gate-integrity.sh` (+457) — the GATE-ON-GATES: "a gate that reads as
      protection but provides none".
    - `fleet/tests/fixture-bypass.test.sh` (+191), `fleet/tests/gate-integrity.test.sh` (+214)
    - wiring into `fleet/checks/rig-ci-scope.sh` (+12) and `fleet/preflight.sh` (+33)
    - `2ca581c` — "correct a FALSE wiring claim in the header (found by gate-integrity G2)":
      the gate-on-gates CAUGHT A REAL FALSE CLAIM IN OUR OWN TREE on its first outing.

  ## WHY THIS IS PRIORITY 0 (evidence from THIS session, 2026-07-31)
  `gate-integrity.sh` targets the single most expensive class we have. Four instances surfaced in
  one session, every one marked Done/merged and none load-bearing:
    1. **REVIEWER-TAB-POOL B1** — `reviewer != builder` compared a shared GitHub bot login against
       `CHARON_DROID_ID`. **Disjoint namespaces: the guard could never fire.** A gate that reads
       as protection and provides none — this gate's exact definition.
    2. **Faktory** — server up 7 days on 4-LOM, `lease-enqueue.sh` self-describes as "the ONLY
       sanctioned path that starts work", ZERO workers running, and `claim.sh` never calls it.
    3. **F2 auto-done-on-merge** — marked Done on the roadmap; did not close ORPHAN-CLAIM-FORENSICS
       after PR #289 merged. The operator noticed, not the rig.
    4. **SESSION REPORT v1** — format + fail-loud validator both exist; `JOIN-PROMPT.md` never asks
       for the block and `fleet-droid.sh` never calls the validator.
  This gate is the mechanical answer to that class. Landing it is worth more than most feature work.

  ## WHAT THIS TICKET REQUIRES (the work is built; the PROOF is what is owed)
  Do NOT rewrite the implementation. Verify it, and close the gaps below:
    a. **Red-proof BOTH gates externally.** Break each gate's assertion and observe the suite go
       RED. A gate-on-gates that cannot itself go red is self-refuting, and this ticket must not
       land on a green nobody made fail. Report the mutation and the RED output verbatim.
    b. **Prove the wiring FIRES.** Both are wired into `rig-ci-scope.sh` AND `preflight.sh`;
       show each actually executes and propagates a non-zero exit, rather than being merely listed.
    c. **Run `gate-integrity.sh` against the CURRENT rig** and report every gate it flags. It
       already found one false wiring claim (`2ca581c`); the live population is the real deliverable.
       Surface findings as new tickets — do NOT fix them here.
    d. Rebase/refresh against master if the branch has drifted (it predates several landings).

  ## OUT OF SCOPE
  Fixing whatever `gate-integrity.sh` flags. Surface, ticket, move on.

D&S — Deps & Sequence:
  - Depends on: nothing. The code exists and is pushed; this ticket exists so land.sh will accept it.
  - Sequence BEFORE substrate-first-gate-v2 (the remaining GATE 2 item, which needs a large rebase).
