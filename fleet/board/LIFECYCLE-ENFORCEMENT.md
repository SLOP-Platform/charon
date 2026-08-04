repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: feat/lifecycle-enforcement
owns: fleet/checks/lifecycle-enforce.sh, fleet/tests/lifecycle-enforce.test.sh
depends_on:
dep-kind:
serial_justified: |
  A blocking gate and its red-proof are one unit, and a gate whose red-proof is missing is the exact
  class this ticket exists to kill. There is nothing to parallelise: one enforcer, one suite.
work_class_note: rig-meta — this is D-003's decided-but-never-built mechanism. It is the single
  highest-leverage unbuilt thing in the estate because every other recurring failure is a special
  case of it.
note: |
  ⛔ OPERATOR ASKED 2026-08-04: "what is the fix for D-007 pattern (and any other pattern that keeps
  happening)?" THIS TICKET IS THE ANSWER, and the answer was already DECIDED in D-003 and never
  built.

  ## THE PATTERNS ARE ONE PATTERN
  | recurring failure | how it shows up |
  |---|---|
  | **D-007** research lands, implementation drops | a verdict + review-log land; no ticket, no diff |
  | **deploy drift** | a fix merges to master and never reaches production (D-012 leaked for a full day AFTER it was fixed) |
  | **landed-but-never-worked** | `retire-done.sh` aborted EVERY retirement sweep since it was written; `DROID-LIFECYCLE-REAP` is marked DONE while orphans lived 2 days |
  | **stranded work** | 291 pushed-no-PR branches; a droid's LITELLM-COST-ADOPT verdict found untracked in the wrong repo with its ticket still open |
  | **unanswered questions** | the product-thesis question went unanswered ~3 WEEKS |

  **D-003 already named the single root cause, from two independent commissioned reviews that
  actually RAN 9 memory products:** *"Neither tool fixes the ROOT CAUSE: nothing in the system
  BLOCKS on an unfinished commitment. Both improve detection but don't enforce."*

  ⇒ The fix is NOT better memory, NOT a better handoff, NOT a rule to remember. **Every one of these
  is "a thing was started and nothing refused to proceed without it finished."** The estate has
  ~393 review artifacts, 76 registry rows and 9 installed memory products, and the operator still
  cannot get a feature built end to end. **A mechanism that exists and does not prevent the failure
  is not a solution — it is a wish** (DECISIONS.md, verbatim).

  ## WHAT TO BUILD — the blocking edges D-003 specified
  1. **An `ASKED` row in DECISIONS.md BLOCKS its dependent tickets.** The ledger already REQUIRES
     every ASKED row to name what it blocks; nothing reads that field. Make `claim`/launch refuse a
     ticket whose blocker is an open ASKED row, naming the question.
  2. **An active `DECIDED` cannot be contradicted by a merge.** At minimum: a diff that reverts or
     contradicts a cited decision REDs and must name the decision.
  3. **A VERDICT WITHOUT A MINTED TICKET IS NOT DONE** (D-007's own rule, currently unenforced). A
     landed `docs/review-log/*` fragment carrying an ADOPT/REJECT verdict must reference a board
     ticket id, or RED. This one edge alone would have caught the Hypothesis ADOPT-NARROW row, the
     merge-queue "configuration-only" row, and the OUTCOME-TEST-REWRITE that was never minted.
  4. **A DONE marker must be backed by evidence the thing RUNS**, not merely that a PR merged.
     Both 2026-08-04 findings were DONE tickets whose code never executed. Pair this with D-005's
     mutation testing rather than reinventing it.
  5. **Out-of-band notify for an unanswered ASKED row** — the operator is not at the terminal 24x7,
     and D-003 mandates it. The gap audit found observability/alerting is currently **NOTHING**.
     Cheapest known option: ntfy or Healthchecks.io — one container or one curl.

  ## HARD CONSTRAINTS
  - ⛔ **Enforcement is a GATE, not a rule to recall.** The rig's own doctrine already says "prefer
    the mechanism over recall" and nothing implements it. If the deliverable is a document telling
    sessions to be careful, THIS TICKET HAS FAILED.
  - ⛔ Start with edge 3 (verdict -> ticket). It is the cheapest, it is mechanically checkable from
    the diff alone, and it targets the most expensive pattern in the project.
  - ⛔ Per D-002/D-004: check for an existing tool before building. **Forgetful** scored B+2 — the
    highest of any target — specifically for "plans+tasks state machines with acceptance criteria,
    dependency gating, optimistic locking and cycle detection", and the review called it "the only
    mechanism in any target that addresses the '26 branches stranded' shape of failure." It was
    rejected for "avoids a new dependency", which D-002 voids as a tainted lens. **Re-open it before
    hand-rolling.**
  - D-008: this must not be bash if it holds state.

  ACCEPTANCE: (a) at least edge 3 is ENFORCED in CI and OBSERVED blocking a real violating diff;
  (b) each edge carries a red-proof — revert the enforcer and the suite goes RED; (c) the suite is
  in the CI_SUITES allowlist or it will never execute; (d) a written statement of which of the five
  edges are built and which are not, so the next session is not misled about coverage.
