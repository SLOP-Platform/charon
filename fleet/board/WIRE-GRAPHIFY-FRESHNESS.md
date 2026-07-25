repo: charon-private
tier: strong
difficulty: 4
priority: 1
work_class: ci-infra
branch: feat/graphify-nocaller-ledger
owns: fleet/checks/graphify-freshness.sh, fleet/tests/graphify-freshness.test.sh, fleet/state/ON-DEMAND-TOOL-LEDGER.tsv, fleet/wci-contention.sh
depends_on: WCI-CONTENTION-TEETH
dep-kind: build
priority-why: |
  P:1 — attached CG work on the live built-but-not-wired CG, and dep-blocked behind WCI-CONTENTION-TEETH
  so it cannot be claimed today. NOT P:0 (HANDOFF-GOTCHA-VERIFIABLE is the keystone gating the landing
  queue); NOT P:2 (it is not standalone — it extends a mechanism that already landed).
source: operator 2026-07-23 ("mechanized automated method to always keep the code map updated as things change"); ON-DEMAND-TOOL-LEDGER.tsv row (graphify: 0 callers, hand-refresh only); EXTENSION source operator 2026-07-24 ("I need this mechanized, fully wired in, anti-stale, with loud notices")
note: |
  The code map (graphify-out/graph.json) is refreshed ONLY by hand — product graph is days stale, rig
  graph absent/week-stale, and `grep graphify` over fleet/*.sh + checks = 0 callers. The freshness gate
  fleet/checks/graphify-freshness.sh ALREADY EXISTS ("MECHANIZED WIRING … never-on-demand") but is
  ORPHANED (0 callers) — built-but-not-wired. REUSE it; do NOT rebuild. This is the [[dynamic-tools-never-on-demand]]
  contract (cadence + multiple smart triggers + tested) and a reconciler leg (code-map == actual code).

  EXTENDED 2026-07-24 — see `accept:` PART 2. The WIRING half LANDED (preflight.sh:766-797,
  land.sh:420, fleet/hooks/session-start.sh:102-107, foreman-cadence.sh:157-180 all call this gate on
  master, and branch fix/wire-graphify-freshness-gate is merged). The pending retire branch
  `chore/retire-wire-graphify` (95a5091, UNMERGED) would archive this ticket — DO NOT MERGE IT until
  the extension below lands. The extension is the QUERY half: the graph has been fresh all day and
  NOTHING EVER ASKS IT "what is built but has no caller". `branch:` is therefore a FRESH name
  (feat/graphify-nocaller-ledger); the old branch is already in master.
accept: |
  ### PART 1 — WIRE THE FRESHNESS GATE (LANDED 2026-07-24, kept as the ratchet)
  - WIRE the existing graphify-freshness.sh gate so it runs automatically on ALL smart triggers, never
    on-demand: (a) fleet/preflight.sh scan-dispatch, (b) post-land (fleet/land.sh success hook),
    (c) SessionStart, (d) a cadence timer (foreman-cadence.sh). Each wiring is a one-line anchor into a
    shared file — COORDINATE with the owners of preflight.sh/land.sh, do not rewrite them.
  - STALE == RED: `graphify-freshness.sh check` fails LOUD when any tracked graph is older than its repo's
    latest code change (map != code drift), covering BOTH the product AND the rig graph (rig currently
    unmapped — add it). A trigger auto-runs `graphify update` to refresh, then re-checks.
  - fail-on-revert test (fleet/tests/graphify-freshness.test.sh): seed a code change newer than the graph
    => check RED; refresh => GREEN. Revert the wiring/staleness logic => a stale map passes silently (RED).
  - bash fleet/validate_board.sh GREEN.

  ### PART 2 — EXTENSION 2026-07-24: ASK THE FRESH GRAPH THE ONE QUESTION IT IS NEVER ASKED
  THE DEFECT: the code map was CURRENT all day, and every one of these was found by a HUMAN ASKING,
  never by a tool. Seed evidence (must appear in the first ledger regeneration — a first run that finds
  none of these is RED, not a pass; that is the vacuity signature):
    - src/charon/decompose_effort.py — an effort scorer (2.0*difficulty + 0.15*size + 1.0*behaviours)
      that the tier classifier ignores entirely.
    - fleet/benchmark/budget-derive.py — p95x1.5 budget derivation, fully tested, ZERO callers, and its
      budgets.tsv does not exist on disk.
    - fleet/plane-canary.sh — zero callers (8/10 planes RED, unseen).
    - fleet/stale-check.sh — zero callers.
    - litellm.Router — 52 params, we set 6; litellm_params["order"] computed then DISCARDED.
    - 33 never-run test files; 21 built-but-unlanded branches.
  The data existed. No question was asked of it. This part makes the question MECHANICAL.

  (E1) NEW SUBCOMMAND ON THE EXISTING TOOL — NO NEW SCRIPT. `graphify-freshness.sh no-callers
    [repo-root]...`, alongside the existing `check` / `update` / `reuse-check` / `summary` / `paths`.
    It reads graphify-out/graph.json, enumerates defined nodes (python defs/classes/modules, bash
    functions and executable scripts — graphify already has a tree-sitter bash extractor and ~6,198 rig
    bash nodes) and reports every node with ZERO inbound call/reference edges. A NEW STANDALONE
    DETECTOR SCRIPT IS FORBIDDEN: the whole point of this ticket is that we keep rebuilding what exists.

  (E2) ANTI-STALE — A CACHED VERDICT PAST ITS TTL IS A LIE (the 9-day-stale-grader failure shape).
    `no-callers` runs the EXISTING staleness primitive FIRST (graph.json[built_at_commit] == HEAD).
    Stale or absent graph => exit 2 and the word UNKNOWN — NEVER a last-known-good verdict, never a
    silent pass. Every ledger row carries a `graph_commit` stamp; a row whose graph_commit != the
    repo's current HEAD renders as UNKNOWN, not carried forward as fact.

  (E3) REUSE THE LEDGER THAT ALREADY IS THIS — fleet/state/ON-DEMAND-TOOL-LEDGER.tsv. It ALREADY
    classifies tools by invocation reality (MECHANIZED | ON-DEMAND-ONLY | NO-TRIGGER | NEVER-RUN |
    RARELY-RUN | DEAD), and it is a HAND-GENERATED 2026-07-16 snapshot that nothing has refreshed since
    — i.e. the ledger is itself an instance of the bug it documents. `no-callers` REGENERATES it from
    the graph. Do NOT create a second ledger. New columns: `graph_commit`, `exempt`, `exempt_reason`.

  (E4) EXEMPTIONS ARE EXPLICIT AND RECORDED, NEVER IMPLICIT-BY-SHAPE. A detector that screams about
    every `__main__` is switched off within a day. An exempt row MUST carry BOTH a category
    (entrypoint | cli-target | test-helper | plugin-hook | external-api | operator-hold) AND a
    non-empty reason. Inferring an exemption from shape alone (has `__main__`, lives under tests/, is
    chmod +x) is FORBIDDEN and is a red-proof case (E9.3). An empty reason is RED, not a skip.

  (E5) LOUD — AND LOUDNESS RIDES ON TEXT, NOT ON EXIT CODE. Two live mask points, verified 2026-07-24:
    fleet/handoff.sh:383 runs `foreman-cadence.sh handoff 2>&1 || true`, and every SessionStart hook in
    settings.json is `|| true`. An exit code is swallowed at BOTH surfaces. Therefore:
      - the finding is emitted as a distinctively-marked TEXT banner at the TOP of the trigger's
        output — `### INERT CODE — N BUILT-BUT-NO-CALLER (graph <sha>)` — never as one more WARN line
        among the existing WARNs;
      - AND it registers a TRACKED RED through preflight's existing register (the
        `GRAPHIFY_FRESHNESS_RED_ID` / cmd_open / cmd_close pattern at preflight.sh:770-787), so it
        BLOCKS preflight instead of scrolling past. Reuse that register; do not invent a second one.

  (E6) FAIL-CLOSED AND NON-VACUOUS. Missing graph, missing graphify, missing/unparsable ledger, or
    missing jq/python => RED (exit 2), never a silent skip. ZERO nodes examined => RED `VACUOUS`. The
    check can never pass by examining nothing.

  (E7) FIX THE CADENCE ORPHAN — OR THIS RECREATES THE BUG ONE LEVEL UP. Verified 2026-07-24: every live
    invocation of foreman-cadence.sh is `session-start` / `post-land` / `handoff` / `watchdog`
    (handoff.sh:383, hooks/session-start.sh, land.sh, plane-canary.sh:86). The `cadence` subcommand
    itself has NO cron and NO systemd caller. Wiring the new leg only there would make the inert
    detector inert. This ticket MUST land a REAL periodic caller for `foreman-cadence.sh cadence`
    (systemd user timer unit or a registered crontab entry, committed to the repo as CONFIG — config is
    not a new detector script) plus the red-proof at E9.7 that asserts a live caller exists.

  (E8) REUSE THE WCI EMIT SEAM — findings become TRACKED WORK, not text. fleet/wci-contention.sh
    `--generate` already does idempotent, board-valid, self-closing, keyed ticket emission (keyed on a
    contended PATH; validates every emitted ticket BEFORE it lands and deletes+reds anything that would
    red the board; reconciles and self-closes when the condition clears). Generalize it to
    `wci-contention.sh emit --source <x> --key <k>`, retaining `--generate` as the exact alias
    `emit --source wci-contention --key <path>` (no behaviour change for the existing caller). The
    no-callers leg then emits via `emit --source inert --key <path>`. DO NOT WRITE A SECOND EMITTER.

  (E9) FAIL-ON-REVERT + NON-VACUOUS ACCEPTANCE, IN A TEST A REAL RUNNER REACHES. All red-proofs go in
    fleet/tests/graphify-freshness.test.sh, which fleet/gate.sh:33 picks up via its `*.test.sh` glob.
    NOTE THE TRAP: the sibling fleet/tests/test_graphify_freshness.sh is named `test_*.sh` and is NOT
    matched by that glob — the gate never runs it. Do not put the red-proof there.
      1. CORE: fixture graph with a defined-but-uncalled node => RED and named in the ledger. Add a real
         inbound call edge => GREEN. Revert the no-callers leg => this test goes RED.
      2. NO FALSE POSITIVE: a node with a real inbound call edge is never flagged.
      3. EXEMPTION IS EXPLICIT: exempt row with category+reason => not flagged; the SAME node with an
         empty reason => RED; a node that merely HAS `__main__` and no recorded exemption => still
         flagged.
      4. ANTI-STALE: stale/absent graph => exit 2 + UNKNOWN, and the ledger's prior verdict is NOT
         reported as current.
      5. NON-VACUOUS: zero nodes examined => RED `VACUOUS`.
      6. LOUD-UNDER-MASK: run the trigger with its exit code discarded (`… || true`) and assert the
         banner TEXT is present in stdout AND that the tracked red got registered.
      7. CADENCE CALLER EXISTS: assert a live periodic caller for `foreman-cadence.sh cadence`; delete
         it => RED. (Guards E7 — this is the anti-decay property.)
      8. EMIT SEAM: `emit --source inert --key <path>` creates exactly ONE board-valid ticket; a re-run
         creates none (idempotent, keyed); the ticket self-closes once the node gains a caller.
      9. SEEDS PRESENT: the first regeneration lists the six seed findings above. A regeneration that
         finds none of them is RED.
  - bash fleet/validate_board.sh stays GREEN, no new REDs.
scope: |
  Wire the orphaned graphify-freshness gate (reuse) + add the rig to mapped repos. Makes the code map
  self-refreshing + drift-loud. A leg of the plane-canary suite ("map plane": code-map == actual code).

  EXTENDED 2026-07-24: and then ASK THE FRESH MAP THE QUESTION NOBODY ASKS — "what is built but has no
  caller". A `no-callers` subcommand on the SAME tool, regenerating the ledger that already exists
  (ON-DEMAND-TOOL-LEDGER.tsv), riding the FOUR TRIGGERS THIS TICKET ALREADY LANDED, fail-closed and
  non-vacuous, loud as TEXT because both surfaces mask exit codes, exemptions explicit-only, and
  emitting tracked tickets through the WCI emit seam rather than a new emitter.
  [[dynamic-tools-never-on-demand]] [[gates-must-actually-run]] [[fix-root-cause-never-workaround]]
  [[adopt-substrate-build-only-novel-slice]] [[detection-ticketed-never-built]]
ds: |
  ## Dependencies & sequence
  P1, no build prereq. Reuse graphify-freshness.sh — do NOT rebuild. Wiring anchors coordinate with
  preflight/land owners. Composes with the reconciliation-gate + the plane-canary design.

  ### EXTENDED 2026-07-24
  - depends_on: WCI-CONTENTION-TEETH — HARD, `dep-kind: build`. The idempotent keyed emitter this
    extension generalizes exists ONLY on branch feat/wci-contention-teeth @ 300e9a4, and this ticket now
    owns fleet/wci-contention.sh, which WCI-CONTENTION-TEETH also owns. Sequencing is by MERGE ORDER:
    that ticket is built+pushed and must land first; the `emit --source/--key` generalization is then a
    small seam change on top, not a concurrent rewrite.
  - REUSE-CHECK RECORD (why this is an EXTENSION and not a fourth ticket — the reuse check IS the point
    of the work):
      * INERT-INSTANCE-DETECT (product repo, owns tools/check_inert_code.py) — the PRODUCT half of the
        same class: constructed-but-never-INVOKED, Python only, and it must ship standalone with no rig
        leak. It cannot see fleet/*.sh, fleet/benchmark/*.py or unlanded branches. Kept separate on
        purpose; this ticket neither duplicates nor edits it.
      * INERT-WIRING-ENFORCEMENT-DURABLE (design-review, owns ONE doc
        fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md) — root-causes WHY prior anti-inert fixes decay
        and explicitly SPAWNS a build backlog. Design-only; it cannot carry a mechanism. This extension
        IS the first item of that backlog, so the design ticket references it instead of boarding a new
        build ticket.
      * WIRE-GRAPHIFY-FRESHNESS (this ticket) — already OWNS the tool that queries the graph AND the
        four landed triggers. Extending it costs zero new scripts and zero new wiring anchors. A fourth
        ticket here would have been self-refuting.
  - ANCHOR FILES ARE READ + AT MOST ONE-LINE ANCHOR, NOT OWNED HERE: fleet/preflight.sh (contended by
    WCI-CONTENTION-TEETH and others), fleet/land.sh, fleet/hooks/session-start.sh,
    fleet/foreman-cadence.sh (contended by PLANE-CANARY-WIRE + RECONCILE-WIRING). All four anchors
    ALREADY EXIST from Part 1 — the extension changes what the gate ASKS, not where it runs. The only
    NEW anchor need is the periodic caller for `foreman-cadence.sh cadence` (E7), a committed
    timer/cron CONFIG file; coordinate its landing with RECONCILE-WIRING, which owns foreman-cadence.sh.
  - SUPERSEDES the unmerged retire branch `chore/retire-wire-graphify` (95a5091), which would archive
    this ticket on the strength of Part 1 alone. Do not merge it until Part 2 lands.
  - FRESH BRANCH `feat/graphify-nocaller-ledger`: the Part-1 branch fix/wire-graphify-freshness-gate is
    ALREADY MERGED into master, so reusing it would be a rebased-branch name collision.
  - reads-only (no owns claim, no edit): fleet/state/TOOL-WIRING-AUDIT.md,
    fleet/state/GAP-AUDIT-toolfirst.md, fleet/state/WIRING-AUDIT-MATRIX.md, tools/check_inert_code.py.
