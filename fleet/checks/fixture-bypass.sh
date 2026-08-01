#!/usr/bin/env bash
# fixture-bypass.sh — detects test suites that are GREEN over a production path they never run.
#
# THE DEFECT CLASS (six confirmed instances on this rig in a single day, 2026-07-19):
#   A suite is fully green while the code it claims to cover is broken or absent, because every
#   test case takes a FIXTURE/STUB/ENV BYPASS that returns before the production path is reached.
#     1-3. branch-reaper.test.sh — 38/38 green while three separate guards were gutted; two of
#          those guards had no test at all (`:` / early `return 0` kept 38/38 green).
#     4.   dogfood-eval-guard.test.sh — 4 of 11 gutting mutations left it green, including a test
#          whose own header CLAIMED fail-on-revert.
#     5.   land-push-ci-gate.test.sh — gutting the RED={"FAILURE"} semantics kept 9/9 green.
#     6.   test_github_limits.sh — every owns-match test sets GH_MERGED_FILES_FIXTURE, which
#          returns before the gh call. A reviewer replaced the ENTIRE production invocation with
#          `if false; then :` and 19/19 still passed. The feature was dead on arrival (`-r` is not
#          a valid gh flag) and the suite structurally could not see it.
#   Unifying shape: A FIXTURE/ENV/STUB SEAM WITH NO TEST THAT RUNS PAST IT.
#   Assertion count is not coverage. Green is not proof [[green-is-not-proof]].
#
# WHY A SEPARATE CHECK (anti-accretion): fleet/checks/gate-creation-standard.sh asks "does this
# gate HAVE a red-proof test?" — a presence question. This asks the orthogonal question "does that
# test actually REACH the production code?" Instances 1-6 all HAD companion tests; every one of
# them satisfied gate-creation-standard and still shipped a dead production path. Neither check
# subsumes the other and neither should absorb the other's logic.
#
# TWO DETECTIONS, deliberately few and high-confidence. A gate that cries wolf gets disabled —
# which is precisely the "gate stops actually running" failure this exists to prevent
# [[gates-must-actually-run]].
#
#   D1 TOTAL-FIXTURE  (static, cheap, DEFAULT, ADVISORY)
#       A fixture/stub env var that (a) guards a SHORT-CIRCUIT in production code — an early
#       return/exit inside `if [ -n "${VAR:-}" ]` — and (b) is set by at least one suite, but
#       (c) is NEVER unset or emptied by ANY suite in the tree. (c) is the load-bearing clause:
#       it means no test anywhere leaves the seam closed, so the post-seam production path has
#       zero executions. This is EXACTLY instance 6's shape.
#       Why low-noise: it fires only on vars that are BOTH a real short-circuit AND already
#       exercised by tests. A var no test sets is not flagged (its production path runs normally).
#       A var with even ONE `unset`/`env -u`/empty-assign anywhere is not flagged (some test does
#       reach the real path). On the tree as of this commit that is 3 findings out of 4 candidate
#       seams — see `report` for the per-var breakdown.
#
#   D2 NOOP-SURVIVAL  (mutation, expensive, OPT-IN `deep`, never wired)
#       Copy the tree to a scratch dir, replace a suite's primary production entry point with a
#       no-op (`exit 0`), re-run the suite IN THE COPY. If it still passes, the suite does not
#       depend on that production script at all — instances 1-5's shape, which no static pattern
#       can see. This is the strongest signal available.
#       It is OPT-IN AND UNWIRED ON PURPOSE, for two reasons, not one:
#         (i)  cost — it re-runs whole suites, and fleet/tests/ contains BENCHMARK GRADER suites
#              that invoke live models over the network and block for HOURS;
#         (ii) blast radius — a suite that hardcodes absolute paths will write to the LIVE tree
#              even when launched from the copy, and this rig runs several worktree agents
#              concurrently. Deep mode is a deliberate operator action against a NAMED suite,
#              never a background sweep. Never add it to preflight or CI.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: a gate that runs tests which re-invoke the gate
# is a fork bomb. D2 hard-refuses its own suite and rig-ci.test.sh (which runs the CI allowlist,
# which includes this gate's suite), and sets FIXTURE_BYPASS_ACTIVE=1 in the child environment so
# any nested invocation refuses. D1 is pure file inspection: no suite execution, no network, no gh.
#
# READ-ONLY: this script never writes outside its own report and a mktemp -d scratch dir. It never
# rm's, never touches git refs, never auto-fixes. Findings are reported for a human to act on.
#
# Usage:
#   fixture-bypass.sh scan            D1 over the tree. ADVISORY: prints findings, ALWAYS exit 0.
#   fixture-bypass.sh check           D1 over the tree. HARD: exit 1 if any finding. (Not wired;
#                                     available for a future ratchet once the tree is at zero.)
#   fixture-bypass.sh report          D1 with the full candidate/covered/flagged breakdown.
#   fixture-bypass.sh deep <suite> [entry]
#                                     D2 against ONE named suite; exit 1 if the suite survives the
#                                     no-op mutation. <entry> is the production script to neuter,
#                                     derived from the suite name when omitted. Opt-in only.
# Env seams (self-test overrides; defaults are the real fleet/):
#   FB_ROOT        repo root to inspect        (default: this script's repo)
#   FB_TESTS_DIR   suite directory             (default: $FB_ROOT/fleet/tests)
#   FB_DEEP_TIMEOUT  seconds for a deep run    (default: 300)
# Exit: 0 = GREEN/advisory, 1 = RED, 2 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root (script in fleet/checks/)
ROOT="${FB_ROOT:-$HERE}"
TESTS_DIR="${FB_TESTS_DIR:-$ROOT/fleet/tests}"
DEEP_TIMEOUT="${FB_DEEP_TIMEOUT:-300}"

# Reentrancy guard. Set unconditionally for children; refuse if we are already a child.
if [ -n "${FIXTURE_BYPASS_ACTIVE:-}" ]; then
  echo "fixture-bypass: refusing to run inside a fixture-bypass child (reentrancy guard)." >&2
  exit 0
fi

RED=0
finding(){ RED=1; echo "FIXTURE-BYPASS: $*"; }

# ---- D1: TOTAL-FIXTURE -----------------------------------------------------------------------
# Production files = every *.sh under the repo EXCEPT the suite directory. Test files may legally
# define and set fixture vars; only production code can own a bypass seam.
_prod_files(){
  local rel_tests="${TESTS_DIR#$ROOT/}"
  git -C "$ROOT" ls-files '*.sh' 2>/dev/null | grep -v "^${rel_tests}/" \
    || find "$ROOT" -name '*.sh' -not -path "$TESTS_DIR/*" -printf '%P\n' 2>/dev/null
}

# A var is a SHORT-CIRCUIT SEAM if a production line both tests it for non-emptiness and, on that
# same line or the two following, returns/exits. Restricting to the 3-line window is what keeps
# this from flagging vars that merely SOURCE a value (e.g. a fake-dir prefix used mid-function)
# rather than SKIPPING the production path. Names are limited to the fixture/stub family so that
# ordinary config vars (CHARON_HOME, RIG_CI_BASE) can never be mistaken for a test seam.
FB_NAME_RE='[A-Z][A-Z0-9_]*(_FIXTURE|_STUB|_FAKE|_MOCK)[A-Z0-9_]*'

_seam_vars(){
  local f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$ROOT/$f" ] || continue
    grep -nE "if[[:space:]]+\[[[:space:]]+-n[[:space:]]+\"?\\\$\{?${FB_NAME_RE}" "$ROOT/$f" 2>/dev/null \
    | while IFS=: read -r ln _; do
        # 3-line window starting at the guard: does it short-circuit?
        if sed -n "${ln},$((ln+2))p" "$ROOT/$f" 2>/dev/null \
           | grep -qE '(^|[;[:space:]&|])(return|exit)([[:space:]]|$)'; then
          sed -n "${ln}p" "$ROOT/$f" | grep -oE "$FB_NAME_RE" | head -1 \
            | sed "s|\$|\t$f:$ln|"
        fi
      done
  done < <(_prod_files)
}

# A suite RELEASES a seam if it ever unsets it, empties it, or runs a command with `env -u VAR`.
# Any ONE such site anywhere in the tree proves some test reaches the post-seam production path.
_releases(){
  local v="$1"
  grep -rlE "(^|[[:space:]])unset([[:space:]]+[A-Z0-9_]+)*[[:space:]]+${v}([[:space:]]|$)|env[[:space:]]+(-[a-zA-Z]+[[:space:]]+)*-u[[:space:]]+${v}([[:space:]]|$)|(^|[[:space:];(])${v}=([\"']{2})?([[:space:]]|$|;)" \
    "$TESTS_DIR" 2>/dev/null | head -1
}

_sets(){ grep -rlE "(^|[[:space:]&;(])(export[[:space:]]+)?${1}=" "$TESTS_DIR" 2>/dev/null | head -1; }

cmd_d1(){
  local verbose="${1:-0}"
  local seen="" v site n_cand=0 n_cov=0
  while IFS=$'\t' read -r v site; do
    [ -n "$v" ] || continue
    case " $seen " in *" $v "*) continue;; esac
    seen="$seen $v"
    n_cand=$((n_cand+1))
    local setter; setter="$(_sets "$v")"
    if [ -z "$setter" ]; then
      [ "$verbose" = 1 ] && echo "     skip  $v — no suite sets it; production path runs unbypassed ($site)"
      continue
    fi
    local rel; rel="$(_releases "$v")"
    if [ -n "$rel" ]; then
      n_cov=$((n_cov+1))
      [ "$verbose" = 1 ] && echo "     ok    $v — released by ${rel#$ROOT/} (a test reaches the real path)"
      continue
    fi
    finding "D1 TOTAL-FIXTURE: \$$v short-circuits production at $site, is set by"
    echo "     ${setter#$ROOT/}, and is NEVER unset/emptied by ANY suite in $(basename "$TESTS_DIR")/."
    echo "     => every test takes the bypass; the code after that seam has zero test executions."
    echo "     FIX: add one case that leaves \$$v unset (or \`env -u $v\`) and asserts the real path."
  done < <(_seam_vars | sort -u)
  echo "fixture-bypass: $n_cand short-circuit fixture seam(s) inspected, $n_cov released by a test."
}

# ---- D2: NOOP-SURVIVAL -----------------------------------------------------------------------
# Name convention: fleet/tests/X.test.sh -> fleet/X.sh or fleet/checks/X.sh.
_entry_for(){
  local base; base="$(basename "$1")"; base="${base%.test.sh}"; base="${base%.sh}"
  local c
  for c in "fleet/$base.sh" "fleet/checks/$base.sh"; do
    [ -f "$ROOT/$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

cmd_deep(){
  local suite="${1:-}"
  [ -n "$suite" ] || { echo "usage: fixture-bypass.sh deep <suite.test.sh>" >&2; return 2; }
  local sbase; sbase="$(basename "$suite")"
  # Fork-bomb refusals: our own suite, and rig-ci.test.sh which runs the CI allowlist (us included).
  case "$sbase" in
    fixture-bypass.test.sh|rig-ci.test.sh)
      echo "fixture-bypass: REFUSING deep mode on $sbase — it re-invokes this gate (fork-bomb class)." >&2
      return 2 ;;
  esac
  local spath="$TESTS_DIR/$sbase"
  [ -f "$spath" ] || { echo "fixture-bypass: no such suite: $spath" >&2; return 2; }
  # The entry point may be named explicitly. Name-convention derivation only resolves suites whose
  # production script shares their name (branch-reaper.test.sh -> fleet/branch-reaper.sh); several
  # real suites do not (land-push-ci-gate.test.sh guards fleet/land-push.sh), so the operator can
  # pass the path. Guessing wrong here would print a confident verdict about the wrong file.
  local entry="${2:-}"
  if [ -n "$entry" ]; then
    [ -f "$ROOT/$entry" ] || { echo "fixture-bypass: no such entry point: $ROOT/$entry" >&2; return 2; }
  else
    entry="$(_entry_for "$sbase")" || {
      echo "fixture-bypass: cannot derive a production entry point for $sbase" >&2
      echo "     (looked for fleet/<name>.sh and fleet/checks/<name>.sh)" >&2
      echo "     Pass it explicitly: fixture-bypass.sh deep $sbase fleet/<entry>.sh" >&2
      return 2; }
  fi

  local tmp; tmp="$(mktemp -d "${TMPDIR:-/tmp}/fixture-bypass.XXXXXX")" || return 2
  echo "     deep: $sbase vs $entry (scratch copy: $tmp)"
  cp -a "$ROOT/." "$tmp/" 2>/dev/null
  printf '#!/usr/bin/env bash\n# NO-OP MUTANT injected by fixture-bypass.sh deep mode.\nexit 0\n' \
    > "$tmp/$entry"

  local out rc
  out="$(cd "$tmp" && FIXTURE_BYPASS_ACTIVE=1 timeout "$DEEP_TIMEOUT" bash "$tmp/fleet/tests/$sbase" 2>&1)"; rc=$?
  if [ "$rc" -eq 124 ]; then
    echo "     deep: INCONCLUSIVE — $sbase exceeded FB_DEEP_TIMEOUT=${DEEP_TIMEOUT}s under mutation."
    rm -rf "$tmp"; return 0
  fi
  if [ "$rc" -eq 0 ]; then
    finding "D2 NOOP-SURVIVAL: $sbase still PASSES with $entry replaced by a no-op."
    echo "     => the suite never depends on that production path. Its green proves nothing about it."
    echo "     FIX: add a case that invokes $entry for real and asserts an observable effect."
  else
    echo "     deep: ok — $sbase goes RED (rc=$rc) when $entry is no-op'd."
  fi
  printf '%s\n' "$out" | tail -3 | sed 's/^/       | /'
  rm -rf "$tmp"
  return $RED
}

case "${1:-}" in
  scan)   cmd_d1 0; exit 0 ;;                 # ADVISORY: findings printed, never blocks.
  check)  cmd_d1 0; exit $RED ;;
  report) echo "--- fixture-bypass D1 report ---"; cmd_d1 1; exit 0 ;;
  deep)   shift; cmd_deep "$@"; exit $? ;;
  *) echo "usage: fixture-bypass.sh {scan|check|report|deep <suite.test.sh>}" >&2; exit 2 ;;
esac
