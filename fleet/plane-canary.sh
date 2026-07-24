#!/usr/bin/env bash
# plane-canary.sh — PLANE-CANARY suite runner + reconciliation leg.
#
# WHY THIS EXISTS (fleet/board/PLANE-CANARY-REGISTRY.md, design of record
# fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 4):
#   Every control/money plane this fleet runs is SUPPOSED to have a proactive
#   canary + a fail-on-revert dogfood, wired into a firing layer (ci / preflight
#   / land / timer). The FINAL-E2E-REVIEW phantom class is a plane that is
#   DECLARED but has no wired+passing+fault-proven canary — nobody notices the
#   gap until the plane silently breaks in production. This runner reads a
#   git-tracked registry of the 10 declared planes and its `reconcile` leg goes
#   LOUD RED on any declared plane that is not wired+passing+proven.
#
# ── ADOPT, DON'T HAND-ROLL A SECOND FRAMEWORK ───────────────────────────────
#   This deliberately MIRRORS two existing rig patterns instead of inventing a
#   third runner shape:
#     • fleet/checks/rig-ci-scope.sh — the ALLOWLIST-iteration + RED-var
#       aggregation + `suites`/`tests` accessor shape (cmd_* dispatch, `RED=0;
#       red(){ RED=1; }`, capture-then-check never pipe-mask).
#     • fleet/flow-canary.sh — the GREEN/RED per-row lines + loud RED banner
#       shape, and the read-a-file-not-a-pipe loop so `RED` survives the loop.
#   No off-the-shelf monitor (Checkly / Grafana-SM / Sensu / blackbox_exporter,
#   all REJECTED in DESIGN Phase 1) models Charon's declared-vs-wired
#   missing-canary semantics, so the reconcile leg itself is the novel slice.
#
# ── SUB-COMMANDS ────────────────────────────────────────────────────────────
#   run [--live|--hermetic]  iterate every registry row and launch its leg:
#                            --live     launches canary_script (real network)
#                            --hermetic launches dogfood_test  (offline; default)
#                            ANY non-zero exit -> suite RED. Prints a per-plane
#                            table + a loud RED banner. Records each leg's exit
#                            to $PC_RUNLOG so `reconcile` can see a failing proof.
#   reconcile                the reconciliation leg (below), callable standalone.
#   suites | tests           print the hermetic dogfood_test path list, one per
#                            line, so fleet/checks/rig-ci-scope.sh's CI_SUITES can
#                            consume it without a second hand-maintained list.
#                            (ACCESSOR ONLY — PLANE-CANARY-WIRE does the wiring.)
#
# ── RECONCILE LEG — RED if ANY of ───────────────────────────────────────────
#   1. a plane in the PLANES=(...) constant has NO row in the registry
#      -> "plane X declared, no canary".
#   2. a row's canary_script/dogfood_test is blank, names a file absent on disk,
#      OR its dogfood_test's LAST recorded run exited non-zero -> "proofless
#      canary" (a canary with no passing fault-seed dogfood is untrusted).
#   3. a row's wired_in names a layer that, when grep'd, does NOT invoke the
#      canary_script or dogfood_test -> "unwired canary" (the FINAL-E2E-REVIEW
#      phantom guard). FAIL CLOSED: an unrecognized wired_in token is treated as
#      "does not fire", never "assume it fires".
#   Exit non-zero on any RED; exit 0 only when every declared plane is
#   wired+passing+proven.
#
# ── ENV (all overridable; the dogfood injects fixtures) ─────────────────────
#   PC_REGISTRY      default <fleet>/plane-canary-registry.tsv
#   PC_ROOT          repo root for resolving script paths (default <fleet>/..)
#   PC_RUNLOG        default <fleet>/state/plane-canary-lastrun.tsv (gitignored)
#   PC_SRC_CI        firing-layer source(s) for `ci`        (space-separated)
#   PC_SRC_PREFLIGHT firing-layer source(s) for `preflight`
#   PC_SRC_LAND      firing-layer source(s) for `land`
#   PC_SRC_TIMER     firing-layer source(s) for `timer`
#
# EXIT: 0 = GREEN, non-zero = RED (loud), 2 = usage.
set -uo pipefail

FLEET="${CHARON_FLEET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ROOT="${PC_ROOT:-$(cd "$FLEET/.." && pwd)}"
REGISTRY="${PC_REGISTRY:-$FLEET/plane-canary-registry.tsv}"
RUNLOG="${PC_RUNLOG:-$FLEET/state/plane-canary-lastrun.tsv}"

# The 10 declared planes — OWNED BY THIS SCRIPT. reconcile cross-checks the
# registry against this constant: a name here with no registry row is a
# declared-but-uncanaried plane. Keep in lockstep with the registry's rows.
# PC_PLANES (space/comma-separated) overrides the constant so the hermetic
# dogfood can inject a small fixture plane-set; DEFAULT is the hardcoded 10.
PLANES=(data/serving failover egress-key review lifecycle landing balance config-ssot map-freshness reconciliation)
if [ -n "${PC_PLANES:-}" ]; then
  # shellcheck disable=SC2206  # deliberate word-split of the override list.
  IFS=', ' read -r -a PLANES <<< "$PC_PLANES"
fi

# Firing-layer source map. A wired_in token counts as WIRED only if one of these
# files' text invokes the canary_script or dogfood_test. FAIL CLOSED: a token
# not in this case is "does not fire" (handled in _unwired_layers).
PC_SRC_CI="${PC_SRC_CI:-$FLEET/checks/rig-ci-scope.sh $ROOT/.github/workflows/rig-ci.yml}"
PC_SRC_PREFLIGHT="${PC_SRC_PREFLIGHT:-$FLEET/preflight.sh}"
PC_SRC_LAND="${PC_SRC_LAND:-$FLEET/land.sh $FLEET/land-push.sh}"
PC_SRC_TIMER="${PC_SRC_TIMER:-$FLEET/foreman-cadence.sh}"

RED=0
_pass(){ echo "  GREEN  $1"; }
_red(){  RED=1; echo "  RED    $1"; }
_info(){ echo "         $1"; }

# ── registry iteration ──────────────────────────────────────────────────────
# Reads from a FILE (not a pipe) so RED / arrays mutated in the callback survive
# the loop (same reason fleet/flow-canary.sh reads $status_file, not a pipe).
_each_row(){
  local cb="$1"
  if [ ! -r "$REGISTRY" ]; then
    echo "plane-canary: registry unreadable at $REGISTRY" >&2
    RED=1; return 2
  fi
  local plane canary dogfood wired owner _rest
  while IFS=$'\t' read -r plane canary dogfood wired owner _rest; do
    [ -n "$plane" ] || continue
    case "$plane" in \#*) continue;; esac
    "$cb" "$plane" "$canary" "$dogfood" "$wired" "$owner"
  done < "$REGISTRY"
}

_registry_has_plane(){
  awk -F'\t' -v p="$1" '$1==p{f=1} END{exit f?0:1}' "$REGISTRY"
}

# ── firing-layer resolution (fail-closed) ───────────────────────────────────
# Prints the source file(s) for a layer (newline-separated) and returns 0, or
# returns 1 for an UNRECOGNIZED layer token (caller must treat as unwired).
_layer_srcs(){
  case "$1" in
    ci)        printf '%s\n' $PC_SRC_CI;;
    preflight) printf '%s\n' $PC_SRC_PREFLIGHT;;
    land)      printf '%s\n' $PC_SRC_LAND;;
    timer)     printf '%s\n' $PC_SRC_TIMER;;
    *) return 1;;
  esac
}

# Echoes a space-separated list of UNWIRED layer tokens for a row (empty = every
# named layer actually invokes the canary or its dogfood). An unrecognized token
# is reported as "<tok>(unknown-layer)" — fail closed.
_unwired_layers(){
  local canary="$1" dogfood="$2" wired="$3"
  local cbase dbase; cbase="$(basename "$canary")"; dbase="$(basename "$dogfood")"
  local bad="" tok srcs s found
  local saved="$IFS"; IFS=','; set -- $wired; IFS="$saved"
  for tok in "$@"; do
    tok="${tok// /}"
    [ -n "$tok" ] || continue
    if ! srcs="$(_layer_srcs "$tok")"; then
      bad="$bad $tok(unknown-layer)"; continue
    fi
    found=0
    while IFS= read -r s; do
      [ -n "$s" ] || continue
      [ -f "$s" ] || continue
      if grep -qF -- "$cbase" "$s" 2>/dev/null || grep -qF -- "$dbase" "$s" 2>/dev/null; then
        found=1; break
      fi
    done <<< "$srcs"
    [ "$found" -eq 1 ] || bad="$bad $tok"
  done
  printf '%s' "${bad# }"
}

# ── last-run proof (optional) ───────────────────────────────────────────────
# $PC_RUNLOG is an append log of "<dogfood_test>\t<rc>\t<ts>"; the LAST line for
# a given dogfood wins. Empty string when there is no recorded run.
_lastrun_status(){
  [ -r "$RUNLOG" ] || { printf ''; return; }
  awk -F'\t' -v d="$1" '$1==d{rc=$2} END{printf "%s", rc}' "$RUNLOG"
}
_record_run(){
  local target="$1" rc="$2" ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo now)"
  mkdir -p "$(dirname "$RUNLOG")" 2>/dev/null || true
  printf '%s\t%s\t%s\n' "$target" "$rc" "$ts" >> "$RUNLOG" 2>/dev/null || true
}

# ── reconcile leg ───────────────────────────────────────────────────────────
_reconcile_row(){
  local plane="$1" canary="$2" dogfood="$3" wired="$4" owner="$5"

  if [ -z "$canary" ] || [ -z "$dogfood" ]; then
    _red "plane '$plane': blank canary_script/dogfood_test column — proofless (a canary column is never silently blank)"
    return
  fi
  if [ -z "$wired" ] || [ -z "$owner" ]; then
    _red "plane '$plane': blank wired_in/owner_ticket column — malformed row"
    return
  fi

  local miss=""
  [ -f "$ROOT/$canary" ]  || miss="$miss canary_script=$canary"
  [ -f "$ROOT/$dogfood" ] || miss="$miss dogfood_test=$dogfood"
  if [ -n "$miss" ]; then
    _red "plane '$plane': proofless canary — file(s) absent on disk:$miss (untrusted until $owner lands them)"
    return
  fi

  local last; last="$(_lastrun_status "$dogfood")"
  if [ -n "$last" ] && [ "$last" != "0" ]; then
    _red "plane '$plane': proofless canary — last recorded '$dogfood' run exited $last (not 0); the fault-seed dogfood is failing"
    return
  fi

  local unwired; unwired="$(_unwired_layers "$canary" "$dogfood" "$wired")"
  if [ -n "$unwired" ]; then
    _red "plane '$plane': unwired canary — wired_in=[$wired] but layer(s) [$unwired] do NOT invoke $(basename "$canary")/$(basename "$dogfood") (FINAL-E2E-REVIEW phantom class; fail-closed)"
    return
  fi

  _pass "plane '$plane': wired [$wired], files present, proven ($owner)"
}

cmd_reconcile(){
  echo "════════════════════════════════════════════════════════════"
  echo " PLANE-CANARY reconcile — every declared plane must be"
  echo " wired + passing + fault-proven, or it is LOUD RED"
  echo " registry: $REGISTRY"
  echo "════════════════════════════════════════════════════════════"
  if [ ! -r "$REGISTRY" ]; then
    _red "registry unreadable at $REGISTRY — cannot reconcile"
    echo "████ PLANE-CANARY reconcile: RED ████"
    return 1
  fi
  local p
  for p in "${PLANES[@]}"; do
    _registry_has_plane "$p" || _red "plane '$p' declared in PLANES but has NO row in $REGISTRY — declared, no canary"
  done
  _each_row _reconcile_row
  echo
  if [ "$RED" -eq 0 ]; then
    echo "════ PLANE-CANARY reconcile: GREEN — all ${#PLANES[@]} planes wired+passing+proven ════"
    return 0
  fi
  echo "████ PLANE-CANARY reconcile: RED — a declared plane is unwired / proofless / uncovered (see RED lines) ████"
  return 1
}

# ── run leg ─────────────────────────────────────────────────────────────────
_RUN_ROWS=()
_RUN_MODE="hermetic"
_run_row(){
  local plane="$1" canary="$2" dogfood="$3" wired="$4" owner="$5"
  local target
  [ "$_RUN_MODE" = "live" ] && target="$canary" || target="$dogfood"
  if [ -z "$target" ]; then
    _RUN_ROWS+=("$plane|RED|blank $_RUN_MODE-target column"); RED=1; return
  fi
  if [ ! -f "$ROOT/$target" ]; then
    _RUN_ROWS+=("$plane|RED|MISSING $target (GAP until $owner)"); RED=1; return
  fi
  # capture-then-check: NEVER `| tee`/`| grep` the runner (KS no_pipe_mask) — a
  # pipe would replace $? with the pipe tail's exit and swallow a real failure.
  local out rc
  out="$(bash "$ROOT/$target" 2>&1)"; rc=$?
  _record_run "$target" "$rc"
  if [ "$rc" -eq 0 ]; then
    _RUN_ROWS+=("$plane|GREEN|$target rc=0")
  else
    _RUN_ROWS+=("$plane|RED|$target rc=$rc"); RED=1
    _info "── $plane RED — tail of $target output ──"
    printf '%s\n' "$out" | tail -8
  fi
}

_print_run_table(){
  echo "── per-plane $_RUN_MODE result ─────────────────────────────"
  [ "${#_RUN_ROWS[@]}" -gt 0 ] || { echo "  (no rows)"; return; }
  local row plane status detail
  for row in "${_RUN_ROWS[@]}"; do
    plane="${row%%|*}"; row="${row#*|}"; status="${row%%|*}"; detail="${row#*|}"
    printf '  %-5s %-15s %s\n' "$status" "$plane" "$detail"
  done
}

cmd_run(){
  local mode="hermetic"
  case "${1:-}" in
    --live)            mode="live";;
    --hermetic|"")     mode="hermetic";;
    *) echo "usage: plane-canary.sh run [--live|--hermetic]" >&2; return 2;;
  esac
  _RUN_MODE="$mode"
  _RUN_ROWS=()
  echo "════════════════════════════════════════════════════════════"
  echo " PLANE-CANARY run (--$mode)"
  echo " $(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo now)"
  echo "════════════════════════════════════════════════════════════"
  _each_row _run_row
  echo
  _print_run_table
  echo
  if [ "$RED" -eq 0 ]; then
    echo "════ PLANE-CANARY run: GREEN — every plane's $mode leg exited 0 ════"
    return 0
  fi
  echo "████ PLANE-CANARY run: RED — a plane leg FAILED or is MISSING (see table above) ████"
  return 1
}

# ── suites / tests accessor ─────────────────────────────────────────────────
_emit_dogfood(){
  local dogfood="$3"
  [ -n "$dogfood" ] && printf '%s\n' "$dogfood"
}
cmd_suites(){ _each_row _emit_dogfood; }

main(){
  case "${1:-}" in
    run)          shift; cmd_run "$@"; exit $?;;
    reconcile)    shift; cmd_reconcile "$@"; exit $?;;
    suites|tests) cmd_suites; exit 0;;
    *) echo "usage: plane-canary.sh {run [--live|--hermetic] | reconcile | suites | tests}" >&2; exit 2;;
  esac
}

# Only dispatch when executed directly; sourcing (for the dogfood) exposes the fns.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
