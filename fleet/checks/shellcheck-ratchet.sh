#!/usr/bin/env bash
# SHELLCHECK-RATCHET.SH (capitalized: a comment starting "# shellcheck" is parsed by shellcheck
# itself as a directive and errors closed — SC1072/SC1073 — so this header cannot spell its own
# filename in lowercase without tripping the very tool it wraps).
# BASELINE RATCHET over shellcheck's FULL rule surface (-o all: default
# severities + all 11 optional checks, which are OFF by default and were never turned on anywhere
# in this rig — see fleet/state/TOOL-UTILIZATION-AUDIT.md, measured 2026-08-01, NOT re-derived
# here). Bare `enable=all` against the live tree is ~36,700 findings today: switching that on as a
# blocking gate with no baseline would fail every PR from the first commit, which gets a gate
# disabled or bypassed, not fixed — the exact failure this file exists to avoid.
#
# MECHANISM: the CURRENT finding set is the accepted FLOOR (`shellcheck-baseline.tsv`, git-tracked
# so it travels with every checkout/clone/CI runner). `check` reruns shellcheck at the same full
# coverage and RATCHET-COMPARES: a (file, SC-code) pair whose live count EXCEEDS its baseline count
# is a NEW finding and REDs. A pair at or below its baseline count (including 0 — the finding was
# fixed) is silently fine. Nothing is required to go green immediately; only regressions are
# blocked from this point forward. Tightening the baseline (re-running `generate` after fixing
# findings) is a separate, always-safe follow-up, never required by this gate.
#
# GRANULARITY IS (file, SC-code), NOT (file, line, SC-code). Line numbers drift on every unrelated
# edit above a finding; keying on the exact line would false-RED on reformatting/insertions that
# touch zero semantics. Keying on the pair means: "this file already carries N instances of this
# rule violation; a PR may not add an (N+1)th." A brand-new file, or a brand-new SC-code in an
# existing file, has an implicit baseline of 0 — any finding there is new by definition.
#
# Usage (a leading "# shellcheck" comment is itself a directive token to the tool, SC1072/SC1073,
# so usage lines below are phrased "bash <this file>" rather than starting with the bare filename):
#   bash shellcheck-ratchet.sh generate   [re]write the baseline from the CURRENT tree -> BASELINE_FILE
#   bash shellcheck-ratchet.sh check      compare live findings to the committed baseline; rc!=0 on
#                                          any (file, code) pair whose live count exceeds baseline
# Env (all overridable — hermetic tests point these at throwaway fixture dirs):
#   SHELLCHECK_RATCHET_ROOT       repo root                         (default: this script's repo)
#   SHELLCHECK_RATCHET_SCAN_DIR   directory scanned for *.sh         (default: $ROOT/fleet)
#   SHELLCHECK_RATCHET_BASELINE   baseline TSV path                  (default:
#                                 $ROOT/fleet/checks/shellcheck-baseline.tsv)
# Exit: 0 = no new findings (or generate succeeded). 1 = new finding(s) present. 2 = usage/tool
# missing/baseline missing — a REFUSAL, never treated as "no new findings" by any caller.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${SHELLCHECK_RATCHET_ROOT:-$(cd "$HERE/../.." && pwd)}"
SCAN_DIR="${SHELLCHECK_RATCHET_SCAN_DIR:-$ROOT/fleet}"
BASELINE="${SHELLCHECK_RATCHET_BASELINE:-$ROOT/fleet/checks/shellcheck-baseline.tsv}"

# _scan -> one "<repo-relative-path>\t<SCcode>" line per finding, across every *.sh under
# SCAN_DIR, at FULL coverage (-o all). Deterministic file order (sorted) so re-runs over an
# unchanged tree produce byte-identical output.
_scan(){
  command -v shellcheck >/dev/null 2>&1 || { echo "shellcheck-ratchet: shellcheck not installed" >&2; return 2; }
  [ -d "$SCAN_DIR" ] || { echo "shellcheck-ratchet: scan dir missing: $SCAN_DIR" >&2; return 2; }
  local files=()
  while IFS= read -r -d '' f; do files+=("$f"); done < <(find "$SCAN_DIR" -name '*.sh' -print0 | sort -z)
  [ "${#files[@]}" -gt 0 ] && \
    shellcheck -o all -f gcc "${files[@]}" 2>/dev/null | sed -E "s#^${ROOT}/##" | \
      sed -nE 's/^([^:]+):[0-9]+:[0-9]+: [a-zA-Z]+: .*\[(SC[0-9]+)\]$/\1\t\2/p'
  return 0
}

# _aggregate <scan output on stdin> -> "<count>\t<file>\t<code>" per distinct pair, sorted.
_aggregate(){ sort | uniq -c | awk '{print $1"\t"$2"\t"$3}' | LC_ALL=C sort -k2,2 -k3,3; }

cmd_generate(){
  local out; out="$(_scan)"; local rc=$?
  [ $rc -eq 0 ] || return $rc
  # `[ -n "$out" ]` on the already-captured string — NOT `printf ... | grep -q .`. grep -q exits
  # the instant it matches line 1, SIGPIPEing the producer; under `pipefail` that SIGPIPE (not
  # grep's true 0) becomes the pipeline's reported status, so a CLEARLY non-empty `$out` reads as
  # "no match" and every generate run false-refused. Exactly the pipefail-swallows-success class
  # this ratchet's set-e-suppressed reporting exists to catch — caught here in its own tooling.
  [ -n "$out" ] || { echo "shellcheck-ratchet: scan produced ZERO findings — refusing to write a suspiciously-empty baseline (fail closed)" >&2; return 2; }
  printf '%s\n' "$out" | _aggregate > "$BASELINE"
  local n; n=$(wc -l < "$BASELINE")
  echo "shellcheck-ratchet: baseline written: $BASELINE ($n distinct file/code pairs)"
}

cmd_check(){
  [ -f "$BASELINE" ] || { echo "RED: shellcheck-ratchet: no baseline at $BASELINE — run 'generate' first (refusing rather than treating a missing floor as a clean one)" >&2; return 2; }
  declare -A BASE=()
  local bcount bfile bcode
  while IFS=$'\t' read -r bcount bfile bcode; do
    [ -n "$bfile" ] || continue
    BASE["$bfile"$'\t'"$bcode"]="$bcount"
  done < "$BASELINE"

  local live; live="$(_scan)"; local rc=$?
  [ $rc -eq 0 ] || return $rc

  local red=0 lcount lfile lcode base_n new_n
  while IFS=$'\t' read -r lcount lfile lcode; do
    [ -n "$lfile" ] || continue
    base_n="${BASE[$lfile$'\t'$lcode]:-0}"
    if [ "$lcount" -gt "$base_n" ]; then
      new_n=$((lcount - base_n))
      echo "RED: shellcheck-ratchet: $lfile [$lcode]: $lcount finding(s) now, baseline $base_n — $new_n NEW"
      red=1
    fi
  done < <(printf '%s\n' "$live" | _aggregate)

  if [ "$red" -eq 0 ]; then
    echo "shellcheck-ratchet: clean — no (file, SC-code) pair exceeds its baseline count"
  fi
  return $red
}

case "${1:-}" in
  generate) cmd_generate ;;
  check)    cmd_check ;;
  *) echo "usage: shellcheck-ratchet.sh {generate|check}" >&2; exit 2 ;;
esac
