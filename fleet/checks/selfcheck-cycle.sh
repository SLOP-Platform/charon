#!/usr/bin/env bash
# selfcheck-cycle.sh — fleet-selfcheck-forkbomb-class mechanized gate.
#
# WHY THIS EXISTS:
#   The 2026-07-15 incident (handoff.sh <-> gate.sh cycle, ~18,900 procs, GitHub
#   GraphQL cap blown) was caused by ONE unguarded self-referential edge: a
#   test under fleet/tests/ invoked handoff.sh via the real fleet root, and
#   handoff.sh's embedded gate.sh call re-entered the test suite. The half
#   of the fix that landed (gate.sh:29 exports CHARON_GATE_ACTIVE, handoff.sh
#   checks it and skips) prevents that ONE cycle — but the class is much
#   larger. fleet/tests/ has ~12 files that shell out to real fleet scripts
#   and four of those target handoff/gate/preflight/foreman/land directly.
#   Any ONE of those becoming a gate-run edge re-arms the same bomb.
#
# WHAT THIS DOES (and does NOT do):
#   Does:    static analysis of bash invocations inside fleet/*.sh and
#            fleet/tests/*.test.sh, building a script -> script call graph,
#            and FAILS on any cycle edge that lacks a reentrancy guard.
#   Does NOT: EXECUTE the scripts under test. The whole point is to keep
#             this checker from becoming the very bomb it detects. Read-only
#             file scans, awk string-parsing, set arithmetic. No `bash`
#             against the analyzed targets. A test that proves reentrancy
#             by actually recursing is how 18k procs happened; a checker
#             that runs the scripts it inspects is the same trap at the
#             meta level.
#
# GUARD MODEL:
#   A cycle is GUARDED iff there is a flag F such that SOME node on the
#   cycle path CHECKS F via ${F:-} (the guard conditional) AND SOME node
#   on the cycle path (the same or a different node) SETS F via `export`
#   or inline `F=` assignment (the guard propagation). The check + set
#   halves of the dataflow must BOTH be present — the existing real-
#   world example has gate.sh:29 exporting CHARON_GATE_ACTIVE and
#   handoff.sh:292 checking it, so the cycle is safe in practice.
#
#   Without this dataflow check, REMOVING gate.sh:29 (the export) would
#   not flip the handoff<->gate cycle to UNGUARDED — the check is in
#   handoff.sh and is unaffected by what gate.sh does. The
#   export+check pair is the entire reentrancy guard; missing either
#   half makes the cycle fork-bomb.
#
#   Recognized reentrancy-flag name suffixes:
#       _ACTIVE / _RUNNING / _LOCK / _BUSY / _REENTER / _NESTED /
#       _RECURSE / _GUARD
#   (plus FLEET_TESTS_DIR, the hermetic-test override convention used
#   by gate.test.sh to redirect gate.sh's test discovery)
#
# NOT-A-CYCLE:
#   A bash invocation is classified as a "fixture" (NOT counted as a real
#   edge) when the target path is rooted at a known temp-dir variable
#   ($D, $d, $WORK, $F, $W, $STRIPPED, $rev, $reg, $M*, $L*, $REG*, $D*)
#   — i.e., the test author has copied the script to a temp dir and is
#   running the COPY. Re-entering a copy of gate.sh under /tmp cannot
#   recurse into the real test suite, so those edges are safe by
#   construction. This classification is heuristic, not airtight —
#   fleet/tests/selfcheck-cycle.test.sh constructs fixtures that
#   intentionally exercise the false-positive case so any future drift
#   in the heuristic goes RED instead of silently misclassifying.
#
# USAGE:
#   fleet/checks/selfcheck-cycle.sh                     # analyze real fleet/
#   fleet/checks/selfcheck-cycle.sh --fleet-root=PATH   # analyze a different root
#   fleet/checks/selfcheck-cycle.sh --json              # machine-readable output
#   exit 0 = GREEN  (no unguarded cycles)
#   exit 1 = RED    (one or more unguarded cycle edges)
#   exit 2 = usage / parse error
#
# RUN CONTEXT:
#   Invoked from fleet/tests/selfcheck-cycle.test.sh. Also picked up by
#   gate.sh implicitly via the *.test.sh convention (gate.sh:33 globs every
#   fleet/tests/*.test.sh and runs them concurrently).
set -uo pipefail
HERE_SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/
FLEET_ROOT="${FLEET_ROOT:-$HERE_SELF}"
JSON_MODE=0
for arg in "$@"; do
  case "$arg" in
    --fleet-root=*) FLEET_ROOT="${arg#--fleet-root=}" ;;
    --json) JSON_MODE=1 ;;
    --help|-h)
      grep '^# ' "$0" | sed 's/^# //'
      exit 0
      ;;
    *) echo "selfcheck-cycle: unknown arg: $arg" >&2; exit 2 ;;
  esac
done
[ -d "$FLEET_ROOT" ] || { echo "selfcheck-cycle: fleet root not found: $FLEET_ROOT" >&2; exit 2; }

# -----------------------------------------------------------------------------
# Heuristic: known "fleet root" path-variable prefixes. A bash invocation
# that uses one of these as the leading component is hitting the REAL
# fleet/, not a fixture copy. Any other leading variable (typical test
# fixtures: $D, $d, $F, $W, $WORK, $STRIPPED, $rev, $REG*, $M*, $L*, etc.)
# is treated as a temp-dir copy and is NOT a real edge.
# -----------------------------------------------------------------------------
REAL_FLEET_VARS='SRC FLEET HERE ROOT FLEET_DIR CHARON_FLEET'

# -----------------------------------------------------------------------------
# Edge extractor — runs as awk over each file. Emits "src|target|kind" lines
# for every bash invocation of a .sh file under the real fleet root.
# -----------------------------------------------------------------------------
# We build the awk program into a file to avoid bash heredoc regex-quoting
# hazards (single-quote safe).
EXTRACTOR="$(mktemp)"
trap 'rm -f "$EXTRACTOR"' EXIT
cat > "$EXTRACTOR" <<'AWK_EOF'
function is_real_edge(raw,   leading, vname) {
  if (raw ~ /^\//) {
    # Absolute path — real iff under FLEET_ROOT or any */fleet/* path.
    if (raw ~ ("^" ENVIRON["FLEET_ROOT"] "/")) return 1
    if (raw ~ /\/fleet\//) return 1
    return 0
  }
  # Relative: peel the first component. Two shapes:
  #   "$VAR/..."      -> leading = "VAR"
  #   "name/..."      -> leading = "name"  (bareword, e.g. "fleet")
  if (match(raw, /^\$\{?([A-Za-z_][A-Za-z0-9_]*)/, m)) vname = m[1]
  else if (match(raw, /^([A-Za-z_][A-Za-z0-9_]*)/, m)) vname = m[1]
  else return 0
  # Look up the variable in the REAL_FLEET_VARS space-delimited list.
  if (index(" " ENVIRON["REAL_FLEET_VARS"] " ", " " vname " ") > 0) return 1
  return 0
}
function classify_kind(line) {
  # The bash/. /source keyword must be in CALL POSITION, not in the middle
  # of an error message or comment. "Call position" = the bash keyword is
  # preceded by: start-of-line, whitespace, `(`, `=`, `;`, `{`, or `|`. We
  # reject lines where `bash` is preceded by a quote that suggests it's
  # inside an echo body (the help-message false positive from the original
  # detector).
  if (line ~ /^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*bash[[:space:]]+/) return "exec"
  # subshell / command-substitution forms: $(bash ...), `bash ...`
  if (line ~ /\$\([[:space:]]*bash[[:space:]]+/) return "exec"
  if (line ~ /`[[:space:]]*bash[[:space:]]+/) return "exec"
  # Variable assignment with command-substitution:  OUT="$(bash ...)" or
  # OUT="$( { VAR=val; bash ... } )" (the brace form is what handoff.sh
  # uses to declare a local FLEET= before invoking gate.sh). Permissive:
  # just require `bash` to appear after the `="`/`='`/`=$(` in the same
  # line. False positives are caught by the path extraction failing (no
  # real fleet path) downstream.
  if (line ~ /[A-Za-z_][A-Za-z0-9_]*=[`"'"'"'$(]/) {
    # Strip everything up to and including the opening quote/paren, then
    # see if `bash` appears in what remains.
    rest = line
    if (match(rest, /[A-Za-z_][A-Za-z0-9_]*=[`"'"'"'$(][^{]*\{?/)) {
      rest = substr(rest, RSTART + RLENGTH)
    }
    if (rest ~ /bash[[:space:]]+/) return "exec"
  }
  # ". " or "source" in call position.
  if (line ~ /^[[:space:]]*\.[[:space:]]+/) return "source"
  if (line ~ /^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*source[[:space:]]+/) return "source"
  return ""
}
function emit_edges(line, src_node,   raw, fname, ftail, rest) {
  rest = line
  while (match(rest, /(\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|\/)[A-Za-z0-9_.\/-]*\.sh/)) {
    raw = substr(rest, RSTART, RLENGTH)
    if (kind == "source") {
      ftail = raw; sub(/.*\//, "", ftail)
      if (ftail == "_lib.sh" || ftail == "lib.sh" || ftail == "common.sh" || ftail == "helpers.sh") {
        rest = substr(rest, RSTART + RLENGTH); continue
      }
    }
    if (is_real_edge(raw)) {
      fname = raw; sub(/.*\//, "", fname); sub(/\.sh$/, "", fname)
      if (fname != "" && fname != src_node) {
        printf "%s|%s|%s\n", src_node, fname, kind
      }
    }
    rest = substr(rest, RSTART + RLENGTH)
  }
}
{
  # Skip comment-only lines.
  t = $0; sub(/^[[:space:]]+/, "", t)
  if (substr(t, 1, 1) == "#") next
  kind = classify_kind($0)
  if (kind == "") next
  emit_edges($0, ENVIRON["SRC_NODE"])
}
AWK_EOF

# -----------------------------------------------------------------------------
# Guard extractor — looks for a reentrancy-flag conditional. The flag
# name must match a reentrancy convention (see is_guard_name below).
# -----------------------------------------------------------------------------
GUARD_EXTRACTOR="$(mktemp)"
trap 'rm -f "$EXTRACTOR" "$GUARD_EXTRACTOR"' EXIT
cat > "$GUARD_EXTRACTOR" <<'AWK_EOF'
function is_guard_name(name) {
  if (name ~ /_ACTIVE$/) return 1
  if (name ~ /_RUNNING$/) return 1
  if (name ~ /_LOCK$/) return 1
  if (name ~ /_BUSY$/) return 1
  if (name ~ /_REENTER$/) return 1
  if (name ~ /_NESTED$/) return 1
  if (name ~ /_RECURSE$/) return 1
  if (name ~ /_GUARD$/) return 1
  return 0
}
# Scan the first 400 lines. The guard is conventionally near the top
# (so a test can read the script and find it cheaply), but a long header
# can push it further down — the real-world handoff.sh guard is at
# line 292, well past the 80-line mark some scripts use.
NR <= 400 {
  # ${X:-} or ${X} form.
  if (match($0, /\$\{([A-Z_][A-Z0-9_]*)(:-)?\}/, m)) {
    if (is_guard_name(m[1])) { print m[1]; exit }
  }
  # "$X" form (no braces) with a UPPER_CASE name.
  if (match($0, /\$[A-Z_][A-Z0-9_]*/)) {
    name = substr($0, RSTART+1, RLENGTH-1)
    if (is_guard_name(name)) { print name; exit }
  }
}
AWK_EOF

# Guard-setter extractor: looks for `export FOO_ACTIVE=...`,
# `FOO_ACTIVE=...` assignments to a reentrancy-flag-named variable, AND
# inline `FLEET_TESTS_DIR=...` assignments (the hermetic-test convention
# used by gate.test.sh to redirect gate.sh's test discovery).
# A node that SETS a guard is the one whose environment propagation
# makes the cycle safe at runtime. The matching CHECK must live in a
# successor on the cycle.
GUARD_SETTER_EXTRACTOR="$(mktemp)"
trap 'rm -f "$EXTRACTOR" "$GUARD_EXTRACTOR" "$GUARD_SETTER_EXTRACTOR"' EXIT
cat > "$GUARD_SETTER_EXTRACTOR" <<'AWK_EOF'
function is_guard_name(name) {
  if (name ~ /_ACTIVE$/) return 1
  if (name ~ /_RUNNING$/) return 1
  if (name ~ /_LOCK$/) return 1
  if (name ~ /_BUSY$/) return 1
  if (name ~ /_REENTER$/) return 1
  if (name ~ /_NESTED$/) return 1
  if (name ~ /_RECURSE$/) return 1
  if (name ~ /_GUARD$/) return 1
  return 0
}
# Look for `export FOO=1` (anywhere in the file, not just the first
# 400 lines — the export is a deliberate setup and may live at line 30
# or line 3000; the cycle guard's purpose is to ALWAYS be set).
{
  if (match($0, /^[ \t]*export[ \t]+([A-Z_][A-Z0-9_]*)=/, m)) {
    if (is_guard_name(m[1])) { print m[1]; exit }
  }
  # Inline `FOO_ACTIVE=1 ...` or `FOO_ACTIVE=...` assignments.
  if (match($0, /(^|[^A-Za-z0-9_])([A-Z_][A-Z0-9_]*)=/, m)) {
    if (is_guard_name(m[2])) { print m[2]; exit }
  }
  # FLEET_TESTS_DIR inline — the hermetic-test convention for the
  # gate.test.sh / gate.sh cycle. gate.sh reads this var, so setting it
  # in the caller breaks the recursion.
  if (match($0, /(^|[^A-Za-z0-9_])FLEET_TESTS_DIR=/)) {
    print "FLEET_TESTS_DIR"; exit
  }
}
AWK_EOF

# -----------------------------------------------------------------------------
# File discovery + graph build.
# -----------------------------------------------------------------------------
mapfile -t ALL_SCRIPTS < <(
  find "$FLEET_ROOT" -maxdepth 3 -type f -name '*.sh' \
    ! -path '*/benchmark/*' ! -path '*/fixtures/*' \
    | sort
)

declare -A NODES=()
declare -A EDGES=()
# GUARDS["node"] = "GUARD_FLAG_NAME" — node has a check for this guard
# GUARD_SETS["node"] = "GUARD_FLAG_NAME" — node has an `export` of this guard
# A cycle is "guarded" iff there exists a node N in the cycle path with
# GUARDS[N]=F AND there exists a node M in the cycle path with
# GUARD_SETS[M]=F (M may be a different node — typically the test-runner
# that starts the chain). This dataflow check ensures that REMOVING the
# `export CHARON_GATE_ACTIVE=1` from gate.sh is detected as making the
# handoff<->gate cycle unguarded, even though handoff.sh's check remains.
declare -A GUARDS=()
declare -A GUARD_SETS=()

for f in "${ALL_SCRIPTS[@]}"; do
  node="$(basename "$f" .sh)"
  [ -n "$node" ] || continue
  NODES["$node"]=1
  g="$(awk -f "$GUARD_EXTRACTOR" "$f")"
  [ -n "$g" ] && GUARDS["$node"]="$g"
  gs="$(awk -f "$GUARD_SETTER_EXTRACTOR" "$f")"
  [ -n "$gs" ] && GUARD_SETS["$node"]="$gs"
  # Env-override guard: a test that sets FLEET_TESTS_DIR to a non-fleet
  # path hermetically redirects gate.sh's test discovery, breaking the
  # gate<->test cycle at runtime even if the static call graph still
  # contains the edge. Without this signal, gate.test.sh would falsely
  # flag the gate<->gate.test cycle as unguarded.
  if grep -qE 'FLEET_TESTS_DIR=' "$f" 2>/dev/null; then
    GUARDS["$node"]="${GUARDS[$node]:-FLEET_TESTS_DIR}"
  fi
done

for f in "${ALL_SCRIPTS[@]}"; do
  node="$(basename "$f" .sh)"
  [ -n "$node" ] || continue
  while IFS='|' read -r src tgt kd; do
    [ -n "$src" ] && [ -n "$tgt" ] || continue
    EDGES["$src|$tgt"]="$kd"
  done < <(SRC_NODE="$node" FLEET_ROOT="$FLEET_ROOT" REAL_FLEET_VARS="$REAL_FLEET_VARS" \
            awk -f "$EXTRACTOR" "$f")
done

# -----------------------------------------------------------------------------
# "Test runner" edge injection: a script that iterates over a glob matching
# fleet/tests/*.test.sh and runs each entry IS A PARENT of every test file,
# even if the static call-site doesn't name individual tests. The literal
# cycle gate.sh <-> handoff-mechanize.test.sh <-> handoff.sh <-> gate.sh only
# becomes visible when we add the runner edge.
#
# We detect a runner by scanning each fleet/*.sh for the pattern
# `*.test.sh` (typical test-runner glob). If found, that script gets a
# synthetic edge to every node in NODES that ENDS IN `.test`. We do NOT add
# a reverse edge from the tests to the runner — the runner is the PARENT,
# not a child, of the tests.
# -----------------------------------------------------------------------------
TEST_RUNNERS=()
for f in "${ALL_SCRIPTS[@]}"; do
  node="$(basename "$f" .sh)"
  [ -n "$node" ] || continue
  if grep -qE '\*\.test\.sh' "$f" 2>/dev/null; then
    TEST_RUNNERS+=("$node")
  fi
done
for runner in "${TEST_RUNNERS[@]}"; do
  for tgt in "${!NODES[@]}"; do
    case "$tgt" in
      *.test)
        EDGES["$runner|$tgt"]="runner"
        ;;
    esac
  done
done

# -----------------------------------------------------------------------------
# Cycle detection (DFS with path tracking, bounded depth).
# A cycle is reported as: "A -> B -> ... -> A".
# A cycle is GUARDED iff ANY node along the cycle path has a recorded
# guard. Why "any" rather than "every": the real-world handoff.sh cycle
# (gate -> handoff-mechanize.test -> handoff -> gate) is made safe by the
# SINGLE guard at handoff.sh — when handoff detects reentrancy, it skips
# its call to gate.sh, the cycle never closes, and the recursion is
# broken. Requiring every node to be guarded would forbid this pattern
# and force the reentrancy-detection logic to be distributed across all
# scripts on the cycle, which is neither necessary nor how the
# gate.sh:29 / handoff.sh:292 guard is actually structured.
# A cycle that has NO guarded node is UNGUARDED and is a HARD FAIL.
# -----------------------------------------------------------------------------
MAX_CYCLE_LEN=8
declare -a UNGUARDED_CYCLES=()
declare -a GUARDED_CYCLES=()

dfs() {
  local current="$1" start="$2" depth="$3" path="$4"
  if [ "$depth" -gt "$MAX_CYCLE_LEN" ]; then return; fi
  local edge_key next
  for edge_key in "${!EDGES[@]}"; do
    case "$edge_key" in
      "$current|"*)
        next="${edge_key#*|}"
        if [ "$next" = "$start" ] && [ "$depth" -ge 1 ]; then
          local cycle="$path -> $next"
          # Cycle is guarded iff there is a flag F such that SOME node in
          # the cycle CHECKS F (GUARDS) AND SOME node (possibly the same)
          # SETS F via `export` or inline `VAR=val bash ...` (GUARD_SETS,
          # which the extractor detects as either `export VAR=...` OR the
          # `FLEET_TESTS_DIR=` inline convention used by hermetic tests).
          local has_guard=0
          local -a cycle_guards=()
          local _tmp="${cycle// -> /$'\x1f'}"
          IFS=$'\x1f' read -r -a path_nodes <<< "$_tmp"
          [ "${SELFCHECK_DIAG:-0}" = "1" ] && {
            echo "DIAG cycle=$cycle" >&2
            echo "DIAG   path_nodes count=${#path_nodes[@]}" >&2
            for n in "${path_nodes[@]}"; do
              g="${GUARDS[$n]:-NONE}"; s="${GUARD_SETS[$n]:-NONE}"
              echo "DIAG   node=[$n] check=[$g] set=[$s]" >&2
            done
            echo "DIAG   cycle_guards=${cycle_guards[*]:-}" >&2
          }
          for edge_target in "${path_nodes[@]}"; do
            edge_target="${edge_target## }"; edge_target="${edge_target%% }"
            [ -n "$edge_target" ] || continue
            [ "${SELFCHECK_DIAG:-0}" = "1" ] && echo "DIAG   check [$edge_target] GUARDS+_=[${GUARDS[$edge_target]+_}] val=[${GUARDS[$edge_target]:-NONE}]" >&2
            if [ -n "${GUARDS[$edge_target]+_}" ]; then
              cycle_guards+=("${GUARDS[$edge_target]}")
            fi
          done
          [ "${SELFCHECK_DIAG:-0}" = "1" ] && echo "DIAG cycle_guards after first loop: [${cycle_guards[*]:-empty}]" >&2
          # Iterate cycle_guards. The `${arr[@]:-}` default-expansion
          # would yield a single empty string for an empty array (a bash
          # footgun: with set -u you can't `${arr[@]}` an unset array, so
          # the conventional `:-` workaround leaks an empty iteration).
          # We use the explicit length check instead.
          if [ "${#cycle_guards[@]}" -gt 0 ]; then
            for g in "${cycle_guards[@]}"; do
              for edge_target in "${path_nodes[@]}"; do
                edge_target="${edge_target## }"; edge_target="${edge_target%% }"
                [ -n "$edge_target" ] || continue
                [ "${SELFCHECK_DIAG:-0}" = "1" ] && echo "DIAG   match [$edge_target] GUARD_SETS=[${GUARD_SETS[$edge_target]:-NONE}] vs g=[$g]" >&2
                if [ "${GUARD_SETS[$edge_target]:-}" = "$g" ]; then
                  has_guard=1
                  break
                fi
              done
              [ "$has_guard" = "1" ] && break
            done
          fi
          if [ "$has_guard" = "1" ]; then
            GUARDED_CYCLES+=("$cycle")
            [ "${SELFCHECK_DIAG:-0}" = "1" ] && echo "DIAG ADDED TO GUARDED: $cycle" >&2
          else
            UNGUARDED_CYCLES+=("$cycle")
            [ "${SELFCHECK_DIAG:-0}" = "1" ] && echo "DIAG ADDED TO UNGUARDED: $cycle (cycle_guards=${cycle_guards[*]:-empty})" >&2
          fi
          continue
        fi
        case " $path " in
          *" $next "*) continue ;;
        esac
        dfs "$next" "$start" "$((depth+1))" "$path -> $next"
        ;;
    esac
  done
}

for n in "${!NODES[@]}"; do
  dfs "$n" "$n" 0 "$n"
done

# -----------------------------------------------------------------------------
# De-dup cycles (same cycle can be reported from each start; same length-2
# cycle from both ends).
# -----------------------------------------------------------------------------
declare -A SEEN=()
declare -A UNGUARDED_SEEN=()
declare -A GUARDED_SEEN=()
dedup_cycle() {
  local c="$1" bucket="$2"
  local -a nodes
  local _tmp="${c// -> /$'\x1f'}"
  IFS=$'\x1f' read -r -a nodes <<< "$_tmp"
  local sorted
  sorted="$(printf '%s\n' "${nodes[@]}" | sort | paste -sd'|')"
  if [ -z "${SEEN[$sorted]+_}" ]; then
    SEEN[$sorted]=1
    if [ "$bucket" = "unguarded" ]; then
      UNGUARDED_SEEN[$sorted]="$c"
    else
      GUARDED_SEEN[$sorted]="$c"
    fi
  fi
}
if [ "${#UNGUARDED_CYCLES[@]}" -gt 0 ]; then
  for c in "${UNGUARDED_CYCLES[@]}"; do [ -n "${c:-}" ] && dedup_cycle "$c" unguarded; done
fi
if [ "${#GUARDED_CYCLES[@]}" -gt 0 ]; then
  for c in "${GUARDED_CYCLES[@]}"; do [ -n "${c:-}" ] && dedup_cycle "$c" guarded; done
fi

unguarded_count=0
guarded_count=0
for _ in "${!UNGUARDED_SEEN[@]}"; do unguarded_count=$((unguarded_count+1)); done
for _ in "${!GUARDED_SEEN[@]}"; do guarded_count=$((guarded_count+1)); done

# -----------------------------------------------------------------------------
# Report.
# -----------------------------------------------------------------------------
if [ "$JSON_MODE" = "1" ]; then
  printf '{\n'
  printf '  "unguarded_cycles": %d,\n' "$unguarded_count"
  printf '  "guarded_cycles": %d,\n' "$guarded_count"
  printf '  "unguarded": [\n'
  first=1
  for k in "${!UNGUARDED_SEEN[@]}"; do
    if [ "$first" = "1" ]; then first=0; else printf ',\n'; fi
    printf '    %s' "$(printf '%s' "${UNGUARDED_SEEN[$k]}" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read().rstrip()))')"
  done
  printf '\n  ],\n'
  printf '  "guarded": [\n'
  first=1
  for k in "${!GUARDED_SEEN[@]}"; do
    if [ "$first" = "1" ]; then first=0; else printf ',\n'; fi
    printf '    %s' "$(printf '%s' "${GUARDED_SEEN[$k]}" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read().rstrip()))')"
  done
  printf '\n  ]\n'
  printf '}\n'
else
  echo "selfcheck-cycle: fleet root = $FLEET_ROOT"
  echo "selfcheck-cycle: nodes = ${#NODES[@]}, edges = ${#EDGES[@]}, guarded scripts = ${#GUARDS[@]}"
  echo "selfcheck-cycle: guarded cycles = $guarded_count, UNGUARDED cycles = $unguarded_count"
  if [ "$unguarded_count" -gt 0 ]; then
    echo
    echo "UNGUARDED CYCLES (would re-enter the suite — FORK-BOMB class):"
    for k in "${!UNGUARDED_SEEN[@]}"; do
      echo "  - ${UNGUARDED_SEEN[$k]}"
    done
    echo
    echo "selfcheck-cycle: RED — at least one unguarded reentrancy edge. Add a"
    echo "  guard (e.g., export SOME_FLAG=1 at the top of the OUTER script;"
    echo "  check \${SOME_FLAG:-} in the INNER script and skip/exit early) or"
    echo "  refactor so the cycle does not exist (e.g., copy the script into"
    echo "  a temp dir under a fixture var and run the copy, not the real one)."
  else
    echo
    echo "selfcheck-cycle: GREEN — no unguarded self-referential edges."
    if [ "$guarded_count" -gt 0 ]; then
      echo "  guarded cycles (safe by guard, but worth knowing about):"
      for k in "${!GUARDED_SEEN[@]}"; do
        echo "    - ${GUARDED_SEEN[$k]}"
      done
    fi
  fi
fi

if [ "$unguarded_count" -gt 0 ]; then exit 1; fi
exit 0
