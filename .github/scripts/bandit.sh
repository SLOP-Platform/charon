#!/usr/bin/env bash
# bandit.sh — thin wrapper over the ADOPTED bandit Python SAST. Runs the maintained bandit
# ruleset (its built-in danger-pattern plugins: eval/exec, subprocess shell=True, pickle,
# yaml.load, weak crypto, ...) and EXITS NON-ZERO on any finding at/above a configured severity,
# so it can serve as a merge-blocking required check. This is a wrapper, NOT a linter: all
# detection lives in bandit + its built-in tests. NO hand-rolled Python security linter.
#
# CI-ONLY. This directory (.github/scripts/) is build/CI infrastructure that ships with the repo
# but is NOT product code: it is not on the import path, not linted as src/, and not typechecked.
#
# SCOPE:
#   default        — scan EVERY tracked *.py, enumerated via git ls-files (excludes
#                    .github/scripts/fixtures/ — see the diff-mode note).
#   --diff         — scan the .py files changed between base and head, then keep only findings on
#                    lines the diff ADDED (see diff_filter.py). Head is CHARON_CI_HEAD or HEAD;
#                    base is CHARON_CI_BASE, else resolve_base() in _common.sh (the merge ref's
#                    FIRST PARENT — read that function's comment before changing it).
#                    If the merge-base cannot resolve, we FAIL CLOSED (exit 2) rather than scan
#                    nothing and report green — a scan-nothing green is the false receipt this
#                    gate exists to prevent. DIFF-SCOPED on purpose: only NEW insecure code
#                    introduced by THIS PR blocks merge. A full-tree scan would (correctly) red on
#                    4 PRE-EXISTING findings measured on master 2026-08-04 (B602 in
#                    src/charon/acceptance.py, src/charon/connect.py, src/charon/land.py; B104 in
#                    src/charon/gateway.py), which are owned by separate work; a gate that reds on
#                    untouched code gets disabled — the exact failure this gate exists to prevent.
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

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS/../.." && pwd)"
# shellcheck source=.github/scripts/_common.sh
. "$SCRIPTS/_common.sh"
SEVERITY="${BANDIT_SEVERITY:-medium}"
# Intentionally-insecure canary fixtures. Excluded from tree/diff scans; the canary still scans
# them by EXPLICIT path, so detection is unaffected.
FIXTURES='.github/scripts/fixtures/'

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

select_py() {  # stdin: NUL-separated repo-relative paths -> stdout: absolute .py paths, one per line
  local p
  while IFS= read -r -d '' p; do
    case "$p" in
      *.py) : ;;
      *) continue ;;
    esac
    case "$p" in
      "$FIXTURES"*) continue ;;
    esac
    printf '%s\n' "$ROOT/$p"
  done
}

if [ "$mode" = "tree" ]; then
  # EVERY tracked *.py, not just src/ and tools/. The earlier src+tools pathspec left 162 of 309
  # tracked Python files ungated (tests/, .ksf/gates/, packaging/, the repo root, and these very
  # scripts): three brand-new shell=True files outside that pathspec produced "OK — no changed
  # Python files … to scan", exit 0, on a diff that changed three Python files.
  mapfile -t paths < <(git -c core.quotePath=false -C "$ROOT" ls-files -z -- '*.py' 2>/dev/null | select_py)
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "bandit.sh: FAIL — tree mode found ZERO tracked Python files;" >&2
    echo "  refusing to report green on a zero-file scan (fail closed)." >&2
    exit 2
  fi
elif [ "$mode" = "diff" ]; then
  base="$(resolve_base "$ROOT")"
  head="${CHARON_CI_HEAD:-HEAD}"
  mb="$(git -C "$ROOT" merge-base "$base" "$head" 2>/dev/null)" || mb=""
  if [ -z "$mb" ]; then
    echo "bandit.sh: FAIL — cannot resolve merge-base($base,$head); refusing to scan nothing (fail closed)." >&2
    exit 2
  fi
  mapfile -t changed < <(changed_files "$ROOT" "$mb" "$head" | tr '\0' '\n')
  mapfile -t paths < <(changed_files "$ROOT" "$mb" "$head" | select_py)
  if [ "${#paths[@]}" -eq 0 ]; then
    # A genuinely empty Python diff is a LEGIT green — there is simply nothing new to gate. Say
    # exactly that; the old message claimed "no changed Python files" even when there were some
    # (they were merely outside the pathspec), which is a false statement in a gate log.
    echo "bandit.sh: OK — ${#changed[@]} changed file(s), none of them in-scope Python, in $base..$head."
    exit 0
  fi
  # FAIL CLOSED before scanning: an unreadable or vanished target is a scan that reads nothing.
  require_readable "bandit.sh" "${paths[@]}"
fi

# Run bandit ONCE, capture its JSON report, and derive BOTH the finding count and the files-scanned
# count from it. --severity-level filters the report to findings at/above the threshold. -q silences
# the progress banner so stdout is clean JSON.
# -x '/__none__' OVERRIDES bandit's DEFAULT exclusion list, which contains `.git` — and bandit's
# path matching also swallows `.github/...`, so without this it scans ZERO files under
# .github/scripts/ and reports a clean exit 0 (verified 1.9.4; the wrapper's files-scanned guard
# caught it as exit 2). Every target here is an EXPLICIT file list from git ls-files / git diff,
# so replacing the default exclusion can never pull in repository internals.
report="$(bandit -q -f json --severity-level "$SEVERITY" -x '/__none__' "${cfg_args[@]}" -- "${paths[@]}" 2>/dev/null)"

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

if [ "$mode" = "diff" ] && [ "${findings:-0}" -ge 1 ]; then
  # LINE-SCOPE (diff mode only). bandit reports on whole FILES, so a file-scoped gate reds on
  # findings that were already on master the moment a PR edits an unrelated line of the same
  # file — measured 4 such pre-existing findings on master 2026-08-04. diff_filter.py keeps only
  # findings that overlap a line this PR ADDED, and FAILS CLOSED (exit 2) if it cannot compute
  # the diff or parse the report.
  echo "bandit.sh: $findings finding(s) in the changed files; keeping only those on ADDED lines." >&2
  kept="$(printf '%s' "$report" | python3 "$SCRIPTS/diff_filter.py" \
    --kind bandit --base "$base" --head "$head" --root "$ROOT" --exclude-prefix "$FIXTURES")"
  frc=$?
  if [ "$frc" -ne 0 ]; then
    echo "bandit.sh: FAIL — diff_filter failed (exit $frc); failing closed." >&2
    exit 2
  fi
  if [ "${kept:-0}" -ge 1 ]; then
    echo "bandit.sh: FINDINGS — $kept NEW issue(s) at/above severity '$SEVERITY' introduced by this diff (listed above)." >&2
    exit 1
  fi
  echo "bandit.sh: OK — $findings pre-existing finding(s) in the changed files, 0 introduced by this diff (${mode})."
  exit 0
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
