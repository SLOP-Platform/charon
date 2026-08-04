#!/usr/bin/env bash
# semgrep.sh — thin wrapper over the ADOPTED Semgrep engine. Runs the git-tracked ruleset
# (.github/scripts/semgrep-rules/) and EXITS NON-ZERO on any finding, so it can serve as a
# merge-blocking required check. This is a wrapper, NOT a linter: all detection lives in semgrep
# + the yaml rules.
#
# CI-ONLY. This directory (.github/scripts/) is build/CI infrastructure that ships with the repo
# but is NOT product code: it is not on the import path, not linted as src/, and not typechecked.
#
# SCOPE:
#   default        — scan the whole tracked tree (semgrep honors .gitignore/.semgrepignore).
#   --diff         — scan the files changed between base and head, then keep only findings on
#                    lines the diff ADDED (see diff_filter.py). Head is CHARON_CI_HEAD or HEAD;
#                    base is CHARON_CI_BASE, else resolve_base() in _common.sh (the merge ref's
#                    FIRST PARENT — read that function's comment before changing it).
#                    If the merge-base cannot resolve, we FAIL CLOSED (exit 2) rather than scan
#                    nothing and report green — a scan-nothing green is the false receipt this
#                    gate exists to prevent.
#   [PATHS...]     — scan exactly the given paths (used by the canary with a fixture file).
#
# CONFIG override: SEMGREP_RULES_DIR (default .github/scripts/semgrep-rules) lets the canary point
# the SAME wrapper at a neutered ruleset copy to prove the rules are load-bearing.
#
# EXIT: 0 = no findings; 1 = at least one finding (blocks merge); 2 = wrapper/scope error (incl. a
#       vacuous zero-rule ruleset, which the wrapper refuses to run — see the guard below).
set -uo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS/../.." && pwd)"
# shellcheck source=.github/scripts/_common.sh
. "$SCRIPTS/_common.sh"
RULES="${SEMGREP_RULES_DIR:-$SCRIPTS/semgrep-rules}"
# Intentionally-bad canary fixtures. Excluded from diff scans; the canary still scans them by
# EXPLICIT path, so detection is unaffected.
FIXTURES='.github/scripts/fixtures/'

command -v semgrep >/dev/null 2>&1 || {
  echo "semgrep.sh: FAIL — semgrep is not installed (adopt the engine: 'pip install semgrep==<pin>')." >&2
  exit 2
}
[ -d "$RULES" ] || { echo "semgrep.sh: FAIL — ruleset dir not found: $RULES" >&2; exit 2; }

# VACUOUS-RULESET GUARD (wrapper-owned, VERSION-INDEPENDENT). A ruleset that loads ZERO rules can never
# find anything, so its exit-0 is a false green. We do NOT lean on semgrep's --strict to red an empty
# ruleset: that behavior is semgrep-VERSION-DEPENDENT — older semgrep (~1.161) errors on `rules: []`,
# but newer semgrep (>=1.170) treats a no-rules directory config as a clean pass (exit 0). So the
# wrapper counts rule definitions ITSELF and FAILS CLOSED (exit 2) on zero. Every valid semgrep rule
# carries an `id:`, so counting top-level `- id:` entries across the ruleset yaml is a stable proxy for
# "how many rules will actually run" — stable across semgrep versions.
rule_count="$(grep -rhE '^[[:space:]]*-[[:space:]]+id:[[:space:]]*\S' "$RULES" --include='*.yml' --include='*.yaml' 2>/dev/null | wc -l | tr -d '[:space:]')"
if [ "${rule_count:-0}" -eq 0 ]; then
  echo "semgrep.sh: FAIL — ruleset dir '$RULES' loads ZERO rules (vacuous); refusing to scan. A no-rules scan can never find anything, so its green is a false receipt (fail closed)." >&2
  exit 2
fi

mode="tree"
declare -a paths=()
while [ $# -gt 0 ]; do
  case "$1" in
    --diff) mode="diff" ;;
    --) shift; mode="paths"; while [ $# -gt 0 ]; do paths+=("$1"); shift; done; break ;;
    -*) echo "semgrep.sh: unknown flag: $1" >&2; exit 2 ;;
    *)  mode="paths"; paths+=("$1") ;;
  esac
  shift
done

py_changed=0
if [ "$mode" = "diff" ]; then
  base="$(resolve_base "$ROOT")"
  head="${CHARON_CI_HEAD:-HEAD}"
  mb="$(git -C "$ROOT" merge-base "$base" "$head" 2>/dev/null)" || mb=""
  if [ -z "$mb" ]; then
    echo "semgrep.sh: FAIL — cannot resolve merge-base($base,$head); refusing to scan nothing (fail closed)." >&2
    exit 2
  fi
  # NUL-safe listing (see _common.sh): git C-quotes non-ASCII paths by default, and the
  # reconstructed path then does not exist — which turned a real finding into a green elsewhere.
  # The fixtures dir is excluded: those files are INTENTIONALLY-bad canary fixtures, so scanning
  # them would make a PR that adds a fixture block itself. The canary scans them by EXPLICIT path.
  while IFS= read -r -d '' p; do
    case "$p" in "$FIXTURES"*) continue ;; esac
    case "$p" in *.py) py_changed=$((py_changed+1)) ;; esac
    paths+=("$ROOT/$p")
  done < <(changed_files "$ROOT" "$mb" "$head")
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "semgrep.sh: OK — no changed files in $base..$head to scan."
    exit 0
  fi
  # FAIL CLOSED before scanning: an unreadable or vanished target is a scan that reads nothing.
  require_readable "semgrep.sh" "${paths[@]}"
fi

declare -a targets
if [ "$mode" = "tree" ]; then
  targets=("$ROOT")
else
  targets=("${paths[@]}")
fi

if [ "$mode" != "diff" ]; then
  # --error: exit 1 on any finding. --strict: fail on rule/parse errors (a broken ruleset must
  # red, not silently pass). --quiet keeps output to findings only.
  semgrep scan --config "$RULES" --error --strict --quiet "${targets[@]}"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "semgrep.sh: OK — no policy findings (${mode})."
  fi
  exit "$rc"
fi

# DIFF MODE — same scan, JSON output, then LINE-SCOPED so only findings on lines this PR ADDED can
# block. Measured on master 2026-08-04 the ruleset is clean across src/, tools/ and tests/ (0
# findings), so nothing is being carved out today; the line scoping keeps this gate's semantics
# IDENTICAL to its bandit/gitleaks siblings rather than leaving a third, subtly different rule for
# the next reader to discover. --strict still turns a broken ruleset into a non-zero exit, which
# is treated as fail-closed below.
report="$(semgrep scan --config "$RULES" --error --strict --quiet --json "${targets[@]}" 2>/dev/null)"
rc=$?
if [ "$rc" -gt 1 ]; then
  echo "semgrep.sh: FAIL — semgrep errored (exit $rc); failing closed." >&2
  exit 2
fi
# A non-empty `errors` array means a rule failed to parse or a target could not be analysed. That
# is a scan that did not do its job, so it must NEVER read as green.
nerr="$(printf '%s' "$report" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("errors",[])))' 2>/dev/null)" || nerr=""
if [ -z "$nerr" ]; then
  echo "semgrep.sh: FAIL — semgrep produced no parseable JSON report; failing closed." >&2
  exit 2
fi
if [ "$nerr" -ne 0 ]; then
  echo "semgrep.sh: FAIL — semgrep reported $nerr scan/rule error(s); failing closed." >&2
  printf '%s' "$report" | python3 -c 'import sys,json;[print("  error:",e.get("message","")[:200]) for e in json.load(sys.stdin).get("errors",[])]' 2>/dev/null || true
  exit 2
fi

# FILES-ANALYSED GUARD. Every rule in the ruleset is currently `languages: [python]`, so if this
# diff changed Python files and semgrep still analysed ZERO of them, the scan did no work and its
# exit-0 is a false receipt. (A PR with no Python legitimately analyses nothing — that is not a
# vacuous green, so it is not gated here.)
nscanned="$(printf '%s' "$report" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("paths",{}).get("scanned",[])))' 2>/dev/null)" || nscanned=""
if [ -z "$nscanned" ]; then
  echo "semgrep.sh: FAIL — semgrep report carries no paths.scanned; failing closed." >&2
  exit 2
fi
if [ "$py_changed" -gt 0 ] && [ "$nscanned" -eq 0 ]; then
  echo "semgrep.sh: FAIL — $py_changed changed Python file(s) but semgrep analysed ZERO files;" >&2
  echo "  refusing to report green on a scan that did no work (fail closed)." >&2
  exit 2
fi

kept="$(printf '%s' "$report" | python3 "$SCRIPTS/diff_filter.py" \
  --kind semgrep --base "$base" --head "$head" --root "$ROOT" --exclude-prefix "$FIXTURES")"
frc=$?
if [ "$frc" -ne 0 ]; then
  echo "semgrep.sh: FAIL — diff_filter failed (exit $frc); failing closed." >&2
  exit 2
fi
if [ "${kept:-0}" -ge 1 ]; then
  echo "semgrep.sh: FINDINGS — $kept NEW policy violation(s) introduced by this diff (listed above)." >&2
  exit 1
fi
echo "semgrep.sh: OK — no policy findings introduced by this diff (${mode})."
exit 0
