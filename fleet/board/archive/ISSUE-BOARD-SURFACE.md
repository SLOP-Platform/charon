retired: |
  RETIRED 2026-07-26 by operator decision (action item #4) — NOT done, STRUCK.
  Its work is preserved and pushed at 42b3904, but 2 of its 5 files wire the STRUCK
  issue-board.tsv fork into the LIVE SessionStart hook, so landing it would install a design
  this fleet explicitly rejected. PR #261 (feat/issue-board-surface) closed unmerged.
  Archived rather than deleted so the rejected design and its rationale stay recoverable.
repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: rig-meta
branch: feat/issue-board-surface-v2
owns: fleet/issue-board.sh, fleet/tests/issue-board.test.sh
depends_on:
serial_justified: the aggregator + its fail-on-revert test are one atomic capability (a surfacer with no
  proof it fires, or a test with no surfacer, ships nothing). NOTE the 2026-07-24 re-scope removed the
  "+ board schema + SessionStart-wire" half of this justification: there is no second schema any more
  (rows go to the canonical fleet/reds.tsv), and the surface anchors are CONTENDED files this ticket does
  not own (see ds:).
priority-why: |
  P:1 (was P:0, re-scoped 2026-07-24) — the P:0 stamp rested on `ds:`'s "slice 1, do FIRST", which was
  premised on the FORKED issue-board.tsv being the mechanism. That premise is dead: the canonical surface
  (fleet/reds.tsv + preflight's auto-register) already EXISTS and already blocks preflight, so the
  remaining work is generalizing a live mechanism, not building the missing #1 surface. That is the P:1
  definition verbatim — "attached CG work, not huge, not over-dependent" — and rig-meta at P:1 is
  well-precedented on this board (CLAIM-LADDER-HEALTH, META-GATE-CALLSITE-ENUM,
  RECONCILE-HANDOFF-FRESHNESS). NOT held at P:0: the operator's decision was to RE-SCOPE, not to
  escalate, and a P:0 here would rank anchor-blocked work above the 38 P:0s already on the board. NOT
  demoted to P:2: the underlying NEED is the operator's named #1 pain and is still genuinely unmet in
  general form — only the fork was rejected.
source: SG-ISSUE-CONTROL-PLANE slice 1 (SURFACE leg) — the genuinely-missing piece + operator's #1 pain
  ("makes issues visible to manager sessions; no red ever silently normalized"). RE-SCOPED 2026-07-24
  (operator decision #4): the NEED stands, the FORKED STORE does not.
bar: |
  ### THIS TICKET MUST NOT CREATE OR WIRE `fleet/state/issue-board.tsv`. NOT AS A CACHE, NOT AS AN
  ### INTERMEDIATE, NOT UNDER ANOTHER NAME. A DIFF THAT ADDS IT FAILS THIS TICKET.

  WHY, quoted so a future claimant cannot re-derive the fork in good faith — because that is exactly
  what would have happened here. `fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md` §5 step 0 (the row
  that governs every later step in its own table):

    "**Fold, don't fork.** This plane SUPERSEDES-SCOPE the desired-vs-actual class
     UNIFIED-RECONCILIATION-GATE owns. Land the DISCOVER+SURFACE legs as *that gate's aggregation
     axis*; the SELF-HEAL leg is the new consumer. **Two reconcilers must not drift.**"
     — risk column: "**HIGH if forked**"

  and §5's closing bar: "do NOT fork a second reconciler".

  THE TRAP IS IN THE DESIGN DOC ITSELF, so read this before reading that. The SAME table's **§5 step 2
  literally prescribes `state/issue-board.tsv`** ("union to `state/issue-board.tsv` … Wire into
  `foreman-cadence.sh` + `session-start.sh`"). Step 2 contradicts step 0, and step 0 wins. **§5 step 2's
  prescription of a `state/issue-board.tsv` store is SUPERSEDED as of 2026-07-24 and must not be
  implemented as written.** A claimant who opens the design doc, reads step 2, and builds the store is
  acting in good faith and is still wrong — which is precisely how branch feat/issue-board-surface came
  to wire the struck fork into the LIVE SessionStart hook and foreman-cadence.

  WHAT REPLACES IT: `fleet/reds.tsv` + `fleet/preflight.sh` ALREADY ARE the unified issue board, and
  they already have every property step 2 wanted — level-triggered re-proof on every preflight,
  auto-register on detection, auto-close when the condition clears, and a red that BLOCKS preflight
  rather than scrolling past. The pattern is implemented SIX times on master today
  (preflight.sh: BOARD_RED_ID:14, EXECUTOR_RED_ID:289, COVERAGE_RED_ID:325, HANDOFF_RED_ID:362,
  GRAPHIFY_FRESHNESS_RED_ID:770, BUDGET_RED_ID:806), each with the same cmd_add/status/cmd_close shape.
  Six hand-copies of one pattern is the thing to generalize. A SEVENTH STORE IS NOT.

  ONLY the forked store was rejected. The NEED — issues surfaced where a session actually sees them,
  with age-escalation so nothing is silently normalized — is REAL, currently UNMET in general form, and
  is why this ticket was re-scoped instead of retired. Retiring it would have discarded the need along
  with the fork, and the need would have resurfaced later as a fresh reinvention.
note: |
  ### RE-SCOPED 2026-07-24 — OPERATOR DECISION #4: RE-SCOPE, DO NOT RETIRE.
  A triage lane recommended retiring this ticket outright after finding that its salvaged branch wires
  the struck fork into live surfaces. The operator's decision is to RE-SCOPE. Reasoning, recorded so it
  is not relitigated: only the FORKED BOARD was rejected. The underlying need is real and unmet, and
  retiring the ticket would throw the need away with the fork — after which it resurfaces as a fresh
  reinvention by someone who never saw this decision.

  BRANCH DISPOSITION — PRESERVED, NOT LANDED:
    - `feat/issue-board-surface` @ `42b3904` ("salvage(issue-board-surface): PARTIAL … [PRESERVE ONLY,
      DO NOT LAND]") is pushed FOR PRESERVATION ONLY. 5 files / 221 lines. TWO of those five files wire
      `fleet/state/issue-board.tsv` into the LIVE SessionStart hook and foreman-cadence — landing them
      would install the design this session explicitly rejected. It is a reference for the detector-union
      logic ONLY; the store and both wires are struck.
    - **PR #261 IS TO BE CLOSED** (open at re-scope time, head `feat/issue-board-surface`, unmerged).
      THE OPERATOR CLOSES IT — no droid, sub-session or automation may close it. This line records the
      decision; it is not a claim that it has happened.
    - `branch:` is therefore a FRESH name (`feat/issue-board-surface-v2`); reusing the old name over a
      preserved-but-unlanded branch is the rebased-name collision class.

  The SURFACE leg. A thin aggregator that unions ALL existing DISCOVER detectors' verdicts (check_inert_code,
  plane-canary reconcile, reconcile-stale-claims, loop-guard, failing gate-tests/reds, done-but-unmerged)
  into ONE fleet/state/issue-board.tsv (severity|class|issue|source_detector|first_seen|age) + emits a
  SessionStart summary line to manager/supervisor sessions. first_seen/age ESCALATION makes silent
  normalization structurally impossible (an issue that persists gets louder). Level-triggered refresh via
  foreman-cadence.sh. A live prototype already dogfooded the detectors — build the real one on that.
accept: |
  ### RE-SCOPED 2026-07-24 — surface THROUGH the canonical mechanism; see `bar:` before starting.
  - `fleet/issue-board.sh` aggregates every registered detector (fail-LOUD if a detector errors, NEVER
    silent-empty) and emits each verdict AS A TRACKED RED IN `fleet/reds.tsv` via preflight's EXISTING
    register — the `cmd_add` / status-read / `cmd_close --override` shape already used six times
    (preflight.sh:14, 289, 325, 362, 770, 806). GENERALIZE that repeated shape into ONE reusable
    register call the aggregator drives; do NOT hand-write a seventh copy, and do NOT write a new store.
  - LEVEL-TRIGGERED, NOT EDGE-TRIGGERED — inherited free from the mechanism above and asserted anyway:
    a red is RE-PROVEN on every preflight, and AUTO-CLOSES when its condition clears. A stale row that
    survives its own condition clearing is RED.
  - age-escalation: a persisting issue's severity/visibility rises with age (anti-normalization). Use
    the reds.tsv row's existing date field as `first_seen`; do NOT add a parallel age store.
  - VISIBLE WHERE A SESSION ALREADY LOOKS. The need is surfacing, and preflight already blocks on a
    tracked red — that is the surface. Any additional SessionStart/foreman-cadence line is a ONE-LINE
    ANCHOR into a file this ticket does NOT own (see ds:), coordinated with that file's owner, not a
    rewrite and not a second surface.
  - e2e DOGFOOD: seed a real inert + a real stale-claim + a real red -> all three appear as tracked reds
    and BLOCK preflight, on a real run; clear one -> it auto-closes on the next run.
  - fail-on-revert test (`fleet/tests/issue-board.test.sh` — the `*.test.sh` name is required so
    fleet/gate.sh's glob actually runs it; a `test_*.sh` name is NOT matched): unregister a detector ->
    its issue class vanishes -> RED. Zero detectors examined -> RED `VACUOUS`, never a silent pass.
  - ANTI-FORK ASSERTION, MERGE-BLOCKING: the test asserts `fleet/state/issue-board.tsv` DOES NOT EXIST
    and that no shipped file references it. Re-introducing the struck store -> RED. This is what makes
    the `bar:` enforceable rather than advisory.
  - ADVERSARIAL REVIEW (reviewer != builder).
scope: |
  RE-SCOPED 2026-07-24. The aggregator ONLY, surfacing THROUGH the canonical issue board that already
  exists (`fleet/reds.tsv` + `fleet/preflight.sh`'s auto-register / level-triggered re-proof /
  self-close). Detectors already exist; this UNIONS them and generalizes the six hand-copied register
  blocks into one. It does NOT build a store, a schema, or a second surface — see `bar:`. Self-heal is a
  separate slice (ISSUE-SELF-HEAL-RULES); discovery of NEW detectors is KS29-DISCOVERY-LEG.
ds: |
  ## Dependencies & sequence
  P:1, no hard prereq (detectors and the target mechanism both exist). Feeds ISSUE-SELF-HEAL-RULES.
  Folds into UNIFIED-RECONCILIATION-GATE per DESIGN-SG-ISSUE-CONTROL-PLANE.md §5 step 0 — that fold is
  now the SCOPE, not a "consider".

  ### OWNS / ANCHOR SEPARATION (the re-scope's operational half)
  - OWNED (uncontended, verified 2026-07-24): `fleet/issue-board.sh`, `fleet/tests/issue-board.test.sh`.
  - REMOVED FROM owns: `fleet/state/issue-board.tsv` — the struck fork. It is not owned because it must
    not exist.
  - NOT OWNED, READ + AT MOST A ONE-LINE ANCHOR, COORDINATE WITH THE OWNER:
      * `fleet/preflight.sh` — the most contended file in the rig: SEVEN live owners (PLANE-CANARY-WIRE,
        REPO-MAP-CONVERGE, WCI-CONTENTION-TEETH, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING,
        SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE). This ticket REUSES its register; it does not restructure
        it and must never become an eighth concurrent writer.
      * `fleet/hooks/session-start.sh` — owned by SYNC-SCHEDULE. The old branch's SessionStart wire is
        struck; any replacement is a single anchor line agreed with that ticket.
      * `fleet/foreman-cadence.sh` — owned by PLANE-CANARY-WIRE + RECONCILE-WIRING.
  - `fleet/reds.tsv` has NO board owner and is a LIVE runtime data file mutated by preflight. It is
    written THROUGH the register, never edited as a file by this ticket, so it is deliberately not
    claimed in `owns:`.
