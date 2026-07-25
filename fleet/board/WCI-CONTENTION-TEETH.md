repo: charon-private
tier: strong
difficulty: 4
priority: 1
work_class: rig-meta
branch: feat/wci-contention-teeth
worktree: /home/stack/charon-private-wt/WCI-TEETH
owns: fleet/wci-contention.sh, fleet/preflight.sh, fleet/tests/wci-contention-teeth.test.sh, fleet/tests/wci-strict.test.sh, fleet/tests/preflight-gate-run.test.sh, fleet/tests/meta-gate-wired.test.sh, fleet/state/GATE-GAP-LEDGER.tsv
depends_on: SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE, PLANE-CANARY-WIRE, RECONCILE-WIRING, REPO-MAP-CONVERGE, META-GATE-CALLSITE-ENUM, META-GATE-REDPROOF-REACHABLE, META-GATE-FINDINGS-ZERO
real-dep: META-GATE-CALLSITE-ENUM — DISJOINT owns, INHERITED from the absorbed leg (iii) and KEPT.
  Real build prereq: PHASE 4 wires the meta-gate into the BLOCKING chain. Wiring a DIRECTORY-shaped
  meta-gate fail-closed would hard-enforce the very addressing scheme that IS the root cause (an
  author still opts out by moving a file), so the audited population must be call-site-derived
  BEFORE it becomes blocking. That branch is BUILT + pushed @ a92019d but UNLANDED — this edge
  clears by LANDING it, not by bundling. dep-kind: build.
real-dep: META-GATE-REDPROOF-REACHABLE — DISJOINT owns, INHERITED and KEPT. Real build prereq: this
  ticket's own PHASE 4 red-proof (fleet/tests/meta-gate-wired.test.sh) must itself be runner-
  reachable under the rule that ticket adds; landing the wiring first ships the ENFORCING gate with
  a proof no runner executes — the exact defect being closed. dep-kind: build.
real-dep: META-GATE-FINDINGS-ZERO — DISJOINT owns, INHERITED and KEPT. Real correctness prereq: the
  meta-gate is RED with 4 live findings today. Wiring it FAIL-CLOSED before they are cleared blocks
  every session on pre-existing debt it did not create, which is precisely how a gate gets bypassed
  or disabled [[gates-must-actually-run]]. dep-kind: build.
real-dep: SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE, PLANE-CANARY-WIRE, RECONCILE-WIRING,
  REPO-MAP-CONVERGE — all SHARED single-owners of fleet/preflight.sh (RECONCILE-WIRING also shares
  fleet/state/GATE-GAP-LEDGER.tsv). Single-writer sequencing on the file PHASE 2 decomposes;
  co-writing it from parallel branches silently drops one side's gate. dep-kind: build.
state: PHASE 1 BUILT + GREEN + STAGED, NOT COMMITTED. The WCI-teeth work is finished in worktree
  /home/stack/charon-private-wt/WCI-TEETH. The commit was correctly REFUSED by the work-lease hook
  (`WORK-LEASE REFUSED: worktree branch 'feat/wci-contention-teeth' maps to NO board ticket`) — THIS
  TICKET IS THAT MAPPING. The sub did NOT bypass; that was the right call. Third ticket-mapping
  refusal today.
bundle: |
  BUNDLED 2026-07-24 (operator re-bundling pass, second wave). This ticket ABSORBED
  PREFLIGHT-GATE-RUN-HELPER — which had itself already absorbed META-GATE-PREFLIGHT-WIRE-CLOSED.
  Three tickets, one file (fleet/preflight.sh), one owner, one worktree, one branch.
  WHY: the operator approved DECOMPOSING fleet/preflight.sh (its 8 inline `*_gate()` functions ->
  one file each under fleet/checks/), and the SAME agent does that as commit 2 on THIS branch. That
  decomposition SUPERSEDES PREFLIGHT-GATE-RUN-HELPER's leg (iv) by construction: the nine copied
  `[ -f "$CHECK" ] || return 0` fail-open guards cannot survive an extraction that gives every check
  a fail-CLOSED contract as it moves. Leaving both tickets live would have two owners rewriting the
  same 906-line file from two branches — the exact multi-writer defect the whole wave exists to
  close. [[fix-root-cause-never-workaround]] [[anchor-lines-serialize-parallel-work]]
  REMOVED EDGE (b): META-GATE-PREFLIGHT-WIRE-CLOSED -> PREFLIGHT-GATE-RUN-HELPER -> (this ticket).
  Both hops were shared-file serialization on fleet/preflight.sh between legs ONE agent does
  sequentially. The real ordering survives as PHASE ordering below, not as board edges.
  ALL OTHER EDGES PRESERVED — see ds:.
source: Session 2026-07-24 board repair + operator approval of the preflight decomposition.
  fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md §2a (execution-verified fail-open
  table), §3 rank 2-3, §4 "Note on the fail-open pattern (#1-8)" and generalization step 3.
priority_justification: P:1 (PRIORITY-LADDER "attached CG work") — attached to the live gate-audit
  wave and it is the ANCHOR that dissolves the rig's worst file contention. Not P:0: nothing is
  mis-gating on master today and phase 1 is already green, so it drains fast rather than needing
  escalation.
work_class_note: rig-meta — the rig's own contention detector plus its primary session gate. No
  product code.
note: |
  PHASE 1 — WCI CONTENTION TEETH (BUILT, staged, needs only this ticket to commit).
  `fleet/wci-contention.sh` previously PRINTED recommendations nobody acted on — a detector whose
  verdict is discarded is decoration, the same class as foreman's DEFECT verdict dying in a
  `|| true` (class-scan §2d #21). This arms it:
    - AUTO-GENERATES a `priority: 1` decompose ticket when a file crosses the ownership threshold.
      IDEMPOTENCY is keyed on the contended PATH -> deterministic id `WCI-DEC-<PATH-SLUG>` plus a
      `wci_contention_target:` field, looked up across `board/*.md`, `*.md.parked` AND
      `board/archive/*.md` so a re-run cannot spawn duplicates or resurrect a parked remedy.
    - GENERATED TICKETS ARE VALIDATED BEFORE PLACEMENT — branch uniqueness, owns format,
      work_class/repo enums, difficulty band, priority band, a D&S section and non-vacuous
      fail-on-revert acceptance. An invalid generated ticket is DELETED and reported RED rather than
      landed on the board. A generator that can emit board-invalid tickets is a board-corruption
      engine. [[unified-work-creation-framework]]
    - SELF-CLOSING: contention dropping below threshold, or ANY owner carrying `serial_justified:`,
      PARKS the auto-ticket and clears its deps. A ticket with an ACTIVE CLAIM is never parked
      (never yank work out from under a running agent). Auto-tickets are EXCLUDED from the
      contention count they track, so the remedy can never sustain itself — a self-feeding remedy is
      a loop, not a fix.
    - FOUR FAIL-OPEN PATHS CLOSED in wci-contention.sh — non-integer N, N<1, missing board dir, and
      zero-discovery now exit 2 instead of 0. Zero items examined must never read green (S2
      NON-VACUOUS). `fleet/preflight.sh` auto-registers a BLOCKING red `wci-contention-detector-broken`
      when the detector is missing or refuses, so deleting the detector cannot green a session.
    - RATCHET SHIPPED OFF: `WCI_RATCHET_DAYS` in preflight.sh, flip `0` -> `7` to arm. Advisory-first
      is deliberate and MECHANICAL, not a follow-up ticket. [[security-is-a-ratchet-gate]]

  PHASE 2 — DECOMPOSE fleet/preflight.sh (operator-approved 2026-07-24; commit 2 on this branch).
  preflight.sh is 906 lines carrying 8 inline `*_gate()` functions and is a WCI DECOMPOSE CANDIDATE
  with SIX live board owners. Extract each inline gate to its own file DIRECTLY under
  `fleet/checks/` — NOT into a subdirectory: `gate-creation-standard.sh`'s enumerator is a
  NON-RECURSIVE glob (`"$CHECKS_DIR"/*.sh`), so a subdirectory would EXEMPT every extracted gate
  from the meta-gate audit, re-creating the class one directory down. That trap is named explicitly
  in the class scan §1 item 2; do not walk into it.
  This is ALSO the structural form of the absorbed leg (iv): each gate, as it is extracted, gets the
  "MISSING MACHINERY IS RED" contract, and the `cmd_add … >/dev/null 2>&1 || true` registry mask is
  dropped — a gate that cannot record its red has not run.

  PHASE 3 — the fail-open invariant, proven (absorbed leg iv acceptance).
  PHASE 4 — wire the meta-gate fail-closed + its ledger row (absorbed leg iii).

  FINDING RECORDED HERE (5th instance today of the same class): the same agent renamed
  `fleet/tests/test_wci_strict.sh` -> `fleet/tests/wci-strict.test.sh` because the `test_*.sh` name
  was NEVER matched by `fleet/gate.sh`'s `*.test.sh` glob — those 5 tests had never executed, ever.
  A red-proof no runner executes is not evidence. This is the fifth instance found today and it
  argues the NAMING CONVENTION ITSELF needs a gate; META-GATE-REDPROOF-REACHABLE is the ticket that
  makes runner-reachability an S1 sub-assertion, and this rename is a live instance of the defect it
  closes. Report the rename in the PR so the pattern is countable.
accept: |
  PHASE 1 — WCI TEETH (built; verify, do not rebuild).
  A. Auto-generation is IDEMPOTENT on the contended PATH: run the detector twice against a fixture
     over threshold => exactly ONE `WCI-DEC-<PATH-SLUG>` ticket exists. The lookup covers
     `fleet/board/*.md`, `fleet/board/*.md.parked` and `fleet/board/archive/*.md` — prove all three
     by fixture (a parked or archived prior remedy must NOT be duplicated).
  B. GENERATED-TICKET VALIDATION IS A GATE, NOT A LINT: a fixture whose generated ticket would be
     board-invalid (bad work_class, missing D&S, vacuous acceptance, duplicate branch, out-of-band
     difficulty or priority) => the file is DELETED and the run reports RED, non-zero. Prove at
     least three distinct invalidity classes.
  C. SELF-CLOSING, WITH THE CLAIM EXCEPTION: contention below threshold => the auto-ticket is PARKED
     and its deps cleared; an owner gaining `serial_justified:` => same; an auto-ticket with an
     ACTIVE CLAIM => NEVER parked. Prove the claim exception by fixture — it is the one that
     destroys work if wrong.
  D. NO SELF-SUSTAINING REMEDY: auto-tickets are excluded from the contention count they track.
     Fixture: generate the remedy, re-run => the file's owner count did NOT rise because of it, and
     no second remedy is generated.
  E. FOUR FAIL-OPEN PATHS EXIT 2, NOT 0: non-integer N, N<1, missing board dir, zero-discovery. Each
     proven by execution. Revert any one to `exit 0` => that case goes RED.
  F. PREFLIGHT REGISTERS THE BLOCKING RED: with `fleet/wci-contention.sh` DELETED from a fixture
     fleet, `preflight scan` opens `wci-contention-detector-broken` and exits non-zero. Deleting the
     detector must never green a session. Revert => RED.
  G. RATCHET IS OFF AND FLIPPABLE: `WCI_RATCHET_DAYS=0` ships; setting it to 7 in a fixture arms the
     blocking behaviour. Both states asserted — an unflippable ratchet is a comment.
  H. `fleet/tests/wci-contention-teeth.test.sh` and `fleet/tests/wci-strict.test.sh` both exit 0 AND
     are executed by `fleet/gate.sh`'s `*.test.sh` glob — PASTE THE RUNNER LINES. The rename of
     `test_wci_strict.sh` exists precisely because the old name was executed by nothing; shipping a
     new suite the runner cannot see would repeat the defect in the same commit.

  PHASE 2 — DECOMPOSITION.
  I. Each of the 8 inline `*_gate()` functions becomes its own file DIRECTLY under `fleet/checks/`
     (non-recursive glob — no subdirectory). preflight.sh becomes a thin chain that INVOKES them.
     Add each new path to this ticket's `owns:` in the SAME commit that creates it — the exact file
     names are set at build time and must not be left undeclared.
  J. NO BEHAVIOUR DRIFT WHEN GREEN: every moved gate keeps its existing red id, priority, class and
     description, and its `_*_red_close_if_open` behaviour on success. A diff that changes red ids
     is wrong — dependents key off them.
  K. EACH EXTRACTED CHECK GAINS A COMPANION RED-PROOF named `fleet/tests/<stem>.test.sh` so the
     meta-gate's matcher finds it AND a real runner executes it. A `test_*.sh` name is refused.

  PHASE 3 — THE FAIL-OPEN INVARIANT (absorbed leg iv).
  L. MISSING MACHINERY IS RED, everywhere: board_gate, executor_gate, coverage_gate, handoff_gate,
     graphify_freshness_gate, hold_reason_gate, done_merge_gate, detect_needs_push,
     startup_budget_gate. MEASURE the real count of fail-open guards on the branch base before
     starting (the class scan counted nine; six are the literal `[ -f … ] || return 0` idiom) and
     state the measured number in the PR — acceptance is "ZERO remaining", not "six changed".
     A missing / non-executable / rc-126 / rc-127 / signal-killed check MUST open the red row and
     make `preflight scan` exit non-zero. No `return 0`, no "skipped", no advisory.
  M. NO SILENT REGISTRY FAILURE: the `cmd_add … || true` mask is gone; if the red row cannot be
     appended, the gate fails loudly (non-zero).
  N. VACUITY GUARD (S2): `preflight scan` REDs if the gate chain executed ZERO gates. Assert a floor
     equal to the measured chain length.
  O. FAIL-ON-REVERT (fleet/tests/preflight-gate-run.test.sh — hermetic mktemp -d fixture fleet;
     NEVER delete anything in the real tree — the source scan proved this defect that way):
     1. per converted gate: machinery present + green => rc 0, no red row; machinery REMOVED from
        the fixture => rc non-zero AND the gate's red row is in the fixture reds.tsv. Restoring
        `[ -f … ] || return 0` makes every one of these go RED.
     2. registry-write failure injected (read-only fixture reds.tsv) => non-zero, never green.
     3. empty gate chain => rc non-zero (vacuity guard).
     4. machinery exists and exits 127 => RED, not pass.

  PHASE 4 — WIRE THE META-GATE FAIL-CLOSED (absorbed leg iii).
  P. Add a `gate_creation_standard_gate` leg running `fleet/checks/gate-creation-standard.sh check`
     through the SAME fail-closed machinery every other leg now uses. NO new script, NO new runner,
     NO bespoke existence guard. Its `scan` (always-rc-0 advisory) mode MUST NOT be used — advisory
     wiring is the defect, not the fix.
  Q. FAIL-CLOSED ON MACHINERY AND ON FINDINGS: a missing/non-executable/rc-127 meta-gate REDs the
     session; a non-zero `check` verdict opens the red row, a zero verdict closes it.
  R. THE SELF-REPORT DIES WITH THE DEFECT: the meta-gate's own `not-wired` ADVISORY stops firing;
     update its wiring-status probe to name where it is ACTUALLY wired (honestly, per S8) — leave
     neither a false "wired" claim nor a stale "not-wired" one.
  S. LEDGER ROW: append ONE row to fleet/state/GATE-GAP-LEDGER.tsv via the sanctioned
     `gate-creation-standard.sh append …` subcommand recording this class miss (a meta-gate whose
     population was directory-shaped, so 23 enforcement checks were never audited and the tier-drift
     block escaped by placement). Use a root_class already traced in fleet/GATE-CREATION-STANDARD.md
     — the subcommand REFUSES an untraced class. APPEND ONLY; the LEDGER_MIN floor must still pass.
  T. FAIL-ON-REVERT (fleet/tests/meta-gate-wired.test.sh — hermetic, `*.test.sh` so gate.sh runs it):
     meta-gate ABSENT => `preflight scan` non-zero + red row (revert to `[ -f … ] || return 0` =>
     this case goes RED); stub exiting 1 => row opened; stub exiting 0 => row closed; the leg ABSENT
     FROM THE CHAIN => RED (it must be provably IN the chain, not merely defined); stub exiting 127
     => RED.

  WHOLE TICKET.
  U. `bash fleet/validate_board.sh` rc 0 modulo pre-existing reds. `bash fleet/preflight.sh scan` on
     the REAL tree reports its rc honestly — a newly-surfaced pre-existing red is a FINDING to
     report, not a reason to weaken a gate [[never-ignore-preexisting-issues]]. Run the NAMED suites
     only; do NOT run the full fleet/tests sweep (the benchmark grader suites block for hours).
  V. PHASE GATING — READ THIS BEFORE MARKING ANYTHING DONE. Phase 1 may be committed as soon as this
     ticket exists (it is already green). Phases 3 and 4 require META-GATE-CALLSITE-ENUM,
     META-GATE-REDPROOF-REACHABLE and META-GATE-FINDINGS-ZERO to have LANDED. If they have not when
     phases 1-2 are ready, SUBMIT phases 1-2 and leave this ticket OPEN — do NOT mark it done with
     phases 3-4 unbuilt, and do NOT downgrade a leg to advisory to get a green session.
  W. ADVERSARIAL REVIEW REQUIRED (reviewer != builder) — this rewrites the rig's primary session
     gate AND arms a board-writing generator. Confirm BY EXECUTION, not by diff: (i) the generated
     -ticket-invalidity path deletes and REDs; (ii) the active-claim park exception holds; (iii) at
     least three converted gates go RED with machinery deleted; (iv) deleting
     gate-creation-standard.sh makes preflight RED. The whole class is "it looked wired".
serial_justified: |
  Phases 1-4 are ONE file and ONE invariant chain. The decomposition (2) is what makes the fail-open
  fix (3) structural rather than nine copy-edits, and the meta-gate wiring (4) is one more leg of
  the chain (2) creates — wiring a directory-shaped meta-gate into a monolith would enforce the very
  addressing scheme that is the root cause. Splitting them re-creates the six-way multi-writer
  contention on fleet/preflight.sh that phase 2 exists to delete, and phase 1 is already built as
  one green commit. There is no collision-free slice to fan out to.
scope: |
  Rig-only [[product-vs-build-rig-boundary]]. Does NOT change the meta-gate's OWN logic (legs i/ii
  — META-GATE-CALLSITE-ENUM / META-GATE-REDPROOF-REACHABLE own that file), does NOT edit
  fleet/checks/rig-ci-scope.sh (HANDOFF-GATE-NONBYPASSABLE), does NOT change any gate's verdict
  logic — only WHERE it lives and what happens when its machinery is missing or unrunnable — and
  does NOT fix the product-registry `reachability-gate` finding (different repo).
ds: |
  ## Dependencies & sequence
  BUNDLE: absorbed PREFLIGHT-GATE-RUN-HELPER (leg iv) which had absorbed META-GATE-PREFLIGHT-WIRE-
  CLOSED (leg iii). Two board edges deleted; both were shared-file serialization on
  fleet/preflight.sh between legs one agent does back-to-back in one worktree.
  KEPT — shared-file single-writer sequencing on fleet/preflight.sh (deleting these would be a real
  multi-writer defect and validate_board would flag the un-ordered owns-collision):
    SYNC-SCHEDULE (BUILT + pushed, UNLANDED — clears by landing), MARKER-PROOF-MECHANIZE,
    PLANE-CANARY-WIRE, RECONCILE-WIRING (also shares fleet/state/GATE-GAP-LEDGER.tsv),
    REPO-MAP-CONVERGE.
  KEPT — real build/correctness prereqs of PHASE 4, disjoint owns:
    META-GATE-CALLSITE-ENUM (BUILT + pushed @ a92019d, UNLANDED), META-GATE-REDPROOF-REACHABLE,
    META-GATE-FINDINGS-ZERO.
  OPERATOR DECISION PENDING — ANCHOR INVERSION (recommended, NOT applied unilaterally): phase 2
  DISSOLVES the fleet/preflight.sh contention, so landing this ticket LAST means all five preflight
  owners first write into the 906-line monolith and are then rewritten by the decomposition — five
  wasted rebases. The cheaper order is to make THIS ticket the ANCHOR: land it first (after
  SYNC-SCHEDULE, the only preflight owner with code ready), and flip MARKER-PROOF-MECHANIZE,
  PLANE-CANARY-WIRE, RECONCILE-WIRING and REPO-MAP-CONVERGE to `depends_on: WCI-CONTENTION-TEETH` so
  each adds its OWN check file under fleet/checks/ instead of co-writing the monolith. All four are
  already blocked on other work, so the edge costs them no schedule time. NOT applied here because
  it rewires four tickets the operator has not signed off on. [[anchor-lines-serialize-parallel-work]]
  BENCH-OOB-GRADING owns `preflight.sh` UNPREFIXED — that is fleet/benchmark/preflight.sh, a
  DIFFERENT file (verified 2026-07-24 by `find . -name preflight.sh`). No edge needed or declared.
  CONCURRENCY-SAFETY: work from /home/stack/charon-private-wt/WCI-TEETH — feat/wci-contention-teeth
  is checked out there and git will refuse a second checkout [[one-checkout-one-agent]]. The
  GATE-GAP-LEDGER edit is a single APPEND through the sanctioned subcommand, never a rewrite. Never
  co-write fleet/preflight.sh from a parallel branch.
