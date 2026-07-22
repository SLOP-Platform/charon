#!/usr/bin/env bash
# semgrep.sh — thin wrapper over the ADOPTED Semgrep engine. Runs the git-tracked ruleset
# (fleet/semgrep-rules/) and EXITS NON-ZERO on any finding, so it can serve as a merge-blocking
# required check. This is a wrapper, NOT a linter: all detection lives in semgrep + the yaml rules.
#
# SCOPE:
#   default        — scan the whole tracked tree (semgrep honors .gitignore/.semgrepignore).
#   --diff         — scan only files changed between base and head. Base/head come from
#                    RIG_CI_BASE/RIG_CI_HEAD (set by CI) or default to origin/master..HEAD.
#                    If the merge-base cannot resolve, we FAIL CLOSED (exit 2) rather than scan
#                    nothing and report green — a scan-nothing green is the false receipt this
#                    gate exists to prevent.
#   [PATHS...]     — scan exactly the given paths (used by the canary with a fixture file).
#
# CONFIG override: SEMGREP_RULES_DIR (default fleet/semgrep-rules) lets the canary point the SAME
# wrapper at a neutered ruleset copy to prove the rules are load-bearing.
#
# EXIT: 0 = no findings; 1 = at least one finding (blocks merge); 2 = wrapper/scope error (incl. a
#       vacuous zero-rule ruleset, which the wrapper refuses to run — see the guard below).
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$FLEET/.." && pwd)"
RULES="${SEMGREP_RULES_DIR:-$FLEET/semgrep-rules}"

command -v semgrep >/dev/null 2>&1 || {
  echo "semgrep.sh: FAIL — semgrep is not installed (adopt the engine: 'uv tool install semgrep')." >&2
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

if [ "$mode" = "diff" ]; then
  base="${RIG_CI_BASE:-origin/master}"
  head="${RIG_CI_HEAD:-HEAD}"
  mb="$(git -C "$ROOT" merge-base "$base" "$head" 2>/dev/null)" || mb=""
  if [ -z "$mb" ]; then
    echo "semgrep.sh: FAIL — cannot resolve merge-base($base,$head); refusing to scan nothing (fail closed)." >&2
    exit 2
  fi
  # Only existing (Added/Copied/Modified/Renamed) files — deleted paths would error the scan.
  # EXCLUDE fleet/tests/fixtures/ : those files are INTENTIONALLY-bad canary fixtures (e.g.
  # semgrep-known-bad.py). Scanning them in --diff mode would make a PR that adds a fixture block
  # itself. The canary still scans them by EXPLICIT path (paths mode), so detection is unaffected.
  mapfile -t paths < <(git -C "$ROOT" diff --name-only --diff-filter=ACMR "$mb" "$head" -- 2>/dev/null \
    | grep -vE '^fleet/tests/fixtures/' | sed "s#^#$ROOT/#")
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "semgrep.sh: OK — no changed files in $base..$head to scan."
    exit 0
  fi
fi

declare -a targets
if [ "$mode" = "tree" ]; then
  targets=("$ROOT")
else
  targets=("${paths[@]}")
fi

# --error: exit 1 on any finding. --strict: fail on rule/parse errors (a broken ruleset must red,
# not silently pass). --quiet keeps output to findings only.
semgrep scan --config "$RULES" --error --strict --quiet "${targets[@]}"
rc=$?
if [ "$rc" -eq 0 ]; then
  echo "semgrep.sh: OK — no policy findings (${mode})."
fi
exit "$rc"
