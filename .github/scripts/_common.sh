#!/usr/bin/env bash
# _common.sh — shared diff-scoping helpers for the three scanner wrappers. CI-only; sourced, not
# executed. Everything here exists because the same three mistakes were made once per wrapper.
#
# resolve_base   — pick the ref the diff is measured AGAINST.
# changed_files  — NUL-safe list of the paths a diff touched.
# require_readable — refuse to scan a set that contains a path we cannot actually read.

# ---------------------------------------------------------------------------------------------
# resolve_base <root>
#
# Order: an explicit CHARON_CI_BASE wins; otherwise, if HEAD is a MERGE commit, its FIRST PARENT.
#
# WHY NOT `github.event.pull_request.base.sha`: that field is master's tip as of the last PR
# event, but GitHub recomputes refs/pull/N/merge against CURRENT master. Anything landed by
# someone else in between therefore falls inside base..head and reads as "added by this PR" —
# proven: a benign PR went RED blaming an unrelated shell=True another lane had landed. The merge
# ref's FIRST PARENT *is* current master, so it is always the honest base and needs no extra
# fetch. Falls back to origin/master (then master) off a merge ref; if none resolve, the caller's
# merge-base lookup FAILS CLOSED, which is the correct outcome for an unscopeable checkout.
resolve_base() {
  local root="$1" nparents
  if [ -n "${CHARON_CI_BASE:-}" ]; then printf '%s' "$CHARON_CI_BASE"; return 0; fi
  nparents="$(git -C "$root" rev-parse HEAD^@ 2>/dev/null | grep -c .)" || nparents=0
  if [ "${nparents:-0}" -eq 2 ]; then printf '%s' "$(git -C "$root" rev-parse HEAD^1)"; return 0; fi
  if git -C "$root" rev-parse --verify -q origin/master >/dev/null 2>&1; then
    printf '%s' "origin/master"; return 0
  fi
  printf '%s' "master"
}

# ---------------------------------------------------------------------------------------------
# changed_files <root> <merge-base> <head> [pathspec...]
#
# Emits NUL-separated repo-relative paths for Added/Copied/Modified/Renamed entries.
#
# -z AND core.quotePath=false are BOTH load-bearing. Without them git C-quotes any path holding a
# non-ASCII byte ("na\303\257ve.txt"), and the caller then builds a path that does not exist:
# gitleaks reported "no leaks found" (exit 0) on a file carrying a live-shaped AWS key, and bandit
# went exit 2 on the same commit. -z also survives spaces and newlines in paths.
changed_files() {
  local root="$1" mb="$2" head="$3"; shift 3
  git -c core.quotePath=false -C "$root" diff --name-only -z --diff-filter=ACMR "$mb" "$head" -- "$@" 2>/dev/null
}

# ---------------------------------------------------------------------------------------------
# require_readable <label> <path>...
#
# FAIL CLOSED (exit 2) if any target is missing or unreadable. A scanner that cannot open a file
# does not say so loudly — gitleaks exits 0 "no leaks found" on a chmod-000 target, which is a
# scan that read NOTHING reporting green. This is the guard that turns that into a red.
require_readable() {
  local label="$1"; shift
  local p
  for p in "$@"; do
    if [ ! -e "$p" ]; then
      echo "$label: FAIL — target does not exist: $p" >&2
      echo "  refusing to report green on a scope we could not read (fail closed)." >&2
      exit 2
    fi
    if [ ! -r "$p" ]; then
      echo "$label: FAIL — target is not readable: $p" >&2
      echo "  a scanner silently skips it, so its green would be a scan that read nothing." >&2
      exit 2
    fi
  done
}
