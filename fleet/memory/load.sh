#!/usr/bin/env bash
# load.sh — PINNED-CORE memory loader for SessionStart hook.
# REPLACES the wholesale memory dump that used to cat every *.md file.
# Now: load only the small PINNED core; rest = pull-on-demand via memory.search.
#
# Usage:
#   bash fleet/memory/load.sh          # load pinned core only
#   bash fleet/memory/load.sh --full   # DEBUG only: compare vs full set
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="$HERE/pin.md"
SEARCH_PY="$HERE/search.py"
MARKDOWN_DIR="$HERE/markdown"

{
  echo "=== CHARON MANAGER PINNED CORE ==="
  echo ""

  if [ -f "$PIN" ]; then
    cat "$PIN"
  else
    echo "(PINNED CORE MISSING — no pinned memory loaded)"
  fi

  echo ""
  echo "---"
  echo "[memory] Pull-on-demand: use memory.search <query> to retrieve facts at point of need."
  echo "[memory] $(ls "$MARKDOWN_DIR"/*.md 2>/dev/null | wc -l) markdown files indexed."
  echo "---"

  if [ "${1:-}" = "--full" ]; then
    echo ""
    echo "=== FULL MEMORY SET (DEBUG) ==="
    echo ""
    for f in "$MARKDOWN_DIR"/*.md; do
      echo "--- $(basename "$f") ---"
      cat "$f"
      echo ""
    done
  fi
}
