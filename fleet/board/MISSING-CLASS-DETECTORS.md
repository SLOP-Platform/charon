repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: ci-infra
branch: feat/missing-class-detectors
depends_on:
owns: fleet/checks/class-detectors.sh, fleet/tests/class-detectors.test.sh, fleet/state/MISSING-CLASS-DETECTORS.md, docs/review-log/MISSING-CLASS-DETECTORS.md
serial_justified: |
  One detector harness with one output contract consumed by one registry. Each class is a few
  lines inside it; splitting per class means N tabs inventing N output shapes the status board
  then cannot consume uniformly.
substrate: N/A
substrate-novel: |
  Where a tool already answers a class it is ADOPTED as-is and merely wired: git for uncommitted
  tools and untracked reviews, gh REST for deploy drift, the existing pricing/catalog readers for
  rot, claim-jedi-name for the name pool. Nothing is reimplemented. The novel slice is the
  UNIFORM verdict contract across classes so one registry can consume them all.
accept: |
  OPERATOR DIRECTIVE 2026-08-02: "anything with a lifecycle and no terminal gate accumulates" —
  mechanize a detector for EVERY class, run on the cron cadence, surfaced LOUDLY at session start.
  FLEET-STATUS-BOARD supplies the registry + runner + meta-check; it can only register checks
  that EXIST. These classes were measured accumulating today and have NO detector:

  | class | measured today | detector |
  |---|---|---|
  | tools built but never committed | 3 files, 362 lines, never in git AT ALL | NONE |
  | reviews written but untracked | 35 review logs, incl. a NEEDS-REVISION that falsified a PR's safety claim | NONE |
  | config SSOT key absent that code READS | SPILL_UP_COST_CEILING missing -> spill-up fails closed on every tab | NONE |
  | deployed artifact drift | 4-LOM on build_sha 9659998, far behind master | NONE |
  | catalog / pricing rot | 10 of 861 priced; a `-free` model billed $0.15 | NONE |
  | daemons/sidecars outliving purpose | session-bridge retirement slated 2026-07-26, still dual-running | NONE |
  | identity/name pool exhaustion | 48% burned by claim stubs, ~9 names left before sessions fail | NONE |
  | scheduled jobs themselves | the crontab entry is untracked machine-local config | NONE |
  | operator-action staleness | OPERATOR-ACTIONS at #30, no age signal | NONE |

  Done contract:
  1. ONE detector per class, uniform contract: id, verdict OK|FINDING(n)|STALE|BROKEN, one-line
     summary, and a recovery command. Same shape stranded-work.sh already emits.
  2. Register every one in CHECK-REGISTRY.tsv so FLEET-STATUS-BOARD's bidirectional meta-check
     covers it — a detector that stops running must show MISSING, never vanish.
  3. Cron cadence + heartbeat per detector. Two-leg rule: REGISTERED is not EXECUTING. Proven
     live 2026-08-02 — the crontab entry existed for 10 minutes before the first fire, and the
     gate correctly refused to read clean until a heartbeat appeared.
  4. Escalate via pending.sh add --key (keyed upsert; a 20-min cadence must not append ~72
     rows/day).
  5. FAIL-ON-REVERT per detector: seed the exact condition it detects and prove it FIRES. A
     detector never seen to fire is not a detector — that is the 101-unrun-proof-suites class,
     and building it here would be self-refuting.
  Start with the cheapest three, all pure git: uncommitted tools, untracked reviews, scheduled-job
  registration. They would each have caught a real loss today.

## Dependencies & Sequence

P0. Companion to FLEET-STATUS-BOARD — that ticket owns registry+runner+meta-check, this one owns
the detectors it registers. Land the status board FIRST so each detector has somewhere to
register as it lands; otherwise detectors accumulate unregistered, which is the very class.
No other inbound deps. Sequence inside: cheapest-and-git-only first (uncommitted tools, untracked
reviews, cron registration), then the ones needing network or live state (deploy drift, catalog
rot, daemon liveness).

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
