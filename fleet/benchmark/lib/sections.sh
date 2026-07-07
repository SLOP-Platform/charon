#!/usr/bin/env bash
# lib/sections.sh — shared section metadata (grader/fixture/timebox/work_class/
# backend-tier) for BOTH run.sh (legacy manual per-section driver, superseded)
# and bench.sh (single in-session one-paste driver). Sourced, never executed
# directly. Extracted verbatim from run.sh so the two drivers can never drift
# out of sync on what each section IS - only HOW it's driven differs.
#
# Callers must set BENCH_DIR (the fleet/benchmark/ absolute path) before
# sourcing, since section_grader/section_fixture resolve paths under it.

ALL_SECTIONS=(S0 S1 S2 S3 S4 S5 S6)

die() { echo "error: $*" >&2; exit 1; }

section_grader() {
  case "$1" in
    S6) echo "node $BENCH_DIR/graders/s6.js" ;;
    *)  echo "python3 $BENCH_DIR/graders/$(echo "$1" | tr 'A-Z' 'a-z').py" ;;
  esac
}

section_fixture() {
  case "$1" in
    S6) echo "$BENCH_DIR/fixtures-fe" ;;
    *)  echo "$BENCH_DIR/fixtures/sections/$(echo "$1" | tr 'A-Z' 'a-z')" ;;
  esac
}

section_timebox_sec() {
  case "$1" in
    S0) echo 180 ;;   # ~3 min
    S1) echo 360 ;;   # ~6 min
    S2) echo 600 ;;   # ~10 min
    S3) echo 480 ;;   # ~8 min
    S4) echo 720 ;;   # ~12 min
    S5) echo 600 ;;   # ~10 min
    S6) echo 720 ;;   # ~12 min
    *) die "unknown section $1" ;;
  esac
}

section_work_class() {
  case "$1" in
    S0) echo bugfix ;;
    S1) echo money-path ;;
    S2) echo routing ;;
    S3) echo ci-infra ;;
    S4) echo refactor ;;   # spec calls it "refactor+tests"; ledger enum has no combined value
    S5) echo greenfield-feature ;;
    S6) echo frontend ;;
    *) die "unknown section $1" ;;
  esac
}

# Backend-ladder tier (S0-S5 only). S6 is a parallel axis (MODEL-BENCHMARK-SPEC.md
# #4) and is NOT looked up here - callers compute its tier from its own score band.
section_tier() {
  case "$1" in
    S0) echo 0 ;; S1) echo 1 ;; S2) echo 2 ;; S3) echo 2 ;; S4) echo 3 ;; S5) echo 4 ;;
    *) die "unknown backend section $1" ;;
  esac
}

verdict_from_score() {
  local s="$1"
  if [ "$s" -ge 90 ]; then echo MERGE; elif [ "$s" -ge 50 ]; then echo FIXES; else echo BLOCK; fi
}

# WORKTREE MTIME-STABILITY GATE (bench-premature-grade, P2, fleet/reds.tsv):
# the model's own file-write(s) in its worktree can still be flushing to
# disk in the instant right after it announces "done" and invokes `grade` -
# grading against a not-yet-fully-settled worktree produces a false-low
# score (observed: kimi-k2.6/S5 and glm-5.2/S5 both scored 60, true settled
# state re-graded 100 ~37s later). Block the grader until the worktree's
# own newest file mtime has been STABLE (no writes) for
# BENCH_MTIME_STABLE_SEC seconds, capped at BENCH_MTIME_MAX_WAIT_SEC total
# wait so a worktree that's *continuously* touched (e.g. a leftover
# build/watch process) can't hang the run forever - it grades anyway past
# the cap, with a clear stderr warning. Shared by bench.sh and run.sh (both
# grade against the same on-disk worktrees) so neither can independently
# drift out of sync on this gate.
wait_for_worktree_stable() {
  local worktree="$1"
  # Default bumped 12s -> 20s (harness-hardening adversarial review,
  # fleet/scratch/harness-hardening-review.md, defer item #2): the observed
  # premature-grade gap that motivated this gate was ~37s of manual re-grade
  # delay, not a proven write-burst length, but 12s left more headroom than
  # warranted against a lone late flush arriving after a >12s quiet gap.
  # Still fully env-overridable (BENCH_MTIME_STABLE_SEC) and still capped by
  # BENCH_MTIME_MAX_WAIT_SEC (unchanged) so a continuously-touched worktree
  # still can't hang the run forever.
  local stable_for="${BENCH_MTIME_STABLE_SEC:-20}"
  local max_wait="${BENCH_MTIME_MAX_WAIT_SEC:-60}"
  local waited=0 newest now_epoch age remaining
  while :; do
    newest="$(find "$worktree" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)"
    if [ -z "$newest" ]; then
      return 0  # empty/missing worktree - nothing to wait on
    fi
    now_epoch="$(date +%s)"
    age=$(( now_epoch - ${newest%.*} ))
    if [ "$age" -ge "$stable_for" ]; then
      return 0
    fi
    if [ "$waited" -ge "$max_wait" ]; then
      echo "(worktree mtime still within ${stable_for}s of a write after ${max_wait}s of waiting - grading anyway; a background process may still be touching files in $worktree)" >&2
      return 0
    fi
    remaining=$(( stable_for - age ))
    if [ "$remaining" -lt 1 ]; then remaining=1; fi
    sleep "$remaining"
    waited=$(( waited + remaining ))
  done
}
