# BENCH-OOB-GRADING — Out-of-band grading (pivot #26, P0 integrity)

RIG-ONLY (fleet repo). The daemon / spool / answer-keys must NEVER be referenced by product code.

## Context
#26 is the top integrity fix — nothing the benchmark says is trustworthy until it lands.
Today the answer key (`benchmark/graders/*.py` + baseline fixtures) is readable by the graded
agent, grading is self-driven (`bench.sh grade` run by the subject), and results are
self-reported (the agent pastes the tier chart). Any one of the three defeats the instrument.

**Authoritative design of record:** `/home/stack/charon-private/scratch/pivot-implementation-plan.md`
§3 (architecture) + §8 Q1. Read those before writing code. Driving verdict:
`fleet/BENCHMARK-VALIDITY-REVIEW.md` §2.

## Scope (#26)
Move scoring OFF the graded model's box and OUT of self-report. Enforce three invariants:
1. Answer key (`graders/*.py` + baseline fixtures + #25 `check_cmd`s) out of the subject's reach.
2. Grading not self-driven: the agent signals "section done"; a SEPARATE scorer process grades.
3. No self-report: the scorer is the sole ledger writer; the agent's pasted output is advisory/discarded.

Recommended architecture (solo-dev WSL, simplest-that-works): a grader-daemon + drop-spool.
The agent has WRITE-ONLY on `$SPOOL/req/` and NO read on `graders/` or `$SPOOL/res/`; the
daemon snapshots the worktree read-only, runs the grader/check_cmd from a mode-0700 answer-key
tree, and appends the row. `bench.sh` keeps driving the agent but LOSES its grading powers.

## owns
`benchmark/bench.sh`, `benchmark/lib/grade_state.py`, `model-scorecard.sh`,
`benchmark/grader-daemon.py`, `benchmark/graders`, `benchmark/RUN-BENCHMARK.md`,
`START-SESSION.md`, `preflight.sh`

## Gate / accept
Human sign-off: from the graded-agent user, `cat` of any grader source / baseline fixture FAILS
(permission denied); a fabricated agent-pasted score does NOT change the ledger (only the
daemon's computed score lands); re-grading the snapshot is deterministic.

## Dependencies & sequence
- build-after: BENCH-PROVISIONAL-SCORING (#20) — shared single-owner of `benchmark/bench.sh`
  + `benchmark/lib/grade_state.py` + `model-scorecard.sh`. #26 moves the grader invocation +
  `grade_state.record` + scorecard append INTO the daemon, editing the SAME call sites #20
  rewires for stage plumbing. Logically parallel per pivot §1, but file-sequenced AFTER #20:
  REBASE onto #20, never co-write. (Expressed as build-after, not depends_on, because #20 is
  currently PARKED — a hard depends_on to a parked ticket would trip the board validator.)
- BLOCKED on operator decision Q1 (substrate: (a) separate `bench-grader` unix user
  [recommended] vs (b) root-owned tree + sudo wrapper vs (c) second host). DO NOT BUILD until
  Q1 is resolved and #20 has landed.

## LAST STEP (required)
Commit your work on branch `feat/bench-oob-grading` with a clear message and report the SHA.

Do NOT push or merge.
