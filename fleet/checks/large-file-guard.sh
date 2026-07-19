#!/usr/bin/env bash
# large-file-guard.sh — MANUALLY-INVOKED CHECK (mechanical). NOT wired into any
# gate today — see the NOT YET WIRED note below; treat large-file protection as
# ABSENT, not enforced. Intended to FAIL LOUD if a staged or
# committed-large file would trip GitHub's push hard-block (>100MB rejected) or
# force a 50MB warning dialog. Sized to fail BELOW the 50MB warning threshold so
# a fix is possible before the operator gets the warning.
#
# THE BUG THIS CATCHES: a single 200MB+ binary in a commit silently hard-blocks
# `git push` with no error message, leaving a droid stuck on "I committed but
# can't land" and stranded work stranded again. Catching it at preflight +
# pre-commit means the droid can `git rm` / re-attach to LFS / carve to a release
# artifact before the land step, not after.
#
# Default threshold: 50MB (52428800 bytes). Override: LARGE_FILE_MAX_BYTES.
# Allowlist: files exactly matching LARGE_FILE_ALLOWLIST (regex) are skipped.
#   Use for the few known-large artifacts that legitimately belong in git
#   (e.g. seed corpora, vendored datasets) so the gate does not false-block them.
#
# Scope: this script only checks the CURRENT repo (PWD or $LARGE_FILE_REPO).
#
# !! NOT YET WIRED — THIS IS A MANUALLY-INVOKED CHECK, NOT A RUNNING GATE. !!
# Nothing invokes this script today: it has ZERO callers outside its own tests
# (verified by repo-wide grep). It does NOT run at preflight and is NOT
# installed as a pre-commit hook, so it currently blocks nothing.
# WHY it ships unwired: the wiring belongs in fleet/preflight.sh, which is
# outside this ticket's `owns:` — editing it here would collide with the
# ticket that owns that file. It is landed standalone-and-tested so the wiring
# ticket has a verified check to hook up.
# Until that lands, treat large-file protection as ABSENT, not enforced.
# Intended once wired: a per-repo preflight gate (auto-registers a blocking
# red) and/or a pre-commit hook (exit 1 = block the commit).
#
# Exit 0 = GREEN (no oversized files).
# Exit 1 = RED  (>= 1 file above the limit — names each path + size).
# Exit 2 = usage / no repo.
#
# Usage:  large-file-guard.sh [<repo>] [--max-bytes N] [--allowlist REGEX]
#   <repo>           path to the git repo to scan (default: PWD)
#   --max-bytes N    override the size threshold (default 52428800)
#   --allowlist RE   regex; matching paths are skipped
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

repo="${LARGE_FILE_REPO:-$PWD}"
max_bytes="${LARGE_FILE_MAX_BYTES:-52428800}"   # 50 MiB
allowlist="${LARGE_FILE_ALLOWLIST:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --max-bytes) [ $# -ge 2 ] || { echo "large-file-guard: --max-bytes needs N" >&2; exit 2; }; max_bytes="$2"; shift 2;;
    --allowlist) [ $# -ge 2 ] || { echo "large-file-guard: --allowlist needs REGEX" >&2; exit 2; }; allowlist="$2"; shift 2;;
    --) shift; break;;
    -*) echo "large-file-guard: unknown flag '$1'" >&2; exit 2;;
    *) repo="$1"; shift;;
  esac
done

# must be a git repo (file:// or worktree or normal)
if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
  echo "large-file-guard: '$repo' is not a git repo" >&2
  exit 2
fi

# 1) STAGED oversized files — the pre-commit path. Anything in the index (already
#    `git add`-ed) is about to enter the next commit. Scanning the index directly
#    catches them whether or not the worktree is clean.
# 2) WORKTREE oversized files — files present and modified but not staged. Catching
#    them at preflight gives the droid a chance to `git rm` BEFORE the next
#    `git add`. A 200MB file that gets `git add`-ed the next turn would otherwise
#    skip both the pre-commit hook and the staged check.
#
# We use `git ls-files --stage` to enumerate the index, plus `git ls-files -o` to
# pick up untracked-but-modified files in the working tree (untracked-only, not
# ignored). Files outside the repo (e.g. /tmp) are out of scope.

hits_staged=""
staged_list="$(git -C "$repo" ls-files --stage -z 2>/dev/null | awk -v RS='\0' '{
  # format: "<mode> <hash> <stage>\t<path>"
  n = index($0, "\t"); if (n == 0) next
  path = substr($0, n+1)
  # we want only the size: pull hash from the third field
  split($0, a, " "); hash = a[2]
  print hash "\t" path
}')"
while IFS=$'\t' read -r hash path; do
  [ -n "$path" ] || continue
  [ -n "$allowlist" ] && printf '%s' "$path" | grep -Eq "$allowlist" && continue
  # index hash is a blob hash; size = the blob's size in the object DB
  size="$(git -C "$repo" cat-file -s "$hash" 2>/dev/null || echo 0)"
  if [ "$size" -gt "$max_bytes" ]; then
    hits_staged="${hits_staged}${path}	${size}
"
  fi
done <<< "$staged_list"

# untracked-but-present files in the working tree (skip ignored). The hard-block
# only fires on a PUSH, so untracked files are advisory UNLESS they are
# known-large by extension (e.g. .bin, .zip, .tar.gz, .parquet, .onnx) — but
# the simpler, safer rule is to flag any untracked >50MB so a `git add` cannot
# silently push it over the line next turn.
hits_untracked=""
untracked_list="$(git -C "$repo" ls-files --others --exclude-standard -z 2>/dev/null | awk -v RS='\0' '{print}')"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  [ -n "$allowlist" ] && printf '%s' "$path" | grep -Eq "$allowlist" && continue
  # only flag things in the worktree (skip /tmp, ~/, etc.)
  full="$repo/$path"
  [ -f "$full" ] || continue
  size="$(stat -c %s "$full" 2>/dev/null || echo 0)"
  if [ "$size" -gt "$max_bytes" ]; then
    hits_untracked="${hits_untracked}${path}	${size}
"
  fi
done <<< "$untracked_list"

rc=0
if [ -n "$hits_staged" ]; then
  echo "large-file-guard: RED — STAGED file(s) exceed ${max_bytes} bytes (would block / warn at push):" >&2
  while IFS=$'\t' read -r path size; do
    [ -n "$path" ] || continue
    printf '    %-12s  %s\n' "$(numfmt --to=iec --suffix=B "$size" 2>/dev/null || echo "${size}B")" "$path" >&2
  done <<< "$hits_staged"
  echo "    FIX: git rm --cached <path>, then either: re-attach to LFS, split into a release artifact," >&2
  echo "         or add an allowlist entry (LARGE_FILE_ALLOWLIST='$path' or pass --allowlist)." >&2
  rc=1
fi
if [ -n "$hits_untracked" ]; then
  echo "large-file-guard: RED — UNTRACKED file(s) in the worktree exceed ${max_bytes} bytes:" >&2
  while IFS=$'\t' read -r path size; do
    [ -n "$path" ] || continue
    printf '    %-12s  %s\n' "$(numfmt --to=iec --suffix=B "$size" 2>/dev/null || echo "${size}B")" "$path" >&2
  done <<< "$hits_untracked"
  echo "    FIX: delete, move out of the repo, or add an allowlist entry before 'git add'." >&2
  rc=1
fi

if [ "$rc" -eq 0 ]; then
  echo "large-file-guard: GREEN (no file >${max_bytes} bytes staged or untracked in $repo)."
fi
exit "$rc"
