repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: rig-meta
branch: eval/workflow-e2e-audit
depends_on:
owns: fleet/state/WORKFLOW-E2E-AUDIT.md, fleet/tests/workflow-e2e.test.sh
substrate: N/A
substrate-novel: |
  The subject under test is OUR OWN ticket lifecycle — board schema, claim ladder, worktree/lease,
  gate, land, done-marking, retire. No external tool models it. Adopted tools are REUSED as
  instruments where they fit (gh for PR state, graphify for reachability, validate_board /
  gate-integrity / stranded-work for the checks that already exist) rather than re-implemented.
serial_justified: |
  A pipeline audit is only meaningful end-to-end. Testing stages in isolation is exactly how these
  defects survived — each stage passed its own check while the SEAMS between stages leaked.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. This is an EXECUTED audit, not a doc review.
source: |
  Operator, 2026-08-01: deep and complete (red/green/dogfood) test of the workflow — ticket
  creation through scheduling, work, wiring, commit, push, close — to find whether the process
  works or creates silent failures and bottlenecks. Adversarial review required afterwards.
note: |
  ## THIS IS A DOGFOOD TEST, NOT A DOC REVIEW
  **Mint a real throwaway fixture ticket and walk it through the ENTIRE pipeline**, instrumenting
  every stage transition. Reading the scripts is NOT the deliverable. If a stage cannot be
  exercised for real, say so explicitly and mark it UNVERIFIED — never infer it works.

  ## THE STAGES TO INSTRUMENT (each is a seam where something has already leaked)
  1. **CREATE** — mint a ticket. Does the creation gate enforce priority/substrate/owns/D&S?
  2. **SCHEDULE** — is it reachable by the claim ladder? At what rank, and why that rank?
  3. **CLAIM** — atomic lease, worktree creation, reviewer/builder identity.
  4. **WORK** — brief rendering, owns-boundary enforcement, model resolution.
  5. **GATE** — does the gate actually run, and can it actually go RED?
  6. **COMMIT/PUSH** — work-lease, board-lock, land paths.
  7. **PR** — draft vs ready, CI required checks.
  8. **REVIEW** — who reviews, is reviewer != builder enforced, what happens on BOUNCE.
  9. **MERGE** — who merges, what proves it.
  10. **CLOSE** — done-marking, retire/archive, dependents unblocking.
  11. **REPORT** — does the session report land, with real derived fields.

  ## KNOWN SILENT FAILURES — ALL MEASURED 2026-08-01. Confirm each still reproduces, then look
  ## for the ones NOBODY HAS FOUND YET. This list is the floor, not the ceiling.
  - **19 tickets MERGED but still marked `submitted`** — F2 auto-done-on-merge is systemic, not
    incidental. The board over-reported remaining work and dependents read as falsely blocked.
  - **9 of 10 open PRs are DRAFT** — never marked ready, so they cannot merge even once reviewed.
  - **46 tickets carried no `priority:`**; claim.sh sorts priority ASC with unset = 9999, so 30
    were never dispatched — oldest 22 days.
  - **loop-guard quarantined 3 P0 tickets on an INFRA fault** — its infra exemption exists and is
    structurally inert because no caller passes `--reason`.
  - **`WCI-CONTENTION-TEETH` merged + archived but its done-marker was never written**, silently
    blocking 2 tickets forever.
  - **Merge resolution DESTROYED 10 board tickets** with no deleting commit; found only by forensics.
  - **A stale `real-dep` held a P0** citing an `owns:` the other ticket no longer declared.
  - **`$FLEET` in the brief resolved relative for 1 of 5 droids**, losing a judgment file and
    silently degrading its report to NOT-REPORTED.
  - **leak-guard flagged the MANAGER's own board edits as a droid leak** (false positive).
  - **Required-full-suite-green CI deadlocked two PRs** that each fixed the other's failure.
  - **`--only` pinning defeats the self-feeding pool** — tabs starve and are never reused.
  - **`fleet/checks/rig-ci-scope.sh` has 9 owners**, serializing every ticket that adds a test.

  ## WHAT THE REPORT MUST ANSWER
  1. For each of the 11 stages: does it work, and HOW IS THAT KNOWN (executed evidence, not code
     reading)?
  2. **Where are the SEAMS that no check covers?** Every failure above lived between two stages
     that each passed their own gate. Enumerate the seams and say which are unguarded.
  3. **Which failures are SILENT** (no red, no alarm, work simply stops)? Silent failures are the
     dangerous class — a loud failure gets fixed.
  4. Where is the throughput actually lost? Measure stage dwell times from real data (PR open->
     merge, submitted->done, mint->claim). **The bottleneck is a measurement, not an opinion.**
  5. What is the MINIMUM set of changes that would close the most seams? Rank by seams-closed,
     not by effort.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  `fleet/tests/workflow-e2e.test.sh`, hermetic (`mktemp -d`, fixture board+repo, offline, no gh):
    a. a fixture ticket walks CREATE->CLAIM->WORK->GATE->COMMIT->CLOSE and every transition is
       asserted. Break any single transition -> RED naming that stage.
    b. **merged-but-not-done is DETECTED** — the 19-ticket class. Revert the detection -> RED.
    c. **a ticket with no `priority:` is caught at creation** — the never-dispatched class.
    d. **an infra-fault release does NOT quarantine** — the false-quarantine class.
    e. **a done-marker missing after archive is DETECTED** — the WCI-CONTENTION-TEETH class.
    f. ANTI-OVER-BLOCK: a clean ticket walking the happy path stays GREEN throughout.
  Then DOGFOOD against the REAL board and report actual counts per stage.

  ## ADVERSARIAL REVIEW REQUIRED (operator directive)
  When the report is done it gets an INDEPENDENT adversarial review — reviewer != builder. The
  reviewer's job is to find the stages the audit declared healthy WITHOUT executed evidence, and
  the seams it missed. A stage marked "works" on the strength of reading the script is a finding
  against the audit, not a pass.

D&S — Deps & Sequence:
  - Depends on: nothing. Read-mostly; owns its own report + a new hermetic test.
  - Do NOT edit the pipeline scripts here — this ticket DIAGNOSES. Fixes are separate tickets so
    each gets its own red-proof.
