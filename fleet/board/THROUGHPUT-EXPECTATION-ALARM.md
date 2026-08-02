repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: ci-infra
branch: feat/throughput-expectation-alarm
depends_on:
owns: fleet/checks/throughput-expectation.sh, fleet/tests/throughput-expectation.test.sh, fleet/state/THROUGHPUT-EXPECTATION-ALARM.md, docs/review-log/THROUGHPUT-EXPECTATION-ALARM.md
serial_justified: |
  One expectation model with one alarm path. Split, you get a producer-liveness check and an
  artifact check that disagree about what "working" means.
substrate: N/A
substrate-novel: |
  Every INPUT exists and stays adopted — board ready/claimed counts, claim markers, git commit
  times, gh PR creation times, loop-guard records, the launcher's per-ticket outcome. Nothing new
  is measured. The novel slice is the EXPECTATION: what SHOULD have been produced by now, given
  what was available to work on.
accept: |
  THE GAP, stated precisely. `FLEET-STATUS-BOARD` (queue #7) verifies that CHECKS still run —
  registry, heartbeat, bidirectional meta-check. It does NOT verify that WORK still happens.
  A fleet where every check is green and nothing is being produced looks perfectly healthy to it.
  That was the literal state for hours on 2026-08-02.
  THREE SUB-SHAPES of "something stopped working, nothing announced it". FSB covers only the first:
    (a) a CHECK stops running        -> crontab wiped, detector silent 8h        -> FSB catches
    (b) a WORKER stops producing     -> reviewer pool at ZERO; droids claiming and no-op'ing
                                        (8 tickets quarantined)                  -> NOTHING catches
    (c) an ARTIFACT stops appearing  -> the next-session bootstrap vanished while
                                        the gate still exited 0                  -> NOTHING catches
  Heartbeats prove a process is ALIVE. Only an EXPECTATION proves it is doing anything.
  Done contract:
  1. (b) THROUGHPUT EXPECTATION: given N claimable tickets and M live tabs, the fleet should
     produce >= 1 commit-or-PR per interval. ZERO production for X while work was AVAILABLE is an
     alarm, not silence. Must distinguish "no work to do" (fine) from "work available and nothing
     produced" (alarm) — that distinction is the whole ticket.
  2. (c) ARTIFACT ASSERTIONS: for each producer that exists to emit something (close gate ->
     bootstrap + handoff; reviewer -> verdict; droid -> commit or an explicit release reason),
     assert the ARTIFACT, never the exit code. A producer that exits 0 having produced nothing is
     a silent partial success.
  3. Register both in FLEET-STATUS-BOARD's CHECK-REGISTRY so they inherit the bidirectional
     meta-check — the alarm must not itself become something that silently stops.
  4. Escalate via `pending.sh add --key` (keyed upsert, no row-spam).
  5. FAIL-ON-REVERT, both: seed claimable work with all tabs no-op'ing and prove the alarm FIRES;
     seed a producer that exits 0 with no artifact and prove it FIRES. Remove each and prove it
     goes quiet. Report verbatim.
  MEASURED CONTEXT: 2026-08-02 the board read healthy, tabs read busy, checks read green, and
  throughput on affected tickets was ZERO — discovered only because the operator asked why nothing
  was landing.

## Dependencies & Sequence

P0. Pairs with FLEET-STATUS-BOARD (#7) — that one watches the WATCHERS, this one watches the WORK.
Land FSB's registry first if they land together, so these two register into it rather than becoming
two more unregistered checks. Independent of ZERO-COMMIT-SPIN (#1): that ticket fixes ONE instance
of (b); this one DETECTS the whole class, including the next instance nobody has found yet.

## SUBSTRATE CHECK IS MANDATORY BEFORE ANY CODE (operator-flagged 2026-08-02)

Operator: "isn't this something a tool like deadcode is supposed to do? Don't we have tools already
that can do this but we are not utilizing them fully?" Half right, and the half that lands is the
important one.

WRONG TOOL, ALREADY PROVEN — do NOT spend time here: `deadcode`/`vulture` answer STATIC
reachability ("is this called anywhere in the source"). They cannot answer "did this process RUN",
"did this worker PRODUCE", or "did this artifact APPEAR" — those are runtime states. PRIORITY-TODO
D4 measured it: vulture flags `litellm_plane` at confidence 60 and **0 at confidence 80**, and
neither tool ever says "this module has no importers". Confidence measures PROVABILITY, not
IMPORTANCE.

RIGHT TOOLS, AND WE HAVE ADOPTED NONE OF THEM. Evaluate BEFORE writing a detector:
  - **dead-man's switch / heartbeat monitoring** (healthchecks.io, Cronitor, or self-hosted):
    purpose-built for "a scheduled job stopped and nobody noticed". EVAL-REGISTRY has **ZERO rows**
    for any of them. This session HAND-ROLLED heartbeat files for exactly this.
  - **Prometheus / OpenTelemetry** for worker liveness and throughput. PR #320 ranked OTel #1 for
    runtime-inert detection, but that eval was BOUNCED as an UNDER-SCOPED TRIAL (by its own table:
    Coverage.py 2/3 -> WATCH, OTel 0/3 -> ADOPT #1; prometheus marked down for a 404 the PR itself
    calls a one-line fix). Re-derive it fairly — do not cite the bounced verdict either way.
  - **monit** — a PAPER adoption: `command -v monit` fails here AND on 4-LOM. Either install it or
    stop listing it as adopted.
  - MCP-first: check EVERY candidate for an MCP interface before writing code (standing operator
    input, see PRICING-FEED).

HARD REQUIREMENT: land an EVAL-REGISTRY row per candidate BEFORE building. If we hand-roll a
detector for a problem healthchecks.io or Prometheus already solves, we have reproduced the exact
class this ticket exists to close — inside the fix for that class. Adopt the substrate; build only
the novel slice (the EXPECTATION model: "work was available and nothing was produced" is our
semantics, not an off-the-shelf metric).

### CORRECTION 2026-08-02 — I MISREAD D4. deadcode/vulture ARE the right tool for the STATIC half

The paragraph above says "WRONG TOOL, do NOT spend time here". That is WRONG for the static
half and the operator caught it. PRIORITY-TODO D4 is a diagnosis PLUS A FIX, and I quoted only the
diagnosis:
  > "Do not tune confidence up; use `exclude` + a whitelist ratchet GENERATED ONLY AFTER known
  >  inertness is fixed, or it freezes the bugs in permanently."
That ratchet IS the answer to the confidence-80 blind spot — not abandoning the tools.
It is also ALREADY BUILT: ticket `DEADCODE-TOOLS-WIRE` is live and **PR #209 (product, OPEN DRAFT)
adopts vulture+deadcode as a ratchet**. It sat in the open-PR list all session unread.

THE ACTUAL SPLIT — two different questions, two different tools, do not conflate them:
  * STATIC  "is this code called from anywhere in the source?"  -> vulture/deadcode WITH the D4
    ratchet (exclude + whitelist generated after known inertness is fixed). Covered by
    DEADCODE-TOOLS-WIRE / PR #209 — REVIEW AND LAND IT rather than rebuilding it.
  * RUNTIME "did this process run / did this worker produce / did this artifact appear?" -> NOT
    static analysis at any confidence setting. This is where dead-man's-switch and metrics tooling
    belong, and where we have ZERO adoptions.
This ticket owns ONLY the runtime half. Do not re-derive the static half; land PR #209.
