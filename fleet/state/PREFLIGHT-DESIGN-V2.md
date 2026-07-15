# PREFLIGHT-DESIGN-V2 — design of record for the model preflight battery

This document is the design of record referenced by:
  - `fleet/benchmark/preflight.sh`  (§2 the T1-T14 battery, §3 validity plan)
  - `fleet/benchmark/graders/preflight.py`  (§1 SUBSTRATE, §4 Chunk 0)
  - `fleet/benchmark/graders/preflight_checks/_pf_common.py`  (§2)
  - `fleet/benchmark/preflight-tasks/manifest.tsv`  (§2)
  - `fleet/benchmark/preflight-tasks/README.md`  (§2)
  - `fleet/benchmark/selftest/test_preflight_graders.py`  (§2 Chunk B)
  - `fleet/tests/test_preflight_runner.sh`  (§3 validity plan, §4 Chunk C)
  - `fleet/board/EVAL-PROMOTION-GATE.md`  (MUST-PASS/MUST-FAIL controls)
  - `fleet/board/MODEL-PREFLIGHT.md`  (LATENCY-BUDGET, staged-elimination rungs)

It supersedes the arbitrary round-number budgets (3/6/10 min rungs, 480/900 s
latency ceilings) documented in `fleet/state/MODEL-TESTING-ADVERSARIAL-
REVIEW.md` §F8 with **DERIVED** budgets keyed on `(canonical work_class ×
difficulty)`, computed from the observed completion-time distribution of
known-good models and normalized per-leg via `token / measured tok_s`.

## §1 — SUBSTRATE

The preflight runs out-of-band (the `bench-grader` user, hidden model-unreadable
assertion keys) so the subject model cannot read its own answer key, grade
itself, or self-report. The grader daemon
(`fleet/benchmark/grader-daemon.py`) is the sole writer of
`model-scorecard.tsv`; in-band grading reproduces the S0-S6 invalidity this
substrate fixes (see `fleet/board/BENCH-OOB-GRADING.md` / `REVIEW-PACKET.md`).
Chunk-0 (the seam between runner and daemon) is merged; the battery builds on it.

## §2 — The T1-T14 battery

14 checks: T1-6 hardened vs gaming vectors (decoys, citation-verify,
all-or-nothing, fix-don't-delete, secret-hygiene, regression), T7-14 the
broader coverage (refactor, cost/latency, etc.). The task manifests live in
`fleet/benchmark/preflight-tasks/manifest.tsv`; each task carries a grader +
fixture resolved by `lib/sections.sh`-style helpers. `_pf_common.py` holds the
shared word-boundary / normalization logic every preflight checker uses so a
model cannot game by padding/casing/Unicode-tricks.

## §3 — Validity plan

N>=3 runs per task (a hard floor; `preflight.sh:224` enforces it), disguised
fixtures (a model cannot recognize a task it has seen), a deepseek-v4-flash
MUST-FAIL control + a strong MUST-PASS control per task (per-task
discrimination proof). `fleet/tests/test_preflight_runner.sh` exercises §3
end-to-end. `fleet/benchmark/selftest/test_preflight_graders.py` exercises §2.

## §4 — Chunk C (capture wire)

The runner -> daemon maildrop hand-off (`req/` -> `res/` poll). The runner
NEVER writes `model-scorecard.tsv` (the daemon owns it); it drops a JSON
request and polls for the JSON result.

## §LATENCY-BUDGET — DERIVED, not arbitrary (EVAL-DERIVED-BUDGETS, review F8)

### The problem with the old numbers

`MODEL-TESTING-ADVERSARIAL-REVIEW.md` §F8 catches that the round-number budgets
were **contradicted by the observed data**:

| task (label) | good-model completions (s) | field range (s) | old flat budget |
|---|---|---|---|
| canary is_bal | 1–7 | 1–7 | 60–90 |
| SECRET-HOTROTATE (bugfix, 2f) | 20, 31, 35 | 20–311 | 420/600 |
| PROVIDER-URL-HELPER (refactor, 3–4f) | 90, 129, 180, 314 | 57–876 | 420–1200 |
| RFL-3 (routing, 1f harder logic) | 410, 439, 499, 538 | 242–538 | **480** |

Two failures, simultaneously: (i) completion time spans **20 s → 538 s (~27×)**
across three tasks all treated as one "small-ticket" tier under one flat budget;
(ii) the RFL-3 field was **jammed at 497–499 s against a 480 s ceiling** — the
budget TRUNCATED most of the field mid-work (below the task's real p50 for
capable models), then failover added ~18 s. Meanwhile SECRET-HOTROTATE finishes
in 20–35 s, so 480 s there is ~15× too loose to catch a slow model. **One flat
budget is simultaneously too tight for RFL-3 AND too loose for
SECRET-HOTROTATE** — direct evidence the round numbers don't map to task
difficulty.

### The DERIVED rule (two-part)

**Part (a) — per-(work_class × difficulty) wall-clock ceiling.**

    budget = p95(good_model_completion_times) + margin
    where  margin = 0.5 * p95      (i.e. total budget = 1.5 * p95)

- **p95, not max**: robust to a single outlier run (a one-off provider hiccup
  that still graded MERGE shouldn't pin the budget at 2× typical).
- **margin = 0.5 × p95 (1.5× total)**: enough headroom that a capable model on a
  slightly-slow-but-healthy leg is not DETAINed for latency (F4's wall-clock
  DETAIN), while a model that needs >>1.5× a known-good model's time is
  genuinely too slow. F8's own worked example ("RFL-3 ~800 s" from a 538 s
  good-model max ≈ p95) sits inside 1.5× (538 × 1.5 = 807).
- The margin is a **function of p95**, never a flat add-on — otherwise slow
  tasks (RFL-3) and fast tasks (SECRET-HOTROTATE) get the same headroom and the
  "one flat budget failed both" problem returns in a different shape.

Per **(canonical work_class × difficulty)**: budgets are keyed on the canonical
product-router vocabulary from `fleet/state/EVAL-TAXONOMY.md`
(`reasoning, coding, translation, creative, analysis, general`), not the fleet
ticket-shape vocabulary — for the exact reason EVAL-TAXONOMY-ALIGN fixed: a
budget keyed on a fleet class the router never queries is useless to the router.
Legacy fleet classes (`bugfix`, `ci-infra`, `routing`, `refactor`, `tests`, ...)
resolve to canonical `coding` at read time via the `_LEGACY_TO_CANONICAL`
table (the same one `grades.py` carries).

Input data:
  - `model-scorecard.tsv` `time_s` (col 10) — KNOWN-GOOD = `verdict == MERGE`,
    `source in {live, bench, bench2}`, `stage == active`. A `MERGE` provisional
    row is not yet trustworthy; a `BLOCK`/`DETAIN(latency)` row is exactly the
    too-slow tail we must NOT let raise the p95 (it would re-introduce the
    RFL-3 499-s truncation as "evidence" the budget should be 499).
  - dogfood-eval result-card SUMMARY.md `wall_s` (col 4) — KNOWN-GOOD =
    `verdict` starts with `REVIEW-READY` (the pre-finalize form of MERGE per
    `dogfood-to-scorecard.sh`).

**Part (b) — per-leg normalization (the "not a flat number" half).**

    wall(leg) = token_budget / measured_tok_s(leg) + fixed_overhead_s

A fixed wall-clock conflates "model is slow to reason" with "leg has low
throughput today" (F8 finding (c): a fast leg and a slow leg doing the *same
correct work* legitimately differ 5–10×; canary tok/s varies per leg; RFL-3
deepseek 410 s vs kimi 439 s vs glm 499 s are the *same diff*). Fix: express
the task budget in TOKENS (p95 of good-model OUTPUT tokens for the task), then
derive the per-run wall as `token_budget / tok_s(leg) + overhead`. A
slow-but-correct leg (low tok/s) gets proportionally more wall time; only a
model that needs MORE tokens than the good-model p95 (thrashing/looping) or
stalls fails. This makes "too-slow" mean "too much work," not "unlucky leg."

- `token_budget` = p95(good-model `tokens_out`) — col 15 of the scorecard, when
  present. Falls back to `p95(good wall_s) × REFERENCE_TOK_S` when no token
  data exists (the common case today — `tokens_in`/`tokens_out` were added
  later and many rows are `-`).
- `measured_tok_s(leg)` = the canary's `tok_s` from `fleet/state/LEG-RANK.tsv`
  (produced by `fleet/benchmark/leg-preflight.sh`, LEG-PREFLIGHT-CANARY). A
  leg with 2× tok_s gets ~½ the streaming wall for the SAME token budget
  (the FAIL-ON-REVERT invariant in `fleet/tests/budget-derive.test.sh`).
- `fixed_overhead_s` = 20 s (covers worktree setup, gate fork, mtime settle).
  NOT a second latency budget — a constant floor so a 1-token leg still gets
  nonzero wall. 20 s matches `BENCH_MTIME_STABLE_SEC` and the leg-preflight
  probe order of magnitude.

### Safe fallback (insufficient data)

If a `(work_class, difficulty)` bucket has ZERO known-good rows, the derived
budget is `status=insufficient-data` with a conservative default
(`wall_budget_s = 900`, `token_budget = 12000`) — NOT a silently-zero budget
that would DETAIN every model on an uncalibrated class. 900 s is the highest
of the old arbitrary numbers, used as a ceiling-not-cliff: better to
over-budget an uncalibrated class than to DETAIN a good model for exceeding 0.
The status column makes it visible which buckets still need calibration data.

### The derivation tool

`fleet/benchmark/budget-derive.py` is the single recompute path. Stdlib-only
(`promote.py` precedent — no numpy in the privileged core). Reads the
scorecard + result cards + LEG-RANK, emits `fleet/state/budgets.tsv`:

    work_class  difficulty  n_good  p95_time_s  wall_budget_s  token_budget  status

`wall_budget_s` is the SLOW-LEG reference ceiling (`p95 × 1.5`); per-run callers
divide `token_budget` by the actual leg's `tok_s` and add `fixed_overhead_s`
for the fair per-run ceiling (the F8(b) win). Both are emitted so a caller
without LEG-RANK.tsv can still use the flat wall (graceful degrade) while a
caller with it gets the normalized number.

    # recompute from the live scorecard + rank + result cards:
    python3 fleet/benchmark/budget-derive.py
    # one-off per-run ceiling for a specific leg:
    python3 fleet/benchmark/budget-derive.py --wall-for-leg "<model>/<tok_s>" \
        --token-budget <T> --work-class <canonical_class>

### What this REPLACES (the consumers' repoint, not this ticket's scope)

The arbitrary numbers still live in three consumer files (NOT edited by
EVAL-DERIVED-BUDGETS — out of `owns:`; this doc names them so the consuming
tickets know what to repoint):

| File | Old arbitrary value | Repoints to |
|---|---|---|
| `fleet/benchmark/dogfood-eval.sh:74` | `LATENCY_BUDGET_S=900` (15 min flat) | `budgets.tsv` `wall_budget_s` for the ticket's `(work_class, difficulty)` + `wall_for_leg` for the actual leg |
| `fleet/benchmark/honest-battery-sweep.sh:45` | `DOGFOOD_LATENCY_BUDGET_S=480` | same |
| `fleet/benchmark/lib/sections.sh:29-40` | `S0=180 / S1=360 / S2=600 / S3=480 / S4=720 / S5=600 / S6=720` | per-section `wall_budget_s` from `budgets.tsv` keyed on the section's `work_class` (`sections.sh:42-53`) |

EVAL-LATENCY-GATE's DETAIN threshold (`elapsed >= LATENCY_BUDGET_S`) consumes
the derived `wall_budget_s` / `wall_for_leg`; EVAL-PIPELINE-CONSOLIDATE's
rungs consume the per-`(work_class, difficulty)` table. This ticket is the
source-of-truth derivation + this design doc; the repoint is the consumers' job
(per the `Feeds EVAL-LATENCY-GATE's DETAIN threshold and EVAL-PIPELINE's rungs`
clause in `fleet/board/EVAL-DERIVED-BUDGETS.md`).

## §5 — Staged-elimination ladder (rungs)

The preflight runs as ESCALATING RUNGS with early-out, NOT one flat 8-min test
(operator ask, folded into MODEL-PREFLIGHT.md):

  R0  leg canary (LEG-PREFLIGHT-CANARY, ~seconds) — reachable + serves-a-working-
      model; dead/degraded legs OUT. This is also the source of the per-leg
      `tok_s` that §LATENCY-BUDGET part (b) normalizes against.
  R1  tier-appropriate, VARIETY of skill areas; screens out weak models.
  R2  broader + harder; screens the mid.
  R3  hardest, only for survivors; LOCATES the ceiling.

Each rung's per-run wall-clock comes from §LATENCY-BUDGET (derived, not the old
3/6/10 min). A rung failure that is leg-fault/throttle (not quality) does NOT
eliminate the model — it parks the leg and retries elsewhere (leg-preflight,
S8 >=1-viable). Elimination is tracked PER (model × skill): a model that PEAKS
in one skill at R2 stops being tested IN THAT SKILL (ceiling found — R3 for
that skill is waste) but still graduates to R3 for the other skills it's still
clearing. The output is a fine-grained per-(model, work_class) CEILING GRADE —
"send refactor to model X, but never routing" — which is exactly what
`assign.py` consumes (`model-scorecard.tsv` is already keyed per work_class).
Feed results to the scorecard/LEG-RANK AS EACH (rung × skill) COMPLETES (faster
data), not only at the end.

## §6 — Relationship to the EVAL-* successors

`fleet/board/MODEL-PREFLIGHT.md` is now the CANDIDATE SLATE + this design-of-
record only; its code surfaces moved to the EVAL-* successors per
MODEL-TESTING-ADVERSARIAL-REVIEW.md §F12:

  - **EVAL-DERIVED-BUDGETS** (this ticket) — §LATENCY-BUDGET derivation + this doc.
  - **EVAL-LATENCY-GATE** — consumes `wall_budget_s` as the DETAIN threshold.
  - **EVAL-TAXONOMY-ALIGN** — the canonical work_class axis §LATENCY-BUDGET keys on.
  - **LEG-PREFLIGHT-CANARY** — R0 + the per-leg `tok_s` §LATENCY-BUDGET part (b) uses.
  - **EVAL-GRADER-PROVISION** — the OOB grader substrate §1 relies on.
  - **EVAL-PIPELINE-CONSOLIDATE** — folds the battery into ONE adaptive pipeline
    whose rungs draw from §LATENCY-BUDGET and whose per-rung budgets come from
    `budget-derive.py`.
