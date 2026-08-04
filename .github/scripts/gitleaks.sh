#!/usr/bin/env bash
# gitleaks.sh — thin wrapper over the ADOPTED gitleaks secret-scanner. Runs the maintained
# gitleaks default ruleset and EXITS NON-ZERO on any leaked-secret finding, so it can serve
# as a merge-blocking required check. This is a wrapper, NOT a scanner: all detection lives
# in gitleaks + its built-in ruleset. NO hand-rolled regex secret scanner.
#
# CI-ONLY. This directory (.github/scripts/) is build/CI infrastructure that ships with the repo
# but is NOT product code: it is not on the import path, not linted as src/, and not typechecked.
#
# SCOPE:
#   default        — scan the whole working tree (gitleaks dir over $ROOT).
#   --diff         — scan the files changed between base and head, then keep only findings on
#                    lines the diff ADDED (see diff_filter.py). Head is CHARON_CI_HEAD or HEAD;
#                    base is CHARON_CI_BASE, else resolve_base() in _common.sh (the merge ref's
#                    FIRST PARENT — read that function's comment before changing it).
#                    If the merge-base cannot resolve, we FAIL CLOSED (exit 2) rather than scan
#                    nothing and report green — a scan-nothing green is the false receipt this
#                    gate exists to prevent.
#   [PATHS...]     — scan exactly the given files/dirs (used by the canary with a fixture file).
#
# CONFIG override: GITLEAKS_CONFIG (gitleaks' native env var) lets the canary point the SAME
# wrapper at a neutered config to prove the ruleset is load-bearing. When UNSET, the wrapper
# writes a config that extends gitleaks' maintained default ruleset (useDefault=true) — no
# separate git-tracked ruleset file is needed (that maintained ruleset is gitleaks' whole point).
#
# EXIT: 0 = no findings; 1 = at least one leaked-secret finding (blocks merge); 2 = wrapper/scope
#       error (incl. a vacuous zero-rule config, which the wrapper refuses to run — see the guard).
set -uo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS/../.." && pwd)"
# shellcheck source=.github/scripts/_common.sh
. "$SCRIPTS/_common.sh"
# Intentionally-planted canary fixtures. Excluded from diff scans; the canary still scans them by
# EXPLICIT path, so detection is unaffected.
FIXTURES='.github/scripts/fixtures/'

command -v gitleaks >/dev/null 2>&1 || {
  echo "gitleaks.sh: FAIL — gitleaks is not installed (adopt the scanner: download the pinned" >&2
  echo "  release binary from https://github.com/gitleaks/gitleaks/releases)." >&2
  exit 2
}

# CONFIG resolution. GITLEAKS_CONFIG (native gitleaks env) wins — the canary uses it to point the
# SAME wrapper at a neutered config. Unset -> generate a config that extends the maintained default
# ruleset. Generated configs are cleaned up on exit.
CLEANUP=""
cleanup() { [ -n "$CLEANUP" ] && rm -f "$CLEANUP"; }
trap cleanup EXIT
if [ -n "${GITLEAKS_CONFIG:-}" ]; then
  CONFIG="$GITLEAKS_CONFIG"
  [ -f "$CONFIG" ] || { echo "gitleaks.sh: FAIL — GITLEAKS_CONFIG not found: $CONFIG" >&2; exit 2; }
else
  # .toml suffix is LOAD-BEARING: gitleaks infers the config format from the file extension and
  # FATALs ("Unsupported Config Type") on a suffixless temp path.
  CONFIG="$(mktemp --suffix=.toml)"; CLEANUP="$CONFIG"
  cat > "$CONFIG" <<'TOML'
title = "charon gitleaks — extends the maintained default ruleset"
[extend]
useDefault = true
TOML
fi
# gitleaks reads GITLEAKS_CONFIG from the environment too; pass --config explicitly and unexport
# the env so a stray inherited value can never silently override the effective config we guard below.
unset GITLEAKS_CONFIG

# VACUOUS-CONFIG GUARD (wrapper-owned, VERSION-INDEPENDENT). A config that loads ZERO rules can never
# find anything, so its exit-0 is a false green — and gitleaks CONFIRMS this failure mode: a config
# with no [[rules]] and no useDefault prints "no leaks found" (exit 0) on a file full of secrets
# (verified on 8.21.2). We do NOT lean on any gitleaks flag to red an empty config: the wrapper counts
# rule sources ITSELF and FAILS CLOSED (exit 2) when the effective config neither loads the maintained
# default (useDefault=true) NOR defines any [[rules]] of its own — stable across gitleaks versions.
rule_count="$(grep -cE '^[[:space:]]*\[\[rules\]\]' "$CONFIG" 2>/dev/null || true)"
use_default="$(grep -ciE '^[[:space:]]*useDefault[[:space:]]*=[[:space:]]*true' "$CONFIG" 2>/dev/null || true)"
if [ "${rule_count:-0}" -eq 0 ] && [ "${use_default:-0}" -eq 0 ]; then
  echo "gitleaks.sh: FAIL — config '$CONFIG' loads ZERO rules (no [[rules]], useDefault not true);" >&2
  echo "  refusing to scan. A no-rules scan can never find anything, so its green is a false receipt" >&2
  echo "  (fail closed)." >&2
  exit 2
fi

mode="tree"
declare -a paths=()
while [ $# -gt 0 ]; do
  case "$1" in
    --diff) mode="diff" ;;
    --) shift; mode="paths"; while [ $# -gt 0 ]; do paths+=("$1"); shift; done; break ;;
    -*) echo "gitleaks.sh: unknown flag: $1" >&2; exit 2 ;;
    *)  mode="paths"; paths+=("$1") ;;
  esac
  shift
done

declare -a targets
if [ "$mode" = "diff" ]; then
  base="$(resolve_base "$ROOT")"
  head="${CHARON_CI_HEAD:-HEAD}"
  mb="$(git -C "$ROOT" merge-base "$base" "$head" 2>/dev/null)" || mb=""
  if [ -z "$mb" ]; then
    echo "gitleaks.sh: FAIL — cannot resolve merge-base($base,$head); refusing to scan nothing (fail closed)." >&2
    exit 2
  fi
  mapfile -t changed < <(changed_files "$ROOT" "$mb" "$head" | tr '\0' '\n')
  if [ "${#changed[@]}" -eq 0 ]; then
    echo "gitleaks.sh: OK — no changed files in $base..$head to scan."
    exit 0
  fi
  # FAIL CLOSED before scanning. gitleaks does NOT complain about a target it cannot open — a
  # chmod-000 file yields "no leaks found", exit 0, i.e. a scan that read nothing reporting green.
  # This check (and NUL-safe, unquoted path listing in _common.sh) is what turns both of those
  # into a red. Deleted paths are already filtered out by --diff-filter=ACMR.
  declare -a abs=()
  for p in "${changed[@]}"; do abs+=("$ROOT/$p"); done
  require_readable "gitleaks.sh" "${abs[@]}"
  # ONE scan of the tree, not one spawn per changed file: a 400-file PR was 400 sequential
  # `gitleaks dir` invocations inside a 10-minute job. The line filter below restricts the verdict
  # to the diff anyway, so scanning the whole checkout is both cheaper and immune to per-path
  # quoting bugs (no path is ever reconstructed).
  targets=("$ROOT")
elif [ "$mode" = "tree" ]; then
  targets=("$ROOT")
else
  targets=("${paths[@]}")
  require_readable "gitleaks.sh" "${targets[@]}"
fi

# A PR must not be able to silence this gate by shipping its own ignore file: gitleaks reads
# .gitleaksignore from the scan root by default, and adding one carrying the finding's fingerprint
# in the SAME PR flips a red to green. Point it at an empty file we own instead.
EMPTY_IGNORE="$(mktemp -d)/.gitleaksignore"; : > "$EMPTY_IGNORE"

# Scan with the maintained ruleset. --exit-code 1 makes a finding exit 1; --redact keeps any REAL
# secret out of CI logs (the fixture is fake, product secrets are not). Reports are collected as
# JSON so diff mode can line-scope them (see below).
REPORTS="$(mktemp -d)"
trap 'cleanup; rm -rf "$REPORTS" "$(dirname "$EMPTY_IGNORE")"' EXIT
worst=0
i=0
for t in "${targets[@]}"; do
  i=$((i+1))
  gitleaks dir --config "$CONFIG" --gitleaks-ignore-path "$EMPTY_IGNORE" \
    --no-banner --redact --exit-code 1 \
    --report-format json --report-path "$REPORTS/$i.json" "$t"
  rc=$?
  [ "$rc" -gt "$worst" ] && worst=$rc
  # A report file MUST exist for every target. gitleaks exits 1 for a scan ERROR as well as for
  # "leaks found", so without this an errored scan yields no report -> 0 findings -> green.
  if [ ! -f "$REPORTS/$i.json" ]; then
    echo "gitleaks.sh: FAIL — gitleaks wrote no report for target '$t' (exit $rc); failing closed." >&2
    exit 2
  fi
done

if [ "$worst" -gt 1 ]; then
  echo "gitleaks.sh: FAIL — gitleaks errored (exit $worst); failing closed." >&2
  exit 2
fi

if [ "$mode" = "diff" ]; then
  # LINE-SCOPE (diff mode only). gitleaks reports on whole FILES, so a file-scoped gate reds on
  # findings that were already on master the moment a PR edits an unrelated line of the same file
  # — measured 12 such pre-existing findings across 7 files under tests/ on master 2026-08-04
  # (synthetic key-shaped strings those tests exist to contain). diff_filter.py keeps only
  # findings that overlap a line this PR ADDED, and FAILS CLOSED (exit 2) if it cannot compute
  # the diff or parse the reports. Note this is STRICTER than excluding tests/ wholesale: a
  # genuinely new secret pasted into a test file still blocks.
  merged="$(python3 -c '
import json, pathlib, sys
out = []
for p in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    try:
        out.extend(json.loads(p.read_text() or "[]"))
    except Exception:
        sys.exit(3)
print(json.dumps(out))
' "$REPORTS")" || {
    echo "gitleaks.sh: FAIL — could not read gitleaks JSON report(s); failing closed." >&2
    exit 2
  }
  kept="$(printf '%s' "$merged" | python3 "$SCRIPTS/diff_filter.py" \
    --kind gitleaks --base "$base" --head "$head" --root "$ROOT" --exclude-prefix "$FIXTURES")"
  frc=$?
  if [ "$frc" -ne 0 ]; then
    echo "gitleaks.sh: FAIL — diff_filter failed (exit $frc); failing closed." >&2
    exit 2
  fi
  if [ "${kept:-0}" -ge 1 ]; then
    echo "gitleaks.sh: FINDINGS — $kept NEW leaked-secret finding(s) introduced by this diff (listed above)." >&2
    exit 1
  fi
  echo "gitleaks.sh: OK — no leaked-secret findings introduced by this diff (${mode})."
  exit 0
fi

case "$worst" in
  0) echo "gitleaks.sh: OK — no leaked-secret findings (${mode})."; exit 0 ;;
  *) exit 1 ;;
esac
