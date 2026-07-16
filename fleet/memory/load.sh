#!/usr/bin/env bash
# load.sh — POINT-OF-NEED memory entry (MEMORY-WIRE-RETRIEVAL).
#
# Replaces the wholesale MEMORY.md dump. Two modes:
#   1. DEFAULT (no args)             — print PINNED core only + point-of-need pointer.
#                                       Wired into SessionStart hook so every session
#                                       opens with a tiny index (the wholesale set is
#                                       NEVER loaded into session context).
#   2. POINT-OF-NEED  --query <topic> — wrap fleet/memory/search.py: print ranked
#                                       results for <topic>. This is the same engine
#                                       a session would invoke inline; load.sh makes
#                                       it the canonical entry point so reuse-check
#                                       and tool-inventory both point here.
#
# Usage:
#   bash fleet/memory/load.sh                   # pinned core + pointer
#   bash fleet/memory/load.sh --query failover  # ranked top-10 for "failover"
#   bash fleet/memory/load.sh --json failover   # machine-readable results
#   bash fleet/memory/load.sh --full            # DEBUG only: compare vs full set
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="$HERE/pin.md"
SEARCH_PY="$HERE/search.py"
MARKDOWN_DIR="$HERE/markdown"

# ── point-of-need mode ──────────────────────────────────────────────────────
if [ "${1:-}" = "--query" ]; then
  shift
  if [ "$#" -eq 0 ]; then
    echo "load.sh: --query requires a topic argument" >&2
    exit 2
  fi
  exec python3 "$SEARCH_PY" "$@"
fi
if [ "${1:-}" = "--json" ]; then
  shift
  if [ "$#" -eq 0 ]; then
    echo "load.sh: --json requires a topic argument" >&2
    exit 2
  fi
  exec python3 "$SEARCH_PY" --json "$@"
fi

# ── default (pinned + pointer) ──────────────────────────────────────────────
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
  echo "[memory] Pull-on-demand: bash fleet/memory/load.sh --query <topic>"
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
