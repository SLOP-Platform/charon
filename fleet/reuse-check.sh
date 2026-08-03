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
# BLAST RADIUS (PRIORITY-TODO A5 — graphify-affected-wire):
#   After the ksf reuse-check, `fleet/checks/blast-radius.sh` is called with the
#   candidate file to surface its graph neighbours — "what depends on this?" — as
#   ADDITIVE advisory output. Suppress with `BLAST_RADIUS=0`. The ksf exit code
#   is preserved as the overall exit code; the blast-radius section never changes
#   it.
#
# Known limitation (checked 2026-07-13): .ksf/keystone.db in code/charon has 4 tables
# (decisions, built_inventory, backlog, sqlite_sequence) and ALL are empty (0 rows).
# reuse-check does NOT read that db — ksf/reuse_check.py does a live filesystem AST/text
# comparison of the candidate against the tree, so it works correctly today even with an
# empty index. The empty db only affects OTHER ksf subcommands (reconcile/gate/module),
# not reuse-check.
set -uo pipefail
KSF="/home/stack/code/keystone/.venv/bin/ksf"
BLAST_RADIUS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/checks/blast-radius.sh"
[ -x "$KSF" ] || { echo "reuse-check.sh: ksf binary not found/executable at $KSF" >&2; exit 2; }
[ $# -ge 1 ] || { echo "usage: reuse-check.sh [repo-root] <candidate-file> [threshold]" >&2; exit 2; }

ROOT="${1:-/home/stack/code/charon}"; [ -n "$ROOT" ] || ROOT="/home/stack/code/charon"
CANDIDATE="${2:?usage: reuse-check.sh [repo-root] <candidate-file> [threshold]}"
THRESHOLD="${3:-}"

if [ -n "$THRESHOLD" ]; then
  "$KSF" --repo-root "$ROOT" reuse-check "$CANDIDATE" --threshold "$THRESHOLD"
else
  "$KSF" --repo-root "$ROOT" reuse-check "$CANDIDATE"
fi
ksf_rc=$?

echo ""
echo "=== BLAST RADIUS (graphify — blast-radius.sh) ==="
if [ -x "$BLAST_RADIUS_SCRIPT" ]; then
  bash "$BLAST_RADIUS_SCRIPT" "$ROOT" "$CANDIDATE" 2>&1 || true
else
  echo "reuse-check.sh: blast-radius.sh not found at $BLAST_RADIUS_SCRIPT — SKIP"
fi
echo "=== END BLAST RADIUS ==="

exit $ksf_rc
