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
candidates: |
  Kimi-K2-Thinking, MiniMax-M2, GPT-OSS-120B, Phi-4, Qwen3.6-27B-MTP, Gemma 4 (31B), GLM 4.7 (Thinking),
  Gemini 2.5 Pro (big Python codebases), GPT-5.1-Codex-Max (complex/refactor). ALSO test PAID variants of models we
  run free (free tiers often quantized/degraded) — record free-vs-paid as a distinct axis.
scope: Router Model-Trust — the ENTRY gate for new models. [[charon-bench-grader-substrate]] [[benchmark-not-a-valid-ranker]] [[green-is-not-proof]]
ds: |
  depends_on: BENCH-OOB-GRADING (OOB substrate). Chunk-0 seam merged; fixtures/graders/runner/proof next. Adversarial review.
note: the accurate model test; design V2 folds in the adversarial gap-review. Run the candidate slate once built.
