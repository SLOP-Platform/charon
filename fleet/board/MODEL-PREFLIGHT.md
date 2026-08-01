tier: frontier
priority: 2
difficulty: 4
work_class: ci-infra
branch: feat/model-preflight
repo: charon-private
depends_on: BENCH-OOB-GRADING
real-dep: BENCH-OOB-GRADING — preflight grading MUST run out-of-band (bench-grader user, hidden model-unreadable assertions). In-band grading reproduces the S0-S6 invalidity this fixes. True correctness prereq.
superseded_by: EVAL-PIPELINE-CONSOLIDATE (battery→one pipeline), EVAL-GRADER-PROVISION (grader), EVAL-DERIVED-BUDGETS (budgets). This ticket is now the CANDIDATE SLATE + design-of-record only; its code surfaces moved to the EVAL-* successors per MODEL-TESTING-ADVERSARIAL-REVIEW.md §F12. The design of record is now fleet/state/EVAL-PIPELINE-DESIGN.md; the candidates below are the slate the adaptive runner places against.
owns: fleet/state/PREFLIGHT-CANDIDATES.md
accept: |
  CANDIDATE SLATE ONLY. The battery, runner, item-bank, and the single-
  capture-path are owned by EVAL-PIPELINE-CONSOLIDATE (design of record:
  fleet/state/EVAL-PIPELINE-DESIGN.md). This file is the human-curated
  list of models the runner places against, plus the historical
  acceptance contract for the slate.
  Design of record: fleet/state/EVAL-PIPELINE-DESIGN.md — ONE item-bank
  + ONE adaptive runner + ONE capture path. The battery is the item-
  bank's saturated items, calibrated per (work_class, difficulty), and
  graded by the ONE OOB grader-daemon path. R0 is the leg-preflight
  canary (LEG-PREFLIGHT-CANARY); R1–R3 are folded into the adaptive
  runner's per-(model, work_class) ceiling placement.
candidates: |
  Kimi-K2-Thinking, MiniMax-M2, GPT-OSS-120B, Phi-4, Qwen3.6-27B-MTP, Gemma 4 (31B), GLM 4.7 (Thinking),
  Gemini 2.5 Pro (big Python codebases), GPT-5.1-Codex-Max (complex/refactor). ALSO test PAID variants of models we
  run free (free tiers often quantized/degraded) — record free-vs-paid as a distinct axis.
scope: Router Model-Trust — the ENTRY gate for new models. The slate below is the human-curated list the adaptive runner places against; the battery + ladder + capture path are the EVAL-PIPELINE-CONSOLIDATE pipeline (not owned by this ticket).
ds: |
  The accurate model test; the slate is fed into pipeline.py place / run-all
  (see fleet/state/EVAL-PIPELINE-DESIGN.md). Per-(model, work_class) ceiling
  grade is the runner's output, fed to model-scorecard.tsv via the SINGLE
  capture path (pipeline._enqueue_capture → enqueue-capture.sh → daemon).
