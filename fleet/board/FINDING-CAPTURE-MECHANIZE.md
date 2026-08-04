repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: design-review
branch: docs/finding-capture-mechanize
owns: docs/review-log/FINDING-CAPTURE-MECHANIZE.md
depends_on:
dep-kind:
work_class_note: design-review — an EXECUTED tool evaluation (D-002 rules apply) whose output is a
  verdict plus EVAL-REGISTRY rows. It writes no product code; the build is a separate ticket that
  this one must justify.
note: |
  ⛔ OPERATOR, 2026-08-04, verbatim: *"I need a way to mechanize ticket creation for sessions... you
  found several issues (ex: River container or D-003) but nothing was going to be done about that if
  I didn't remember it and that work would go stale until rediscovered... Including a tool that
  mechanizes enforcement, things can be DONE if it doesn't have enforcement attached. there has to be
  a tool for this."*

  ## THE MEASURED CASE — be precise about it, because the near-miss is the point
  On 2026-08-04 a session found, in passing: an UNDOCUMENTED `river-pg` container running 3 days on
  the gateway host; a compose file pinned 3 minor versions behind production; `DROID-LIFECYCLE-REAP`
  marked DONE while its reaper demonstrably does not reap; a droid's completed verdict sitting
  untracked in the wrong repo with its ticket still open; and the D-003 enforcement mechanism decided
  and never built.
  **All of them WERE eventually ticketed — but only because the operator asked for a session-end
  review.** Absent that prompt, every one dies in a session transcript. THE OPERATOR IS CURRENTLY THE
  CAPTURE MECHANISM. That is the defect. A finding that depends on a human remembering to ask is not
  captured, it is merely postponed.

  ## TWO DISTINCT CAPABILITIES — do not conflate them, score them separately
  **(A) FINDING → TICKET.** An observation made mid-work becomes a durable, triaged work item without
  a human remembering. Where do findings appear today? session transcripts, review-log fragments,
  agent reports, gate output, cron output. None of those routes into the board.
  **(B) DONE → REQUIRES ENFORCEMENT ATTACHED.** The operator's second sentence is the sharper half:
  *a ticket must not be closeable unless an enforcing mechanism is attached to it.* Today `done.sh`
  verifies a PR MERGED — nothing more. Both 2026-08-04 findings were DONE tickets whose code never
  ran. Candidate rule: a ticket cannot reach DONE without naming a REQUIRED check, a red-proofed
  test, or an explicit operator-approved waiver — and the named thing must be verified to EXIST and
  to be capable of going red.

  ## ⛔ METHOD IS FIXED BY D-002/D-009 — AN EXECUTED TRIAL, NOT A README SURVEY ⛔
  - **Re-open the candidate set** (D-002): selection was tainted, not just verdicts. Dependency-weight
    as a veto is a VOID lens — under D-001 a work-tracking layer with dependency gating is factory
    core, not a dependency to avoid.
  - **Both sides at full strength** (L6). Report what adopting DELETES (L2), total cost of ownership
    including session time (L1), and wall-clock to working for an operator who does not read code (L3).
  - **Reputation and star counts are explicitly disallowed.** The registry's own Mem0 case: 62K stars
    and its headline auto-extraction claim does not exist in the code. RUN the candidate.
  - File results as EVAL-REGISTRY rows (append-only, consult-first for all future tool questions).

  ## STARTING CANDIDATE SET — extend it, do not treat it as complete
  **Must re-open, already scored under a tainted lens:** **Forgetful** — B+2, the HIGHEST of any
  target, specifically for *"plans+tasks state machines with acceptance criteria, dependency gating,
  optimistic locking and cycle detection"*, and the reviewer called it *"the only mechanism in any
  target that addresses the '26 branches stranded' shape of failure."* **Rejected for "avoids a new
  dependency" — the exact lens D-002 voids.**
  **Capability (A):** Claude Code hooks (a SessionEnd/PostToolUse hook that extracts findings — on
  the AXIS 1 RE-TEST list already); GitHub `todo-to-issue`-style actions; git-bug; Linear/Plane
  (AXIS 1 RE-TEST); task-orchestrator (AXIS 2).
  **Capability (B):** OPA/Rego (AXIS 2 — policy-as-code, the natural fit for "DONE requires an
  enforcing artifact"); Conftest; GitHub required checks + rulesets + merge queue (already partly
  owned, `MERGE-QUEUE-EVAL.md` carries an unapplied ADOPT verdict); Danger/policy-bot for PR policy.
  **Adjacent, already running and undocumented:** `river-pg` — see RIVER-QUEUE-TRIAGE before scoring.

  ## SEQUENCING
  Overlaps LIFECYCLE-ENFORCEMENT, which is the BUILD of capability (B). **Run this evaluation FIRST**
  so that build either adopts something or is justified as a genuine gap — per D-009 axis 3, a
  hand-rolled capability nobody ever tool-shopped is how 73,019 lines of bash came to exist.

  ACCEPTANCE: (a) capabilities A and B scored SEPARATELY under the corrected lenses; (b) at least the
  top candidate per capability actually EXECUTED against this estate, with what-it-deletes measured;
  (c) EVAL-REGISTRY rows filed; (d) an explicit ADOPT / ADOPT-NARROW / BUILD verdict per capability,
  and if BUILD, a statement of why no tool fits; (e) Forgetful re-scored with its tainted rejection
  explicitly addressed.
