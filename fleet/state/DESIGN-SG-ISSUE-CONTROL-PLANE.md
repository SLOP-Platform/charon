# SG-ISSUE-CONTROL-PLANE — design of record (2026-07-24, manager-authored, operator-approved)

> Deliverable for `SG-ISSUE-CONTROL-PLANE` (P:0, DESIGN umbrella). DESIGN ONLY — spawns 3
> one-lens build-slice tickets on operator approval; nothing here is built yet. THE universal
> DISCOVER → SURFACE → SELF-HEAL control plane for the droid fleet: auto-discover every
> recurring failure CLASS, SURFACE them LOUDLY so none is ever silently normalized, and
> (gated, per-class) AUTO-LAUNCH the fix to the SG droid tab.
> Supersedes/absorbs UNIFIED-PLANE-CANARY-FRAMEWORK, gate-test-health-on-master, loud-failure-monitor.
> Tags: `[[reviews-use-our-own-tools]]` `[[gates-must-actually-run]]` `[[anti-accretion-KS20]]`
> `[[decomposed-by-design-not-reactive]]`.

## 0. The shape of the problem — why a control plane, not a script

The fleet today has detectors that FIND issues and a board that TRACKS work, but the
gap between them is the operator's entire burden:

| What the fleet HAS | What the fleet DOESN'T have | Real incident (this repo) |
|---|---|---|
| 10+ detectors firing on preflight (detect_untracked_drift, detect_secret_scan, detect_repo_drift, detect_claim_loop, detect_wci_contention, detect_inflight_landscape, detect_stranded_work, detect_cg_drift, detect_gateway_token_drift, detect_config_drift) | A unified ISSUE BOARD that aggregates every detector's output into ONE visible surface the manager/supervisor/operator checks at SessionStart | The operator ran `preflight.sh` every session, scanning 10+ detector blocks, mentally re-deriving "what matters" each time |
| plane-canary.sh + plane-canary-registry.tsv (10 declared planes, wired+passing+proven) | A DISCOVERY leg that walks graphify's relations graph and finds CLASSES of failure not yet in any registry — the unregistered-inert, unregistered-stale, unregistered-quarantined | The FINAL-E2E-REVIEW phantom class: a plane declared-but-unwired; nobody noticed the gap until a false-green silenced the check |
| UNIFIED-RECONCILIATION-GATE (board↔PR, owns-tracked, gate-wired, review-gate) | An AUTO-HEAL leg that (gated, per-class) LAUNCHES a droid to fix a detected issue instead of just printing RED | A stranded-work finding stays on the detector block for days; the operator must manually convert it to a ticket |
| lease-enqueue.sh + claim.sh + fleet-droid.sh (SG droid dispatch) | A SELF-HEAL RULE ENGINE that matches issue-class → fix-ticket-template → gated autonomous launch | The operator is the rule engine |

The cure is **one closed-loop event-driven auto-remediation control plane**: sensors discover
failure classes → an issue-board surfaces them LOUDLY at SessionStart → (gated, per-class)
self-heal rules auto-launch the fix to the SG droid tab. Same substrate, three legs,
one live loop.

**Folding scope (per this design's recommendation):** the DISCOVER + SURFACE legs fold INTO
the existing UNIFIED-RECONCILIATION-GATE axis, not a second reconciler. The preflight scan
dispatch already runs reconciliation checks; the issue board is a SURFACE of what those
checks + detectors produce. The self-heal leg is the new axis.

**ADOPT THE PATTERN, NOT THE TOOL.** The architecture is **StackStorm sensor → rule → action**
(sensors emit events, rules match class → template, actions launch work) + **ArgoCD opt-in
self-heal** (auto-remediation is gated, never automatic for high-blast classes) + **Kubernetes
level-triggered** (every check re-runs on cadence; state is re-proven, not assumed) +
**Backstage/Dagster facts → checks → scorecard/freshness** (the issue board is a
scorecard of fleet health). All four are ADOPTED AS PATTERNS, not as tools — every one
is service-shaped (K8s API server, ArgoCD controller, StackStorm event bus, Backstage
catalog) and wrong for a solo bash/python fleet. The **algorithm** is adopted; the
**infrastructure** is bash+python on ~0 infrastructure.

## 1. Architecture — the closed loop

```
┌─────────────────────────────────────────────────────────────────┐
│                    SG-ISSUE-CONTROL-PLANE                        │
│                                                                   │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────────────┐  │
│  │ DISCOVER │────>│   SURFACE    │────>│     SELF-HEAL        │  │
│  │  (KS29   │     │  (issue-     │     │  (rule-engine +      │  │
│  │  discov- │     │   board)     │     │   gated launch)      │  │
│  │  ery leg)│     │              │     │                      │  │
│  └────┬─────┘     └──────┬───────┘     └──────────┬───────────┘  │
│       │                  │                        │               │
│  ┌────▼──────────────────▼────────────────────────▼───────────┐  │
│  │                SHARED SUBSTRATE                             │  │
│  │  • graphify relations graph  (code/component topology)      │  │
│  │  • issue-class registry      (KS20 data rows, not scripts)  │  │
│  │  • heal-template registry    (issue-class → fix template)   │  │
│  │  • UNIFIED-RECONCILIATION-GATE (the existing axis)          │  │
│  │  • plane-canary framework    (the existing canary suite)    │  │
│  │  • lease-enqueue + review-pool (droid dispatch + review)    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  FIRING LAYER: preflight (session start + gate) + cadence timer   │
└─────────────────────────────────────────────────────────────────┘
```

**Level-triggered, not edge-triggered.** Every check re-runs on cadence (the same shape
as `fleet/checks/reconcile-timer.sh` in UNIFIED-RECONCILIATION-GATE §3.1). Issues are
re-proven on every tick — a cleared issue auto-closes; a re-emergent issue re-opens.
The board is always a **current** picture, not a ledger of past events.

**The loop, per cadence tick:**
1. **DISCOVER:** walk graphify's relations graph + the issue-class registry + the
   existing detector suite. For every registered failure class, run its discovery
   algorithm primitive (set-diff, graph-reach, staleness-probe, subset-membership,
   content-hash — the KS29 vocabulary from UNIFIED-RECONCILIATION-GATE §4.3). Produce
   a flat list of `(class, instance, severity, evidence)` tuples.
2. **SURFACE:** upsert every instance into the issue-board (`fleet/state/issue-board.tsv`).
   Closed issues whose evidence matches the last RED snapshot stay closed. NEW or
   re-emergent issues open. The board is rendered LOUDLY at SessionStart (preflight)
   with a per-class summary the operator can NOT miss.
3. **SELF-HEAL:** for every OPEN issue of a class with a registered heal-template AND
   a gating policy that permits auto-launch, compute eligibility (blast-tier of the
   fix ≤ droid tier threshold, heal-template adheres to conventional-commit,
   reviewer != builder). If eligible, lease-enqueue the fix to the SG droid tab.
   Record the launch in the issue-board row (`heal_launched_at`, `heal_ticket`).
   The launched droid's `done.sh` + review-log are the proof of remediation;
   the next cadence tick closes the issue iff the evidence is gone.

**Why level-triggered (K8s control-loop pattern):** an edge-triggered architecture
("when a failure happens, fire an event") requires a durable event bus and misses
pre-existing issues forever. A level-triggered architecture re-proves state every
tick — an issue that existed before the plane was built is caught on the first run.
This is the same pattern UNIFIED-RECONCILIATION-GATE uses (§3.1 timer) and the same
posture plane-canary.sh takes (reconcile leg re-proves every declared plane is
wired+passing+proven on demand).

## 2. The seven failure classes (DISCOVER)

Every class has the same five fields from the UNIFIED-RECONCILIATION-GATE substrate
(§1): **name**, **desired-source**, **actual-source**, **drift-algorithm**, **RED
condition**. Plus a **heal-template** (optional — not every class is auto-healable).

### 2.1 `inert/not-wired` — built-but-never-invoked

- **desired-source:** every detector/gate/canary declared in the registries:
  - `fleet/checks/*.sh` + `fleet/checks/*.py` (the rig check suite)
  - `tools/check_*.py` (the product check suite)
  - RULE-REGISTRY.tsv rows with `status ∈ {ACTIVE, ENFORCED}`
  - EVAL-REGISTRY.md rows with `verdict = ADOPT` and non-empty `enforced_in`
  - plane-canary-registry.tsv rows (every declared plane)
  - RECONCILER-REGISTRY.tsv rows (every declared reconciler)
  - issue-class registry rows (this plane dogfoods itself — see §6)
- **actual-source:** the set of paths actually executed by a real firing layer:
  - preflight.sh scan dispatch (the existing chain at `preflight.sh:878`)
  - land.sh pre-conditions
  - foreman-cadence.sh timer ticks
  - hooks/session-start.sh
  - .github/workflows/*.yml (product CI)
- **drift-algorithm:** `graph-reachability` (KS29 leg) — declared nodes MUST be
  reachable from the firing-layer root set. Walk the call graph from every firing-
  layer entry point; any declared node with indegree 0 from the firing set is inert.
- **RED condition:** any declared check/detector/canary with no reachable invocation
  path → RED with a "wire this into `<firing layer>` at `<location>`" instruction.
  **This is the exact class GATE-GAP-LEDGER tracks** (e.g., `check_catalog_case_quant.py`
  shipped wired-into-zero gates). The issue-board entry for this class is a
  consolidation of the GATE-GAP-LEDGER into the unified surface.
- **heal-template:** `fix/wire-inert-<id>` — add the invocation line to the correct
  firing layer. **GATED: NEVER auto-launch.** Wiring the privileged control plane is
  hot-path work; the heuristic for WHERE to wire it is operator judgment, not a
  script. Surface-only.

### 2.2 `failing/RED` — check-failing-on-master

- **desired-source:** every check in the gate suite that should return GREEN on
  master.
- **actual-source:** the last-run exit code of each check (from `fleet/state/` run
  logs, or from a live re-run on the current cadence tick).
- **drift-algorithm:** `exit-code-check` — re-run each check against the current
  tree; any non-zero exit is RED.
- **RED condition:** a check on master returns non-zero → the check is RED.
  This is the `board-validator-red` class (preflight.sh auto-registers
  `board-validator-red` in reds.tsv when validate_board.sh goes RED). The
  issue-board generalizes this: every check produces its own row, not just
  the board-validator umbrella.
- **heal-template:** variable — per-check, the fix is different. A `tooling`
  class fix (e.g., a lint rule triggered by a new file) may be auto-launchable;
  a `hot-path` fix (e.g., a routing regression) is gated-operator-only.

### 2.3 `stale/drift` — drift-between-desired-and-actual

- **desired-source:** the declared desired state in every registry (config-manifest.tsv,
  SSOT sources, graphify stamps, plane-canary lastrun records, done markers,
  review markers).
- **actual-source:** the observed state (live config diffs, graphify-out/graph.json's
  `graph_built_at_commit` vs HEAD, plane-canary-lastrun.tsv timestamps, git log
  merge SHAs vs done.sh records).
- **drift-algorithm:** `staleness-probe-TTL` + `set-diff/bidirectional` (KS29 legs).
  For time-sensitive state: current time - `last_updated_ts` > `max_staleness_s` →
  STALE. For set-membership state: (desired_set, actual_set) → set-diff → any
  asymmetric element is DRIFT.
- **RED condition:** any STALE or DRIFT pair. The existing detectors cover subsets:
  - `detect_config_drift` → config SSOT drift (config-drift.sh --advisory)
  - `graphify_freshness_gate` → code-map staleness (graphify-freshness.sh check)
  - `detect_repo_drift` → unpushed/dirty tracked files
  - `detect_gateway_token_drift` → env-vs-opencode.json token staleness
  - UNIFIED-RECONCILIATION-GATE §1.1 (board↔PR drift), §1.2 (owns-tracked drift),
    §1.3 (gate-wired drift), §2.1 (review-gate drift)
  The issue-board consolidates all drift detectors into ONE surface.
- **heal-template:** `fix/drift-<class>` — auto-refresh stale state (run
  `graphify update`, run `config-sync.sh`, run `reconcile-merged.sh`). For
  non-destructive refresh (graphify, config-sync): SAFE to auto-launch. For
  destructive (auto-close a ticket): gated.

### 2.4 `quarantined-good` — false-green canary

- **desired-source:** every declared plane-canary row + every gate check MUST produce
  a provable RED when the thing they guard fails (fail-on-revert).
- **actual-source:** the dogfood_test for each canary/check — the fail-on-revert
  test that seeds a failure and proves the check catches it. A canary whose
  dogfood_test passes (the check guards the breach) is proven. A canary whose
  dogfood_test fails was never proven, or a regression broke the fail-on-revert.
- **drift-algorithm:** `boolean-probe` — run the fail-on-revert dogfood. If it
  exits 0, the canary is proven. If it exits non-zero, the canary is quarantined-
  good (the guard is broken, so the GREEN the canary currently shows is unreliable).
- **RED condition:** any canary whose dogfood_test exits non-zero, or whose
  dogfood_test was never run (no row in plane-canary-lastrun.tsv), or whose
  dogfood_test is missing/blank. This is the `proofless canary` class from
  plane-canary.sh's `_reconcile_row` — generalized to the issue board.
- **heal-template:** `fix/quarantine-<plane>` — investigate WHY the dogfood fails
  and fix the canary or the dogfood. **GATED: NEVER auto-launch.** A false-green
  canary means the guard is blind; fixing it requires understanding WHAT it should
  have caught. Operator judgment only.

### 2.5 `junk-commit` — unreviewed-merge / wrong-branch / creation-masquerading-as-completion

- **desired-source:** the merge discipline:
  - Every `≥hot-path` merge carries a review marker (BLAST-TIER Consumer A)
  - Every merge's branch matches a ticket's `branch:` (UNIFIED-RECONCILIATION-GATE §1.1)
  - Every merge's files are owned by exactly ONE ticket (the AMBIGUOUS ladder)
  - Every merge's branch was created from origin/master (no merge-from-stale-base)
  - No direct push to master bypasses land.sh
- **actual-source:** `git log` + `gh pr list --state merged` + `done.sh` records +
  `reviewed/<id>` markers.
- **drift-algorithm:** `subset-membership` + `content-hash/checksum` (KS29 legs).
  The creation-PR guard (`reconcile-merged.sh:194-222`): a merged PR that adds the
  ticket's `fleet/board/<id>.md` but delivers NONE of its `owns:` is a creation, not
  a completion.
- **RED condition:** the AMBIGUOUS ladder's R-A, R-B, R-C conditions (UNIFIED-
  RECONCILIATION-GATE §1.1) + the review-gate's R-J, R-K, R-L (§2.1) + the
  `land.sh` `git -C` bypass seam (§3.3). The issue-board row for this class
  is the consolidation of ALL merge-discipline violations across all reconcilers.
- **heal-template:** `fix/junk-<kind>` — close the false-done ticket (R-A, safe),
  flag operator PR for ticketing (R-B, needs operator), warn stale branch (R-C,
  advisory only). **Safe auto-launch: R-A only** (auto-close a proven-done ticket
  with `done.sh --merged-sha`).

### 2.6 `done-but-unmerged` — work-landed-but-not-recorded-as-done

- **desired-source:** every ticket marked `done` in the board's status column.
- **actual-source:** GitHub PRs merged whose head branch matches a ticket's
  `branch:` AND whose merge SHA is recorded in `done.sh` / `fleet/state/done/`.
- **drift-algorithm:** `set-diff/bidirectional` over `(done-ticket-set, merged-PR-set)`.
  The inverse of R-A (§1.1): a ticket is DONE (board says so) but no merged PR
  exists for its branch → false-done. AND: a PR is merged but the board ticket
  is NOT done → merged-but-not-retired (R-A). Both are the same set-diff, opposite
  direction.
- **RED condition:**
  - **S-A:** a board ticket whose `status` says done/in-review but whose `branch:`
    has NO merged PR → false-done (the ticket claims done but no evidence).
  - **S-B:** a merged PR whose files touch a ticket's `owns:` but the ticket is NOT
    done → the merging happened without a ticket (or the wrong ticket was marked).
- **heal-template:** `fix/unmerged-done-<id>` — mark the ticket done if the evidence
  proves it (merged PR exists for its branch). **Safe to auto-launch** for S-A
  when the merged PR evidence is deterministic.

### 2.7 `un-registered component` — fleet-component-with-no-registry-row

- **desired-source:** every fleet component MUST have a row in at least ONE registry
  (plane-canary-registry.tsv, RULE-REGISTRY.tsv, RECONCILER-REGISTRY.tsv, EVAL-REGISTRY.md,
  config-manifest.tsv, or the issue-class registry itself).
- **actual-source:** walk the fleet file tree (`fleet/*.sh`, `fleet/checks/*`,
  `fleet/state/*.md`, `fleet/hooks/*`, `fleet/tests/*`) + graphify's component graph.
  For each component, check registry membership.
- **drift-algorithm:** `set-diff` over `(registry-entries, fleet-files)`. The
  `graph-reachability` primitive from §2.1 already catches inert components;
  this catches components that are WIRED but UN-DECLARED — the inverse class.
- **RED condition:** any fleet file that is load-bearing (invoked from a firing
  layer) but has no registry row → un-registered. AND: any registry row that
  names a file absent on disk → ghost entry. The pair together cover the full
  registry coverage axis.
- **heal-template:** `fix/register-<component>` — add a registry row for the
  component. **Safe to auto-launch for tooling-tier components** (a script
  that runs on preflight is tooling; auto-registering it is safe).

## 3. The SURFACE — issue-board as the single pane of glass

### 3.1 Issue-board schema

One git-tracked tsv: `fleet/state/issue-board.tsv`.

```
class          instance_id           severity  status    first_seen            last_seen             evidence_summary    heal_template    heal_launched_at  heal_ticket
inert          check-gate-parity     P1        open      2026-07-23T14:00:00Z  2026-07-24T08:00:00Z  unreachable from preflight; declared in RULE-REGISTRY row 17  fix/wire-inert-gate-parity  —  —
failing        validate-board        P0        open      2026-07-24T06:00:00Z  2026-07-24T08:00:00Z  exit=1: cycle `next` status on 3 tickets  —  —  —
stale          graphify-map          P1        open      2026-07-23T18:00:00Z  2026-07-24T08:00:00Z  graph_built_at_commit=abc1234, HEAD=def5678 (7 code files changed)  fix/drift-graphify-refresh  2026-07-24T08:01:00Z  SG-FIX-graphify-stale
quarantined    egress-key-canary     P0        open      2026-07-23T20:00:00Z  2026-07-24T08:00:00Z  dogfood test egress-key-canary.test.sh exit=2; canary unproven  —  —  —
junk-commit    feat/unsafe-merge     P0        open      2026-07-24T01:00:00Z  2026-07-24T08:00:00Z  PR #456 merged without review marker; blast_tier=hot-path  —  —  —
done-unmerged  WORKLOOP-FIX-3        P2        open      2026-07-24T07:00:00Z  2026-07-24T08:00:00Z  board says done; branch feat/wl-fix-3 has no merged PR  fix/unmerged-done-WORKLOOP-FIX-3  —  —
unregistered   fleet/checks/selfcheck-cycle.sh  P2  open  2026-07-24T08:00:00Z  2026-07-24T08:00:00Z  invoked from preflight:878, not in any registry  fix/register-selfcheck-cycle  —  —
```

**Status lifecycle:** `open` → (evidence re-proven RED) → stays `open`. Evidence
GREEN on a cadence tick → `auto-closed`. Operator can `defer` an issue with a
human note (a `deferred_until` + `defer_reason` pair — the issue re-opens
after the deferral expires so it can't be silently forgotten). `auto-closed`
issues that re-emerge are `re-opened`.

### 3.2 Surface at SessionStart (loud, unmissable)

The issue-board is rendered as the FIRST block of preflight output, after the
header and BEFORE the tracked-reds scan. Shape (from existing patterns in
plane-canary.sh's reconcile output + preflight.sh's reds table):

```
════════════════════════════════════════════════════════════
 ISSUE BOARD — 7 open issues across 7 classes
 (auto-closed: 3 since last cadence tick; deferred: 1)
 Registry: fleet/state/issue-board.tsv
════════════════════════════════════════════════════════════
 P0  failing          validate-board           board-validator RED (3 tickets with cycle `next`)
 P0  quarantined      egress-key-canary        dogfood broken — untrusted GREEN
 P0  junk-commit      feat/unsafe-merge        PR #456: no review marker (hot-path)
 P1  inert            check-gate-parity        declared in RULE-REGISTRY, unreachable from preflight
 P1  stale            graphify-map             code map stale (7 file changes since last stamp)
 P2  done-unmerged    WORKLOOP-FIX-3           board done, no merged PR
 P2  unregistered     selfcheck-cycle.sh       wired in preflight, not in any registry
────────────────────────────────────────────────────────────
 SELF-HEAL launched this tick (1):
   stale/graphify-map → ticket SG-FIX-graphify-stale (droid queued)
────────────────────────────────────────────────────────────
 AUTO-ACTION PENDING (operator must decide — 3):
   junk-commit/feat/unsafe-merge → review the merged PR then adjudicate
   quarantined/egress-key-canary → fix the dogfood or retire the canary
   inert/check-gate-parity → wire into preflight or remove from registry
════════════════════════════════════════════════════════════
```

The operator can NOT miss this block — it renders before the reds table and
the gate verdict, and a non-empty open-issue count is a preflight WARN (never
a BLOCK for surface-only issues, but a tracked-red for P0 classes).

### 3.3 The board as the reconciliation axis convergence point

The issue-board is the destination for ALL the following sources:

| source | class(es) surfaced |
|---|---|
| preflight detectors (10+) | failing, stale (partial), junk-commit (partial) |
| UNIFIED-RECONCILIATION-GATE (3 reconcilers + review-gate) | stale (board↔PR, owns-tracked, gate-wired), junk-commit (review-gate) |
| plane-canary.sh reconcile leg | quarantined (proofless/unwired canary), inert (declared-but-unwired plane) |
| KS29 discovery leg (graphify walk) | inert (node reachability from graph entry points), unregistered (file vs registry set-diff), stale (graph stamp vs HEAD) |
| config-drift.sh, cg-drift.sh, gateway-token-drift | stale (config / CG / token drift) |
| stranded-work.sh, claim-loop, wci-contention | failing (detector findings) |

The board is ONE tsv; every source writes to it via a shared `issue-board-upsert`
primitive. No source opens its own side-channel; the board is the single pane of
glass.

## 4. The SELF-HEAL — gated auto-remediation

### 4.1 Heal-template registry

One git-tracked tsv: `fleet/state/heal-templates.tsv`.

```
class          heal_template_id              template_ticket        auto_launch_gate          max_blast_tier  reviewer_must_not_be
stale          fix/drift-graphify-refresh    — (built-in command)   ALWAYS (safe refresh)     doc (0)         —
stale          fix/drift-config-sync         — (built-in command)   ALWAYS (safe refresh)     doc (0)         —
done-unmerged  fix/unmerged-done-<id>        FLEET-BOARD/fix-done   after_N_green_ticks=2     tooling (1)     builder
failing        — (per-check, variable)       —                      NEVER (per §5 gating)    —               —
inert          — (wiring, needs judgment)    —                      NEVER (per §5 gating)    —               —
quarantined    — (investigation, needs judgment)  —                 NEVER (per §5 gating)    —               —
junk-commit    fix/junk-auto-close-<id>      FLEET-BOARD/fix-close  after_N_green_ticks=3     tooling (1)     builder
unregistered   fix/register-<component>      FLEET-BOARD/fix-register  after_N_green_ticks=1  tooling (1)     builder
```

**Fields:**
- `class` — the failure class from §2
- `heal_template_id` — a kebab-case id; when a heal is launched, the id
  is used to look up the fix template OR a built-in command path
- `template_ticket` — a `FLEET-BOARD/<id>` ticket (from `fleet/board/`) that
  contains the fix brief for the class. The droid reads this brief to understand
  what to fix. `— (built-in command)` means the fix is a single bash invocation
  (`graphify-freshness.sh update`, `config-sync.sh`) — no droid needed.
- `auto_launch_gate` — `ALWAYS` (safe, non-destructive refresh), `after_N_green_ticks=N`
  (the issue must persist for N consecutive green cadence ticks before auto-launch;
  prevents flapping), or `NEVER` (operator must launch manually — the heal-template
  is a documentation shortcut, not an auto-action)
- `max_blast_tier` — the highest blast-tier a droid executing this heal is
  permitted to touch. A `doc (0)` template touches only registry rows; a
  `tooling (1)` template may write fleet scripts.
- `reviewer_must_not_be` — `builder` (the reviewing droid must NOT be the same
  as the fixing droid — reusing BLAST-TIER Consumer A's independence rule) or
  `—` (no review constraint for built-in commands).

### 4.2 Auto-launch eligibility

On each cadence tick, for every OPEN issue of a class with a registered
heal-template:

1. **Gate: `auto_launch_gate`.** If `NEVER` → skip. If `after_N_green_ticks=N` →
   check the issue's consecutive-ticks-since-first-seen ≥ N. If not enough ticks →
   skip.
2. **Gate: heal already launched.** If the issue's `heal_launched_at` is non-empty
   AND the launched ticket is still open → skip (don't double-launch). If the
   launched ticket is done AND the issue is still open → the heal didn't fix it;
   flag as "heal-failed" and escalate (don't auto-retry).
3. **Gate: blast-tier gating.** If the template has `max_blast_tier ≥ hot-path` →
   operator approval required (the auto-launch gate is treated as `NEVER` for
   hot-path+ templates). This is the ArgoCD opt-in self-heal pattern: auto-heal
   is opt-in per class; high-blast classes are opt-in-by-operator.
4. **Gate: review.** If `reviewer_must_not_be = builder` → a review-pool claim
   with `reviewer != builder` must be satisfied before the heal can launch.
   The launch itself queues the fix AND the review as paired items.
5. **Launch:** call `lease-enqueue.sh <ticket-id> --session <session> --` with
   the fix brief. Record `heal_launched_at=<ts>` and `heal_ticket=<id>` in the
   issue-board row.

### 4.3 Built-in heal commands (no droid)

Some heal templates are single bash invocations:

```
class          heal_template_id              command
stale          fix/drift-graphify-refresh    fleet/checks/graphify-freshness.sh update
stale          fix/drift-config-sync         fleet/config-sync.sh
```

These run inline on the cadence tick; no droid is dispatched. The command's
exit code determines success; a failure escalates the issue to "heal-failed"
and triggers a P0 surface.

### 4.4 Self-heal circuit breaker

Reuse `ReviewerCircuitBreaker` from `src/charon/failover.py:73-142` (the same
breaker BLAST-TIER-ENFORCEMENT reuses for the review doom-loop). Per-class,
fingerprinted: `(class, instance_id, heuristic_id)`. If the SAME heal for the
SAME issue fails ≥3 times → the breaker TRIPS → the issue is marked
`heal-breaker-tripped` and the operator is alerted LOUDLY at SessionStart.

The fingerprint heuristic prevents the breaker from tripping on a genuinely
new issue of the same class (different `instance_id`) or a different heal
strategy (different `heal_template_id`).

## 5. Gating — what the plane MUST NOT auto-launch

Per `[[gates-must-actually-run]]`: a self-heal that incorrectly fixes a non-bug is
worse than no self-heal at all. The following classes are **SURFACE-ONLY, NEVER
AUTO-HEAL** in v1:

| class | reason NEVER auto-heal |
|---|---|
| `inert/not-wired` | Wiring a check into the control plane's own firing layer is hot-path work — where the invocation goes is operator judgment. A wrong wiring can suppress a real RED. |
| `failing/RED` | A failing check's root cause is unknown — the fix could be anything from a lint rule to a routing regression. Auto-launching a fix without understanding the cause is a denial-of-service on the droid pool. |
| `quarantined-good` | A false-green canary means the guard is blind. Fixing it requires understanding WHAT it should have caught — that is adversarial reasoning, not a template. |
| `junk-commit` (review-gate sub-class) | The review-gate's R-K/R-L conditions (mismatched review SHA, doom-loop) are operator-adjudicated. Auto-closing a review-gate RED is the REVIEWER-DOGFOOD failure class. |

Safe-to-auto-heal classes in v1:

| class | safe because |
|---|---|
| `stale` (graphify, config-sync) | The fix is a single idempotent refresh command. Non-destructive. |
| `done-but-unmerged` (S-A) | The fix is `done.sh --merged-sha` — idempotent, deterministic, non-destructive. |
| `unregistered` (tooling-tier) | The fix is appending a row to a registry tsv — a mechanical data entry. The registry's own drift test catches mistakes. |

**Expansion to more classes is by appending rows to heal-templates.tsv** (KS20
anti-accretion) — never by adding a new script per class.

## 6. Build decomposition — the 3 slices (one-lens tickets, spawned on approval)

The work is the 3 build-slice tickets. Sequence is ordered by dependency;
parallelism within the slices is the builder's choice.

| # | ticket id | lens | one-liner |
|---|---|---|---|
| 1 | `ISSUE-BOARD-SURFACE` | SURFACE (do first — operator's #1 pain) | The issue-board (`fleet/state/issue-board.tsv`) + the `issue-board-upsert` primitive + the SessionStart surface block in preflight (`fleet/checks/issue-board-surface.sh`). Aggregates ALL existing detector output (the 10+ detectors in `cmd_detect` + the UNIFIED-RECONCILIATION-GATE reconcilers + plane-canary.sh reconcile leg) into ONE tsv + ONE loud preflight block. The board self-closes issues when evidence goes GREEN; re-opens on re-emergent RED. The operator sees ONE block instead of scanning 10+ detector sections. **Blocks the other two slices** — the DISCOVERY leg writes TO the issue-board; the SELF-HEAL leg reads FROM it. |
| 2 | `KS29-DISCOVERY-LEG` | DISCOVER (highest-risk new build) | The KS29 algorithm-primitive framework that walks graphify's relations graph + the issue-class registry to discover failure classes NOT yet caught by existing detectors. Implements the 7 class-discovery algorithms from §2 as composable primitives (`set-diff/bidirectional`, `graph-reachability`, `staleness-probe-TTL`, `subset-membership`, `content-hash/checksum`, `exit-code-check`, `boolean-probe`) in `fleet/checks/discover-issues.sh`. Each primitive is data-configured via the issue-class registry (`fleet/state/issue-class-registry.tsv`), not hard-coded — KS20 anti-accretion. Dogfoods itself: the issue-class registry MUST be self-registered. **Depends on #1 (ISSUE-BOARD-SURFACE)** for the write target; parallel after #1 lands. |
| 3 | `ISSUE-SELF-HEAL-RULES` | SELF-HEAL (gated, last) | The heal-template registry (`fleet/state/heal-templates.tsv`) + the auto-launch eligibility engine in `fleet/checks/self-heal-engine.sh` + the built-in command executor + the `ReviewerCircuitBreaker` integration for the heal-breaker. Composes lease-enqueue.sh (already built) for droid dispatch and review-pool.sh (already built) for reviewer≠builder enforcement. Gated per §5 — safe classes only; the gate itself is a registry row, not hard-coded. **Depends on #1 (reads the issue-board) and #2 (discovers issues that may need healing)**. |

### 6.1 What each slice owns (file-disjoint — no collision)

| slice | owns |
|---|---|
| ISSUE-BOARD-SURFACE | NEW `fleet/state/issue-board.tsv` (schema + initial empty board), NEW `fleet/checks/issue-board-surface.sh` (the surface block + upsert primitive), MODIFY `fleet/preflight.sh` (insert the surface block at the start of `cmd_scan`, before the tracked-reds table). |
| KS29-DISCOVERY-LEG | NEW `fleet/state/issue-class-registry.tsv` (the 7 classes as data rows), NEW `fleet/checks/discover-issues.sh` (the walk + primitives), NEW `fleet/tests/discover-issues.test.sh` (fail-on-revert for each primitive). |
| ISSUE-SELF-HEAL-RULES | NEW `fleet/state/heal-templates.tsv` (the safe-class heal templates), NEW `fleet/checks/self-heal-engine.sh` (the eligibility engine + command executor), MODIFY `fleet/preflight.sh` (wire the self-heal engine into the cadence dispatch), NEW `fleet/tests/self-heal-engine.test.sh` (fail-on-revert — prove the breaker trips on repeated failure, prove SAFE classes auto-launch, prove NEVER classes do not). |

### 6.2 Shared integration (wiring the loop)

After all 3 slices land, a 4th wiring commit (on the last ticket to land, or a
follow-up) connects them into the live loop:

```
preflight.sh / foreman-cadence.sh tick:
  1. discover-issues.sh           (KS29-DISCOVERY-LEG: read registries, walk graphify, produce issue tuples)
  2. issue-board-surface.sh upsert  (ISSUE-BOARD-SURFACE: write tuples into issue-board.tsv)
  3. issue-board-surface.sh render  (ISSUE-BOARD-SURFACE: print the loud SessionStart block)
  4. self-heal-engine.sh evaluate   (ISSUE-SELF-HEAL-RULES: read issue-board, match heal-templates, gate, launch)
```

The preflight.scan dispatch already runs `reconcile-merged.sh` → `board_gate` →
... → `foreman_advisory` at `preflight.sh:878`. The new blocks insert into this
chain:
- (1+2) → between `reconcile-merged.sh` and `board_gate` (the UNIFIED-
  RECONCILIATION-GATE's DISCOVER write happens here too)
- (3) → the FIRST block of preflight output (after the header, before reds)
- (4) → after the detectors block, before `foreman_advisory`

**The cadence timer** (`foreman-cadence.sh` or `fleet/checks/reconcile-timer.sh`)
runs the same (1+2+4) on a timer tick, without the human-facing render (3).
SessionStart runs (1+2+3+4) — full discover + surface render + heal evaluation.

## 7. Adopt-first posture — pattern, not product

Every pattern this plane composes is ADOPTED FROM a proven system, NOT hand-rolled
from scratch. The hand-roll is the thin bash/python glue — not the algorithm.

| pattern | adopted from | how the plane uses it | why not the tool itself |
|---|---|---|---|
| sensor → rule → action (event-driven auto-remediation) | StackStorm | The DISCOVER leg is the sensor; the issue-class registry is the rule; the SELF-HEAL engine is the action. | StackStorm is a full event-bus + workflow engine (MongoDB, RabbitMQ, st2api, st2actionrunner) — service-shaped overkill for a solo bash fleet. |
| opt-in self-heal (auto-remediation is gated, per-class) | ArgoCD (syncPolicy.automated.selfHeal) | The heal-template registry's `auto_launch_gate` + blast-tier gate is ArgoCD's "sync windows + automated selfHeal" pattern — opt-in, per-class, with manual override. | ArgoCD is a Kubernetes controller — depends on a K8s API server and etcd. The plane runs on a single Linux box with bash + python. |
| level-triggered control loop (desired → observe → diff → act) | Kubernetes controller pattern | Every cadence tick re-proves state; issues auto-close when evidence is GREEN; re-open when it returns RED. Never assumes "the last event was the last change." | K8s controllers depend on the API server's watch + list + informer pattern. The plane's "watch" is a timer + a git log diff. |
| facts → checks → scorecard → freshness | Backstage (Software Catalog) / Dagster (asset freshness) | The issue-board is a scorecard; each row is a check; graphify's graph is the catalog; staleness-probe-TTL is Dagster's asset-freshness policy. | Backstage is a React+Node web app with a Postgres catalog. Dagster is a Python orchestrator with a web UI. The plane's "scorecard" is a tsv rendered in a preflight block. |

**The core novel slice — the ~15% that is genuinely new build:**
1. The `issue-board-upsert` primitive that unions all detector output into ONE
   surface (the SURFACE slice). The detectors exist; the union doesn't.
2. The `graph-reachability` walk of graphify's relations graph to find inert
   components (the DISCOVERY slice's novel primitive). Graphify exists; the
   reachability-from-firing-layer walk doesn't.
3. The `heal-eligibility` engine that gates auto-launch based on class, blast-tier,
   and prior-heal success (the SELF-HEAL slice). Lease-enqueue exists; the
   gating + circuit-breaker doesn't.

Everything else (~85%) is composing already-owned pieces: the 10+ detectors, the
UNIFIED-RECONCILIATION-GATE, plane-canary.sh, graphify, lease-enqueue.sh,
review-pool.sh, preflight.sh's scan dispatch.

## 8. fail-on-revert — who-tests-the-tester

Every leg of the plane MUST carry a fail-on-revert dogfood. The plane is a
meta-checker — a false-green plane is worse than no plane at all.

| plane leg | fail-on-revert test | what it proves |
|---|---|---|
| issue-board upsert | `fleet/tests/issue-board-surface.test.sh` | Remove the upsert from preflight → a seeded RED detector finding does NOT appear on the issue-board → the test goes RED. |
| discover-issues primitives | `fleet/tests/discover-issues.test.sh` | Remove the `graph-reachability` walk → a seeded inert component (a script in `fleet/checks/` with no preflight invocation) is NOT discovered → RED. |
| self-heal eligibility | `fleet/tests/self-heal-engine.test.sh` | Remove the `NEVER` gate → a seeded `inert` class issue is auto-launched (when it must NOT be) → RED. Remove the `ALWAYS` gate → a seeded `stale` class issue is NOT auto-launched → RED. |

**The plane's own plane-canary row** (dogfooding the very framework it implements):

```
plane              canary_script                      dogfood_test                              wired_in     owner_ticket
sg-issue-control   fleet/checks/issue-board-surface.sh  fleet/tests/issue-board-surface.test.sh  preflight,timer  SG-ISSUE-CONTROL-PLANE
```

The plane's own row is in plane-canary-registry.tsv — the plane-canary reconcile
leg catches if the plane itself is unwired/proofless. A canary of the canary.

## 9. OPEN SEAMS — flagged, not faked-closed

### 9.1 The graphify dependency for reachability

The `graph-reachability` primitive in the DISCOVERY leg depends on graphify
having a complete call graph (bash + Python extractors). The rig's graphify
BASH extractor (graphify/extractors/bash.py) is proven (6,198 fleet functions
extracted). The product's Python graphify extractor depends on the product
tree being graphified — that is `graphify update <product>` and is already
wired as a cadence tick (`foreman-cadence.sh cmd_graphify_cadence`). The
reachability walk is as complete as graphify's graph.

**Mitigation:** the DISCOVERY leg runs `graphify-freshness.sh check` as a
pre-condition. A stale graph produces its own issue-board row (class `stale`),
and the reachability walk warns "graph stale — inert detection is incomplete"
rather than silently missing inert components.

### 9.2 The review-pool dependency for reviewer≠builder

The SELF-HEAL engine's `reviewer_must_not_be = builder` constraint depends on
review-pool.sh having a live reviewer queue. If the review pool is empty (no
available reviewer), the heal CANNOT launch. The issue stays open with
`heal_blocked_reason = "no reviewer available"` — surfaced, not silently skipped.

**Mitigation:** the issue-board renders `heal_blocked_reason` in the surface
block so the operator sees blocked heals. The `NEVER` gate + `ALWAYS` built-in
commands do not depend on review-pool.

### 9.3 The preflight `git -C` bypass seam (inherited)

The `land.sh` `git -C` bypass seam from UNIFIED-RECONCILIATION-GATE §3.3 applies
here too: a direct push to master bypasses land.sh → the plane's preflight check
doesn't run → an issue that the plane WOULD have caught slips through. The
mitigations are the same (§3.3): post-receive hook detection + timer-based
reconcile that catches drift at the next tick.

## 10. v2 — explicitly deferred

| v2 capability | why deferred |
|---|---|
| **Per-model blast-tier routing for heal droids** | Depends on BLAST-TIER Consumer B (grading substrate) being repaired. v1 heals use the CLAIM_ONLY pin — the SG droid that picks the heal ticket is whatever droid the operator assigns. |
| **Heal effectiveness scoring** | Did the launched heal FIX the issue? The plane needs N heals to have launched before it can compute a heal-effectiveness score. v1 records heal → outcome; v2 computes the score. |
| **Cross-repo issue discovery (charon product repo)** | The plane currently operates on the rig repo (charon-private). The product repo (charon) has its own set of checks + detectors + drift. A cross-repo issue board is a v2 expansion — the same tsv schema, different repo root. |
| **Session-context issue injection** | The operator's ask: "surfaces at SessionStart" includes injecting the issue-board into the droid's session context so a droid assigned a fix ticket sees the issue evidence. v1: droid reads the ticket brief (which includes the issue evidence inline). v2: session-ctx-preamble.sh injects it. |
| **Slack/webhook notification adapter** | The loud surface block is preflight-only. A non-preflight notification (Slack, webhook) for P0 issues that appear between SessionStart ticks is a v2 adapter — the same board read, different render target. Depends on the WORKLOOP-INTEGRITY-STACK-SPIKE harness verdict. |

## 11. Self-check — this design is COMPLETE iff

- [x] **The 7 failure classes (§2)** — each with desired-source, actual-source,
  drift-algorithm, RED condition, and heal-template classification (safe/never).
- [x] **The 3 build-slice decomposition (§6)** — file-disjoint, sequence ordered,
  with clear dependencies (SURFACE → DISCOVERY → SELF-HEAL).
- [x] **The shared substrate (§1)** — graphify, the issue-class registry, the
  heal-template registry, the existing UNIFIED-RECONCILIATION-GATE axis,
  plane-canary, lease-enqueue, review-pool.
- [x] **Adopt-first posture (§7)** — all 4 patterns cited (StackStorm, ArgoCD,
  K8s, Backstage/Dagster), with explicit "why not the tool itself" for each.
- [x] **fail-on-revert (§8)** — one dogfood per slice, plus the plane's own
  plane-canary row.
- [x] **OPEN SEAMS (§9)** — graphify dependency, review-pool dependency,
  preflight bypass — each flagged with mitigation.
- [x] **v2 deferred list (§10)** — 5 items, each with a one-line reason.
- [x] **Gating (§5)** — safe vs NEVER classes listed; the gate is data in the
  registry, not hard-coded.
- [x] **KS20 anti-accretion** — per-class detectors are registry rows, not scripts;
  per-class heal-templates are registry rows, not scripts; future classes are data
  appends, not new build.

## 12. Reviewer notes (this doc only)

- **Why this design supersedes UNIFIED-PLANE-CANARY-FRAMEWORK:** UNIFIED-PLANE-
  CANARY-FRAMEWORK scoped a canary framework for the 10 declared planes. This
  design scopes the WHOLE control plane — DISCOVER, SURFACE, SELF-HEAL — of
  which the plane-canary is the quarantined-good leg. The canary framework's
  surface is preserved (plane-canary.sh + registry continue to operate); this
  design adds the universal issue-board that reads the plane-canary's output
  alongside every other detector.
- **Why this design supersedes gate-test-health-on-master:** gate-test-health-on-
  master was a specific surface ask (tracking which checks fail on master). This
  design's `failing/RED` class (§2.2) is the generalized form — every check,
  not just the gate suite, and surfaced on the issue board alongside every other
  issue class.
- **Why this design supersedes loud-failure-monitor:** loud-failure-monitor was
  the "surface loudly" half of this design — make issues unmissable at
  SessionStart. This design's SURFACE slice (§3) is that half, wired into a
  larger loop.
- **Why the decomposition is SURFACE → DISCOVERY → SELF-HEAL, not parallel:**
  The SURFACE slice is the write target for both DISCOVERY and SELF-HEAL. It
  must land first so the other two have a destination. DISCOVERY is higher-risk
  new build (graphify reachability walk) and produces the raw issue tuples.
  SELF-HEAL consumes those tuples and is the lowest-risk (it gates and launches;
  the launch mechanism — lease-enqueue — already exists). The serial dependency
  is data-flow: SURFACE provides the tsv schema → DISCOVERY writes to it →
  SELF-HEAL reads from it.
- **Why ~85% is already owned:** the detectors exist (10+ in preflight), the
  reconcilers exist (UNIFIED-RECONCILIATION-GATE), the droid dispatch exists
  (lease-enqueue), the review pool exists (review-pool.sh), the graph exists
  (graphify), the canary suite exists (plane-canary). The ~15% new build: the
  union surface, the graphify reachability walk, and the gated auto-launch engine.
- **Why this doc is in `fleet/state/` (gitignored) and force-added:** same as
  UNIFIED-RECONCILIATION-GATE-DESIGN.md reviewer note #1 — this is the `owns-tracked`
  class (§1.2 R-E). The design is its own first test fixture. The
  `RECONCILE-OWNS-TRACKED` reconciler (already designed, not yet built) MUST cite
  this doc as a second canonical R-E example alongside UNIFIED-RECONCILIATION-
  GATE-DESIGN.md.
