# MODEL-TESTING / EVALUATION SYSTEM — ADVERSARIAL DESIGN + CODE REVIEW

Date: 2026-07-14. Reviewer: adversarial read-only sub-session. Assume-flawed mandate.
Scope read end-to-end: `fleet/benchmark/dogfood-eval.sh`, `fleet/benchmark/lib/dogfood-attribution.sh`,
`fleet/charon-run.sh`, `fleet/benchmark/honest-battery-sweep.sh`, the 3 honest briefs,
`fleet/board/MODEL-PREFLIGHT.md`, `fleet/state/PREFLIGHT-DESIGN-V2.md`, `fleet/benchmark/preflight.sh`,
`fleet/benchmark/preflight-tasks/*` + `manifest.tsv`, `fleet/benchmark/graders/preflight.py` +
`preflight_checks/`, `fleet/state/preflight-results/*`, `fleet/board/LEG-PREFLIGHT-CANARY.md` +
`fleet/state/leg-canary-prototype.py`, `fleet/capability/grades.py` + `assign.py`,
`fleet/benchmark/promote.py`, `fleet/benchmark/units.tsv`, `fleet/model-scorecard.tsv` (92 rows +
all dogfood result cards), `fleet/tier-models.tsv`, `fleet/state/S8-GRACEFUL-DEGRADE-DESIGN.md`,
product `src/charon/routing_policy/matrix.py` + `src/charon/capability/taxonomy.py`.

**Bottom line: the two systems that are supposed to rank models both fail to do so today.**
The synthetic OOB battery (MODEL-PREFLIGHT) has *never produced a valid discrimination result* — it
fails closed for every model on environment faults. The live dogfood ranker *cannot enforce its
central invariant* (latency-is-a-failure-class) because the too-slow attribution path is dead code,
and it grades models on a taxonomy the product router can't consume. Everything else (leg pinning,
the R0–R3 ladder, per-skill elimination, the discrimination proof) is design-only or prototype-only.

---

## SEVERITY SUMMARY

| # | Sev | Finding (one line) |
|---|-----|--------------------|
| 1 | BLOCKER | too-slow attribution is DEAD CODE — every rc=124 hang is excused as `provider-throttled`, never `DETAIN(latency)` |
| 2 | BLOCKER | MODEL-PREFLIGHT battery has never validly discriminated — controls fail-closed on grader infra (perm + no pytest); no Chunk-D proof exists |
| 3 | BLOCKER | Eval grades the WRONG taxonomy — fleet build-classes, not the product router's semantic work_classes; "two consumers, one taxonomy" is false |
| 4 | HIGH | dogfood's own measured `elapsed>=budget` is computed but never gates the verdict — a budget-BREACHING clean run lands REVIEW-READY (proven: glm-5.2 RFL-3 499s>480) |
| 5 | HIGH | 3 "skills" are 1 skill — the honest battery is three small-Python charon edits mislabeled bugfix/refactor/routing; ~14 real work_classes untested |
| 6 | HIGH | No per-provider/leg attribution in the ranking path — base pool ids route cheapest-available; free-vs-paid + per-leg rank unmeasurable; leg-canary is prototype-only |
| 7 | HIGH | Difficulty ramp is ASSERTED not proven — R0–R3 ladder + per-(model×skill) elimination unbuilt; canary task saturated (5/5 for all); no per-rung split control |
| 8 | HIGH | Rung/latency budgets (3/6/10 min, 480/900 s) are arbitrary round numbers contradicted by observed 20 s–538 s spread |
| 9 | HIGH | Ramp STRUCTURE unprincipled — 4 fixed rungs, undefined step size, rungs conflated with tiers, no adaptive placement |
| 10 | MED | promote.py gate confuses between-model spread with discrimination validity; no good-vs-bad control; N=1 noise can promote |
| 11 | MED | assign.py tier filter is a no-op for the exact ids the eval tests (tier_hint None → passes) |
| 12 | MED | 4–5 overlapping harnesses, no single pipeline; S0–S6 still `active` in units.tsv |
| 13 | MED | live rows written `stage=active` with NO promotion gate — one run moves the grade; compounds #4 |
| 14 | LOW | canary `exec()`s model output unsandboxed |
| 15 | LOW | product-side slow-axis hold (S8) is design-only — even a correct too-slow flag can't hold a leg |

---

## 1. BUGS / CORRECTNESS

### F1 — BLOCKER — too-slow attribution is dead code; latency-is-a-failure-class is unenforced in dogfood

`lib/dogfood-attribution.sh:41-46` classifies a nonzero run by grepping charon-run's log:
```
grep 'TIMEOUT (rc=124.*CAUSE: gateway pool exhausted'   -> provider-degraded->retry
grep 'TIMEOUT (rc=124.*too-slow FAIL'                    -> too-slow(latency-budget-exceeded)
```
**Neither string is emitted anywhere.** `grep -rn 'too-slow FAIL|CAUSE: gateway pool exhausted|TIMEOUT (rc=124'`
over all of `fleet/` returns ONLY the attribution lib itself (the matcher), never a producer.
What `charon-run.sh` actually does on a timeout:
- `charon-run.sh:89` runs `timeout "$CHARON_RUN_TIMEOUT_S" opencode …`; a budget hit gives `RC=124`.
- `charon-run.sh:100` → `is_infra_fault` which at its first line does `[ "$rc" -eq 124 ] && return 0`
  (charon-run.sh:44) — so a timeout is declared an **infra fault**, prints `hit a provider/local/infra FAULT (rc=124…)`, `continue`s.
- With one candidate model, the loop then falls through to `charon-run.sh:120` `ALL MODELS EXHAUSTED`.

So `classify_attribution` skips buckets 1–2 (strings absent), skips the LIMIT/db-lock/UnknownError
greps, and matches `charon-run.sh:56` `"ALL MODELS EXHAUSTED"` → returns
**`provider-throttled->try-another(all-exhausted)`**. In `dogfood-eval.sh:289-299` that yields
`overall = RETRY(provider-symptom-not-model-fault)` — **explicitly NOT disqualifying**. The `too-slow`
branch (dogfood-eval.sh:289 `overall="DETAIN(latency)"`) is unreachable.

**Net effect: a model that hangs forever and is killed at its budget is treated identically to a
provider outage and retried, never failed.** This is the exact bug the lib's header claims to fix; it
fixed the *ordering* but wired the correct buckets to strings that don't exist. `is_infra_fault`'s
rc=124→infra rule (charon-run.sh:44) is defensible for the 1800 s hard ceiling but is precisely wrong
when dogfood/preflight pass a *tight* `CHARON_RUN_TIMEOUT_S` as a real latency budget.

**Fix:** make the budget-hit self-describing. In `charon-run.sh`, when `RC==124` AND
`CHARON_RUN_TIMEOUT_S` was caller-supplied (budget mode, not the 1800 default), emit a distinct line,
e.g. `echo "[charon-run] model '$M' TIMEOUT (rc=124) budget=${CHARON_RUN_TIMEOUT_S}s too-slow FAIL"` and
do NOT route it through `is_infra_fault`. Then the existing `classify_attribution` grep at
dogfood-attribution.sh:44 fires and DETAIN(latency) is reachable. Add a `selftest/` fixture that feeds
a real budget-timeout log through `classify_attribution` and asserts `too-slow*` (the current selftest
clearly never exercised this path, or the dead string would have been caught).

### F4 — HIGH — dogfood measures elapsed≥budget but never gates on it; budget-breaching clean runs pass

Independently of F1, `dogfood-eval.sh:222-223` computes a real wall-clock verdict:
```
[ "$elapsed" -ge "$LATENCY_BUDGET_S" ] && latency_verdict="BUDGET-EXCEEDED(too-slow-is-a-fail-by-itself)"
```
But the overall-verdict block (dogfood-eval.sh:288-299) **never reads `latency_verdict`** — it branches
only on the grep-derived `attribution`. So a run that overran the budget on the wall clock but graded
clean is REVIEW-READY.

**Proven in the data.** `results/RFL-3-20260715T001840Z-SUMMARY.md`: `glm-5.2` wall=499 s, budget=480 s
→ `latency_verdict` must have been BUDGET-EXCEEDED, yet `overall = REVIEW-READY`. Worse, that same clean
row is eligible for `finalize_live_capture` (dogfood-eval.sh:305/136) → enqueues a **MERGE score=100
source=live/stage=active** scorecard row for a run that broke the latency budget. The ranker is being
fed budget-violating passes as clean wins.

**Fix:** in the overall block, before the REVIEW-READY branch, add
`elif [ "$elapsed" -ge "$LATENCY_BUDGET_S" ]; then overall="DETAIN(latency-wallclock)"`. This is the
belt-and-suspenders check that should exist regardless of F1 (it does not depend on any log string). Then
`finalize_live_capture`'s `DETAIN*)` case (dogfood-eval.sh:147) correctly maps it to BLOCK.

### F-attr-2 — MED — other classifier mislabels remain

- A genuine provider limit that DID print a 429 banner is caught (dogfood-attribution.sh:47) — good — but
  a limit that surfaces only as `rc=124` (timeout while throttled) is indistinguishable from a slow model
  after the F1 fix, because both become rc=124. The design's "CONFIRM-would-finish re-run at 2–3× budget"
  (MODEL-PREFLIGHT.md:22-25) is the intended disambiguator and is **unbuilt** — there is no re-run harness.
- `error-nonlimit` and `local-error(opaque)` both funnel to `RETRY … needs human triage` (never
  disqualifying). Phi-4's 4/4 `UnknownError` runs (dogfood-attribution.sh:16-21) are thus permanently
  un-rankable — correct to not blame the model, but the system has no path to ever get a verdict for such
  a model; it just silently never scores. That is a coverage hole, not just an attribution nicety.

### F-finalize — MED — finalize_live_capture is single-log-safe but selection-biased

The double-log guard (dogfood-eval.sh:142, requires `CHARON_RUN_RESULT=SUCCESS`) is sound: `charon-run.sh`
writes that marker only on the rc=0 path (charon-run.sh:113), and writes its own FINAL row only on the
`error-failover` path (charon-run.sh:109) which has no marker. So no double count. BUT: the reclassified
"trailing-provider-after-success" REVIEW-READY runs (rc≠0, e.g. glm-5.2 RFL-3) have **no SUCCESS marker**,
so they are silently dropped from the live lane. The live ledger therefore systematically under-samples
exactly the hardest/slowest-leg cases. Not a miscount, but a survivorship bias in what feeds grades.py.

---

## 2. SKILL / AREA COVERAGE GAPS (emphasis)

### F3 — BLOCKER — the eval measures a taxonomy the product router cannot consume

There are **three disjoint work_class vocabularies** in the tree:

| Source | Classes | Consumer |
|---|---|---|
| `capability/grades.py:138-142` + scorecard header | money-path, routing, ci-infra, refactor, bugfix, tests, greenfield-feature, docs, frontend, rig-meta, design-review | fleet `assign.py`, live-lane ranking |
| `src/charon/routing_policy/matrix.py:20-27` | reasoning, coding, translation, creative, analysis, general | **product gateway routing** (`CapabilityMatrix.get_grade`) |
| `src/charon/capability/taxonomy.py` `_SEED_CLASSES` | reasoning, coding, translation, creative, analysis, general | product request classifier (`classify_request`, hot path) |

`grades.py:1-16` promises "Two callers share this module … Both must see the SAME work_class taxonomy" —
the fleet assigner and "later, the gateway request-routing consumer." **They do not share a taxonomy.**
The dogfood/honest sweep tags rows `bugfix|refactor|routing` (honest-battery-sweep.sh:49-59) — fleet
classes. When the gateway routing consumer ships, it will classify a live request as `coding`/`reasoning`/
`translation` and query grades.py, which has **zero rows** in those classes → every model
`grade()==None` → generalist fallback for everything. The entire live-lane ranking effort produces data
the router-of-record cannot use for its actual per-class decisions.

**Fix:** pick ONE taxonomy before collecting more data. The product's semantic classes
(reasoning/coding/translation/creative/analysis/general, matrix.py:20) are what a *gateway* must route on;
the fleet classes (money-path/refactor/bugfix…) are ticket-shaped. Either (a) map fleet→semantic at
capture time and grade in the semantic space, or (b) explicitly declare the live lane is fleet-assignment-
only and stand up a SEPARATE semantic-class eval for the router. Today's silent conflation guarantees the
router starts cold.

### F5 — HIGH — the honest battery is one skill wearing three labels

All three honest tasks are small Python edits in the Charon repo, graded by `pytest + a grep-by-name`:
- SECRET-HOTROTATE (`bugfix`): add a kwarg to `secrets.py`, 2 files (SECRET-HOTROTATE-eval.md:26-49).
- PROVIDER-URL-HELPER (`refactor`): extract 2 helpers, ~3 files (PROVIDER-URL-HELPER-eval.md:20-52).
- RFL-3 (`routing`): add one exclusion block in `forwarder.py`, 1 file (RFL-3-eval.md:27-56).

These differ in label, not in *capability exercised*: all are ≤4-file, single-function, local-logic
edits with a mechanical accept-check. There is no discrimination among genuinely different skills — a
model good at "add a small function with a test" scores identically across all three. `assign.py` then
publishes per-work_class grades that are really the same signal three times.

**Untested work_classes** (against BOTH taxonomies): multi-file / large-context refactor (≥3 files,
every call site — designed as preflight T8 but never run), agentic multi-step tool-use, test-QUALITY /
vacuous-test detection (preflight T2, never validly run), security/secret-hygiene beyond a regex grep
(T12, never run), debugging-under-ambiguity, long instruction-following (≥ several constraints), citation/
hallucination (T9), SQL/data, concurrency, frontend (S6 exists but is synthetic+demoted), long-context
≥32 k, reasoning, translation, creative, analysis. So of ~14 skills that matter, the *live* lane exercises
~1.

**Fix:** define a minimal skill matrix (≥1 discriminating, RED-proof task per semantic class + the high-
risk cross-cutting traps) and require live coverage before any per-class grade is trusted; until a class
has a real task, `grade(model, class)` should return `None`/UNKNOWN, not a generalist borrow.

### Saturation check
The canary (`is_bal` balanced-parens, leg-canary-prototype.py:8-12) is trivially saturated — the ticket
itself notes "canary gave every model 5/5." Zero discrimination signal at R0 beyond reachability. The
prototype names a "small fast" second model as a would-be weak control but records no result proving it
scores low, so the "must discriminate a real top-tier from a degraded model" acceptance
(LEG-PREFLIGHT-CANARY.md:19) is unmet.

---

## 3. DIFFICULTY RAMP — asserted, not proven

### F7 — HIGH — no per-rung discrimination proof; the ladder is unbuilt

`PREFLIGHT-DESIGN-V2.md:154-161` §3.3 REQUIRES, as a ship-gate, a per-task split: deepseek-v4-flash
(MUST-FAIL) fails T1/T2/T9/T10 while a strong control passes them — "Prove discrimination PER TASK … do
not ship" otherwise. **That proof does not exist.** `benchmark/preflight-discrimination.md` (the Chunk-D
owns artifact, PREFLIGHT-DESIGN-V2.md:179) is absent. The only control run on record
(`state/preflight-results/deepseek-v4-flash.card/.log`) is a SINGLE task (T2) and its `FAIL` is a
**grader-side `PermissionError: … gateway/headers.py`** (see F2 below), i.e. a false fail from infra, not
a judgment of the model. So even the one data point is invalid.

The R0→R1→R2→R3 STAGED ELIMINATION LADDER and per-(model×skill) elimination
(MODEL-PREFLIGHT.md:26-40) are **design text only**. `preflight.sh` implements no rungs — it runs a flat
`N≥3` over every manifest row (preflight.sh:267-340) and emits one trust/detain card
(preflight.sh:366-372). There is no R0 gate, no early-out, no per-skill ceiling. The budgets 3/6/10 min
are never encoded anywhere in code.

### F2 — BLOCKER — the synthetic battery fails closed for ALL models (never validly discriminated)

`state/preflight-results/CONTROLS-STATUS.md` documents that when preflight was actually driven:
1. Attempt 1: daemon-side `PermissionError` on the session root (cross-user `mktemp -d 0700`).
2. Attempt 2: `shutil.Error` on a hypothesis cache file `0600` the daemon can't read.
3. Attempt 3: real grader ran but returned `FAIL … "No module named pytest"` — **`bench-grader`'s
   `python3` has no pytest**, and every task grader folds a T13 "full suite green" check
   (manifest T13, PREFLIGHT-DESIGN-V2.md:129-131). So **every candidate FAILs every task** for an
   environment reason, independent of model quality.

The `deepseek-v4-flash.log` I read confirms it: all 3 T2 runs `FAIL` with
`grader internal error (fail-closed): PermissionError: … gateway/headers.py`. The grader's fail-closed
contract (graders/preflight.py FAIL-CLOSED) is correct in principle, but combined with these two
environment faults it means the battery **cannot distinguish good from bad** — it detains everyone. Per
its own §3 rule, it must not be used to gate tier entry, yet `MODEL-PREFLIGHT.md:48` bills it as "the
accurate model test."

**Fix (both blockers):** (a) provision `bench-grader` with pytest (system or its own venv) and make the
graders invoke a pinned interpreter, not bare `python3`; (b) fix the snapshot to tolerate/normalize
unreadable tool-cache files (the `chmod -R o+rX` band-aid in preflight.sh:282 is fighting a symptom —
exclude `.hypothesis`/`.pytest_cache`/`__pycache__` in the tar at copy_session_files, and have the daemon
snapshot skip-and-log unreadable files rather than aborting); (c) THEN run Chunk D and publish the
per-task split before the battery gates anything. Until (c), preflight output is noise.

### F8 — HIGH — rung/latency budgets are arbitrary; observed data contradicts them (coordinator ask #1)

**(a) No data basis for 3/6/10.** MODEL-PREFLIGHT.md:26-31 states the rungs "~3 min / ~5-6 min / ~10+ min"
and the design admits the 480 s figure is "only headroom over the slowest observed real completion (410s)
— make it a derived number … not an arbitrary round figure" (MODEL-PREFLIGHT.md:20-21). They are operator-
comment round numbers.

**(b) Cross-check against real wall-clock (from the dogfood cards / scorecard `time_s`):**

| task (label) | good-model completions (s) | field range (s) | flat budget used |
|---|---|---|---|
| canary is_bal | 1–7 | 1–7 | 60–90 |
| SECRET-HOTROTATE (bugfix, 2f) | 20, 31, 35 | 20–311 | 420/600 |
| PROVIDER-URL-HELPER (refactor, 3–4f) | 90, 129, 180, 314 | 57–876 | 420–1200 |
| RFL-3 (routing, 1f harder logic) | 410, 439, 499, 538 | 242–538 | **480** |

Two things jump out: (i) completion time spans **20 s → 538 s (~27×)** across three tasks all treated as
one "small-ticket" tier under one flat budget; (ii) the RFL-3 field is jammed at **497–499 s against a 480
s ceiling** (glm 499, minimax-m3 498, gemma 497, free-mistral 498, minimax-m2 498) — i.e. the budget
TRUNCATED most of the field mid-work, then failover added ~18 s. RFL-3's own good models needed 410–538 s;
a 480 s budget is below the task's real p50 for capable models. Meanwhile SECRET-HOTROTATE finishes in
20–35 s, so 480 s there is ~15× too loose to catch a slow model. **One flat budget is simultaneously too
tight for RFL-3 and too loose for SECRET-HOTROTATE** — direct evidence the round numbers don't map to task
difficulty.

**(c) A fixed wall-clock is the wrong unit anyway.** A fast leg and a slow leg doing the *same correct
work* legitimately differ 5–10× (canary tok/s varies per leg; RFL-3 deepseek 410 s vs kimi 439 s vs glm
499 s are the same diff). A wall-clock cutoff conflates "model is slow to reason" with "leg has low
throughput today."

**Fix — derived, two-part budget:**
1. Derive a per-(work_class × difficulty) budget from the observed completion-time distribution of
   KNOWN-GOOD models: `budget = p95(good_model_completion) + margin` (e.g. 1.5×). Recompute from the
   scorecard `time_s` column as data accrues; store it in a small `fleet/state/budgets.tsv` keyed
   (work_class, difficulty), NOT hard-coded in prose. On today's data that alone gives RFL-3 ~800 s and
   SECRET-HOTROTATE ~55 s — both far from 480.
2. Normalize out leg throughput: measure each leg's tok/s at R0 (the canary already reports it,
   leg-canary-prototype.py:38), express the budget as a **token budget** `T_task` (p95 good-model output
   tokens for the task), and set the per-run wall budget = `T_task / measured_tok_s(leg) + fixed_overhead`.
   A slow-but-correct leg then gets proportionally more wall time; only a model that needs *more tokens*
   (thrashing/looping) or stalls fails. This makes "too-slow" mean "too much work," not "unlucky leg."

Rank: HIGH (the budget directly gates the DETAIN(latency) verdict that F1/F4 also touch — a wrong budget
mis-eliminates good models and passes slow ones).

### F9 — HIGH — ramp STRUCTURE is unprincipled (coordinator ask #2)

**(a) Is 4 rungs right?** R0 (canary) does reachability only; R1/R2/R3 are three quality rungs with no
stated size relationship. Four is neither justified nor tied to how many candidates each rung should shed.
A model that clears R1 and fails R2 tells you only "ceiling somewhere in a huge R1→R2 gap" — the ramp is
too coarse to *locate* a ceiling, which is its stated job (MODEL-PREFLIGHT.md:31 "R3 … LOCATES the
ceiling"). No rung has a defined difficulty delta, so "locate" is aspirational.

**(b) Step size undefined.** There is no rule for how much harder each rung is. Uniform steps waste rungs
where candidates cluster; the elimination is most efficient when each rung is placed to split the
*remaining* candidate field roughly in half (binary-search / adaptive-testing logic). Concretely: size the
step so each rung's expected pass-rate over the current field is ~50% (max information per rung), which for
a roughly log-normal ability spread means **geometric** difficulty steps, not linear.

**(c) Rungs vs tiers are conflated.** MODEL-PREFLIGHT.md:27 says "difficulty scaled to the tier" but never
defines the mapping — are R1/R2/R3 the same axis as economy/strong/frontier, orthogonal, or nested? Today
they're informally equated ("tier-appropriate difficulty") with no concrete definition (see F-tier). A
'strong'-band distinction (deepseek-flash vs glm vs kimi) needs *finer* rungs than the economy/frontier
gaps; a single global 3-rung ladder can't provide that.

**(d) Fixed vs adaptive.** Every model starts at R1 and climbs. That wastes rungs on both ends — a known-
frontier model re-proves R1 it will obviously clear; a known-weak model climbs rungs it will obviously
fail. Adaptive placement (start each candidate at its *expected* tier from prior/cheap signal, then search
up until it fails and down until it passes) locates a ceiling in ~log₂(rungs) tests instead of linear.

**Proposed concrete structure:**
- Keep **R0** = cheap leg canary (reachability + throughput + gross-degradation control), pass/park only.
- Replace the fixed 3-quality-rung climb with an **item-bank + adaptive placement**: a bank of RED-proof
  tasks each tagged with a *calibrated* difficulty (calibrated empirically = the pass-rate of the known
  control panel on that task, IRT-style — a task the MUST-PASS control clears and the MUST-FAIL control
  misses has difficulty between them). Start a candidate at the difficulty of its cost-tier prior; after
  each task move up on pass / down on fail with a shrinking step (standard adaptive step-halving); stop
  when the pass/fail boundary is bracketed within one difficulty unit. Report the bracketed ceiling PER
  (skill, model), which is exactly the per-(model×skill) grade assign.py wants
  (MODEL-PREFLIGHT.md:32-38).
- Difficulty steps: geometric, sized so the control panel's pass-rate falls ~one band per step; finer bank
  density inside the 'strong' region (where routing decisions are close) than at the frontier extreme.
- Tier mapping made concrete: a model's tier = the difficulty band where its per-skill ceiling lands, NOT
  a pre-assigned label — so tiers become an *output* of the ramp, resolving the conflation.

Rank: HIGH (the ramp is the core mechanism for the stated per-skill ceiling grade; the current
under-specification is why the ladder was never built).

---

## 4. TIER DESIGN

### F-tier — HIGH — "tier-appropriate difficulty" is undefined and tier boundaries are inconsistent/unenforced

- `tier-models.tsv` is explicitly PROVISIONAL — its own header says "NO workhorse-per-tier is finalized …
  NOT a 'chosen' workhorse" (tier-models.tsv:16-18). So the eval is ranking into buckets that are
  admittedly not real.
- The three tier axes don't line up: `tier-models.tsv` uses frontier/strong/economy failover CHAINS;
  `grades.py:436-440` maps those to low/med/high COST tiers from the product catalog; the scorecard `tier`
  column is a 0–4 *benchmark difficulty* index (scorecard header line 4) — a THIRD meaning of "tier." The
  ladder's "tier-appropriate difficulty" (MODEL-PREFLIGHT.md:27) is never pinned to any of these.
- **assign.py's tier filter is a no-op for the models the eval actually tests.** `assign.py:117` excludes a
  candidate only when `tier_hint is not None and tier_hint != req_tier`. `get_tier_hint` (grades.py:466)
  returns None for any id not in the curated `model_catalog` — which is *most* gateway ids the sweep uses
  (`deepseek-v4-pro-ds`, `gemma-4-31b-cb`, `minimax-m3-together`, `free-mistral-code`…). None → passes the
  filter. So `--tier strong` silently admits every uncatalogued id regardless of cost tier.

**Fix:** define ONE canonical tier axis (cost band is the meaningful one for routing) with a concrete
rule: a model's tier = the difficulty band where its per-skill ceiling lands (see F9) crossed with its
$/token. Make assign.py's tier filter fail-closed for unknown tier_hint (exclude or require an explicit
override) so an uncatalogued id can't sneak into a tier it was never graded for. Add a catalog-parity check
(memory: always-fix-catalog-mismatches) so every gateway id in tier-models.tsv has a catalog tier_hint.

---

## 5. CONSOLIDATION / REDUNDANCY

### F12 — MED — four-to-five overlapping harnesses; no single pipeline

| Harness | Built? | Grading | Battery | Feeds |
|---|---|---|---|---|
| `benchmark/preflight.sh` (T1–T12) | built, but non-functional (F2) | OOB $KEYS graders | 12 synthetic charon-shaped fixtures | trust/detain card only (not the live grade) |
| `benchmark/dogfood-eval.sh` | built + used | `charon.cli gate` + DOGFOOD_TEST_CMD | 3 real charon tickets | live-lane scorecard rows |
| `benchmark/honest-battery-sweep.sh` | built (wraps dogfood) | (delegates) | same 3 tickets × roster | (delegates) |
| `leg-preflight.sh` / canary R0 | **prototype only** (no leg-preflight.sh, no preflight-tasks/canary/, no LEG-RANK.tsv) | exec-check | is_bal | nothing |
| `benchmark/bench.sh` + `run.sh` (S0–S6) | built, DEMOTED to smoke | mixed | 7 synthetic sections | excluded from grades (source=bench) but still `active` in units.tsv |

That's three synthetic coding batteries (T1–T12, S0–S6, canary) plus one live battery, all measuring
"can this model do a small Python code task correctly." The preflight T-tasks and the S-sections overlap
heavily in intent (T1 cross-module-wire ≈ S2 routing wire; T8 refactor ≈ S4 refactor; T2 vacuous-test ≈
the honest briefs' grep-by-name test-quality check). The honest briefs re-implement, as live tasks, the
same "objective RED-proof accept-check" the T-graders implement OOB.

**Consolidated design (one pipeline):**
1. **R0 leg gate** (build the prototype into `leg-preflight.sh`) — reachability + throughput + gross-
   degradation control; parks dead legs; writes LEG-RANK.tsv. Cheap front-half of the ≥1-viable invariant.
2. **One item-bank** of RED-proof tasks (merge the surviving, non-saturated T-tasks + the honest briefs +
   any S-section that discriminates), each tagged (semantic work_class, calibrated difficulty), graded
   OOB by the ONE grader-daemon path (kind=="preflight"/"live" unified). Retire S0–S6 as a separate battery
   (keep S0 only as the harness smoke test, which tier_chart already does).
3. **One adaptive runner** (F9) that places each candidate, produces the per-(model×skill) ceiling, and is
   the SOLE writer of `source=live` scorecard rows via one capture path.
4. `promote.py`/grades.py stay as the trust gate, but promotion keys on the control-panel split (F10), not
   raw between-model spread.

This collapses 5 harnesses to R0 + one battery + one runner, removes the taxonomy fork (F3), and gives one
place that answers "is this model trusted for this skill at this cost."

---

## 6. VALIDITY

### F10 — MED — promote.py confuses between-model spread with discrimination validity

`promote.py:144-163` promotes a unit iff `spread = max-min per-model mean ≥ 15` AND `distinct_models ≥ 2`.
Problems:
- It measures whether two models *differ*, not whether the task separates *good from bad*. Two mediocre
  models differing by noise (each N=1) satisfy spread≥15 and promote a non-diagnostic unit. There is no
  requirement that the spread be driven by the known MUST-PASS vs MUST-FAIL control split that
  PREFLIGHT-DESIGN-V2.md:154-161 makes the actual validity criterion.
- It uses per-model MEAN, so a high-variance-but-real task where both models score {100,0} (mean 50 each,
  spread 0) is wrongly rejected as saturated; a saturated-but-noisy pair is wrongly promoted.
- K=2 distinct models (promote.py:46) is too weak to distinguish signal from a coin flip.

**Fix:** gate promotion on a control-panel result — require the designated MUST-FAIL control to FAIL and the
MUST-PASS control to PASS the unit (the §3 rule), N≥3 each; use that split, not raw between-model spread,
as the discrimination proof. Keep spread only as a secondary sanity check.

### F13 — MED — live rows are `active` on write with no promotion gate

`finalize_live_capture` enqueues `--stage active` (dogfood-eval.sh:155). grades.py trusts `source=live` +
`stage=active` immediately (grades.py:176,198,350-352). So a SINGLE dogfood run moves the capability grade
the moment it lands — the Wilson lower bound (grades.py:59-82) discounts small N but does not *gate* it,
and there is no per-unit discrimination check for live tasks the way promote.py (nominally) provides for
synthetic units. Combined with F4, a budget-breaching clean run injects a `MERGE score=100` that
immediately shifts the pick. The provisional→active gate that the design is so careful about for synthetic
units simply doesn't exist on the live path.

**Fix:** run live tasks through the same control-panel discrimination gate before their rows count toward a
grade (or require N≥MIN_N and a control split for the task before any live row for that task is admitted).

### Validity — is the live lane the trusted source? Partially, and it's leaking synthetic-era problems
grades.py's real-outcomes allow-list (grades.py:176 `{"live"}`, fail-closed) is the right instinct and
correctly demotes S0–S6. But "live" here is dogfood-eval output whose objectivity depends entirely on
`charon.cli gate` + the ticket's DOGFOOD_TEST_CMD. Those accept-checks ARE genuine RED-proofs (verified in
the briefs, e.g. RFL-3-eval.md:82-88 rc=4-before/rc=0-after), which is good. But: (i) all three probe the
same skill (F5); (ii) budget-violating passes leak in (F4); (iii) there's no provider attribution (F6), so
a "live" grade for `deepseek-v4-pro` blends however-many providers served it. The live lane is trustworthy
as *"did a real objective check pass"* but not yet as *"this MODEL (on this LEG, at this cost, for this
skill) is grade X."*

---

## Cross-cutting: per-provider / leg pinning (F6 — HIGH, answers the mandate's leg-pinning question)

The ranking harnesses (dogfood-eval, honest-battery-sweep) invoke **base pool ids** (`deepseek-v4-pro`,
`glm-5.2`, honest-battery-sweep.sh:18-21). The gateway then routes each to its own cheapest-available
PROVIDER and does cross-provider failover *inside* one id. The result card admits this outright:
`provider: best-effort unknown-clientside … gateway alias only, needs gateway-log correlation for real
per-provider attribution` (dogfood-eval.sh:328). **So per-provider ranking through the main harness is
impossible** — a `deepseek-v4-pro` grade is an average over whatever legs happened to serve, and the
free-vs-paid axis the design wants (MODEL-PREFLIGHT.md:43-44) can't be isolated.

The ONLY leg-pinned mechanism is the canary prototype, which pins by using provider-suffixed ids
(`nvidia/…`, leg-canary-prototype.py:11-12) — that technique works, but `leg-preflight.sh`,
`preflight-tasks/canary/`, and `LEG-RANK.tsv` (the ticket's owns) **do not exist**; it's a scratch script.
The scorecard already shows the workaround in use ad hoc: `deepseek-v4-pro-ds` (a -ds provider-pinned
alias) appears as a distinct row from `deepseek-v4-pro`, but this is manual and inconsistent.

**Fix:** rank on provider-pinned ids end-to-end (make dogfood/sweep take a leg-suffixed id and disable the
gateway's internal cross-provider failover for the ranking run, or correlate the gateway request log by
request-id to recover which leg served — the card already flags this as the missing correlation). Build
`leg-preflight.sh` from the prototype so R0 emits LEG-RANK.tsv and the sweep skips non-HEALTHY legs
(the availability gate the design says is missing today, LEG-PREFLIGHT-CANARY.md:27-29).

---

## Minor / LOW

- **F14** `leg-canary-prototype.py:32` `exec(code, ns)` runs model-emitted code unsandboxed ("trusted-ish,
  short"). Fine for a throwaway prototype; if promoted to `leg-preflight.sh`, run the exec-check in a
  subprocess with a resource/seccomp/`ulimit` boundary — a canary that lets the tested model run arbitrary
  code on the eval host is a supply-chain hole.
- **F15** Even a correct too-slow verdict can't act on the product side: `S8-GRACEFUL-DEGRADE-DESIGN.md`
  documents `is_slow`/`is_slow_provider` are DEFINED but have zero callers — "latency-is-a-failure-class is
  not actually wired." So the eval's latency axis and the product's provider-hold are both inert on latency;
  fixing the eval (F1/F4) without wiring S8 still leaves slow legs in rotation.
- **units.tsv** grandfathers S0–S6 as `active` (units.tsv:19-26); harmless today (source=bench excluded)
  but a latent trap if a future run ever re-tags an S-section with a real source.

---

## RECOMMENDED SEQUENCE (highest leverage first)
1. F1 + F4 together (make budget-timeout self-describing in charon-run.sh; add the wall-clock DETAIN branch
   in dogfood-eval.sh) — restores latency-is-a-failure-class. Small, high-value.
2. F2 (provision bench-grader pytest + fix snapshot perms/excludes) — without it the entire synthetic
   battery is dead weight.
3. F3 (decide the taxonomy) — every further data-collection decision depends on it.
4. F8 (derived per-(work_class×difficulty) + token/tok_s budgets) — feeds F1/F4/F9.
5. F6 (leg pinning end-to-end + build leg-preflight.sh).
6. F9 + F12 (adaptive item-bank ramp = the consolidated single pipeline), then F10/F13 (control-panel
   promotion gate on both synthetic and live), then F-tier.
