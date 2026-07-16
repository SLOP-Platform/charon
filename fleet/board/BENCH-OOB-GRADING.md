repurpose-2026-07-10: grade REAL tasks (reds-replay + sub-session actuals), NOT synthetic S0-S6; write VERSIONED frozen scorecard artifacts consumed via freeze-ring (GATEWAY-PROGRAM).
tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
parked: false
work_class: ci-infra
branch: feat/bench-oob-grading
depends_on:
build-after: BENCH-PROVISIONAL-SCORING (un-parked 2026-07-08 as approved to track the pivot as active, but #20 is still PARKED; hard depends_on to a parked ticket would trip the validator, so the sequencing is expressed as build-after. RESTORE depends_on: BENCH-PROVISIONAL-SCORING when #20 is un-parked. Also gated on operator Q1 — do NOT build yet.)
real-dep: BENCH-PROVISIONAL-SCORING — shared single-owner of benchmark/bench.sh +
  benchmark/lib/grade_state.py + model-scorecard.sh. #26 moves the grader invocation +
  grade_state.record + scorecard append INTO the daemon, editing the SAME call sites #20 rewires
  for stage plumbing; must rebase onto #20, never co-write. Logically parallel per pivot §1 but
  file-sequenced after #20.
owns: benchmark/bench.sh, benchmark/lib/grade_state.py, model-scorecard.sh, benchmark/grader-daemon.py, benchmark/graders, benchmark/RUN-BENCHMARK.md, START-SESSION.md, preflight.sh
accept: human sign-off — from the graded-agent user, `cat` of any grader source/baseline fixture FAILS (permission denied); a fabricated agent-pasted score does NOT change the ledger (only the daemon's computed score lands); re-grading the snapshot is deterministic
prompt: /home/stack/charon-private/prompts/bench-oob-grading.md
scope: #26 (P0 INTEGRITY — the top fix; nothing the benchmark says is trustworthy until it lands).
  Out-of-band grading — move scoring OFF the graded model's box and OUT of self-report. Enforce 3
  invariants: (1) answer key (graders/*.py + baseline fixtures + #25 check_cmds) out of the
  subject's reach; (2) grading not self-driven (agent signals done; a SEPARATE scorer process
  grades); (3) no self-report (scorer is the sole ledger writer; agent's pasted output is
  advisory/discarded). Recommended arch: grader-daemon + drop-spool (agent write-only on req/, no
  read on graders/ or res/); daemon snapshots the worktree read-only, runs grader/check_cmd from a
  mode-0700 answer-key tree, appends the row. bench.sh keeps driving the agent but LOSES its grading
  powers. RIG-ONLY — daemon/spool/answer-keys must never be referenced by product code.
  D&S: PENDING operator decision Q1 (substrate: (a) separate `bench-grader` unix user [recommended]
  vs (b) root-owned tree + sudo wrapper vs (c) second host) — DO NOT BUILD until Q1 is resolved.
  Enables trustworthy #25 (reds-replay). Authoritative: scratch/pivot-implementation-plan.md §3 + §8 Q1.
note: UN-PARKED 2026-07-15 (operator: work the 3 critical path). Q1 RESOLVED (OOB grader = dedicated unix user on local WSL box) + #20 landed; substrate design settled. Manager reviews the PR before land.

Q1-RESOLVED 2026-07-09: substrate = A (dedicated bench-grader unix user on LOCAL WSL box, answer-keys mode 0700). Still parked for BUILD pending: (1) proper #26/#25 design review, (2) build-after #20 (BENCH-PROVISIONAL-SCORING) resolution. Keep parked: true until both clear.
