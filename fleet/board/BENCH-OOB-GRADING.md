repurpose-2026-07-10: grade REAL tasks (reds-replay + sub-session actuals), NOT synthetic S0-S6; write VERSIONED frozen scorecard artifacts consumed via freeze-ring (GATEWAY-PROGRAM).
priority: 0
tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
parked: false
work_class: ci-infra
branch: feat/bench-oob-grading
depends_on: STAGE-DEMUX
build-after-done: BENCH-PROVISIONAL-SCORING (un-parked 2026-07-08 as approved to track the pivot as active, but #20 is still PARKED; hard depends_on to a parked ticket would trip the validator, so the sequencing is expressed as build-after. RESTORE depends_on: BENCH-PROVISIONAL-SCORING when #20 is un-parked. Also gated on operator Q1 — do NOT build yet.)
real-dep: STAGE-DEMUX — added 2026-07-16. #26's premise is that the OOB grader's verdict is what EARNS
  `stage=active`, but grader-daemon.py:410 hardcodes the literal "active" into ledger col 16 and
  _handle_capture (:452) never reads req["stage"] — so the daemon writes `active` regardless of WHO
  graded, and #26 would land on a trust axis that cannot distinguish it (ledger proof: 45/45 live rows
  active, zero provisional ever). STAGE-DEMUX makes the axis expressible; #26 rebases onto it. Shared
  owner of grader-daemon.py -> file-sequenced after STAGE-DEMUX, never co-write. Evidence:
  fleet/session-notes/2026-07-16-evidence/bench-provisional-deepdive.md §"#26 sequencing".
real-dep: BENCH-PROVISIONAL-SCORING — shared single-owner of benchmark/bench.sh +
  benchmark/lib/grade_state.py + model-scorecard.sh. #26 moves the grader invocation +
  grade_state.record + scorecard append INTO the daemon, editing the SAME call sites #20 rewires
  for stage plumbing; must rebase onto #20, never co-write. Logically parallel per pivot §1 but
  file-sequenced after #20.
owns: benchmark/bench.sh, benchmark/lib/grade_state.py, model-scorecard.sh, benchmark/grader-daemon.py, benchmark/graders, benchmark/RUN-BENCHMARK.md, START-SESSION.md, preflight.sh
serial_justified: Remaining work is a single cohesive VERIFICATION pass of an already-built integrity system (13 graders + daemon deployed & live via bench-grader-setup.sh 2026-07-16); difficulty:5 is a placeholder auto-seed (see its own comment 'refine when purpose is fresh'), not a real size estimate, and the 8 owns are surfaces the built work TOUCHED, not 8 independent remaining builds. Accept is verify-and-human-sign-off (unreadable keys, forged-score rejection, deterministic re-grade) — inherently serial, not parallelizable.
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
note: SUPERSESSION VERIFIED FALSE (2026-07-23, adversarial) — KEEP. EVAL-* is a ledger CONSUMER that ASSUMES the OOB grader; BENCH-OOB IS the tamper-proof substrate (grader-daemon + 3 invariants) it sits on. NOT superseded (also clears the MODEL-PREFLIGHT/GRADER-SECFIX flag). Remaining: (a) human sign-off verification (daemon DEPLOYED), (b) STAGE-FAILCLOSED default flip. Line-410 fixed by STAGE-DEMUX. Prior: HELD pending supersession review - reorg audit (WORK-REORG-PROPOSAL.md) flags this + MODEL-PREFLIGHT + GRADER-SECFIX likely SUPERSEDED by the merged EVAL-* pipeline. Verify before any build; do not route to a tab yet.

Q1-RESOLVED 2026-07-09: substrate = A (dedicated bench-grader unix user on LOCAL WSL box, answer-keys mode 0700). Still parked for BUILD pending: (1) proper #26/#25 design review, (2) build-after #20 (BENCH-PROVISIONAL-SCORING) resolution. Keep parked: true until both clear.

SG-READY-NOTE 2026-07-24 (P0): gate RED on PR #193 (5835/33) — likely new gate unregistered in tools/gates.json + version bump; fix green, then merge
