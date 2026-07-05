# TICKET — BENCHMARK-HARNESS: make MODEL-BENCHMARK-SPEC.md runnable + first run

**Type:** build-rig (fleet tooling — NOT product; never touch `src/charon` product code except read-only fixtures)
**Recommended model:** Claude **Opus** (the graders are correctness-critical — a grader that doesn't truly discriminate makes the whole benchmark worthless; this is the exact skill the benchmark itself tests). Build as a Claude sub-session, not a manual opencode droid (a droid building the graders would itself need grading — chicken-and-egg).
**Depends on (both exist):** `fleet/MODEL-BENCHMARK-SPEC.md` (section definitions S0–S5), `fleet/model-scorecard.sh` (ledger; bench-row schema).

## GOAL
Turn the benchmark SPEC into a RUNNABLE, deterministically-graded harness that scores a coding model 0–100 per section and appends `bench` rows to `model-scorecard.tsv`. Then do a first run of **glm-5.2** and **deepseek-v4-pro**.

## DELIVERABLES (all under `fleet/benchmark/`)
1. **Fixtures** — for each section S0–S5 in `MODEL-BENCHMARK-SPEC.md`, a self-contained fixture: a minimal repo state / injected bug / task setup the model works against, plus the "golden" expected outcome. Read the spec for each section's exact task + objective checks. Keep fixtures small.
2. **Deterministic graders** — one grader per section, 0–100, NO LLM-judge. Each must implement the spec's objective checks, e.g.: the model's test FAILS on the buggy fixture and PASSES on the fixed one; `charon gate` passes; only the intended files changed (diff-scoped); the real-path proof (e.g. S2: grader mutates the config and re-runs the model's own test so a dodged/inert feature scores 0). Partial-credit bands per the spec. The grader takes the model's produced worktree/diff and emits a score + reason.
3. **Runner** — `fleet/benchmark/run.sh <model>`: for each section, (a) prepare the fixture in an isolated worktree, (b) present the section's task PROMPT for the model (see model-driving seam below), (c) once the model has produced its attempt, run the grader, (d) `model-scorecard.sh append <date> bench <section> <work_class> <tier> <model> <verdict> <gate> <score> "<note>"`. Print a per-model summary: tier reach = highest section cleared above its class floor.
4. **Model-driving seam** — for now, driving the model is MANUAL (matches the current opencode-tab flow): `run.sh` prints each section's prompt + the fixture worktree path; the operator pastes it into an opencode tab (model selected) pointed at that worktree; `run.sh --grade <section> <model>` then grades what's there. DESIGN this as a clean seam so a future headless opencode/gateway driver can slot in without reworking the graders. Document the manual steps.
5. **First run** — run all 6 sections for **glm-5.2** and **deepseek-v4-pro**, append their `bench` rows, and report the two scorecards. (If full manual driving is impractical in one session, at minimum build+self-test the graders against the golden fixtures — prove each grader gives 100 on the golden-fixed and 0 on the golden-buggy — and leave the model runs as a documented next step.)

## MUST / BOUNDARY
- Graders MUST be self-tested: prove each gives ~100 on the golden-correct solution and low/0 on the inert/buggy one. A grader that can't distinguish them is a bug.
- No product-code edits; fixtures may COPY/read product code but the harness lives in `fleet/benchmark/`. No secrets/keys.
- Deterministic only — re-running a grader on the same worktree gives the same score.

## LAST STEP (REQUIRED) — commit, do not skip
`git add -A && git commit -m "bench(harness): runnable graders + runner for MODEL-BENCHMARK-SPEC S0–S5 (+ grader self-tests)"` then **report the commit SHA**.
Do NOT push. Do NOT merge. (Commit is REQUIRED; pushing/landing is the manager's job.)

## REPORT BACK (short, no dumps)
Files created; per-section grader self-test result (100-on-golden / 0-on-buggy); whether the two model runs happened (+ their scores) or are left as documented next step; commit SHA.
