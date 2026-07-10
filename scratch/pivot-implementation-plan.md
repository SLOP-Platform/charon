# Real-Outcomes Pivot — Implementation Plan

Reconciles tickets #26 / #25 / #20 / #16 / #17 / #27 + the pools-redesign grades-table
source change into ONE buildable, sequenced workstream. Design-only; no code written.

- **Confirmed pivot (2026-07-08):** demote synthetic S0–S6 to a smoke-test; re-ground the
  model-ranking / capability-grades brain in REAL OUTCOMES = `source=live` actuals ledger
  (`model-scorecard.tsv`) + replayed `reds.tsv` (#25).
- **Design-of-record it feeds:** `POOLS-REDESIGN-ADR-v2.md`. Phase 1 (tier-collapse +
  cost/health) has NO dependency on any of this. Phase 2 (per-work-class capability grades)
  now takes its `work_class_grades` column from the real-outcomes signal instead of the
  synthetic composite — **same schema, strictly more valid source**.
- **Driving verdict:** `fleet/BENCHMARK-VALIDITY-REVIEW.md` ("theater not measure" for
  ranking; graders world-readable + self-driven + self-reported; 5/7 sections saturate; the
  two real failure modes — green-but-inert, confabulation — are structurally invisible).
- **Scope flag:** every ticket below is **build-RIG only (fleet repo)**. The only
  product-boundary contact is §7 (grades table consumed by the product gateway) — read that
  section before wiring anything the gateway imports.

---

## 0. Ground truth as it exists today (so a build session doesn't re-investigate)

**The current synthetic grading flow (what the pivot is fixing):**
`benchmark/bench.sh` — the *graded model itself* runs `start` (prepares a worktree from a
fixture tarball), implements in it, then runs `grade` which:
1. invokes `$grader --worktree <wt> --baseline <fixture>` where graders are
   `benchmark/graders/s0..s6.py`, mode **`-rw-r--r--` (world-readable)**, on the same box the
   agent drives — `cat graders/s2.py` reveals the answer key;
2. records score/gate via `benchmark/lib/grade_state.py`;
3. appends the row to `model-scorecard.tsv` via `model-scorecard.sh append`;
4. `RUN-BENCHMARK.md` instructs the agent to **paste the tier chart verbatim as its own
   output** — the subject is the scorer AND the reporter.

**The actuals ledger (already valid, already out-discriminating):**
`model-scorecard.tsv`, 15 cols:
`date, source(live|bench|bench2), ref, work_class, tier, model, verdict(MERGE|FIXES|BLOCK),
gate, score, time_s, cost_usd, corrections, note, tokens_in, tokens_out`.
`source=live` rows are real routed tickets/PRs with a human/gate verdict produced **out-of-band
by construction** — these 4 rows carry more discriminating signal than every synthetic 100
combined (they're the only rows that separate glm-inert from deepseek-confabulate from
gpt-clean). `model-scorecard.sh render` aggregates per `(model, work_class)` merge%/block%.

**The capability brain (the swap point already exists):**
`capability/grades.py` — `GradesProvider` interface + `ScorecardGradesProvider`
(Wilson-interval confidence-aware scoring, `MIN_N=4`, `LOW_CONFIDENCE` disclosure flag).
`_load()` reads `model-scorecard.tsv`; `grade(model, wc)` counts MERGE/BLOCK across **all**
rows for that (model, wc) and pulls bench mean only from `source in (bench, bench2)`.
`capability/assign.py` consumes it for ticket→best-agent (#14/#15, built `ba0f9d5`).
`capability/selftest.py` already contains a **proof-of-effect differentiation gate** on a
frozen fixture — the runtime analog of that gate is exactly what #27 wants.
The module docstring already names the swap: *"when the pools-redesign grades table lands, a
new provider class implements the same interface and every caller keeps working unchanged."*

**reds.tsv:** append-only, TAB-separated. Key column `check_cmd` **EXITS 0 when the red is
GONE (green)**, non-zero when still red; literal `manual:<instruction>` for reds not
auto-checkable. Of the 17 rows: several are `manual:` (not machine-gradable); the auto ones
split into **behavioral** (run a check script, e.g. `checks/gpt55-primary.sh`,
`checks/bridge-health.py`) and **string-presence** (`git show origin/master:…proxy.py | grep
-q rsplit`). Behavioral > string-presence for un-gameability. Every check_cmd currently asserts
**current** `origin/master` (i.e. the *already-fixed* state) — replaying a red as a task
requires reconstituting the **pre-fix** state (see #25).

---

## 1. Dependency spine / build sequence (what blocks what)

```
                       ┌─────────────────────────────────────────────┐
   (pivot decision ─── │ A2  RE-GROUND grades brain on live actuals   │  ← immediate value,
    CONFIRMED)         │     (demote synthetic composite to smoke)    │    near-zero build
                       └───────────────┬─────────────────────────────┘
                                       │ feeds
   ┌─────────────────────┐             ▼
   │ #20 PROVISIONAL-vs-  │──unblocks──►  #25 reds-replay ──┐
   │     ACTIVE scoring   │──unblocks──►  #16 aggregate N   │──feeds──►  #17 difficulty
   │   (stage machine +   │──unblocks──►  (harder sections  │            calibration
   │    promotion gate)   │               into live grades) │                 │
   └──────────┬───────────┘                                 │                 │ refines
              │                                              │                 ▼
              │ parallel P0 integrity track                 │        #20 promotion gate v2
              ▼                                              │
   ┌─────────────────────┐                                  │
   │ #26 OUT-OF-BAND      │◄──── all bench/replay scores ────┘
   │     grading          │      must route through this before load-bearing
   └─────────────────────┘

   A2  ──feeds──►  #27 gate ASSIGNMENT on discrimination  ──and──►  §7 pools Phase-2
                   (same carve-out routing has)                     grades-table source swap
```

**Two P0s run in parallel, not in series:**
- **#20** is the *structural enabler* — it lets #25 / #16 / #17 land and collect data WITHOUT
  corrupting the live ranking. It unblocks the most and should start first.
- **#26** is the *integrity gate* — nothing the *synthetic or replay* path says is trustworthy
  until scoring is off the subject's box and out of self-report. It has no build dependency and
  can proceed concurrently with #20.
- **A2 (re-ground on live)** is the *immediate-value, least-build* move: the `source=live`
  rows are already out-of-band-valid by construction (a human/gate produced the verdict), so
  pointing the grades brain to *prefer* them and demoting the synthetic composite to smoke-only
  is mostly a weighting/source-filter change in `grades.py` + `tier_chart.py`. It does not need
  #26 or #20 to be safe, and it delivers the pivot's core thesis on day one.

**Recommended order:** A2 (quick win, ship first) ∥ #20 (enabler) ∥ #26 (integrity) →
#25 (content) → #16 → #17 → #27. §7 (pools source swap) trails A2 + #25, gated by the ADR's
existing decision-differentiation gate.

**One near-cycle to resolve up front:** #20's promotion gate needs a *discrimination measure*,
#17 *is* that measure, and #17 needs #16's N-run data, which needs #20's provisional
collection. Break it by shipping #20 with a **v1 gate** (simple score-spread-over-threshold
across ≥K models), then let #16/#17 upgrade it to a CI-aware v2 gate. Do not block #20 on #17.

---

## 2. #20 — Provisional-vs-active scoring (P0 enabler) — BUILD FIRST

**Intent:** new tests/sections/replayed-reds collect data WITHOUT touching live grades until
they are *proven to discriminate*. This is what makes it safe to add reds-replay (#25) and
harder sections (#17) incrementally.

**State machine (per test unit = a section OR a replayed red):**
```
provisional ──(promotion gate passes)──► active ──(discrimination decays / retired)──► retired
     │                                      │
     └── rows recorded, EXCLUDED from       └── rows recorded, INCLUDED in live grades
         live grades + tier chart
```

**Mechanism / files:**
- **Ledger encoding (DECISION needed — see §5):** mark a row's stage. Recommended:
  add a **16th trailing column `stage` (values `provisional|active`)** to `model-scorecard.tsv`,
  following the exact backward-compatible pattern used for `tokens_in`/`tokens_out` (cols 14/15
  ride along via env var because `note` is variadic — see `model-scorecard.sh` L53-72). A
  missing 16th col defaults to `active` so every legacy row keeps counting. Alternative
  (lower-touch on the writer, higher-touch on readers): reuse the `source` field with new values
  `bench-prov` / `reds-prov` — existing aggregators that key on `source=="bench"`/`"live"`
  already ignore these, but every reader that should *eventually* count them must be updated.
  **Prefer the `stage` column** — it keeps `source` meaning "provenance" and `stage` meaning
  "trust", orthogonally.
- **`benchmark/lib/grade_state.py` / `bench.sh` grade path:** a run's unit carries its stage
  from a small registry (e.g. `benchmark/units.tsv`: `unit_id, kind(section|red), stage,
  promoted_on`). `bench.sh` passes the unit's current stage through to
  `model-scorecard.sh append` (via a new `CHARON_SCORECARD_STAGE` env var, same channel as the
  token vars).
- **Aggregators filter by stage:**
  - `capability/grades.py::ScorecardGradesProvider._load` — add `stage` to the parsed dict;
    `_rows_for` (or `grade`) filters to `stage=="active"` by default, with a `include_provisional`
    kwarg for analysis/promotion tooling.
  - `benchmark/lib/tier_chart.py` — exclude provisional rows from the composite/tier.
  - `model-scorecard.sh render` — either exclude provisional or render them in a separate,
    clearly-labeled "PROVISIONAL (not counted)" block.
- **Promotion gate (v1):** a new tool `benchmark/promote.py` (or `bench.sh promote --unit
  <id>`): a provisional unit promotes to `active` iff, over models that have run it,
  `score_spread = max - min ≥ SPREAD_MIN` (headroom exists) AND `distinct_models ≥ K`. This is
  the local analog of the pools ADR's decision-differentiation gate and the assign selftest's
  proof-of-effect. v2 (after #16/#17) replaces raw spread with a CI-aware discrimination test.

**Acceptance criteria:**
- A provisional unit's rows are present in the ledger but change *no* active grade, *no* tier
  chart position, and *no* assign() pick (assert with a frozen fixture, mirroring
  `selftest.py`).
- `promote` flips a unit to active only when the v1 gate passes; a saturated unit (all models
  ~100) provably *cannot* promote (regression-guards the whole point of the pivot).
- Legacy 13/15-column rows still parse and default to `active` (no silent grade shift on
  existing data).

**Blast radius:** touches every ledger reader (`grades.py`, `tier_chart.py`,
`model-scorecard.sh`, and transitively `assign.py`). Contained by the append-only,
default-`active` design — no destructive migration. Add a stage-parse unit test to each reader.

---

## 3. #26 — Out-of-band grading (P0 integrity) — parallel track

**Threat being closed (validity review §2, CRITICAL):** answer key (`graders/*.py` + baseline
fixtures) is readable by the graded agent; grading is self-driven (`bench.sh grade` run by the
subject); results are self-reported (agent pastes the chart). Any one of the three defeats the
instrument.

**Three invariants the architecture must enforce:**
1. **Answer key out of the subject's reach.** The graded agent must not be able to read
   `graders/*.py`, the baseline fixtures, or (for #25) the `check_cmd`.
2. **Grading not self-driven.** The agent signals "section done"; a *separate* scorer process
   performs grading. The agent never executes the grader.
3. **No self-report.** Scores + the tier chart are written to the ledger **by the scorer
   process**, and that ledger write is the single source of truth. The agent's pasted output is
   discarded / advisory only.

**Recommended architecture (solo-dev WSL, simplest-that-works — grader-daemon + drop spool):**

```
 graded agent (normal user)                       scorer (separate trust domain)
 ────────────────────────────                     ──────────────────────────────
 implements in $WORKTREE (agent-owned, rw)
 writes a request to  $SPOOL/req/<run>.json  ───► grader-daemon watches $SPOOL/req/ (inotify/poll)
   { model, unit_id, worktree_path }                 1. snapshots $WORKTREE → grader-owned tree
        (agent has WRITE-ONLY on $SPOOL/req,             (read-only copy; agent can't tamper mid-grade)
         NO read on graders/ or $SPOOL/res)           2. runs grader / check_cmd from the
                                                         grader-owned, mode-0700 answer-key tree
 reads score ONLY from $SPOOL/res/<run>.json ◄──     3. appends the row to model-scorecard.tsv
   (verdict/score/next-prompt; NEVER the                  (scorer is the ledger writer)
    grader source or baseline)                        4. writes $SPOOL/res/<run>.json (score + next
                                                         section prompt only)
```

**Substrate options (operator decision — §5 Q1):**
- **(a) separate unix user** `bench-grader` on the same box: `graders/`, fixtures, and the
  spool `res/` dir owned by `bench-grader`, mode `0700`; agent user has write-only on
  `req/`. Daemon runs as `bench-grader`. Strongest isolation available without a second host;
  needs one-time user + sudo/systemd-user setup. **Recommended default.**
- **(b) root-owned answer-key tree + tiny setuid/sudo grade wrapper:** lighter than a full
  second user; the wrapper is the only path into the graders. Weaker (wrapper surface).
- **(c) second host / container** (the "grader host"): strongest (§7 of the review's ideal) but
  infra-heavy for a solo dev; defer unless (a) proves insufficient.

Keep **`bench.sh` as the agent-facing driver** but strip its grading powers: `grade` becomes
"flush worktree, drop a `req`, poll `res`, print the returned next-section prompt." The
`grader --worktree/--baseline` invocation, `grade_state.record`, and `model-scorecard.sh
append` all move **into the daemon**. `wait_for_worktree_stable` (the mtime-flush gate from
`bench-premature-grade`) moves to the daemon side too (grade the snapshot, not the live tree).

**Acceptance criteria:**
- From the graded agent's user, `cat` / `read` of any grader source or baseline fixture
  **fails** (permission denied) — assert in a hardening test.
- A run where the agent writes a fabricated score to its own output does **not** change the
  ledger; only the daemon's computed score lands (no-self-report proof).
- Re-grading the *snapshot* yields the same score the daemon recorded (determinism preserved).

**Blast radius:** changes the operator/agent run ritual (RUN-BENCHMARK.md, START-SESSION.md)
and adds a long-lived daemon + spool to `preflight.sh` health checks. Reversible: the daemon
can fall back to in-process grading behind a flag during bring-up. **Rig-only**; the daemon,
spool, and answer keys must never be referenced by product code.

---

## 4. #25 — reds-replay (the primary valid ranking signal) — depends on #26 + #20

**Intent:** replay real `reds.tsv` bugs as benchmark tasks; the deterministic `check_cmd` is
the grader. Real, self-refreshing (grows as reds are filed), un-memorizable (the model never
sees the check_cmd — it's run out-of-band by #26's daemon).

**The reconstitution problem (core design point):** every existing `check_cmd` asserts the
**current, already-fixed** `origin/master`. To replay a red as a *task*, the model must be
handed the **pre-fix (red) state** and asked to make `check_cmd` pass. So each replayable red
needs a **fixture snapshot at its red commit** + its `check_cmd`.

**Mechanism / files:**
- **Curation pass → `benchmark/reds-replay.tsv`** (or a `replayable=yes|no` column on
  `reds.tsv`): select reds that are (a) NOT `manual:`, (b) have a **behavioral** check_cmd
  preferred over bare `grep -q <string>` (string-presence is targetable; keep only if no
  behavioral check exists), and (c) have a recoverable pre-fix state.
- **Pre-fix snapshot per red:** for product-repo reds, the pre-fix commit is the parent of the
  fix SHA recorded in `closed_by` (e.g. `f3a73f2^`); build a fixture tarball of that tree, same
  shape as the synthetic fixtures. For rig-side reds (bridge/board/ci), snapshot the relevant
  files at the pre-fix commit. **DECISION §5 Q2:** retroactively snapshot all recoverable
  closed reds now, vs. capture pre-fix fixtures only for *new* reds going forward. Retroactive
  gives corpus mass immediately; forward-only is cheaper but slow to accrue.
- **Harness:** reuse the existing worktree machinery — a replayed red is just another "unit"
  (kind=`red`) fed to `bench.sh start`; the daemon (#26) runs its `check_cmd` against the
  worktree snapshot instead of a `graders/sN.py`. Score model: check_cmd exit 0 = pass (MERGE),
  non-zero = BLOCK, with correction rounds as today.
- **Lands as `provisional` (#20)** until the replay unit proves it discriminates.

**Acceptance criteria:**
- ≥1 replayed red runs end-to-end through the out-of-band daemon and records a provisional row
  with a MERGE/BLOCK derived solely from `check_cmd` exit status.
- The `check_cmd` is **never** present in the agent-readable worktree or prompt (integrity with
  #26).
- A model that leaves the red unfixed scores BLOCK; a correct fix scores MERGE — on the *real*
  pre-fix state, not a synthetic mock.

**Blast radius:** rig-only, additive. Main risk is fixture-reconstruction fidelity (a pre-fix
snapshot that doesn't actually exhibit the red → false-green). Mitigate: the curation pass must
verify `check_cmd` FAILS on the pre-fix snapshot before the unit is admitted (a red that's
already green pre-fix is not a valid task).

---

## 5. #16 / #17 — statistical validity (P1) — depend on data flowing

**#16 — aggregate N runs per (model, section/red):**
- `tier_chart.py` and `grades.py` currently treat one row per (model, section) as the score.
  The ledger is already append-only and multi-row-capable. Switch aggregation from
  "latest/only" to **mean ± variance over ≥3 repeat runs**, and publish the noise band. A tier
  gap smaller than the band is a **tie, not a rank** (validity review §4/§5:
  glm-5.2 scored S3 100→75 and S5 100→60 across runs — proven not test-retest reliable at N=1).
- `grades.py` already has Wilson bounds for merge/block proportions; add mean/stddev (or a
  small-sample CI) for the bench-score aggregate and expose the band on the `Grade` object.

**#17 — difficulty calibration:**
- Compute per-section discrimination from the observed score distribution (variance / spread
  across models). Saturated sections (all models ~100 — currently 5/7) carry ~0 discrimination
  and must be **down-weighted or retired** from the composite, not equal-weighted.
- Feeds #20's **promotion gate v2**: replace v1's raw score-spread with a CI-aware
  discrimination test (unit promotes only if its between-model variance exceeds the
  within-model noise band by a margin).
- Adds headroom by construction: reds-replay (#25) and hidden-diagnosis sections are the source
  of new difficulty; synthetic S0 stays only as the sanity/smoke gate.

**Acceptance criteria:**
- Tier chart shows N and a variance/CI per (model, section); a sub-band gap renders as "tie".
- A saturated section's composite weight → ~0 (asserted on the current 5/7-saturated data).
- Promotion gate v2 rejects a unit whose between-model spread is within the noise band.

**Blast radius:** rig-only; changes tier/grade *numbers*, so re-run the assign frozen-fixture
selftest to confirm no unintended pick changes. No schema change beyond what #20 adds.

---

## 6. #27 — gate the assignment consumer on discrimination (P1) — depends on A2

**Intent:** the validity review §6 flagged **assignment (#14/#15) as the unguarded consumer** —
the ADR-v2 "two consumers" carve-out lets `assign.py` consume the grades table independent of
the gateway's decision-differentiation gate, so it can silently rank on a saturated,
non-discriminating composite. #27 gives assignment the **same carve-out routing has**.

**Mechanism / files:** `capability/assign.py`. Today `assign()` sorts candidates by grade and
picks #1. Add a **runtime discrimination guard** (promote the existing `selftest.py`
proof-of-effect from test-time to runtime): before trusting the capability pick, check whether
the top candidates' grades actually separate for this work_class —
- if all eligible candidates are within each other's CI band (post-#16), OR all are
  `LOW_CONFIDENCE` / all `generalist-fallback` (no direct work_class evidence), then the
  capability signal is inert for this decision → **fall back to the cost/availability-only
  pick** (routing's analog is cost/health), and say so explicitly in the rationale
  ("no capability differentiation at work_class X — fell back to availability/cost").
- **DECISION §5 Q6:** on no-differentiation, does assign() *refuse* (return no confident pick)
  or *fall back* to cost/availability? Recommend **fall back with disclosure** (mirrors
  routing's always-valid cost/health terminal state; a refusal blocks the human unnecessarily).

**Acceptance criteria:**
- On a frozen saturated fixture (all candidates ~equal), assign() reports "no differentiation,
  fell back" instead of silently ranking on noise.
- On a frozen discriminating fixture, assign() still makes the capability pick (guard doesn't
  over-fire).
- Rationale always states which regime fired (capability vs fallback).

**Blast radius:** rig-only. Only changes assignment *rationale/pick under saturation*; the
discriminating case is unchanged. Guardrail against the exact SR-6 "inert-but-shipped" failure.

---

## 7. Grades-table source swap (pools-redesign Phase 2) — the pivot's landing point

**What changes vs POOLS-REDESIGN-ADR-v2.md:** the ADR's Phase-2 `work_class_grades` column was
"benchmark-fed (S0–S6 own runs)". The pivot changes the **source** to **real-outcomes-fed** —
same schema (`model → {tier, per-work-class grades, cost, health}`), same consumers, strictly
more valid input:
- `work_class_grades[wc]` for a model is derived from **(a) `source=live` actuals rows** (merge%
  /block% at that work_class, Wilson-discounted — the code already does this in `grades.py`) **+
  (b) reds-replay (#25) rows** at that work_class, once promoted to `active` (#20).
- The **synthetic S0–S6 composite is removed as a grade source** and kept only as the S0
  sanity/smoke gate (validity review's recommended hybrid).

**Why this is mostly a data-source swap, not a rebuild:** `capability/grades.py`'s
`GradesProvider` is already the documented swap point. `ScorecardGradesProvider` already blends
live + bench rows; the pivot is: prefer live, add promoted reds-replay, drop the synthetic
composite's weight. The pools Phase-2 gate (decision-differentiation) is **unchanged** — it
still correctly *fails* on today's saturated data and will only pass when the real-outcomes
signal actually moves a routing pick.

**⚠ PRODUCT-BOUNDARY FLAG (the one place this touches the standalone product):**
The ADR names a *second* consumer of the grades table — the **gateway request-routing path,
which ships in the Charon PRODUCT** (`/home/stack/code/charon`). The product must stay
standalone (per `product-vs-build-rig-boundary`): it must **NOT** import `capability/grades.py`,
read `model-scorecard.tsv`, or read `reds.tsv` — all three are rig artifacts, and
`reds.tsv`'s `check_cmd`s even embed `/home/stack/...` absolute paths and `git origin/master`
refs. The product side must consume the grades as a **self-contained data artifact** (a
generated, checked-in grades table with no rig back-references) OR recompute grades from its
**own** live gateway telemetry. The `GradesProvider` *interface* may be mirrored in-product, but
the fleet `ScorecardGradesProvider` *implementation* is rig-only. Any build session wiring the
gateway consumer must be handed this constraint explicitly. Everything else in this plan
(#20/#25/#26/#16/#17/#27, the assignment consumer) is **rig-only and never ships in the
product**.

---

## 8. Open questions / decisions needed before build

| # | Decision | Blocks | Recommendation |
|---|----------|--------|----------------|
| Q1 | **#26 out-of-band substrate:** separate `bench-grader` unix user (a) vs root-owned tree + sudo wrapper (b) vs second host/container (c)? | #26 (and therefore trustworthy #25) | **(a)** — strongest isolation without a second host; one-time setup on the WSL box. **This is the top blocking question.** |
| Q2 | **reds-replay corpus scope:** retroactively snapshot all recoverable closed reds' pre-fix state, vs. capture pre-fix fixtures only for new reds going forward? | #25 corpus size | Retroactive for the behavioral, non-`manual:` subset (fast corpus mass); forward-only as the steady state. |
| Q3 | **check_cmd admissibility bar:** exclude `manual:` (unavoidable) and bare `grep -q <string>` (targetable) reds? Minimum bar = behavioral? | #25 quality | Yes — prefer behavioral; admit string-presence only where no behavioral check exists, and only because #26 keeps the check_cmd out of the model's reach. |
| Q4 | **Ledger stage encoding:** new 16th `stage` column vs new `source` values (`bench-prov`/`reds-prov`)? | #20 (and every reader) | New `stage` column — keeps `source`=provenance and `stage`=trust orthogonal; follows the proven tokens_in/out trailing-column pattern. |
| Q5 | **Promotion / tie thresholds:** initial `SPREAD_MIN`, distinct-model floor `K` for #20 v1, and the CI "tie band" for #16? | #20, #16 | Start deliberately low (mirror the pools gate's 10–15% "prove non-zero effect" stance); tighten as coverage grows. Operator to set the first X. |
| Q6 | **#27 no-differentiation behavior:** assign() *refuse* vs *fall back to cost/availability*? | #27 | Fall back with explicit disclosure (mirrors routing's always-valid cost/health terminal state). |
| Q7 | **A2 timing:** ship the live-actuals re-grounding immediately (ahead of #26/#20) since live rows are out-of-band-valid by construction? | sequencing | Yes — least build, immediate value, independently reversible; it's the pivot's thesis proven on existing data. |

---

## 9. Rig vs product summary (leak audit)

- **Build-RIG only (fleet repo), never ships in product:** #20, #25, #26, #16, #17, #27, the
  actuals ledger, `reds.tsv`, `capability/*` assignment engine, the grader daemon + spool + all
  answer keys, `benchmark/*`.
- **Product contact — ONE point, §7:** the pools-redesign Phase-2 grades table has a second
  consumer in the standalone gateway. Guardrail: the product consumes a self-contained grades
  artifact (or its own telemetry) and must not import fleet `capability/grades.py` or read
  `model-scorecard.tsv` / `reds.tsv`. Flag handed to whoever builds the gateway consumer.
- **No other product leak** exists in this workstream.
```
