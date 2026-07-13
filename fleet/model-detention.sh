#!/usr/bin/env bash
# model-detention.sh — scorecard -> assignment GUARDRAIL (build-rig only).
#
# Closes the scorecard->assignment loop: a (model x work_class) that crosses a REDLINE is
# DETAINED so fleet-droid.sh drops it from that tier's failover chain FOR THAT work_class.
# The scorecard (fleet/model-scorecard.tsv) is the SOLE input; it is grader-owned
# (bench-grader, 0644) and this feature READS it only — it NEVER writes/chowns it, so the
# out-of-band grader integrity isolation survives untouched. Pure awk over the ledger; no
# Python, and nothing here takes a lock.
#
# REDLINE RULES (per model x work_class, computed chronologically from the ledger):
#   FABRICATION  a row with gate=pass AND verdict=BLOCK ("green-but-fake"): >=1 occurrence
#                -> DETAINED, HARD (assignment-blocking) from day one. Fabrication is
#                deceptive — near-zero tolerance.
#   BLOCK-RATE   block% >= 50% over n >= 3 rows in that work_class -> DETAINED, ADVISORY
#                (log a loud warning, still allow). Flip to HARD later via a config flag.
#   PAROLE       2 consecutive MERGE rows in that work_class -> HARD detention cleared
#                (restored). Detention is recomputed every run, so parole is automatic the
#                moment the ledger shows the streak.
#
# SCOPE IS PER work_class: a model detained on money-path may still serve ci-infra. Never a
# global ban.
#
# Subcommands:
#   detained <work_class>       list detained models for that work_class, "<model>\t<HARD|ADVISORY>"
#   check <model> <work_class>  exit 0 = eligible, 3 = HARD-detained, 1 = advisory-flagged
#
# Scorecard columns (tab-separated; see model-scorecard.sh / model-scorecard.tsv header):
#   1 date  2 source  3 ref  4 work_class  5 tier  6 model  7 verdict  8 gate  9 score
#   10 time_s  11 cost_usd  12 corrections  13 note  14 tokens_in  15 tokens_out  16 stage
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# READ-ONLY input. The env override exists FOR TESTS ONLY (a fixture ledger, so the
# fail-on-revert suite never touches the live grader-owned tsv); production always resolves
# to the grader-owned scorecard beside this script.
TSV="${CHARON_SCORECARD_TSV:-$HERE/model-scorecard.tsv}"

die() { echo "error: $*" >&2; exit 2; }

# Emit the redline status ("HARD" | "ADVISORY" | "OK") for one model x work_class.
# Chronological single pass over the ledger rows for that pair:
#   - FABRICATION (gate=pass AND verdict=BLOCK) sets HARD and breaks any MERGE streak.
#   - PAROLE: 2 consecutive MERGE rows clear HARD (a later fabrication re-detains).
#   - Any non-MERGE row breaks the MERGE streak.
#   - BLOCK-RATE (>=50% over n>=3) is reported as ADVISORY only when not HARD.
_status_for() {
  local model="$1" wc="$2"
  awk -F'\t' -v M="$model" -v WC="$wc" '
    !/^#/ && NF>0 && $6==M && $4==WC {
      n++
      fab = ($8=="pass" && $7=="BLOCK")   # green-but-fake
      if (fab)          { hard=1; cm=0 }
      if ($7=="MERGE")  { cm++; if (cm>=2) hard=0 }   # parole: 2 consecutive MERGE clears HARD
      else              { cm=0 }                      # any non-MERGE breaks the streak
      if ($7=="BLOCK")  block++
    }
    END {
      if (hard)                               { print "HARD" }
      else if (n>=3 && (block*100)/n >= 50)   { print "ADVISORY" }
      else                                    { print "OK" }
    }' "$TSV"
}

cmd_check() {
  [ $# -eq 2 ] || die "check needs: <model> <work_class>"
  [ -f "$TSV" ] || die "scorecard not found: $TSV"
  local st; st="$(_status_for "$1" "$2")"
  case "$st" in
    HARD)     exit 3 ;;
    ADVISORY) exit 1 ;;
    *)        exit 0 ;;
  esac
}

cmd_detained() {
  [ $# -eq 1 ] || die "detained needs: <work_class>"
  [ -f "$TSV" ] || die "scorecard not found: $TSV"
  local wc="$1"
  awk -F'\t' -v WC="$wc" '
    !/^#/ && NF>0 && $4==WC {
      m=$6
      if (!(m in seen)) { seen[m]=1; order[++k]=m }
      n[m]++
      fab = ($8=="pass" && $7=="BLOCK")
      if (fab)          { hard[m]=1; cm[m]=0 }
      if ($7=="MERGE")  { cm[m]++; if (cm[m]>=2) hard[m]=0 }
      else              { cm[m]=0 }
      if ($7=="BLOCK")  block[m]++
    }
    END {
      for (i=1;i<=k;i++) {
        m=order[i]
        if (hard[m])                                    print m "\tHARD"
        else if (n[m]>=3 && (block[m]*100)/n[m] >= 50)  print m "\tADVISORY"
      }
    }' "$TSV"
}

case "${1:-}" in
  check)    shift; cmd_check "$@" ;;
  detained) shift; cmd_detained "$@" ;;
  *) echo "usage: $0 {check <model> <work_class>|detained <work_class>}" >&2; exit 2 ;;
esac
