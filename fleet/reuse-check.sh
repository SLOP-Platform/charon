#!/usr/bin/env bash
# reuse-check.sh — one-command wrapper around `ksf reuse-check` so sessions never
# hand-roll a fresh grep/reimplementation search when a candidate module/function
# might already exist somewhere in the repo.
#
# Usage:
#   fleet/reuse-check.sh [repo-root] <candidate-file> [threshold]
#   fleet/reuse-check.sh "" src/charon/cache.py                       # repo-root defaults to code/charon
#   fleet/reuse-check.sh /path/to/other/repo src/charon/cache.py
#   fleet/reuse-check.sh /path/to/other/repo src/charon/cache.py 0.6
#
# Arg order matches `ksf --repo-root <R> reuse-check <candidate> [--threshold T]`:
#   $1 = repo-root (defaults to /home/stack/code/charon; pass "" to take the default)
#   $2 = candidate (a real file PATH relative to repo-root — ksf reads+diffs its
#        source text against the rest of the tree; NOT a free-text tool name)
#   $3 = threshold (optional; ksf's own default is used when omitted)
#
# Known limitation (checked 2026-07-13): .ksf/keystone.db in code/charon has 4 tables
# (decisions, built_inventory, backlog, sqlite_sequence) and ALL are empty (0 rows).
# reuse-check does NOT read that db — ksf/reuse_check.py does a live filesystem AST/text
# comparison of the candidate against the tree, so it works correctly today even with an
# empty index. The empty db only affects OTHER ksf subcommands (reconcile/gate/module),
# not reuse-check.
set -euo pipefail
KSF="/home/stack/code/keystone/.venv/bin/ksf"
[ -x "$KSF" ] || { echo "reuse-check.sh: ksf binary not found/executable at $KSF" >&2; exit 2; }
[ $# -ge 1 ] || { echo "usage: reuse-check.sh [repo-root] <candidate-file> [threshold]" >&2; exit 2; }

ROOT="${1:-/home/stack/code/charon}"; [ -n "$ROOT" ] || ROOT="/home/stack/code/charon"
CANDIDATE="${2:?usage: reuse-check.sh [repo-root] <candidate-file> [threshold]}"
THRESHOLD="${3:-}"

if [ -n "$THRESHOLD" ]; then
  exec "$KSF" --repo-root "$ROOT" reuse-check "$CANDIDATE" --threshold "$THRESHOLD"
else
  exec "$KSF" --repo-root "$ROOT" reuse-check "$CANDIDATE"
fi
