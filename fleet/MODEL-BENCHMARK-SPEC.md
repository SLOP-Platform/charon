# MODEL-BENCHMARK-SPEC — tiered capability benchmark for fleet coding models

Status: DESIGN (spec only — not built, not run). Owner: fleet manager.
Purpose: a short, graded, **deterministic** test that CALIBRATES which capability tier a
coding model belongs in (glm-5.2, deepseek-v4-pro, etc.) and surfaces **mis-tiered** models:
a cheap model acing a high section → **promote candidate**; an expensive model failing a mid
section → **demote candidate**. Total ~30–70 min of model time across 7 small self-contained
sections (S0–S5 backend + S6 frontend). It is calibration, not a leaderboard vanity metric.
Charon is about to ship a Svelte GUI and we currently have **zero** frontend signal on any
fleet model — S6 exists to close that gap before the GUI work is handed to a droid.

Anchored to the real work classes this project ships so section scores **predict ticket
performance**: `{money-path, routing, ci-infra, refactor, tests, greenfield-feature}` — the same
`work_class` enum the live ledger already uses.

---

## 0. Model-class taxonomy (from MODEL-WORK-MATRIX.md)

| Class | Examples | Expected use |
|---|---|---|
| economy | MiMo V2.5, Step 3.7 Flash | background/classify/cron |
| strong | DeepSeek V4 Flash, GLM 5.2, Qwen 3.6, MiniMax M2.7 | routine→general coding |
| frontier-open | DeepSeek V4 Pro, Kimi K2.6, Hy3 | hard agentic coding, review |
| premium | GPT-5.5, Claude-Opus | gate/consensus only |

"Model-class" is the **prior** (what we paid for / expect). The benchmark produces the
**posterior** (measured tier reach). Divergence = the promote/demote signal.

---

## 1. Sections at a glance

Each section is one self-contained task in a throwaway fixture repo, yields **0–100**, and
targets one difficulty tier. Bottom section is trivial (everyone ~100); each higher section
separates models. Auto-checkable — no LLM-judge in the pass path.

| # | Section | Tier | work_class | Separates | Time |
|---|---|---|---|---|---|
| S0 | Trivial fix | 0 | bugfix | nobody (floor 100 = sanity/harness check) | ~3 min |
| S1 | Localized money-path bugfix + obvious test | 1 | money-path | economy from the rest | ~6 min |
| S2 | Routing correctness proven on the REAL path | 2 | routing | **catches the #6 "dead-path" dodge** | ~10 min |
| S3 | CI-infra: fix broken workflow (YAML + shell) | 2 | ci-infra | strong from frontier-open | ~8 min |
| S4 | Adversarial: find subtle injected bug, write failing test, fix without regression | 3 | refactor + tests | frontier-open from strong | ~12 min |
| S5 | Spec/scoping honesty on an UNDER-specified ticket | 4 | greenfield-feature | honest scoping vs. confident overbuild/hallucination | ~10 min |
| S6 | Frontend: fetch + render a status component from a mocked API | 2–3 | frontend | can the model wire real data into a UI vs. fake/hardcode it | ~12 min |

Gradient: 0 (trivial) → 1 (localized) → 2 (prove-it routing / infra) → 3 (adversarial) →
4 (judgment under ambiguity). S6 is a **parallel axis** (frontend capability), not a rung on
the backend tier ladder — see §4. Total ≈ 61 min budget.

---

## 2. Shared fixture (describe only — do NOT build)

A single small throwaway repo `bench-fixture/` mirroring Charon's shape, seeded per run from a
frozen tag so every model gets identical inputs:

- `gateway/providers.py` — `Provider` dataclass (`name, base_url, cost_class, cost_rank`).
- `gateway/pools.py` — pool selection; ordered failover over providers.
- `gateway/routing.py` — `select_provider(model, pools)` reading a real `models.json`.
- `gateway/normalize.py` — `normalize_request()` / `normalize_response()` (OpenAI-compatible).
- `gateway/failover.py` — `classify_error(status, body) -> RETRY|FAILOVER|FATAL`.
- `models.json` — real config mapping model-id → provider list + `cost_class`/`cost_rank`.
- `tests/` — a passing baseline suite; `pytest -q` green at the seed tag.
- `.github/workflows/ci.yml` — lint+test gate (the "gate" referenced in rubrics).

Each section ships a per-section overlay (a patch that injects the bug / mutates the ticket) and
a **hidden grader** (`grader/sX.py`) the model never sees. The model gets only the prompt + repo
state. Runs are diff-scoped: the grader records `git diff --stat` and rejects out-of-scope edits.

---

## 3. Sections (prompt · setup · checks · rubric)

### S0 — Trivial fix · Tier 0 · work_class=bugfix
**Prompt (hand to model):** "`Provider.cost_class` has an enum value misspelled `'chearp'`; it
should be `'cheap'`. Fix it. Change nothing else."
**Setup:** overlay introduces the typo in `providers.py` and one referencing test asserting
`'cheap'` (currently failing).
**Objective checks:** (a) `pytest -q` green; (b) `git diff` touches only `providers.py`;
(c) no other token changed.
**Rubric (0–100):** 100 = a+b+c. 60 = tests pass but stray edits (b fails). 0 = tests red.
**Floor:** economy 100, strong 100, frontier 100. *Any model <100 here = harness/model-plumbing
problem, not capability — investigate before trusting the rest of the run.*

### S1 — Localized money-path bugfix + obvious test · Tier 1 · work_class=money-path
**Prompt:** "`cheapest_provider(providers)` is meant to return the provider with the lowest
`cost_rank`. It currently returns the **last** provider in the list. Fix it and add a test that
would have caught the bug."
**Setup:** overlay replaces the min-selection with `providers[-1]`; existing tests happen to pass
because the fixture list is pre-sorted (the trap: a lazy fix leaves the test blind).
**Objective checks:** (a) fixed `cheapest_provider` returns true min on an **unsorted** input;
(b) the model's new test **fails on the buggy code, passes on the fixed code** (grader applies
the test to both trees); (c) diff scoped to `providers.py` + a test file.
**Rubric:** 100 = a+b+c. 70 = a+c but test doesn't distinguish buggy vs fixed (b fails). 40 =
code fixed, no test. 0 = still returns wrong provider.
**Floor:** economy 70, strong 100, frontier 100.

### S2 — Routing correctness proven on the REAL path · Tier 2 · work_class=routing
> This section exists to catch **exactly the ticket-#6 failure**: glm-5.2 wrote a feature whose
> tests dodged the real `models.json` path, so a dead feature looked done
> (ledger note: *"feature inert; tests dodged models.json path"*).

**Prompt:** "Add cost-aware ordering: `select_provider()` must return candidate providers sorted
by ascending `cost_rank` as declared **in `models.json`**. Prove it with a test that exercises
the real config-loading path end-to-end."
**Setup:** `models.json` lists a model whose providers are declared **out of cost order**.
`select_provider()` currently returns config order. A monkeypatch/stub shortcut exists that a
lazy solution can use to fake the result without loading `models.json`.
**Objective checks (grader, deterministic):**
- (a) FUNCTIONAL: with the real `models.json`, `select_provider()` returns providers in
  ascending `cost_rank`.
- (b) **REAL-PATH PROOF (the anti-dodge gate):** grader mutates `models.json` (swaps two
  `cost_rank` values) and re-runs BOTH (i) the FUNCTIONAL snippet, requiring `select_provider()`'s
  *returned order itself* to track the new data (proves the CODE reads the file — this is the
  proof that actually gates the score; a code that fails it lands in BLOCK regardless of what the
  test does), and (ii) **the model's own test**, which MUST now fail (proves the TEST reads the
  file). Checking only (ii), as an earlier version of this grader did, is gameable: a hardcoded
  `select_provider()` paired with an honest test that computes its expected value from the file
  can still make the test fail after mutation (its *expected* value moved, not its subject), even
  though the code never touched `models.json`. (i) closes that vector.
- (c) The model's test does not stub/monkeypatch `models.json` loading (grader greps the test
  for the loader symbol being patched → auto-fail if patched).
- (d) diff scoped to `routing.py` + test.
**Rubric:** 100 = a+b(code)+b(test)+c+d. **20 = a passes but b(code) fails —
`select_provider()` itself doesn't track the mutated data (hardcoded/inert); the critical #6
signature, scored BELOW the test-dodge case below regardless of what the test does — this is
the fix that closes the "hardcoded code + honest test" gaming vector.** 50/40 = a+b(code) pass
but b(test) fails — code is honest and data-driven, but the model's own test still passes after
mutation (dodged at the test level); 50 in-scope, 40 if scope also violated. 25 = test present
but c fails (mocked the path), or no test was written at all. 0 = wrong order.
**Floor:** economy 50, strong 100, frontier 100. *A `strong`/`frontier` model scoring 50 here is
the single most predictive demotion signal for real coding tickets.*

### S3 — CI-infra: fix broken workflow · Tier 2 · work_class=ci-infra
**Prompt:** "CI is red. `.github/workflows/ci.yml` and `scripts/smoke.sh` are broken. Make the
gate green without weakening what it checks."
**Setup:** overlay injects three defects: (1) YAML indentation error under `steps:`;
(2) shell bug — pipeline masks failure because `set -o pipefail` is missing (a curl-through-grep
returns 0 on failure); (3) a hardcoded host port that collides. All three are real bugs pulled
from this repo's own CI history (HANDOFF-PIPEFAIL, RELEASE-SMOKE-FIX, TEST-PORT-FLAKE).
**Objective checks:** (a) `yamllint`/`actionlint` clean; (b) `bash -n scripts/smoke.sh` clean and
`set -o pipefail` present; (c) grader runs the smoke script against a **stubbed failing** endpoint
and it must exit non-zero (proves the masking bug is fixed, not just deleted); (d) no assertion
removed (grader diffs the check count).
**Rubric:** 100 = all four. 75 = 3 defects fixed. 50 = 2. 25 = 1. 0 = still red or gate weakened
(any check deleted → cap at 25 regardless).
**Floor:** economy 25, strong 75, frontier 100.

### S4 — Adversarial: find subtle bug, write failing test, fix without regression · Tier 3 · work_class=refactor+tests
**Prompt:** "`normalize_response()` has a subtle bug that corrupts a minority of responses. Find
it, write a test that fails on the current code and passes once fixed, then fix it. All existing
tests must stay green."
**Setup:** overlay injects a **subtle** normalizer bug modeled on the real silent-downgrade defect
— a namespaced model-id (`deepseek/fireworks/…`) is split with `split('/')[0]` instead of
`rsplit('/',1)[-1]`, so only namespaced ids are mishandled; the common non-namespaced case passes,
so the baseline suite stays green and the bug hides in the minority path.
**Objective checks:** (a) the model's new test **fails on the injected code, passes on the
reference fix** (grader runs it against both); (b) the injected-bug input class (namespaced id) is
the one exercised (grader checks the test input contains a `/`-namespaced id); (c) after the
model's fix the **entire baseline suite is still green** (no regression); (d) diff scoped to
`normalize.py` + test.
**Rubric:** 100 = a+b+c+d. 70 = correct fix + green suite but test doesn't isolate the namespaced
path (b weak). 40 = found & fixed, no discriminating test. 20 = wrote a test but never located the
bug (test doesn't fail on injected code). 0 = broke the baseline suite or wrong fix.
**Floor:** economy 20, strong 40, frontier 100. *Finding a subtle minority-path bug + proving it is
the frontier-open discriminator.*

### S5 — Spec/scoping honesty on an UNDER-specified ticket · Tier 4 · work_class=greenfield-feature
**Prompt (deliberately under-specified):** "Add a 'fallback tier' so exhausted providers fail over
to a cheaper pool. Implement it." *(The ticket omits: what 'exhausted' means, whether tiers are
per-model or global, free-vs-paid ordering, and where config lives. There is NO single correct
implementation.)*
**Setup:** the fixture intentionally lacks a tier config schema and any precedent. The **correct
behavior is to scope, flag ambiguity, and ask/propose — not to confidently overbuild.** Grader is
a deterministic checklist over the model's written response + diff (keyword/structure match, not
subjective judgement).
**Objective checks (checklist, each pass/fail):**
- (a) Names ≥3 of the 4 material ambiguities (grader keyword-matches: exhausted-definition,
  per-model-vs-global, free/paid ordering, config location).
- (b) Does NOT invent unrequested config keys/files as if specified (grader flags any **new**
  config schema written without a "proposed/assumption" hedge → hallucinated-requirement penalty).
- (c) Delivers a **minimal, clearly-labeled** proposal or a thin scaffold behind stated
  assumptions — not a sprawling implementation across >2 files.
- (d) Explicitly defers or asks before committing to the ambiguous decisions.
**Rubric:** 100 = a+b+c+d (honest scoping). 60 = flags some ambiguity but partially overbuilds.
30 = builds a plausible feature but silently invents requirements (b fails). **0 = confident full
implementation with hallucinated spec (worst outcome — actively harmful on real tickets).**
**Floor:** economy 30, strong 60, frontier 100. *Note the inversion: here a bigger diff is often a
WORSE score. This section rewards restraint, which cheap models rarely fake.*

### S6 — Frontend: fetch + render a status component from a mocked API · Tier 2–3 · work_class=frontend
> Charon is about to ship a Svelte GUI and no fleet model has been scored on frontend work.
> This section is the frontend analogue of S2 (routing): it isn't enough for the UI to *look*
> right on the sample data — the grader proves the component actually reads the response rather
> than faking/hardcoding it, the same "anti-dodge" pattern as the #6 real-path proof.

**Fixture (separate small throwaway repo `bench-fixture-fe/`, NOT the backend fixture):**
- `index.html` — a bare mount point: `<div id="app"></div>` and a script tag loading the build
  output.
- `fixtures/status.json` — a mocked `GET /charon/status` response: a JSON array of 3 provider
  rows, each `{ "name": string, "cost_class": "cheap"|"strong"|"premium", "status":
  "ok"|"degraded"|"down" }`.
- A preconfigured build toolchain (`package.json` + `vite.config.js`) with a Svelte template
  already wired (`npm run build` → `dist/bundle.js`), so the model is not scored on tooling setup.
- `tests/` is intentionally empty — the model does not write the grader-facing test here; the
  hidden grader supplies its own harness (below).

**Prompt (hand to model):** "Given the shape of `GET /charon/status` (see `fixtures/status.json`
for an example response) and the bare mount point in `index.html`, build a small component that
fetches `/charon/status` on load and renders one row per provider into `#app`. Each row must be
a `[data-testid="provider-row"]` element containing `[data-testid="name"]`,
`[data-testid="cost_class"]`, and `[data-testid="status"]` with the corresponding field text.
Prefer Svelte (the project template is already set up for it). **If you cannot get a working
Svelte build, plain vanilla JS with no framework is an acceptable fallback** — either way it
must build via the provided `npm run build` and the rendered output must satisfy the
`data-testid` contract above. Change only the component/app source; do not touch
`fixtures/`, the grader, or the build config."

**Objective checks (grader, deterministic, no LLM-judge):**
- (a) **BUILD:** `npm run build` exits 0 and produces `dist/bundle.js` (or the configured output
  path — grader reads `package.json`'s `build` script output, it doesn't hardcode a bundler).
- (b) **RENDER:** grader loads the built bundle in a headless DOM (jsdom), stubs `global.fetch`
  to resolve with `fixtures/status.json`, drives the mount (page load / `DOMContentLoaded`), and
  asserts `#app` contains exactly 3 `[data-testid="provider-row"]` nodes whose
  name/cost_class/status text matches the fixture — pure DOM assertions, no visual/screenshot
  judging.
- (c) **REAL-DATA PROOF (the anti-dodge gate, S2's frontend twin):** grader swaps in a
  **mutated** fixture (different row count and values) and re-runs the same DOM harness. Output
  MUST change to match the new fixture. A component that still renders the original 3 rows
  proves it hardcoded/memorized the sample data instead of wiring the fetch response →
  **feature-inert, section fails hard.**
- (d) **SCOPE:** `git diff --stat` touches only the component/app source (+ generated `dist/`);
  no edits to `fixtures/status.json`, the grader, or build config (grader diffs the file list).
**Rubric (0–100):** 100 = a+b+c+d. 40 = a+b+d but c fails (renders correctly once, doesn't react
to changed data — hardcoded/static; the frontend twin of S2's #6 signature: the feature LOOKS
done but is fake). 40 = a only (builds, but rendered DOM doesn't satisfy the `data-testid`
contract or fetch wiring is broken). **A dodge that fakes doneness must never score above an
honest failure** — hardcoded/static therefore lands in the same BLOCK band as "a only" (both
< 50), never the 75/FIXES a naive "renders once" credit would suggest. 0 = build fails, or scope
violated (cap at 25 regardless of a/b/c if the model edited the fixture/grader to cheat).
**Floor:** economy 25, strong 60, frontier 90. *A ≥90 score is treated as tier-3-caliber frontend
work (real-data proof + clean scope); 60–89 is tier-2 (usable but not yet trusted unsupervised on
GUI tickets).*
**Fallback note (explicit ambiguity call):** the grader is framework-agnostic by construction —
it never inspects source, only the built bundle's DOM behavior in jsdom — so a vanilla-JS
solution that passes (a)–(d) scores identically to a Svelte solution. Svelte is preferred only
because it's what the real GUI will use, not because the grader rewards it.

---

## 4. Aggregate & tiering rule

- **Section scores are NOT summed.** Tier reach = the **highest tier at which the model clears the
  section floor for its class** with no lower section failing. (Monotonic: can't claim Tier 3 while
  flunking Tier 1.)
- **Measured tier** = highest cleared tier. **Promote candidate:** measured tier ≥ prior class tier
  AND cost is low (cheap model clears a high section). **Demote candidate:** measured tier < prior
  class tier (expensive model fails a mid section — e.g. strong model scoring 50 on S2).
- S0 is a **sanity gate**, not a discriminator: <100 invalidates the run.
- **S6 is a parallel axis, not part of the backend tier ladder.** It scores frontend capability
  independently and is reported alongside — not folded into — the S0–S5 tier reach, since a
  model's backend routing/refactor tier does not predict its frontend tier (and vice versa;
  we have zero prior data here). A model can be e.g. "backend tier 3 / frontend tier 2."

---

## 5. Ledger mapping (writes the SAME store as live reviews)

A benchmark run appends `bench` rows to `fleet/state/model-scorecard.tsv` — identical schema to
live-review rows, so tiering reads one store:

```
date        source  ref   work_class          tier  model          verdict  gate  score  time_s  cost_usd  corrections  note
2026-07-05  bench   S2    routing             2     glm-5.2        FIXES    pass  50     612     0.0084    2            real-path proof failed; test dodged models.json (#6 signature)
2026-07-05  bench   S4    refactor            3     deepseek-v4-pro MERGE   pass  100    701     0.0119    1            isolated namespaced-id bug; test discriminates; suite green
2026-07-05  bench   S6    frontend            2     glm-5.2        BLOCK    pass  40     540     0.0071    3            builds+renders but static; failed mutated-fixture real-data proof (BLOCK, not FIXES - dodge scores below honest work)
```

Column mapping:
- `date` = run date; `source` = **`bench`** (live reviews use `live`).
- `ref` = section id (`S0`..`S6`).
- `work_class` = the section's class, from the existing enum
  `{money-path,routing,ci-infra,refactor,tests,greenfield-feature,bugfix,docs,frontend}` —
  **`frontend` added for S6.**
- `tier` = section tier `0..4`. For S6 (spec range "2–3"), the row's `tier` field carries the
  **band actually reached** (2 for a 60–89 score, 3 for a ≥90 score) — the TSV column stays a
  single int like every other row; the 2–3 range in §1/§3 describes the section's spread, not a
  literal cell value.
- `model` = model id under test.
- `verdict` = **derived from score** (deterministic, no judge): `score≥90 → MERGE`,
  `50–89 → FIXES`, `<50 → BLOCK`. Mirrors how live reviews land a verdict.
- `gate` = `pass|fail` from the section's gate check (pytest/actionlint/smoke); `-` if section has
  no gate.
- `score` = the 0–100 rubric score (live rows carry `-` here; bench rows always carry a number).
- `time_s`, `cost_usd`, `corrections` = the **efficiency triple** — see §5a. Live rows carry `-`
  for all three unless a future live-review flow starts capturing them too.
- `note` = one line, no tabs.

One row per (model, section). A full calibration run = 7 rows/model (S0–S6).

---

## 5a. Efficiency metrics — capture, cap, and effect on score

Score alone answers "did it clear the bar." The efficiency triple answers "how much did clearing
it cost" — a model that ties on score but takes 3x longer, 3x the corrections, or 3x the tokens
is a *worse* tiering candidate even at equal score. **All three are AUTO-captured by the runner —
never hand-entered.** A human does not time a stopwatch or eyeball a token count; if a value can't
be captured automatically for a given run, the cell is `-`, not a guess.

- **`time_s`** — wall-clock seconds for the section, measured by the runner itself (start
  timestamp when the fixture/prompt is handed to the model, end timestamp when the model's
  attempt is ready for grading). This is **free** — the runner already brackets each section to
  enforce the per-section time-box (see TICKET-BENCHMARK-HARNESS.md §5 "Fast-to-run"), so
  `time_s` is just that same clock's elapsed value, recorded rather than discarded. No
  self-reporting by the model.
- **`corrections`** — count of correction/iteration rounds the model needed within the section:
  each time the model's attempt fails a checkable gate (tests red, build fails, grader partial
  check fails) and the model is given another pass to fix it before the section's final grade,
  that's one correction round. The runner counts these as they happen (it already knows when it
  re-prompts after a failed intermediate check); this is not a subjective judgment call.
  **CAP: 3 correction rounds per section.** A run that needs a 4th round is cut off — the section
  is graded on whatever state exists at the cap, `corrections` is recorded as the literal count
  (may report `3+` if the cap forced a stop before convergence), and the **rubric score is capped
  at the section's "partial credit" band** for that section (i.e. the run cannot land in the
  section's top band once it has blown the correction cap, even if the final diff would otherwise
  qualify) — repeated flailing to a correct answer is not equivalent to reaching it directly, and
  an uncapped model could otherwise game score by brute-force retrying. This also prevents an
  unresponsive/looping model from hanging a many-models run indefinitely, same rationale as the
  wall-clock time-box.
- **`cost_usd`** — attributed from the gateway's own per-request cost tracking (SR-5b already
  computes `cost_usd` per request at the proxy). **Best-effort:** populated only when the section
  is driven through a flow that can attribute gateway usage back to this specific benchmark call
  (e.g. a headless driver hitting the gateway directly, or a manual opencode-tab run configured to
  tag/attribute its requests to the section). When the driving flow can't make that attribution
  (e.g. an ungated manual paste with no request tagging), the cell is `-` — never estimated or
  backfilled with a guess. No new cost-accounting logic is invented here; this column only
  surfaces a number the gateway is already computing.

Aggregate reads (`model-scorecard.sh render`) report the **mean** of each efficiency column per
model across rows where that column has data, alongside the existing merge/block and bench-score
pivots — so the scorecard is genuinely multi-axis: score tells you *if* a model clears the bar,
the efficiency triple tells you *how expensively*.

---

## 6. How to run + how it feeds tiering

**Benchmark = initial tier calibration (point-in-time).** Run once when onboarding a new model or
after a provider swaps the weights behind a name. Seed fixture from the frozen tag, hand each
section's prompt to the model in a clean worktree, run the hidden grader, append 7 `bench` rows.
Budget-gate it: premium models run only on demand.

**Live ledger = ongoing per-class drift monitoring.** Every reviewed real ticket already appends a
`live` row (`source=live`, `score=-`, verdict from the human/adversarial review). Over time,
per-`(model,work_class)` verdict trends demote a model that passed calibration but rots in
production — self-correcting, no re-benchmark needed.

**Both write the same TSV**, so the tiering read is one query: for each model, take the `bench`
rows as the **prior tier** and the rolling `live` verdicts per work_class as the **posterior
correction**. Benchmark sets the starting tier; the live ledger moves it. Divergence between a
model's `bench` score on a work_class and its `live` verdict trend on that same class is the
highest-signal re-tiering trigger.
