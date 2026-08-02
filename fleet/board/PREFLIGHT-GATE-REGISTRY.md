repo: charon-private
tier: frontier
difficulty: 4
work_class: refactor
priority: 0
branch: feat/preflight-gate-registry
depends_on: MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE
owns: fleet/preflight.sh, fleet/state/GATE-REGISTRY.tsv, fleet/tests/preflight-gate-registry.test.sh
dep-kind: merge-order
real-dep: |
  real-dep: MARKER-PROOF-MECHANIZE — co-owns fleet/preflight.sh; merge-order only.
  real-dep: PREFLIGHT-GATE-RUN-HELPER — co-owns fleet/preflight.sh; merge-order only.
  real-dep: RECONCILE-WIRING — co-owns fleet/preflight.sh; merge-order only.
  real-dep: REPO-MAP-CONVERGE — co-owns fleet/preflight.sh; merge-order only.
  real-dep: SYNC-SCHEDULE — co-owns fleet/preflight.sh; merge-order only.

  MERGE-ORDER edges, NOT build prerequisites [[disjoint-owns-not-no-dependency]]. Five other live
  tickets declare `owns: fleet/preflight.sh`. NONE is claimed or in flight, so there is no concurrent
  writer today. These edges exist so the collision is ORDERED rather than silent, and because this
  ticket is the one that ENDS the contention: after it lands, a new gate is a ROW IN A TABLE, not an
  edit to a shared file, so those five tickets stop colliding on this file by construction.
  Whoever lands after this rebases onto the registry.
serial_justified: |
  ONE behaviour-preserving extraction. The registry, the single shared gate implementation, and the
  migration of all 9 existing gates are inseparable: a registry with no gates migrated changes
  nothing, and gates migrated without the shared implementation is the duplication again with extra
  indirection. Splitting it would also mean two agents editing preflight.sh — the exact contention
  this ticket exists to end.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Own worktree, one checkout one agent.
source: |
  Operator question 2026-07-31: "has fleet/preflight.sh become a GOD file? Is there a way to
  decompose it?" Investigated and confirmed — see MEASURED FACTS. Operator approved option (b).
note: |
  ## MEASURED FACTS (2026-07-31, verified — confirm, do not re-derive)
  `fleet/preflight.sh` is 968 lines / 61 functions. It is NOT tangled-organic-growth. It is ONE
  TEMPLATE COPY-PASTED:
    - the identical awk reopen block `$1==id{$7="open";$8=""}` appears **9 times, verbatim**
    - **23** `_<name>_red_<verb>` helper functions — the same status / ensure_open / close_if_open
      triad repeated per gate
    - **377 of 969 lines (38%)** sit inside gate/red functions

  Diffing `_board_red_ensure_open`, `_coverage_red_ensure_open` and `_handoff_red_ensure_open`
  shows them structurally IDENTICAL. Only FIVE values vary:
      id · priority · class · description · check-command

  This is a MISSING ABSTRACTION, not a god file — which is why it is mechanically extractable.

  ## WHAT TO BUILD
  A gate REGISTRY (declarative table: id, priority, class, description, check-command) plus ONE
  implementation of status / ensure_open / close_if_open / gate. Migrate all 9 existing gates to it.

  Target: collapse ~377 lines of duplication to a single implementation plus a data table.
  **Adding a new gate must become adding a ROW, with no edit to preflight.sh.** That property is
  the deliverable — it is what dissolves the 6-way contention. Prove it by adding a throwaway gate
  as a row in a test and showing it fires without touching preflight.sh.

  ## THIS IS A BEHAVIOUR-PRESERVING REFACTOR — THAT IS THE HARD PART
  preflight.sh runs at EVERY session start for every session. A botched extraction breaks everyone's
  startup. "The tests pass" is NOT sufficient evidence.

  ## DONE CONTRACT — RED, GREEN, AND DOGFOOD. ALL THREE.

  ### 1. BEFORE/AFTER EQUIVALENCE (the core proof)
  For **each of the 9 gates**, capture behaviour BEFORE the refactor and AFTER, and show they match:
    - gate condition BROKEN  -> gate goes RED, opens the correct TSV row (id, priority, class)
    - gate condition HEALED  -> gate goes GREEN and closes/clears the row
  Paste the before and after transcripts side by side. A gate you did not exercise in BOTH states,
  in BOTH versions, is a gate you have not preserved. Nine gates, four observations each.

  ### 2. RED-PROOF WITH EXTERNALLY SPECIFIED BREAKS
  Do NOT choose your own breaks — a self-chosen red-proof is why two prior P0 gates shipped catching
  nothing. For each of these, apply the break, WATCH IT GO RED, restore, watch GREEN, paste both:
    a. registry row with a check-command that exits non-zero -> that gate REDs
    b. registry row whose check-command is MISSING/unreadable -> FAIL CLOSED (RED), never silent green
    c. a gate row DELETED from the registry -> the gate stops running, and that is DETECTED
       (a silently-dropped gate is the worst failure mode of this refactor — it is invisible)
    d. the reopen path: a row previously `closed` whose condition re-breaks is RE-OPENED, not left closed
    e. priority/class from the registry actually reach the opened row (not hardcoded defaults)
    f. two gates RED simultaneously -> BOTH rows open (no last-writer-wins on the TSV)

  ### 3. DOGFOOD — REAL END-TO-END, NOT MOCKED
  Run the REAL `fleet/preflight.sh scan` against a REAL fleet and assert OBSERVABLE EFFECTS:
    - break one real gate's precondition, run the real preflight, and show the real TSV row opened
      with the right id/priority/class; heal it, re-run, show it closed
    - show total gate COUNT before == after (9 in, 9 out — nothing silently dropped)
    - show preflight's exit code semantics are unchanged for both a clean and a RED fleet
  Use a throwaway fleet copy under mktemp -d for anything destructive. Do NOT leave the live
  operator TSV mutated — restore it and prove it is restored.

  ### 4. GATES MUST ACTUALLY RUN
  Add the suite to the CI allowlist. `fleet/checks/rig-ci-scope.sh` is owned by other tickets — do
  NOT edit it. Write the exact CI_SUITES line you need to
  `fleet/state/handoff/PREFLIGHT-REGISTRY-CI-SUITE-LINE.txt` and say so in your report.

  ## SCOPE DISCIPLINE
  - Behaviour-preserving ONLY. Do NOT fix, improve, retune or re-prioritise any gate while moving it.
    If you find a gate that looks wrong, REPORT it — changing it hides a regression inside a refactor.
  - Do NOT touch the non-gate 62% of the file (detect_*, cmd_*, sync, foreman) beyond what the
    extraction strictly requires.
  - Do NOT add new gates. UNREVIEWED-WORK-ALARM is being built in parallel and will be added as a
    registry ROW by the manager after this lands — leave room for it, do not implement it.

## Dependencies & Sequence
  - Depends on: nothing to BUILD. The five depends_on entries are merge-order only (see real-dep).
  - Blocks: UNREVIEWED-WORK-ALARM's wiring (its check is built in parallel, wired after this lands),
    and it unblocks the five contending preflight.sh tickets by ending the collision.
  - Sequence: land BEFORE the alarm is wired. The alarm's own check does not depend on this.
  - Runs in parallel with: UNREVIEWED-WORK-ALARM (disjoint owns), BRIDGE-MIGRATE-DROID-CLIENT,
    and the five read-only research lanes.
