#!/usr/bin/env bash
# _difflab.sh — throwaway-repo harness for --diff MODE canary assertions. Sourced, not executed.
#
# WHY THIS EXISTS. The first version of these canaries asserted everything in PATHS mode: fire,
# neuter, clean, vacuous. The only --diff case used an unresolvable base and returned before
# scanning. So the code path CI ACTUALLY RUNS — resolve base, list changed files, scan, LINE-FILTER,
# verdict — had zero coverage, and a filter bug that silently turned every RED into a green passed
# 10/10 canaries. Everything below exercises that path end to end.
#
# The lab reproduces GitHub's shape exactly: a base commit, a PR lane, an independent master lane,
# and a MERGE COMMIT whose FIRST PARENT is master — which is what refs/pull/N/merge is. So
# resolve_base() is exercised for real; no CHARON_CI_BASE is set.
#
#   difflab <lab-dir> <mode> <violation-source-line>
#     modes:
#       plain      — the PR adds the violation.                          expect RED
#       payload    — same, plus an earlier hunk whose added line is
#                    "++ sample" (git renders it "+++ sample").          expect RED
#       otherlane  — the PR is benign; MASTER gains the violation.       expect GREEN
#       nonascii   — the PR adds the violation in a non-ASCII filename.  expect RED
#       unreadable — the PR adds the violation, then chmod 000.          expect FAIL-CLOSED
#       reformat   — the violation is ALREADY at base; the PR only
#                    reindents/moves it.                                 expect GREEN

difflab() {
  local lab="$1" mode="$2" viol="$3"
  rm -rf "$lab"; mkdir -p "$lab/pkg"
  cp -r "$SCRIPTS" "$lab/.github_scripts_tmp"
  mkdir -p "$lab/.github"; mv "$lab/.github_scripts_tmp" "$lab/.github/scripts"
  git -C "$lab" init -q -b master
  git -C "$lab" config user.email lab@example.invalid
  git -C "$lab" config user.name lab

  # A base file long enough that a top edit and a bottom edit are two separate -U0 hunks.
  {
    echo "sample = 1"
    for i in $(seq 1 40); do echo "CONST_$i = $i"; done
  } > "$lab/pkg/mod.py"
  if [ "$mode" = "reformat" ]; then printf '%s\n' "$viol" >> "$lab/pkg/mod.py"; fi
  git -C "$lab" add -A >/dev/null; git -C "$lab" commit -qm base

  # ── the PR lane ──
  git -C "$lab" checkout -q -b pr
  case "$mode" in
    plain)
      printf '%s\n' "$viol" >> "$lab/pkg/mod.py" ;;
    payload)
      # An ADDED CONTENT LINE that begins with "++ " renders as "+++ sample" in the diff. A parser
      # that treats a leading "+++ " as a file header loses every later hunk of this file — which
      # silently turned this exact RED into a green.
      python3 - "$lab/pkg/mod.py" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).read().split("\n")
lines.insert(2, "++ sample")
open(p, "w").write("\n".join(lines))
PY
      printf '%s\n' "$viol" >> "$lab/pkg/mod.py" ;;
    nonascii)
      python3 -c 'import sys;open(sys.argv[1],"w").write(sys.argv[2]+"\n")' "$lab/pkg/naïve.py" "$viol" ;;
    unreadable)
      printf '%s\n' "$viol" >> "$lab/pkg/mod.py" ;;
    otherlane)
      echo "BENIGN = True" >> "$lab/pkg/mod.py" ;;
    reformat)
      # Same violation, reindented and moved — a `ruff format` pass, not new code.
      python3 - "$lab/pkg/mod.py" "$viol" <<'PY'
import sys
p, viol = sys.argv[1], sys.argv[2]
lines = [ln for ln in open(p).read().split("\n") if ln != viol]
lines.insert(3, viol)
open(p, "w").write("\n".join(lines))
PY
      ;;
  esac
  git -C "$lab" add -A >/dev/null; git -C "$lab" commit -qm pr

  # ── the master lane: an independent commit landed by someone else, in its OWN file so the
  #    merge below never conflicts (a conflict would make the lab, not the gate, the thing failing)
  git -C "$lab" checkout -q master
  if [ "$mode" = "otherlane" ]; then
    printf '%s\n' "$viol" > "$lab/pkg/master_side.py"
  else
    echo "# master moved on" > "$lab/pkg/master_side.py"
  fi
  git -C "$lab" add -A >/dev/null; git -C "$lab" commit -qm master-lane

  # ── the merge ref: first parent is MASTER, exactly like refs/pull/N/merge ──
  git -C "$lab" merge -q --no-ff pr -m "merge ref"
  if [ "$mode" = "unreadable" ]; then chmod 000 "$lab/pkg/mod.py"; fi
}

# difflab_run <lab> <wrapper-basename> -> echoes the wrapper's exit code
difflab_run() {
  local lab="$1" wrap="$2" rc=0
  ( cd "$lab" && bash "$lab/.github/scripts/$wrap" --diff ) >"$lab/out.txt" 2>&1 || rc=$?
  echo "$rc"
}
