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
