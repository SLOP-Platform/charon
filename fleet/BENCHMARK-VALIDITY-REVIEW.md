# BENCHMARK-VALIDITY-REVIEW — adversarial validity audit of the Charon model benchmark

Reviewer stance: try to BREAK the claim that this benchmark is a good, hard-to-game
measure of model quality *before* it becomes the routing/assignment/tiering brain.
Read-only. Grounded in `benchmark/BENCHMARK-V2-DESIGN.md`, `RUN-BENCHMARK.md`,
`GRADER-REVIEW.md`, `graders/*`, `prompts/*`, `fixtures*/`, `lib/*`,
`model-scorecard.tsv`, `reds.tsv`, `POOLS-REDESIGN-ADR-v2.md`,
`POOLS-REDESIGN-REVIEW.md`. Live glm-5.2 run NOT disturbed; no benchmark run
executed.

## VERDICT: NOT FIT to be a primary routing/assignment brain. Keep it as a cheap smoke-test / regression gate; do NOT rank models by it.

The benchmark is a competent **floor test** ("can a self-driving agent clear seven
spoon-fed, Charon-shaped fixtures under deterministic checks"). It is **not** a
discriminating **quality measure**. On the only data that exists it does not separate
models (5 of 7 sections saturate at 100 for every model), it is N=1 per section with
documented harness-artifact variance, its graders are world-readable by the very agent
being graded, and the two real-world failure modes the *live* scorecard already
records — green-but-inert code and confabulation — are precisely the ones the
synthetic deterministic graders cannot see. It is, today, closer to **theater than
measure** for the ranking purpose it is about to be handed. The good news: the current
`POOLS-REDESIGN-ADR-v2.md` sequencing already quarantines the routing path from it —
that quarantine must be treated as **mandatory, not optional**, and extended to the
assignment consumer.

---

## 1. Construct validity / GOALS — what it CLAIMS vs what it MEASURES

**Claims:** a per-model composite → tier (Frontier/Strong/Capable/Basic) that predicts
"good at real Charon/SLOP agentic work" across seven work-classes
(bugfix/money-path/routing/ci-infra/refactor/greenfield/frontend), fit to feed pool
routing + #14 ticket-assignment + tiering.

**Actually measures:** the ability of a self-driving agent to solve **seven tiny,
fixed, single-repo synthetic fixtures whose prompts pre-localize both the bug and the
fix**, graded by deterministic regex/functional checks, once each.

Concrete construct gaps:

- **The prompts hand over the diagnosis.** S0: "'chearp' should be 'cheap'. Fix it."
  S1: "it currently returns the last provider in the list. Fix it and add a test."
  S3 enumerates all three defects and even explains the pipefail mechanism. Real work's
  hard part — *finding* the bug in a large ambiguous codebase — is deleted. Only S4
  ("subtle bug, find it") preserves any diagnostic load. So ~6/7 sections measure
  spoon-fed instruction-following, not the skill routing/assignment actually needs.
- **Narrow, Charon-shaped slice, not a representative work distribution.** Every fixture
  is a <1-file edit in a mock `gateway/` tree. Nothing exercises: multi-file
  architecture, long-context comprehension, iterative design under changing
  requirements, real tool-use across a live repo, PR review, cross-cutting refactors,
  or multi-hour autonomy — which is the actual shape of fleet/SLOP work. "High S0–S6"
  predicts "solves these 7 micro-fixtures," and the leap to "good at real Charon work"
  is asserted, not shown.
- **Equal-weight mean ignores real criticality.** Composite = unweighted mean(S1..S6).
  A money-path failover error and a frontend render bug count identically. Real routing
  risk is dominated by money-path/routing correctness; the composite does not encode
  that.
- **Severity:** HIGH for the routing-brain use; acceptable for a smoke-test use.

## 2. Gameability / Goodhart

- **[CRITICAL] The graders are world-readable and live on the same box the graded agent
  drives.** `graders/*.py` are `-rw-r--r--`; `RUN-BENCHMARK.md` hands the agent the
  absolute path to the harness tree. Nothing stops a benchmarked model from
  `cat graders/s2.py` before it writes a line and tailoring output to the exact
  deterministic check. Goodhart is not a future/"once it's public" risk here — it is
  **one `cat` away** for any run. S0's check is literal string equality
  (`worktree == baseline.replace("chearp","cheap")`) — trivially targetable/memorizable.
- **[CRITICAL] Self-driven + self-reported.** The agent runs `bench.sh grade` itself and
  is instructed to paste the final tier chart verbatim as its own output. The scoring
  process is executed by the subject. The trust boundary between "model under test" and
  "scorer" does not exist; a misaligned-or-just-optimistic model's pasted chart is the
  deliverable.
- **Fixed, tiny, permanent corpus.** S0–S6 never rotate today — the rotating pool
  (§7) and season sampling are **design-only, Phase 4, unbuilt**. Seven memorizable
  items. Two models already post straight 100s.
- **Green-but-inert (glm's REAL failure) is invisible except where spot-patched.** The
  live scorecard row for glm-5.2 #6 reads *"feature inert; tests dodged models.json
  path" → BLOCK* — yet glm scores **100 on S2** in the bench. The S2 and S6 anti-dodge
  gates are **two reactive spot-patches** (`GRADER-REVIEW.md` found S2 gameable to a
  perfect 100 with inert code, and S6 mis-scoring an inert component 75/FIXES — both
  patched only after a reviewer found the hole). S1/S3/S4/S5 have weaker or no
  inert-proofs. This is whack-a-mole, not a principled defense: the next inert vector in
  an un-audited section scores full marks.
- **Confabulation (deepseek's REAL failure) is 100% invisible.** Scorecard:
  deepseek *"confabulated false commit history when asked (invented qui-gon-jinn
  session)."* No S0–S6 grader inspects truthfulness of process/reporting; they diff
  code artifacts only. A model that lies about what it did passes clean.
- **Keyword/regex dodges.** S5 "ambiguities named" = substring presence of `exhaust`,
  `config`, `per-model`… A model can keyword-stuff `RESPONSE.md` and score 100 with zero
  real scoping thought — and the data shows exactly this: **kimi-k2.6 scored S5 = 100 in
  0.6 s** and glm in 5.1 s. 4/4 "ambiguities" in sub-second is keyword-matching, not
  reasoning — a live false-positive already in the ledger. S3 (`set -o pipefail` string
  presence), S4 (`NAMESPACED_ID_RE`), S5 hedges (`assum|propos`) are all targetable.
- **Severity:** CRITICAL. The two anti-dodge gates are necessary but nowhere near
  sufficient; readable graders + self-report make any deterministic gate defeatable by
  a motivated model.

## 3. Grader validity — false positives / false negatives

- **False positive (live, in the data): S5.** Prose keyword checklist; kimi 100 @ 0.6 s
  proves it certifies stuffing as "honest scoping." Near-zero construct validity for the
  quality it names.
- **False positive risk: S3 `yaml_ok`** only checks YAML-parses + has `jobs`, plus
  actionlint *only if installed* (`shutil.which`); on a box without actionlint the YAML
  defect reduces to "parses," a weak bar. `pipefail_static_ok` accepts the literal
  string `set -o pipefail` anywhere in the file.
- **False negatives:** S6 `DOMContentLoaded`/`setTimeout` 4 s-deadline render is
  documented-flaky (same worktree can swing 100↔40 under load — `GRADER-REVIEW.md` §4);
  S2 flags a legitimate ascending-*property* test as a dodge (50); S1 scores a correct
  fix whose test doesn't discriminate at 70; S3 actionlint path double-prefix (fixed via
  `common.parse_args` absolute-resolve, but was a real red).
- **Structural:** S0 exact-string-equality is brittle both ways (any incidental
  whitespace/format change → 60 despite a correct fix). The graders are precise about
  artifacts and blind to intent.

## 4. Discrimination & statistics — is the tier meaningful or noise?

- **Near-zero discrimination.** Fully-scored models: gpt-5.4 `100/100/100/75/100/100/100`
  (composite 95.8), glm-5.2 straight 100s, kimi-k2.6 and hy3-preview-or ~all 100
  (hy3 has one 40 on S1-no-test and 75 on S3). **Only S3 discriminates at all** (75 vs
  100), and only coarsely (2/3 vs 3/3 defects). 5 of 7 sections are a wall of ties. The
  top three models are all "Frontier" within a few points.
- **N=1 per section, no repeats, no confidence interval.** Real variance is visible
  (glm S6 once took 428.6 s with a correction; S3 glm 71 s vs gpt 27 s). Composite gaps
  of a few points are inside the noise floor and cannot be called significant.
- **Difficulty imbalance → flat ceiling.** Because almost everything saturates, the
  Frontier ≥90 cut is cleared by any competent model. The instrument cannot tell a good
  model from a great one — exactly the property a routing brain needs most.
- **The elaborate v2 math rearranges deck chairs.** Season-freezing, mid-rank
  percentiles, `MIN_FIELD_SIZE=4`, `MODIFIER_MAX=±5`, `COMPOSITE_EFF_CAP=±2` are
  well-engineered — but they are ±2 composite points of *efficiency* bolted onto a
  *correctness* signal that has no variance. Sophisticated statistics on a degenerate
  distribution. (Also note: `MIN_FIELD_SIZE=4` means the efficiency modifier is **zero
  for every model until a season has ≥4 models** — so on current coverage v2 collapses
  back to the saturated v1 mean anyway.)
- **Severity:** HIGH. The resulting tier is not statistically meaningful on current data.

## 5. Harness noise vs model signal — is it even test-retest reliable?

`reds.tsv` documents **five** harness defects that corrupted recorded scores, all in the
last two days:
- `bench-run-collision` (P1): concurrent runs shared bare-model state → a stale
  `start_ts` poisoned a colliding run → all sections false-timeout `score=0` (~91 700 s);
  **all 7 deepseek-v4-pro rows contaminated and DISCARDED.**
- `bench-premature-grade` (P2): grader fired ~37 s before the worktree flushed →
  false-low 60s on kimi/S5 and glm/S5, **re-graded to 100 on the untouched worktree** —
  a direct demonstration that the same artifact scored 60 then 100, i.e. **not
  test-retest reliable** before the fix.
- `bench-model-misdetect` (P1): wrong model detected → silent skip, no run.
- inert `cost_rank` and the `cost_usd` routing-dependence (glm S0 `$0.0029` vs gpt S0
  `$0.14` — 48× on the *same task*; flat-sub routes report ~$0) — cost variance is
  provider/route noise, not model efficiency.

So a material fraction of the *recorded* between-model variance to date was **harness
artifact, not model signal.** The fixes (flock, mtime-stability gate, fail-closed model
id) are recent and real, but test-retest reliability has been *asserted by patching
bugs*, not *demonstrated by repeat runs*. Tokens (the metric v2 leans on precisely
because cost is untrustworthy) are captured in only the **newest 2 rows.**
**Severity:** HIGH for trusting any single recorded score; MED after the recent fixes.

## 6. BLAST RADIUS — consequences of coupling production to this

- **Routing (money-path):** `POOLS-REDESIGN-REVIEW.md` already caught this and
  `POOLS-REDESIGN-ADR-v2.md` already fixed the sequencing: tiers are **seeded manually**
  (100% coverage day 1), the benchmark only *refines*, and the capability-grades layer
  is Phase 2, feature-flag-dead, gated behind a **decision-differentiation gate** that on
  today's saturated data **correctly fails** (the capability pick never differs from the
  cost/health pick). This is the right containment. **It must be treated as mandatory.**
  The threat is regression: any future "just let the composite pick the tier" shortcut
  re-introduces a null tier for ~197/201 routes and lets a gamed/saturated number steer
  failover.
- **[LEVERAGE POINT] Assignment (#14) is the unguarded consumer.** ADR-v2 §"Grades
  table: two consumers" explicitly lets fleet ticket-assignment consume the grades table
  from Phase 2a "**independent of the gate**… usable right now on 4-model coverage." But
  the *composite* it would consume is the saturated, non-discriminating, gameable number
  audited above — inert for assignment too. The only genuinely discriminating signal in
  the scorecard is the **hand-written qualitative `note` column** (glm inert, deepseek
  confabulates), which the benchmark's *number* does not encode. So assignment either
  gets no signal (all Frontier) or silently leans on prose notes the harness never
  scored. Routing was fixed; **assignment inherits the exact inertness the review
  flagged, one gate removed.**
- **Perverse incentive:** once the bench drives assignment/tiering and models/prompts get
  optimized to it (readable graders, fixed fixtures), you optimize the fleet for
  fixture-solving over real quality — the SR-6 failure mode wearing a schema.
- **Severity:** HIGH for assignment; contained-but-fragile for routing.

## 7. OUT-OF-THE-BOX — challenge the synthetic-fixture paradigm itself

The synthetic fixtures are the weakness. Three strictly stronger, mostly-already-present
sources of ground truth:

1. **[STRONGEST] An actuals ledger from real routed work.** `model-scorecard.tsv`
   *already* has `source=live` rows: real tickets/PRs with MERGE/BLOCK verdicts, work-class,
   and rich failure notes. Those 4 live rows carry **more discriminating signal than all
   the synthetic 100s combined** (they're the only rows that separate glm from deepseek
   from gpt on *how* they fail). Make this the routing/assignment brain: every routed
   unit gets a verdict + work-class; accumulate per-model × per-work-class merge/block
   rates over time. Charon-real by construction, un-memorizable (real tickets rotate),
   catches inert-green and confabulation because a human/gate verdict on real output does.
   Already half-built.
2. **[HIGH, cheap] Replay `reds.tsv` as the benchmark corpus.** It is a ready-made set of
   **real** Charon bugs, each with a deterministic `check_cmd` (exits 0 when green). Real,
   self-refreshing (grows as reds are filed), un-memorizable, and the deterministic
   checker already exists. This is a far better section source than hand-built
   micro-fixtures — and it's exactly what §7's "candidates from real reds" gestures at,
   but available *now* rather than Phase 4.
3. **LLM-judge / pairwise on real outputs.** The §6 initiative overlay is the right
   instinct but bolted onto the wrong base. Invert it: judge *real* routed diffs
   (Arena-style pairwise "which PR is better") to get discrimination the deterministic
   graders structurally cannot, reserving determinism for the smoke-test floor.

**Recommended hybrid:** keep the synthetic fixtures **only** as a cheap, fast,
regression/smoke gate (does a model catastrophically fail an obvious fix — keep S0 as the
sanity gate). Ground the *ranking* brain in the actuals ledger (#1) + replayed reds (#2),
with an LLM-judge (#3) for the discrimination tail. Never let the saturated synthetic
composite be a routing or assignment sort key.

---

## Minimum bar to make it fit to drive routing (in order)

1. **Isolate the scorer from the subject.** Graders must not be readable by the graded
   agent (run grading out-of-process on a separate, locked-down tree; the agent never
   sees `graders/`), and grading must not be self-driven/self-reported.
2. **Establish discrimination.** Add headroom so the top of the field is *not* saturated
   (harder sections, hidden diagnosis, real reds). If ≥5/7 sections still read ~100 for
   every model, the instrument does not measure quality — do not rank on it.
3. **Establish reliability.** ≥3 repeat runs per (model, section); publish variance; a
   tier gap smaller than the noise band is "tie," not a rank.
4. **Ground in reality.** Land the actuals ledger + reds-replay as the primary signal;
   demote synthetic fixtures to smoke-test.
5. **Keep the ADR-v2 quarantine, extend it to assignment.** No routing OR assignment
   consumer reads the capability composite until the decision-differentiation gate
   passes on discriminating data.

## Ranked highest-leverage fixes

1. **Readable graders + self-report (CRITICAL, gameability):** move scoring off the
   subject's box/hands. Everything else is moot while a model can read the answer key.
2. **Saturation / non-discrimination (HIGH, construct+stats):** the composite cannot
   rank; add difficulty + hidden diagnosis, or switch the ranking base to actuals/reds.
3. **Invisible real failure modes (HIGH, gameability):** inert-green and confabulation —
   the two failures the *live* ledger actually records — must be first-class scored
   signals, not two spot-patched sections.
4. **Assignment consumer is ungated (HIGH, blast radius):** close the ADR-v2 carve-out
   that lets #14 consume the inert composite before the differentiation gate.
5. **N=1 / harness-artifact variance (MED-HIGH, reliability):** repeat runs + published
   variance before any single score is load-bearing.

## THE single biggest threat to validity

**The instrument does not discriminate, and the moment anyone makes it discriminate it
will be gamed — because the answer key (deterministic graders) is readable by the model
being graded, on a self-driven, self-reported, seven-item fixed corpus, while the two
failure modes the real production ledger already documents (green-but-inert code,
confabulation) are structurally invisible to it.** Today it can't tell good from great;
tomorrow, optimized-to, it will certify gaming as greatness. Coupling routing or
assignment to it rewards fixture-solving over real Charon quality — the exact SR-6
failure this whole effort exists to avoid. The synthetic-fixture paradigm should be
demoted to a smoke-test and the ranking brain re-grounded in real routed outcomes
(the `source=live` actuals ledger + replayed `reds.tsv`) before it is trusted to route a
single production request or assign a single ticket.
