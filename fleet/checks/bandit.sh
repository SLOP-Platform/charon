#!/usr/bin/env bash
# bandit.sh — thin wrapper over the ADOPTED bandit Python SAST. Runs the maintained bandit
# ruleset (its built-in danger-pattern plugins: eval/exec, subprocess shell=True, pickle,
# yaml.load, weak crypto, ...) and EXITS NON-ZERO on any finding at/above a configured severity,
# so it can serve as a merge-blocking required check. This is a wrapper, NOT a linter: all
# detection lives in bandit + its built-in tests. NO hand-rolled Python security linter.
#
# SCOPE:
#   default        — scan the rig's own Python (fleet/**/*.py, tools/**/*.py), enumerated via
#                    git ls-files (excludes fleet/tests/fixtures/ — see the diff-mode note).
#   --diff         — scan only the .py files changed between base and head. Base/head come from
#                    RIG_CI_BASE/RIG_CI_HEAD (set by CI) or default to origin/master..HEAD.
#                    If the merge-base cannot resolve, we FAIL CLOSED (exit 2) rather than scan
#                    nothing and report green — a scan-nothing green is the false receipt this
#                    gate exists to prevent. DIFF-SCOPED on purpose: only NEW insecure code
#                    introduced by THIS PR blocks merge. A full-tree scan would (correctly) red on
#                    the PRE-EXISTING shell=True at fleet/benchmark/graders/real.py:54, which is
#                    owned by a SEPARATE ticket (GRADER-SECFIX); a gate that reds on untouched code
#                    gets disabled — the exact failure this gate exists to prevent.
#   [PATHS...]     — scan exactly the given files/dirs (used by the canary with a fixture file).
#
# CONFIG override: BANDIT_CONFIG (bandit's native --configfile) lets the canary point the SAME
# wrapper at a neutered config (skips: [B602,...]) to prove the ruleset is load-bearing. Unset ->
# bandit runs its full built-in test set (that maintained ruleset is bandit's whole point; no
# separate git-tracked ruleset file is needed).
# SEVERITY override: BANDIT_SEVERITY (all|low|medium|high; default medium) — the threshold at/above
# which a finding blocks merge. medium keeps low-severity import advisories (e.g. B404) from
# blocking while still catching real vulnerabilities (shell=True, yaml.load, pickle, weak crypto).
#
# EXIT: 0 = no findings at/above severity; 1 = at least one finding (blocks merge); 2 = wrapper/
#       scope error, incl. a scanned-ZERO-files scope (which the wrapper refuses to report green —
#       see the vacuous guard) or a bandit crash producing no parseable report.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$FLEET/.." && pwd)"
SEVERITY="${BANDIT_SEVERITY:-medium}"

command -v bandit >/dev/null 2>&1 || {
  echo "bandit.sh: FAIL — bandit is not installed (adopt the SAST: 'pip install --user bandit==<pin>'" >&2
  echo "  or 'pipx install bandit'; the CI workflow pins the exact version)." >&2
  exit 2
}
command -v python3 >/dev/null 2>&1 || { echo "bandit.sh: FAIL — python3 required to parse the report." >&2; exit 2; }

# Native config knob. BANDIT_CONFIG (== bandit --configfile) wins — the canary uses it to point the
# SAME wrapper at a neutered config. Unset -> no -c, bandit uses its full built-in test set.
declare -a cfg_args=()
if [ -n "${BANDIT_CONFIG:-}" ]; then
  [ -f "$BANDIT_CONFIG" ] || { echo "bandit.sh: FAIL — BANDIT_CONFIG not found: $BANDIT_CONFIG" >&2; exit 2; }
  cfg_args=(-c "$BANDIT_CONFIG")
fi

mode="tree"
declare -a paths=()
while [ $# -gt 0 ]; do
  case "$1" in
    --diff) mode="diff" ;;
    --) shift; mode="paths"; while [ $# -gt 0 ]; do paths+=("$1"); shift; done; break ;;
    -*) echo "bandit.sh: unknown flag: $1" >&2; exit 2 ;;
    *)  mode="paths"; paths+=("$1") ;;
  esac
  shift
done

if [ "$mode" = "tree" ]; then
  # The rig's own Python: fleet/ and tools/. Enumerate via git ls-files so only tracked files are
  # scanned. EXCLUDE fleet/tests/fixtures/ : those are INTENTIONALLY-insecure canary fixtures (e.g.
  # bandit-known-bad.py); scanning them in a full/diff pass would make a PR that ADDS a fixture red
  # itself. The canary still scans them by EXPLICIT path (paths mode), so detection is unaffected.
  mapfile -t paths < <(git -C "$ROOT" ls-files -- 'fleet/**/*.py' 'tools/**/*.py' 'fleet/*.py' 'tools/*.py' 2>/dev/null \
    | grep -vE '^fleet/tests/fixtures/' | sed "s#^#$ROOT/#")
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "bandit.sh: FAIL — tree mode found ZERO tracked Python files under fleet/ or tools/;" >&2
    echo "  refusing to report green on a zero-file scan (fail closed)." >&2
    exit 2
  fi
elif [ "$mode" = "diff" ]; then
  base="${RIG_CI_BASE:-origin/master}"
  head="${RIG_CI_HEAD:-HEAD}"
  mb="$(git -C "$ROOT" merge-base "$base" "$head" 2>/dev/null)" || mb=""
  if [ -z "$mb" ]; then
    echo "bandit.sh: FAIL — cannot resolve merge-base($base,$head); refusing to scan nothing (fail closed)." >&2
    exit 2
  fi
  # Only existing (Added/Copied/Modified/Renamed) .py files under fleet/ or tools/. Deleted paths
  # would error the scan; the fixtures dir is excluded (see tree-mode note).
  mapfile -t paths < <(git -C "$ROOT" diff --name-only --diff-filter=ACMR "$mb" "$head" -- 'fleet/**/*.py' 'tools/**/*.py' 'fleet/*.py' 'tools/*.py' 2>/dev/null \
    | grep -vE '^fleet/tests/fixtures/' | sed "s#^#$ROOT/#")
  if [ "${#paths[@]}" -eq 0 ]; then
    # A genuinely empty diff (no changed Python) is a LEGIT green — unlike a scanned-nothing scope
    # error, there is simply nothing new to gate. Mirror semgrep.sh / gitleaks.sh.
    echo "bandit.sh: OK — no changed Python files in $base..$head to scan."
    exit 0
  fi
fi

# Run bandit ONCE, capture its JSON report, and derive BOTH the finding count and the files-scanned
# count from it. --severity-level filters the report to findings at/above the threshold. -q silences
# the progress banner so stdout is clean JSON.
report="$(bandit -q -f json --severity-level "$SEVERITY" "${cfg_args[@]}" -- "${paths[@]}" 2>/dev/null)"

# Parse the report. python3 emits three space-separated ints: <files_scanned> <findings> <errors>.
# If bandit crashed / produced no parseable JSON, this fails and we FAIL CLOSED (exit 2).
parsed="$(printf '%s' "$report" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(3)
m = d.get("metrics", {})
files = len([k for k in m if k != "_totals"])
findings = len(d.get("results", []))
errors = len(d.get("errors", []))
print(files, findings, errors)
' 2>/dev/null)" || {
  echo "bandit.sh: FAIL — bandit produced no parseable JSON report (crash/error); failing closed." >&2
  exit 2
}
read -r files findings errors <<<"$parsed"

# VACUOUS / SCOPE GUARD (wrapper-owned, VERSION-INDEPENDENT). A scan that touched ZERO files can never
# find anything, so its exit-0 is a false green — bandit CONFIRMS this: over an empty dir (or a target
# that resolves to no Python) it exits 0 "no issues". We do NOT lean on bandit's exit code to red this:
# the wrapper counts files-scanned from bandit's OWN metrics and FAILS CLOSED (exit 2) on zero —
# stable across bandit versions.
if [ "${files:-0}" -eq 0 ]; then
  echo "bandit.sh: FAIL — bandit scanned ZERO files for the given scope; refusing to report green." >&2
  echo "  A no-file scan can never find anything, so its green is a false receipt (fail closed)." >&2
  exit 2
fi

if [ "${errors:-0}" -ne 0 ]; then
  # Surface scan errors (e.g. a syntax error that stopped bandit reading a target) as a warning. They
  # do not on their own flip the verdict as long as >=1 file WAS scanned (guard above); a file that
  # could not be parsed is reported here rather than silently dropped.
  echo "bandit.sh: WARN — bandit reported $errors scan error(s) (unparseable target[s]); see report." >&2
  printf '%s' "$report" | python3 -c 'import sys,json;[print("  error:",e.get("filename"),"-",e.get("reason")) for e in json.load(sys.stdin).get("errors",[])]' 2>/dev/null || true
fi

if [ "${findings:-0}" -ge 1 ]; then
  echo "bandit.sh: FINDINGS — $findings issue(s) at/above severity '$SEVERITY' across $files file(s) (${mode}):" >&2
  printf '%s' "$report" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for r in d.get("results", []):
    print("  {sev}/{conf}  {tid} {name}  {f}:{line}  {text}".format(
        sev=r.get("issue_severity"), conf=r.get("issue_confidence"),
        tid=r.get("test_id"), name=r.get("test_name"),
        f=r.get("filename"), line=r.get("line_number"),
        text=r.get("issue_text")))
' 2>/dev/null || true
  exit 1
fi

echo "bandit.sh: OK — no bandit findings at/above severity '$SEVERITY' across $files file(s) (${mode})."
exit 0
