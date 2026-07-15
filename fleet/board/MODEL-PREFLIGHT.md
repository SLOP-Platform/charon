tier: frontier
difficulty: 4
work_class: ci-infra
branch: feat/model-preflight
repo: charon-private
depends_on: BENCH-OOB-GRADING
real-dep: BENCH-OOB-GRADING — preflight grading MUST run out-of-band (bench-grader user, hidden model-unreadable assertions). In-band grading reproduces the S0-S6 invalidity this fixes. True correctness prereq.
owns: fleet/benchmark/preflight.sh, fleet/benchmark/preflight-tasks/, fleet/benchmark/graders/preflight.py
accept: |
  DISCRIMINATING, OUT-OF-BAND-graded battery that screens a candidate model on our real failure modes BEFORE it
  enters tier-models.tsv. Grade = the FUNCTIONAL OUTCOME checked OOB, never the model's word. Design of record:
  fleet/state/PREFLIGHT-DESIGN-V2.md — 14 checks (T1-6 hardened vs gaming vectors + T7-14: refactor, decoys,
  citation-verify, all-or-nothing, fix-don't-delete, secret-hygiene, regression, cost/latency). Validity: N>=3 per
  task, disguised fixtures, deepseek-v4-flash MUST-FAIL control + strong MUST-PASS control (per-task discrimination
  proof). Substrate BUILT (grader-daemon; chunk-0 seam merged). Build chunks: fixtures · graders->$KEYS · runner ·
  discrimination-proof.
  LATENCY-BUDGET (hardens T14 cost/latency — folded 2026-07-15, operator ask):
  (1) DERIVE the budget, don't guess it: state the product per-unit time-budget (max acceptable wall-clock for a
      real work unit in production) in PREFLIGHT-DESIGN-V2.md and set the eval latency budget = that + margin. Today's
      480s is only "headroom over the slowest observed real completion (410s)" — make it a derived number with a
      written rationale, not an arbitrary round figure.
  (2) CONFIRM-would-finish: when a candidate hits the budget with attribution `too-slow` (healthy legs, genuinely
      slow — NOT `provider-throttled`/`pool-exhausted`/rc=124-hang), re-run it ONCE at 2-3x budget out-of-band and
      RECORD whether it WOULD have finished, so the cutoff is validated by data, not assumed. Throttled/leg-fault
      runs are EXCLUDED from the re-test (no point re-running into a dead/capped leg — those are parked, not slow).
  STAGED ELIMINATION LADDER (token-economical preflight — folded 2026-07-15, operator ask): run the battery as
  ESCALATING RUNGS with early-out, NOT one flat 8-min test. Rungs (per tier, difficulty scaled to the tier):
    R0  leg canary (LEG-PREFLIGHT-CANARY, ~seconds) — reachable + serves-a-working-model; dead/degraded legs OUT.
    R1  ~3 min — tier-appropriate, VARIETY of skills (bugfix/routing/refactor mini-tasks); screens out weak models.
    R2  ~5-6 min — broader + harder; screens the mid.
    R3  ~10+ min — hardest, only for survivors; LOCATES the ceiling.
  ELIMINATE at each rung: a candidate advances ONLY if it clears the current rung. A model that PEAKS/plateaus at
  R2 is NOT sent to R3 — we already know its ceiling, so R3's tokens are waste. Record the highest rung cleared as
  the model's grade; feed results to the scorecard/LEG-RANK AS EACH RUNG COMPLETES (faster data), not only at the end.
  Budgets per rung are DERIVED (see LATENCY-BUDGET #1), and a rung failure that is leg-fault/throttle (not quality)
  does NOT eliminate the model — it parks the leg and retries elsewhere ([leg-preflight-canary], S8 >=1-viable).
candidates: |
  Kimi-K2-Thinking, MiniMax-M2, GPT-OSS-120B, Phi-4, Qwen3.6-27B-MTP, Gemma 4 (31B), GLM 4.7 (Thinking),
  Gemini 2.5 Pro (big Python codebases), GPT-5.1-Codex-Max (complex/refactor). ALSO test PAID variants of models we
  run free (free tiers often quantized/degraded) — record free-vs-paid as a distinct axis.
scope: Router Model-Trust — the ENTRY gate for new models. [[charon-bench-grader-substrate]] [[benchmark-not-a-valid-ranker]] [[green-is-not-proof]]
ds: |
  depends_on: BENCH-OOB-GRADING (OOB substrate). Chunk-0 seam merged; fixtures/graders/runner/proof next. Adversarial review.
note: the accurate model test; design V2 folds in the adversarial gap-review. Run the candidate slate once built.
