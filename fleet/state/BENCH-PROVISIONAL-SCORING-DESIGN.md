# BENCH-PROVISIONAL-SCORING — Design of Record (#20)

Status: **PROPOSED** (design-only deep-dive per operator 2026-07-16;
   "bench-provisional-scoring was supposed to be something I would have next
   session do a deep dive"). Owner: operator. Grounded from the live code on
   `origin/master` as of 2026-07-16. Tracked by
   `fleet/board/BENCH-PROVISIONAL-SCORING.md`. Gates `BENCH-OOB-GRADING` (#26)
   — that ticket stays parked until this design lands + is reviewed.

> Authored 2026-07-16 by the #20 design droid (ahsoka-tano), grounded against
> the current code with file:line citations. Design-only — no code changed.
> This document is the **single design of record**; every prior scattered
> treatment of the stage mechanism (the pivot plan §2, the SELFCONTROL/control-
> panel rule, the v1 vs v2 promotion gate, the FAIL-ON-REVERT tests) is
> summarized here and pointed at, not duplicated.

---

## 0. Why this ticket exists (one paragraph, then we go)

Every per-(model × work-class) number the rig uses to steer real money
(assign's pick, budget's p95 ceiling, routing's grade column, the operator's
tier chart) is grounded in `fleet/model-scorecard.tsv`. A row in that ledger
is either **trusted** (a real outcome, provably out-of-band-graded) or
**collected-but-not-trusted** (a synthetic grade, a self-reported probe, a
replayed red that has not yet been observed to discriminate). The stage
mechanism is the **trust axis**: a column on the ledger that says
"provisional" or "active" and is the single gate every consumer reads before
that row's score can move a live number. It is the fail-closed backstop of
the whole real-outcomes pivot (`scratch/pivot-implementation-plan.md` §2).

**One-line purpose:** a row is *active* iff a trusted OOB/live grade
authoritatively produced it; otherwise it is *provisional* and the trust
gate forbids it from moving a budget, a tier, or an assignment pick.
Unknown / unpaired / uncalibrated → **provisional, never active** (fail-
closed). The promotion from provisional → active is a single, auditable
event, not a property the row's own writer is allowed to claim.

This document captures the operator's deep-dive decisions on every open
question about that mechanism and writes them down in one place.

---

## 1. What is on disk today (grounded from code, 2026-07-16)

The pivot plan (`scratch/pivot-implementation-plan.md` §2) committed
**commit `9c5714a` "bench(#20): provisional-vs-active staging + promotion
gate" + `facfc23` "merge(bench): #20 provisional-vs-active scoring gate"**;
the sibling `ADR-BENCH-OOB-GRADING.md` §0 calls it out as "already BUILT".
A code-read against the worktree confirms the wiring is present and
consistent:

| Surface | What it does | File:line |
|---|---|---|
| `model-scorecard.tsv` column 16 | `stage` (16th trailing col, `provisional\|active`); legacy 13/15-col rows default `active` so no historical shift | `fleet/model-scorecard.sh:24-31, 84-89, 102-103` |
| `cmd_append` accepts `stage` | rides in env `CHARON_SCORECARD_STAGE`; defaults `active`; any legacy caller keeps writing `active` | `fleet/model-scorecard.sh:77-85` |
| `cmd_render` separates provisional | provisional rows are tallied into a clearly-labeled "PROVISIONAL (not counted)" block, never into merge%/block%/mean | `fleet/model-scorecard.sh:96-156` |
| `capability/grades.py` filters | `_rows_for(include_provisional=False)` is the DEFAULT — every live grade path (`grade()`, `assign()`) drops provisional; `_stage` reads col 16, defaults `active` on legacy | `fleet/capability/grades.py:342-362, 444-481, 573-643` |
| `tier_chart.py` filters | `_stage(cols)` in lockstep with `grades.py`; both `bench_rows_for` and `bench2_rows_for` exclude `provisional` | `fleet/benchmark/lib/tier_chart.py:204-210, 222-230, 376` |
| `close_season.py` filters | bench2 season composites also exclude provisional (closes the smoke-only consistency gap the v1 review found) | `fleet/benchmark/lib/close_season.py:58-67, 137-142` |
| `grade_state.record` | finalizes the run; writes `meta.json` only — the stage rides on the SCORECARD row, not the meta, so a single source of truth | `fleet/benchmark/lib/grade_state.py:268-394` |
| `bench.sh::unit_stage` | reads `benchmark/units.tsv`, returns the unit's current stage; `do_grade` passes it to `model-scorecard.sh append` via `CHARON_SCORECARD_STAGE` | `fleet/benchmark/bench.sh:79-92, 441-446` |
| `benchmark/units.tsv` | the unit registry: `unit_id  kind(section\|red)  stage  promoted_on  [control_pass  control_fail]`. S0–S6 grandfathered `active`; NEW units (reds-replay #25, harder sections #17) MUST be added as `provisional` and earn `active` via `promote.py --apply` | `fleet/benchmark/units.tsv:1-24` |
| `benchmark/promote.py` | the v2 control-panel gate (EVAL-PROMOTION-GATE, F10 fix) — promotes a unit IFF a `strong-control` MUST-PASS has N≥3 rows at mean ≥80 AND a `deepseek-v4-flash` MUST-FAIL has N≥3 rows at mean ≤20; **secondary** spread≥15 backstop | `fleet/benchmark/promote.py:1-82, 285-421` |
| `auto_append.py` | Python equivalent of `cmd_append` for graders/hooks; same `VALID_STAGE` enum, same default `active` | `fleet/capability/auto_append.py:28, 68-130` |
| `dogfood-eval.sh` | Path-C dogfood probes — generates scorecard rows as `stage=provisional`; `finalize_live_capture` ONLY flips to `stage=active` when an OBJECTIVE OOB grade is paired | `fleet/benchmark/dogfood-to-scorecard.sh:24-30, 109-116`; `fleet/benchmark/dogfood-eval.sh:127-189` |
| Live `pipeline._enqueue_capture` | the SOLE writer of `source=live` rows; `--stage active` paired-finals (i.e. an OOB grader produced the verdict) are the only path the live lane uses to land `stage=active` | `fleet/benchmark/item-bank/pipeline.py` (EVAL-PIPELINE-DESIGN §1.4 / §"single-capture-path") |

`promote.py` is the ONLY tool that may flip a unit from `provisional` →
`active` directly. `pipeline._enqueue_capture` is the ONLY path that may
write `source=live` rows (EVAL-PIPELINE-CONSOLIDATE F12's single-capture-
path). Path-C dogfood writes rows, but only as `provisional`; a paired
OOB-grade finalization is what flips them.

The current ledger (`fleet/model-scorecard.tsv` on this box) holds 43
rows, all `source=live / stage=active` — the active collection is real
production ticket close-out records (`done.sh` writes them); no
`provisional` row is in the live ledger today because the S0–S6
bench sections are grandfathered `active` and no replayed-red/harder-
section unit has yet been registered.

---

## 2. The state machine

```
                    ┌──────────────────────┐
                    │  NOT YET REGISTERED  │   (a unit the harness has
                    │                      │    never seen — bench.sh
                    │                      │    unit_stage() defaults
                    │                      │    "active" per its END branch,
                    │                      │    so a brand-new ref that
                    │                      │    was never added to units.tsv
                    │                      │    looks active today; see §6 Q1)
                    └──────────┬───────────┘
                               │ author registers it in units.tsv
                               ▼
            ┌──────────────────────────────────────┐
            │            PROVISIONAL               │
            │  rows are COLLECTED in the ledger    │
            │  but EXCLUDED from every live grade, │
            │  tier, and assign pick.              │
            │                                      │
            │  Promotion requires:                 │
            │  (a) v2 control-panel split proven   │
            │      (strong-control mean ≥80,       │
            │       deepseek-v4-flash mean ≤20,    │
            │       N≥3 each — promote.py)         │
            │  AND                                │
            │  (b) secondary spread≥15 backstop    │
            │      (no-spread = non-discriminating,│
            │       refused even on the v2 split)  │
            └──────────────────┬───────────────────┘
                               │ promote.py --apply flips stage=active
                               ▼ (auditable: units.tsv::promoted_on stamps today)
            ┌──────────────────────────────────────┐
            │              ACTIVE                  │
            │  rows feed live grades, tier chart,  │
            │  assign picks, and the F8 budget     │
            │  derivation. Still excluded from     │
            │  live grades if the per-ref control  │
            │  panel is not yet proven (F13 —      │
            │  EVAL-PROMOTION-GATE control-panel   │
            │  gate is the live-row corollary).    │
            └──────────────────┬───────────────────┘
                               │ discrimination decays / unit retired
                               ▼
            ┌──────────────────────────────────────┐
            │             RETIRED                  │  (not implemented today;
            │  rows are kept for audit but         │   #17 difficulty calibration
            │  excluded from live grades           │   may need it; out of scope
            │  regardless of source/stage.         │   for #20 — #20 ships with
            │                                      │   the two-stage machine only.)
            └──────────────────────────────────────┘
```

**One transition matters today (provisional → active).** A new unit enters
the registry at `provisional` and never returns; the only forward edge is
the audited `promote.py --apply` flip.

---

## 3. The trust gate (FAIL-CLOSED)

Every consumer that lets a row's score steer a real number applies the SAME
two-axis check:

| Axis | Values | Fail-closed default | Where enforced |
|---|---|---|---|
| `source` (provenance) | `live` (real outcome) — synthetic `bench`/`bench2` are DEMOTED per the real-outcomes pivot A2, see `grades.py:_REAL_OUTCOME_SOURCES = {"live"}` | not in the allow-list → excluded | `fleet/capability/grades.py:325-339, 562-643` |
| `stage` (trust) | `active` (promoted) — `provisional` is COLLECTED but excluded | legacy rows default `active`; an explicit `provisional` value is the only thing that excludes | `fleet/capability/grades.py:342-362, 481, 573-643`; `fleet/benchmark/lib/tier_chart.py:204-230, 376`; `fleet/benchmark/lib/close_season.py:58-67, 137-142` |
| (EVAL-PROMOTION-GATE) per-ref control panel | a `source=live` row's `ref` MUST have a measured `strong-control` MUST-PASS (N≥3, mean ≥80) AND `deepseek-v4-flash` MUST-FAIL (N≥3, mean ≤20) | ref with no control data → live row excluded until the control split is measured | `fleet/capability/grades.py:44-82, 492-643` (F13 fix) |

**Strict AND.** A row fails either axis → it cannot move a live number,
regardless of which axis failed. The two axes are independent `continue`
guards in `_rows_for` — no OR / no short-circuit / no default leak. This is
the verified-by-code property the v1 review's Q1 confirmed (PASS in
`fleet/scratch/bench-provisional-review.md` §"Fail-closed composition").

**Who MAY promote a unit:** `benchmark/promote.py --apply` and only that
tool, by a human (operator) on a dry-run report that names the unit and
the v2-gate pass evidence. The flip is auditable (it stamps
`promoted_on = YYYY-MM-DD` in `units.tsv` and the new `stage=active` rows
emitted by the runner from that unit onward ride on the audit trail).

**Who MAY write a `source=live / stage=active` row:** the
`pipeline._enqueue_capture` single capture path (EVAL-PIPELINE-CONSOLIDATE
F12), and ONLY when an OOB grader (`bench-grader` daemon) has computed the
verdict+gate+score. A live `done.sh` close-out on a real ticket is
out-of-band-valid by construction: a human/gate produced the verdict, not
the model. (`done.sh` runs the same `pipeline._enqueue_capture` under the
hood; see `EVAL-PIPELINE-DESIGN.md` §"single-capture-path guarantee" —
that guarantee is the discipline that prevents a second writer from
silently re-introducing the F12 leak.)

---

## 4. The fail-closed default (the part that matters most)

Unknown / unpaired / uncalibrated → **provisional, never active.** Three
corollaries:

1. **A brand-new unit is provisional until proven.** Adding a row to
   `units.tsv` (e.g. a replayed red per #25, a harder section per #17) is
   the ONLY way a new unit enters the registry; the loader at
   `promote.py:load_units` reads the explicit `stage` column verbatim. A
   new unit MUST be added as `provisional` (the file's own header says so);
   the grandfathered S0–S6 `active` rows are the load-bearing exception,
   NOT the default behavior.

2. **An unregistered `ref` defaults active — and that is the v1 review's
   known caveat.** `bench.sh:unit_stage` looks the unit up in `units.tsv`
   and on miss returns `active` (the `END { if(!f) print "active" }` branch).
   This is fail-open ONLY on the legacy/unregistered axis; the trust gate
   itself stays fail-closed (an explicit `provisional` is the only thing
   that excludes a row). The caveat is documented and accepted because
   (a) all current bench sections S0–S6 are explicitly registered, (b) the
   only synthetic source today is `bench`/`bench2` which the real-outcomes
   pivot already demotes, and (c) #25 / #17 register their units as
   `provisional` on creation. **Q1 (§6) decides whether to tighten this
   default to `provisional`.**

3. **Legacy 13/15-col rows default `active`** so the historical ledger
   does not silently re-evaluate; this is the
   `else "active"` branch in every `_stage` reader. An EMPTY 16th cell on
   a NEW row also defaults `active` (`if _rest[2].strip() else _ACTIVE_
   STAGE` in `grades.py:481`). A non-empty explicit value is the only
   thing that excludes — the trust gate is fail-closed on the explicit
   axis.

---

## 5. Composition with the OOB grader (#26)

`pipeline._enqueue_capture` writes `source=live` rows. It carries
`--claimed-result OOB_GRADED --stage active` for a paired finalization
(an OOB daemon produced the verdict), and `--claimed-result PROVISIONAL
--stage provisional` for a `charon-run.sh` SUCCESS without a paired
final (i.e. the model claims success, the daemon has not yet graded it —
the row is COLLECTED but excluded from every live grade). The dogfood
path uses the same pair: `dogfood-to-scorecard.sh` always emits
`stage=provisional`; `dogfood-eval.sh::finalize_live_capture` only
emits `stage=active` when the OBJECTIVE grade (charon.cli gate + ticket
accept-test) is paired with a SUCCESS marker (the double-log guard at
`dogfood-eval.sh:154-156`).

**The composition rule #26 inherits from this design:**

- #26 is the daemon (the OOB scorer). It does NOT introduce a new stage.
  It is the trusted OOB grader that produces the verdict the live path
  then writes as `source=live / stage=active` via
  `pipeline._enqueue_capture`.
- #26 must NOT write the ledger directly. The single-capture-path
  guarantee (EVAL-PIPELINE-CONSOLIDATE F12) is preserved: daemon → spool
  → pipeline → enqueue-capture.sh → ledger. Reversing the direction
  (daemon writes ledger directly) re-introduces the F12 leak that a
  second writer could silently exploit. The promotion gate (`promote.py`)
  is the only other path that may flip a unit; both stay distinct from
  the row-write path.
- #26's `check_cmd` for a replayed red (#25) is the OOB grader's
  verdict. The captured row is `source=live` (the OOB grader produced
  the verdict), but the unit is `provisional` until `promote.py --apply`
  flips it on the v2 control-panel gate. The composition is therefore
  `source=live` (provenance: OOB) ∧ `stage=provisional` (trust: not yet
  promoted) — both axes must be open for a row to influence a live
  grade. A new red's first run is therefore inert to live grades, by
  design.

---

## 6. Open decisions (operator's call)

The pivot plan §8 listed these as `Q4` / `Q5`; this design closes the
majority but keeps the smaller open ones explicit so the operator can
answer them at review.

| # | Decision | Status | This design's recommendation |
|---|---|---|---|
| Q1 | **Unknown-unit default.** `bench.sh:unit_stage` defaults `active` on a units.tsv miss. Tighten to `provisional`? | OPEN | **Tighten to `provisional`.** The load-bearing reason for the v1 default was "every existing S0–S6 is grandfathered `active`" — but those are now EXPLICITLY registered in `units.tsv`, so the lookup-miss path is reached only for genuinely-new units (replayed reds, harder sections). Those must earn `active` via `promote.py`. The current `active` default is a foot-gun: a typo in `units.tsv` silently promotes a not-yet-proven unit. Risk to legacy callers: zero, because the only ones today are S0–S6 and they all look up. **Action:** tighten to `provisional` on lookup-miss; S0–S6 are unaffected; new units must register. |
| Q2 | **Legacy row's stage.** A row already in the ledger with <16 cols defaults `active`; an empty 16th cell on a NEW row also defaults `active`. Both are load-bearing for "no historical shift" — keep? | DECIDED — keep | Both are load-bearing. An explicit `provisional` is the only way a row is excluded. The risk of accidental new-`active` is bounded by Q1's tightening (the harness-side writer now defaults `provisional` on a units.tsv miss) and by the F12 single-capture-path guarantee (live rows only come from `pipeline._enqueue_capture`). |
| Q3 | **Promotion rule: v1 spread (SPREAD_MIN=15, DISTINCT_MODELS_MIN=2) vs v2 control-panel (MUST-PASS mean ≥80, MUST-FAIL mean ≤20, N≥3 each).** | DECIDED — v2 + v1 secondary | v2 control-panel is the actual discrimination proof; the v1 spread is kept as a SECONDARY sanity backstop (a unit the controls agree on at the same value carries no signal even if the absolute values look right). This is the F10 fix the v1 review accepted and `promote.py:evaluate_gate_v2` implements verbatim. A unit the v2 split would wrongly reject as "saturated" (`{100,0}` per-run split, per-model mean 50) IS promoted; a unit the v2 split catches that v1 missed (MUST-FAIL also passes) is correctly rejected. |
| Q4 | **Per-ref control-panel rule on `source=live` rows** (review F13 — the same control-panel rule applied to live rows as to synthetic units). | DECIDED — yes, on by default | `grades.py:_rows_for(require_control_panel=True)` is the live path's F13 fix: a `source=live` row is admitted ONLY when its `ref` has a measured MUST-PASS/MUST-FAIL split. A ref with no control data yet (a brand-new live task) does NOT count toward a grade until it earns one. `require_control_panel=False` is analysis/smoke-only. The F13 hole — a single (F4) budget-breaching live run shifting the pick the moment it landed — is closed. |
| Q5 | **Thresholds for v2 gate (CONTROL_N, MUST_PASS_MIN, MUST_FAIL_MAX, SPREAD_MIN).** | DECIDED — current defaults | `CONTROL_N=3` reuses PREFLIGHT-DESIGN-V2 §3's "N≥3 each" verbatim; `MUST_PASS_MIN=80` / `MUST_FAIL_MAX=20` mirror item-bank/manifest.tsv's calibration anchors; `SPREAD_MIN=15` is the v1 number kept as the secondary backstop. All overridable per invocation for unit tests / future tuning. |
| Q6 | **Path-C dogfood probe default.** Every Path-C dogfood row is `stage=provisional`; a paired OOB-grade finalization (the `finalize_live_capture` SUCCESS-marker-guarded path) is what flips it. | DECIDED — keep | This is the whole point of Path-C: a real-ticket run is COLLECTED but does not steer real spend until a human reads the diff and the OOB grader has paired the verdict. A path-C row that was never paired final stays `provisional` forever (no auto-promote) — the operator promotes it manually via `pipeline._enqueue_capture` after diff review. No bulk auto-promote. |
| Q7 | **Retired state.** The pivot plan's diagram shows a `retired` state; nothing in code implements it today. | DEFERRED to #17 | Out of scope for #20. #20 ships the two-stage machine. A `retired` state can be added when #17's difficulty calibration identifies saturated units that should stop influencing a live number even though they are formally `active`. #20 is not blocked on it. |
| Q8 | **A `source=bench` / `source=bench2` row's stage.** Bench rows are DEMOTED by `_REAL_OUTCOME_SOURCES` regardless of `stage`; today they are `stage=active` (S0–S6 grandfathered) and the real-outcomes pivot excludes them from the grade. Is this an unnecessary stage value? | DECIDED — keep | The `stage` axis is orthogonal to `source`. A bench row's `stage=active` is true (its unit is `active`) but its `source=bench` excludes it from the grade by the real-outcomes pivot. The two filters compose. Removing `stage` from bench rows would conflate provenance with trust. Keep as-is. |
| Q9 | **A `source=live` row's stage on a brand-new live task (no control panel yet).** | DECIDED — `provisional` | The OOB grader produces the verdict, so `source=live`. But the per-ref control panel has not been measured yet, so the live-row gate (F13) excludes it. The combined effect: `source=live` rows on a ref without a control split are COLLECTED but excluded from the grade until the control panel is measured. Once measured, the row's `stage` does not change (it is still `provisional` — a live row is `provisional` until a unit's promotion gate flips it, OR the row itself is the control-panel evidence). See `grades.py:_control_panel_for`. |

---

## 7. What this design does NOT change

For the build droid (or the operator) to know what to leave alone:

- **`model-scorecard.tsv` 16-column shape.** No schema change.
  The 16th `stage` column is the existing trailing-column pattern (cols
  14/15 are tokens_in/out, same optional-env-var channel). Legacy 13/15-col
  rows keep parsing and default `active`.
- **The F12 single-capture-path guarantee.** `pipeline._enqueue_capture`
  is the SOLE writer of `source=live` rows. `done.sh`, `dogfood-eval.sh`
  via `finalize_live_capture`, and the adaptive runner all funnel through
  it. `promote.py` is the SOLE flippable of a unit's `stage`. These two
  writers are distinct and must stay distinct.
- **The real-outcomes pivot (A2) and aggregate-N (#16).** Both are
  upstream dependencies of #20 and already landed (`4ab02a3` A2,
  `da61356`/`36e7b25` #16). They compose with the stage gate — a row
  must pass ALL of (source allow-list, stage=active, real-only filter,
  per-ref control panel, AGGREGATE-N's noise-band disclosure) to move
  a live number. No single gate is sufficient.
- **The FAILS-ON-REVERT tests** (`fleet/capability/selftest.py`,
  `fleet/tests/promotion-gate.test.sh`, `fleet/tests/dogfood-to-scorecard
  .test.sh`). Each empirically reverts the gate it guards and confirms
  the test goes RED. The #20 build droid MUST keep them green.

---

## 8. What the build droid (or operator) WOULD change in a follow-on

These are out of scope for this design doc (the ticket's `owns:` is this
file + the review fragment). They are listed so the operator's next-session
review can pick them up or punt them:

1. **Tighten Q1** (the unknown-unit default to `provisional`):
   `bench.sh:unit_stage` line 91 changes `END { if(!f) print "active" }` →
   `END { if(!f) print "provisional" }`. One-line. Zero impact on the
   S0–S6 grandfathered `active` rows (they look up correctly). New
   units (replayed reds, harder sections) MUST register; the only
   failure mode is a typo, which is now a fail-closed typo.

2. **Add a `--require-control-panel` and `--include-provisional` matrix
   test** to `fleet/capability/selftest.py` (it has the live-row
   control-panel test today; this would extend it to cover all four
   combinations of the two flags).

3. **`model-scorecard.sh render` provisional tally** could be enriched
   to show the unit_id of each provisional row (it currently shows
   per-(model × work_class) counts only). Cosmetic; useful for operator
   diff-review.

4. **An `end_session.sh`-style `retired` lifecycle** (Q7). Out of scope
   until #17 needs it.

5. **`pipeline.py self-test`** for the F12 single-capture-path should
   assert that `--stage active` is rejected when the captured row lacks
   an OOB-grader verdict (today the daemon's contract is implicit).
   Defense in depth; not load-bearing today.

---

## 9. Operator-review checklist (for the review pass this design unblocks)

- [ ] Confirm Q1 — tighten unknown-unit default to `provisional` (this
      design recommends yes; the one-line change is in §8.1).
- [ ] Confirm the F13 live-row control-panel gate is on by default in
      `grades.py:_rows_for` (it is, but operators who want a softer
      gate can override per call; verify the default is what the
      "money-path" ticket stream expects).
- [ ] Confirm `pipeline._enqueue_capture` is still the SOLE writer of
      `source=live` rows (EVAL-PIPELINE-CONSOLIDATE F12; the
      `pipeline.py self-test` FAIL-ON-REVERT (b) greps for this).
- [ ] Confirm Path-C dogfood remains `provisional`-only by default
      (`dogfood-to-scorecard.sh:24-30` + `dogfood-eval.sh:127-189`).
- [ ] Confirm `promote.py --apply` is the only path that flips a unit
      from `provisional` to `active` (auditable via `units.tsv::
      promoted_on`).
- [ ] Confirm the FAIL-ON-REVERT tests
      (`fleet/capability/selftest.py` + `fleet/tests/promotion-gate.test
      .sh` + `fleet/tests/dogfood-to-scorecard.test.sh`) are GREEN on
      the worktree this design was grounded against.
- [ ] Once Q1 is decided and the operator has signed off, BENCH-OOB-
      GRADING (#26) is unblocked — its design (`fleet/ADR-BENCH-OOB-
      GRADING.md`) is already drafted and rebase-ready.

---

## 10. References (every claim's source-of-truth pointer)

- `scratch/pivot-implementation-plan.md` §2 — the original #20 intent,
  mechanism, and acceptance criteria.
- `fleet/scratch/bench-provisional-review.md` — the v1 review that
  confirmed fail-closed composition + legacy default-active + the
  close_season smoke-gap (now closed).
- `fleet/state/PREFLIGHT-DESIGN-V2.md` §3 — the "N≥3 each" hard floor
  reused by `CONTROL_N`.
- `fleet/benchmark/promote.py:1-82` — the v2 control-panel gate rule,
  with the F10 fix documented at lines 12-54.
- `fleet/benchmark/units.tsv:1-24` — the unit registry; the grandfather
  exception for S0–S6 and the MUST-register-as-provisional rule for
  new units.
- `fleet/capability/grades.py:44-82, 342-362, 444-481, 573-643` — the
  F13 live-row control-panel gate, the `_stage` reader, the
  `_rows_for(include_provisional=...)` default, the `_REAL_OUTCOME_
  SOURCES` allow-list.
- `fleet/benchmark/lib/tier_chart.py:204-230, 376` — the tier-chart
  reader in lockstep with `grades.py`.
- `fleet/benchmark/lib/close_season.py:58-67, 137-142` — the
  bench2-season reader that closes the v1 review's smoke-gap.
- `fleet/benchmark/bench.sh:79-92, 441-446` — `unit_stage` + the
  `CHARON_SCORECARD_STAGE` plumbing.
- `fleet/model-scorecard.sh:24-31, 77-89, 96-156` — the 16th `stage`
  column, the `cmd_append`/`cmd_render` behavior, the "PROVISIONAL
  (not counted)" block.
- `fleet/benchmark/dogfood-to-scorecard.sh:24-30, 109-116` — Path-C
  dogfood probe default `provisional`; no auto-promote by design.
- `fleet/benchmark/dogfood-eval.sh:127-189` — the `finalize_live_
  capture` double-log guard; SUCCESS-marker-gated `stage=active`
  paired-final.
- `fleet/capability/auto_append.py:28, 68-130` — Python equivalent of
  `cmd_append`; same `VALID_STAGE`, same default `active`.
- `fleet/tests/promotion-gate.test.sh` — the FAIL-ON-REVERT tests for
  the v2 gate + the F13 live-row gate.
- `fleet/ADR-BENCH-OOB-GRADING.md` §0 — the load-bearing finding that
  #20 is already built; §1–§5 are the OOB substrate the design
  composes with.
- `fleet/state/EVAL-PIPELINE-DESIGN.md` §"single-capture-path" — the
  F12 guarantee that `pipeline._enqueue_capture` is the sole
  `source=live` writer.

---

## 11. TL;DR (operator-facing, one screen)

- **The stage mechanism is two values: `provisional` and `active`.** The
  16th column of `model-scorecard.tsv`; the only knob every consumer
  reads before a row's score can move a live number.
- **Promote = `promote.py --apply` on the v2 control-panel rule (must-
  pass mean ≥80, must-fail mean ≤20, N≥3 each; secondary spread≥15).**
  Auditable (stamps `promoted_on` in `units.tsv`). The operator does this,
  not the model.
- **Trusted `source=live` rows are the only path that writes
  `stage=active` directly (via `pipeline._enqueue_capture`, the F12
  single-capture-path).** An OOB-grade paired-final is what flips a
  Path-C dogfood probe from `provisional` to `active`.
- **Fail-closed default: unknown / unpaired / uncalibrated →
  `provisional`.** Legacy rows default `active` to preserve history;
  the only thing that excludes is an explicit `provisional` value.
- **One open decision (Q1):** should the `bench.sh::unit_stage` lookup-
  miss default tighten from `active` to `provisional`? This design says
  yes (one-line change, zero impact on S0–S6, fails closed on typos in
  `units.tsv`). Operator call.
- **Composition with #26 is clean:** the OOB daemon does NOT introduce a
  new stage; it is the trusted OOB grader whose verdict the live
  capture path writes. `promote.py` and `pipeline._enqueue_capture` stay
  the only two writers of `stage`, and they stay distinct. #26 is
  unblocked the moment this design is signed off.
