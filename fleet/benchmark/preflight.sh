#!/usr/bin/env bash
# preflight.sh — SHIM to the consolidated eval pipeline
# (EVAL-PIPELINE-CONSOLIDATE, review F9 + F12).
#
# Historical role (pre-consolidation): the T1–T12 MODEL-PREFLIGHT runner
# (see PREFLIGHT-DESIGN-V2.md §2). F12 collapses the 4–5 overlapping
# harnesses — preflight.sh T1–T12, dogfood-eval, honest-battery-sweep,
# canary R0, bench.sh S0–S6 — into ONE adaptive pipeline
# (fleet/benchmark/item-bank/pipeline.py).
#
# This script is now a DELEGATING WRAPPER around `pipeline.py place`,
# kept for backward compatibility with operators/scripts that still
# invoke `preflight.sh <model>`. The legacy T1–T12 manifest, the
# per-task N≥3 design, and the OOB grader-daemon kind=="preflight"
# substrate are all preserved by the item-bank dispatcher
# (fleet/benchmark/item-bank/grade.py), which is the SAME daemon
# substrate (kind=="preflight" -> grader-daemon.py -> graders.preflight
# vs. the item-bank dispatcher) — just with the calibrated
# item-bank as the source instead of the legacy T1–T12 manifest.
#
# USAGE
#   preflight.sh <candidate-model> [--tier economy|strong|frontier]
#                [--runs N] [--out FILE]
#                [--tasks-dir DIR] [--manifest FILE]
#
#   --runs N          is accepted for backward compatibility but is
#                     IGNORED (the adaptive runner does ONE run per item
#                     per placement; per-skill ceiling is found via the
#                     per-skill break, not via repetition). A warning is
#                     printed.
#   --tasks-dir / --manifest   are accepted for backward compatibility
#                     and IGNORED (the item-bank's manifest is the
#                     single source of truth; pointing preflight.sh at
#                     a different manifest is no longer supported).
#
# The real options that matter:
#   --tier  economy|strong|frontier    (default: derive from price map;
#                                       see TIER-CANON.md for the
#                                       blended-$/Mtok rule)
#   --work-class <wc>                  (restrict to one canonical
#                                       work_class; optional)
#   --out FILE                         (write placement JSON to FILE
#                                       instead of stdout)
#   --dry-run                          (do not enqueue captures; the
#                                       runner is the sole writer of
#                                       source=live scorecard rows
#                                       and enqueues via
#                                       enqueue-capture.sh — --dry-run
#                                       prints what would be enqueued
#                                       and is the default for testing)
#
# Exit codes: 0 = placement ran to completion (per-skill ceilings
#                 returned; individual work_classes may still have no
#                 ceiling — that is DATA, not a script failure)
#             2 = fail-loud abort (item-bank missing, no candidate)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '[preflight] %s\n' "$*" >&2; }
die()  { log "ERROR: $*"; exit 2; }

# ── arg parse (backward-compat shim) ────────────────────────────────────────
candidate=""
tier=""
work_class=""
out=""
dry_run=0
runs_n=""
tasks_dir=""
manifest=""

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      sed -n '2,/^set -uo pipefail/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --tier)        tier="$2"; shift 2 ;;
    --work-class)  work_class="$2"; shift 2 ;;
    --out)         out="$2"; shift 2 ;;
    --dry-run)     dry_run=1; shift ;;
    --runs)        runs_n="$2"; shift 2 ;;
    --tasks-dir)   tasks_dir="$2"; shift 2 ;;
    --manifest)    manifest="$2"; shift 2 ;;
    --) shift; break ;;
    -*) die "unknown argument: $1 (the legacy T1–T12 runner is retired; see fleet/state/EVAL-PIPELINE-DESIGN.md)" ;;
    *)
      if [ -z "$candidate" ]; then
        candidate="$1"; shift
      else
        die "unexpected extra positional argument: $1"
      fi
      ;;
  esac
done

[ -n "$candidate" ] || die "candidate model is required (usage: preflight.sh <model> [--tier ...] [--work-class ...])"
[ -n "$runs_n" ] && log "WARNING: --runs=$runs_n is IGNORED by the consolidated pipeline (the adaptive runner does ONE run per item per placement; per-skill ceiling is found via per-skill break, not repetition). See fleet/state/EVAL-PIPELINE-DESIGN.md."
[ -n "$tasks_dir" ] && log "WARNING: --tasks-dir=$tasks_dir is IGNORED (the item-bank's manifest is the single source of truth)."
[ -n "$manifest" ] && log "WARNING: --manifest=$manifest is IGNORED (the item-bank's manifest is the single source of truth)."

PIPELINE="$HERE/item-bank/pipeline.py"
[ -f "$PIPELINE" ] || die "item-bank pipeline missing: $PIPELINE — the consolidated pipeline is a hard dep of preflight.sh"

cmd=(python3 "$PIPELINE" place "$candidate")
[ -n "$tier" ] && cmd+=(--tier "$tier")
[ -n "$work_class" ] && cmd+=(--work-class "$work_class")
[ -n "$out" ] && cmd+=(--out "$out")
[ "$dry_run" -eq 1 ] && cmd+=(--dry-run)

log "delegating to consolidated pipeline: ${cmd[*]}"
exec "${cmd[@]}"
