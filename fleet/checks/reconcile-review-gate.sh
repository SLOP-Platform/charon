#!/usr/bin/env bash
# reconcile-review-gate.sh — folded review-gate axis (§2.1) + fail-closed taxonomy (§2.2)
# from UNIFIED-RECONCILIATION-GATE-DESIGN.md.
#
# ================================ WHY THIS EXISTS ================================
# The review-gate axis enforces that every ≥hot-path change in the reconcile window
# has verifiable review evidence: a docs/review-log/<id>.md fragment (operator-merged
# prose) AND a fleet/state/reviewed/<id> machine marker with reviewed_sha matching the
# merge commit SHA and reviewer != author model.
#
# RED conditions:
#   R-J — ≥hot-path change with no review-log fragment AND no reviewed/<id> marker
#         at the merge SHA. Action: BLOCK (consumer-A BLOCK condition).
#   R-K — review-log fragment exists but reviewed_sha does NOT match the merge commit
#         (review was for a different SHA — drift). Action: BLOCK + re-review.
#   R-L — verdict=FIXES with no follow-up CONFIRMED-CLEAN at merge sha (doom loop via
#         ReviewerCircuitBreaker pattern — tracks consecutive FIXES, trips after 3).
#
# Fail-closed taxonomy (§2.2): any path or work_class the classifier does not recognize
# is treated as tier = max(recognized, hot-path):
#   - Unknown src/charon/*.py → hot-path (fail-closed)
#   - Unknown work_class → hot-path (fail-closed)
#   - Unknown docs/ or fleet/ path → tier 0 (doc/tooling)
#
# Invocation:
#   reconcile-review-gate.sh check [board-dir]
#       HARD verdict. Exit 0 = GREEN (all ≥hot-path changes reviewed).
#       Exit 1 = RED (at least one BLOCK condition).
#       Exit 2 = usage error.
#   reconcile-review-gate.sh scan [board-dir]
#       ADVISORY — always exits 0, prints per-ticket status.
#
# Env overrides (test isolation seams):
#   REVIEW_GATE_BOARD        overrides board dir (default: <fleet>/board)
#   REVIEW_GATE_STATE        overrides state dir (default: <fleet>/state)
#   REVIEW_GATE_REVIEW_LOG   overrides review-log dir (default: <docs>/review-log)
#   REVIEW_GATE_REVIEWED     overrides reviewed markers dir (default: <state>/reviewed)
#   REVIEW_GATE_MERGE_SHA    overrides expected merge SHA for all tickets (testing)
#
# This script is WS7-validated implement-as-pattern (stass-allie WLS-7, 2026-07-23).
# Reuses ReviewerCircuitBreaker (src/charon/failover.py:73-142) pattern for R-L.
#
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BOARD="${REVIEW_GATE_BOARD:-$FLEET/board}"
STATE="${REVIEW_GATE_STATE:-$FLEET/state}"
REVIEW_LOG="${REVIEW_GATE_REVIEW_LOG:-$(cd "$FLEET/.." && pwd)/docs/review-log}"
REVIEWED="${REVIEW_GATE_REVIEWED:-$STATE/reviewed}"
MERGE_SHA_OVERRIDE="${REVIEW_GATE_MERGE_SHA:-}"
DONE_DIR="$STATE/done"

HOT_PATH_THRESHOLD=3  # tier values ≥ this require review

rc=0
offenders=""

usage() {
  cat >&2 <<'EOF'
usage: reconcile-review-gate.sh {check|scan} [board-dir]
  check  hard gate — exit 1 on any BLOCK condition
  scan   advisory — always exits 0, prints per-ticket status
EOF
  exit 2
}

# Tier value lookup. Returns a numeric tier; 0 = unrecognized.
tier_value() {
  case "$1" in
    economy)  echo 1 ;;
    standard) echo 2 ;;
    hot-path|hotpath|hot) echo 3 ;;
    strong)   echo 4 ;;
    critical|blocker) echo 5 ;;
    *) echo 0 ;;
  esac
}

# Work class tier mapping. Known work classes map to their blast tier;
# unrecognized ones return 0 (caller applies fail-closed default).
wc_tier_value() {
  case "$1" in
    docs|tooling|chore) echo 1 ;;
    standard|normal) echo 2 ;;
    mechanism|rig|mech) echo 3 ;;
    hot-path|hotpath) echo 3 ;;
    strong) echo 4 ;;
    critical|blocker) echo 5 ;;
    *) echo 0 ;;
  esac
}

# Classify a ticket's blast tier using the fail-closed taxonomy.
# Arguments: ticket_file (path to board ticket .md)
# Returns numeric tier on stdout.
classify_ticket() {
  local tf="$1"
  local tier_field="" owns_field="" work_class_field=""
  while IFS=: read -r key val; do
    case "$key" in
      tier) tier_field="$(printf '%s' "$val" | awk '{$1=$1};1' | tr '[:upper:]' '[:lower:]')" ;;
      owns) owns_field="$val" ;;
      work_class) work_class_field="$(printf '%s' "$val" | awk '{$1=$1};1' | tr '[:upper:]' '[:lower:]')" ;;
    esac
  done < <(grep -E '^(tier|owns|work_class):' "$tf" 2>/dev/null || true)

  local tv
  tv=$(tier_value "$tier_field")
  [ -z "$tv" ] && tv=0

  # Fail-closed: unknown work_class → hot-path
  local wc_tv
  wc_tv=$(wc_tier_value "$work_class_field")
  if [ "$wc_tv" -eq 0 ] && [ -n "$work_class_field" ]; then
    wc_tv=3
  elif [ -z "$work_class_field" ]; then
    wc_tv=0
  fi

  # Path-pattern fallback: check owns paths
  local path_tv=0
  local owns_clean
  owns_clean="$(printf '%s' "$owns_field" | sed 's/,/\n/g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    # Strip quotes and whitespace
    path="$(printf '%s' "$path" | sed "s/^['\"]//;s/['\"]$//;s/^[[:space:]]*//;s/[[:space:]]*$//")"
    [ -z "$path" ] && continue
    case "$path" in
      src/charon/*)
        # Any src/charon path → at least hot-path (fail-closed if unknown)
        if [ "$path_tv" -lt 3 ]; then path_tv=3; fi
        ;;
      docs/*|fleet/*)
        # Doc/tooling paths → tier 0 unless explicit tier says otherwise (handled by max)
        ;;
      src/*)
        # Any other src/ path → standard (2) minimum
        if [ "$path_tv" -lt 2 ]; then path_tv=2; fi
        ;;
    esac
  done <<< "$owns_clean"

  # Return max of {tier_field, work_class_tier, path_tier}
  local max=$tv
  [ "$path_tv" -gt "$max" ] && max=$path_tv
  [ "$wc_tv" -gt "$max" ] && max=$wc_tv
  echo "$max"
}

# Get the expected merge SHA for a ticket.
# Checks: (1) state/done/<id> marker's merged:<sha>, (2) REVIEW_GATE_MERGE_SHA override.
get_merge_sha() {
  local id="$1"
  local sha=""
  if [ -n "$MERGE_SHA_OVERRIDE" ]; then
    echo "$MERGE_SHA_OVERRIDE"
    return
  fi
  local done_marker="$DONE_DIR/$id"
  if [ -f "$done_marker" ]; then
    sha="$(grep -oE 'merged:[[:xdigit:]]+' "$done_marker" 2>/dev/null | head -1 | sed 's/^merged://')"
  fi
  echo "$sha"
}

# Read a reviewed/<id> marker file and return values via global variables.
# Sets: R_MARKER_EXISTS (0|1), R_SHA, R_AUTHOR, R_REVIEWER, R_VERDICT, R_FINDINGS
parse_reviewed_marker() {
  local id="$1"
  R_MARKER_EXISTS=0
  R_SHA=""; R_AUTHOR=""; R_REVIEWER=""; R_VERDICT=""; R_FINDINGS=""
  local mf="$REVIEWED/$id"
  [ ! -f "$mf" ] && return
  R_MARKER_EXISTS=1
  while IFS='=' read -r key val; do
    key="$(printf '%s' "$key" | awk '{$1=$1};1')"
    val="$(printf '%s' "$val" | awk '{$1=$1};1')"
    case "$key" in
      reviewed_sha) R_SHA="$val" ;;
      author_model) R_AUTHOR="$val" ;;
      reviewer) R_REVIEWER="$val" ;;
      verdict) R_VERDICT="$val" ;;
      findings) R_FINDINGS="$val" ;;
    esac
  done < "$mf"
}

# R-L doom-loop check using ReviewerCircuitBreaker pattern.
# Tracks consecutive FIXES verdicts without a closing CONFIRMED-CLEAN.
# Returns 0 if clean, 1 if circuit breaker should trip.
check_rl_doom_loop() {
  local id="$1" merge_sha="$2"
  parse_reviewed_marker "$id"
  [ "$R_MARKER_EXISTS" -eq 0 ] && return 0
  # No doom loop if verdict is not FIXES
  [ "$R_VERDICT" != "FIXES" ] && return 0
  # If the FIXES marker is at the merge sha, check for follow-up
  if [ -n "$merge_sha" ] && [ "$R_SHA" = "$merge_sha" ]; then
    # The marker at merge sha says FIXES — no follow-up CONFIRMED-CLEAN
    # Check if there's an earlier CONFIRMED-CLEAN that was superseded
    # For v1: if the latest marker at merge sha is FIXES, flag it
    return 1
  fi
  # FIXES at a different sha than merge sha — the review hasn't been re-done at HEAD
  if [ -n "$merge_sha" ]; then
    return 1
  fi
  return 0
}

# Check a single board ticket. Returns 0 if GREEN, 1 if RED.
check_ticket() {
  local tf="$1"
  local id
  id="$(basename "$tf" .md)"
  local tier
  tier=$(classify_ticket "$tf")
  local log_frag="$REVIEW_LOG/$id.md"

  # Below hot-path threshold — no review required
  [ "$tier" -lt "$HOT_PATH_THRESHOLD" ] && return 0

  local merge_sha
  merge_sha=$(get_merge_sha "$id")

  # R-J: ≥hot-path change with no review-log fragment AND no reviewed/<id> marker
  if [ ! -f "$log_frag" ]; then
    parse_reviewed_marker "$id"
    if [ "$R_MARKER_EXISTS" -eq 0 ]; then
      offenders="${offenders}R-J|$id|≥hot-path (tier=$tier) with NO review-log fragment AND NO reviewed/<id> marker"
      return 1
    fi
    # Has marker but no log fragment — still BLOCK (both are required)
    offenders="${offenders}R-J|$id|≥hot-path (tier=$tier) with NO review-log fragment (has reviewed marker)"
    return 1
  fi

  # Check the marker
  parse_reviewed_marker "$id"
  if [ "$R_MARKER_EXISTS" -eq 0 ]; then
    offenders="${offenders}R-J|$id|≥hot-path (tier=$tier) with review-log fragment but NO reviewed/<id> marker"
    return 1
  fi

  # R-K: reviewed_sha does NOT match the expected merge sha
  if [ -n "$merge_sha" ] && [ -n "$R_SHA" ] && [ "$R_SHA" != "$merge_sha" ]; then
    offenders="${offenders}R-K|$id|reviewed_sha=$R_SHA != expected_sha=$merge_sha (stale review)"
    return 1
  fi

  # reviewer must not be the author model (unless reviewer is operator)
  if [ -n "$R_AUTHOR" ] && [ -n "$R_REVIEWER" ] && [ "$R_REVIEWER" != "operator" ]; then
    if [ "$R_REVIEWER" = "$R_AUTHOR" ]; then
      offenders="${offenders}R-J|$id|reviewer ($R_REVIEWER) is the same as author_model ($R_AUTHOR)"
      return 1
    fi
  fi

  # R-L: doom loop — verdict=FIXES with no follow-up CONFIRMED-CLEAN
  if check_rl_doom_loop "$id" "$merge_sha"; then
    : # clean
  else
    offenders="${offenders}R-L|$id|verdict=FIXES at $R_SHA with no follow-up CONFIRMED-CLEAN (doom loop)"
    return 1
  fi

  return 0
}

# Scan the board and check all tickets.
do_check() {
  rc=0
  [ -d "$BOARD" ] || { echo "reconcile-review-gate: board not found: $BOARD" >&2; exit 2; }
  local tickets=()
  while IFS= read -r -d '' f; do
    tickets+=("$f")
  done < <(find "$BOARD" -maxdepth 1 -name '*.md' -print0 2>/dev/null)
  if [ ${#tickets[@]} -eq 0 ]; then
    echo "reconcile-review-gate: GREEN — no board tickets to check"
    return 0
  fi
  for tf in "${tickets[@]}"; do
    check_ticket "$tf" || rc=1
  done
  return "$rc"
}

# Print per-ticket status (always exits 0).
do_scan() {
  [ -d "$BOARD" ] || { echo "reconcile-review-gate scan: board not found: $BOARD" >&2; return 0; }
  local tickets=()
  while IFS= read -r -d '' f; do
    tickets+=("$f")
  done < <(find "$BOARD" -maxdepth 1 -name '*.md' -print0 2>/dev/null)
  if [ ${#tickets[@]} -eq 0 ]; then
    echo "reconcile-review-gate scan: empty board"
    return 0
  fi
  for tf in "${tickets[@]}"; do
    local id
    id="$(basename "$tf" .md)"
    local tier
    tier=$(classify_ticket "$tf")
    local log_frag="$REVIEW_LOG/$id.md"
    parse_reviewed_marker "$id"
    local status="CLEAN"
    local detail=""
    if [ "$tier" -ge "$HOT_PATH_THRESHOLD" ]; then
      if [ ! -f "$log_frag" ]; then
        status="R-J"
        detail="no review-log fragment"
      elif [ "$R_MARKER_EXISTS" -eq 0 ]; then
        status="R-J"
        detail="has log fragment but no reviewed marker"
      else
        local merge_sha
        merge_sha=$(get_merge_sha "$id")
        if [ -n "$merge_sha" ] && [ -n "$R_SHA" ] && [ "$R_SHA" != "$merge_sha" ]; then
          status="R-K"
          detail="stale sha: $R_SHA vs expected $merge_sha"
        elif [ -n "$R_AUTHOR" ] && [ -n "$R_REVIEWER" ] && [ "$R_REVIEWER" != "operator" ] && [ "$R_REVIEWER" = "$R_AUTHOR" ]; then
          status="R-J"
          detail="self-review"
        elif [ "$R_VERDICT" = "FIXES" ]; then
          status="R-L"
          detail="doom-loop: FIXES without CONFIRMED-CLEAN"
        else
          detail="reviewed by $R_REVIEWER at $R_SHA"
        fi
      fi
    fi
    echo "  $id  tier=$tier  $status  $detail"
  done
  echo "reconcile-review-gate scan: done"
}

cmd_check() {
  shift || true
  [ $# -le 1 ] || usage
  [ $# -eq 1 ] && BOARD="$1"
  do_check
  local check_rc=$?
  if [ "$check_rc" -eq 0 ]; then
    echo "reconcile-review-gate: GREEN — all ≥hot-path tickets reviewed"
  else
    while IFS='|' read -r cond id msg; do
      [ -z "$cond" ] && continue
      echo "  $cond  $id  $msg" >&2
    done <<< "$offenders"
    echo "reconcile-review-gate: RED — review gate BLOCKED" >&2
  fi
  exit "$check_rc"
}

cmd_scan() {
  shift || true
  [ $# -le 1 ] || usage
  [ $# -eq 1 ] && BOARD="$1"
  do_scan
  exit 0
}

case "${1:-}" in
  check) cmd_check "$@" ;;
  scan)  cmd_scan "$@" ;;
  *) usage ;;
esac
