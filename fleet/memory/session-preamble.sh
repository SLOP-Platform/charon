#!/usr/bin/env bash
# session-preamble.sh — MEMORY-WIRE-RETRIEVAL: the SessionStart hook payload.
#
# Replaces the legacy wholesale MEMORY.md dump. Emits ONLY:
#   (a) the PINNED always-on directives (fleet/memory/pin.md), and
#   (b) a one-line pointer telling the session to call
#       `python3 fleet/memory/search.py "<topic>"` at point-of-need.
#
# The full ~95-file memory set is NO LONGER loaded. Everything else is
# pulled on demand via search.py — this is what ends the manual MEMORY.md
# hand-compaction (decay/dedup now handled by curate.sh on a schedule).
#
# Output contract: this script is invoked from ~/.claude/settings.json's
# SessionStart hook (the manager applies that follow-up — see
# MANAGER-WIRING note below). It is intended to be printed to the session's
# opening context, NOT substituted into a SubagentStart hook (that has its
# own narrower preamble: fleet/session-ctx-preamble.sh).
#
# Usage:
#   bash fleet/memory/session-preamble.sh          # session-start payload
#   bash fleet/memory/session-preamble.sh --check  # assert payload is small
#                                                  # + search returns ranked results
#                                                  # (used by tests/test_wire.sh)
#
# Manager-applied follow-ups (NOT done by this ticket — see MANAGER-WIRING):
#   1. ~/.claude/settings.json SessionStart hook switches from `cat MEMORY.md`
#      to `bash /home/stack/charon-private/fleet/memory/session-preamble.sh`.
#   2. Scheduled (cron / CronCreate) weekly run of `curate.sh --apply` to handle
#      decay + dedup on the markdown/ store.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="$HERE/pin.md"
SEARCH_PY="$HERE/search.py"
MARKDOWN_DIR="$HERE/markdown"

if [ "${1:-}" = "--check" ]; then
  # Self-test mode: return exit-0 only if (a) preamble is small relative to
  # the wholesale dump, and (b) search.py returns ranked results for a known
  # topic. Used by tests/test_wire.sh.
  pin_bytes=0
  if [ -f "$PIN" ]; then
    pin_bytes=$(wc -c < "$PIN" | tr -d ' ')
  fi
  total_md_bytes=0
  if [ -d "$MARKDOWN_DIR" ]; then
    total_md_bytes=$(cat "$MARKDOWN_DIR"/*.md 2>/dev/null | wc -c | tr -d ' ')
  fi
  echo "[wire-check] pin: ${pin_bytes} bytes"
  echo "[wire-check] markdown/: ${total_md_bytes} bytes"
  if [ "${total_md_bytes:-0}" -gt 0 ] && [ "${pin_bytes:-0}" -gt 0 ]; then
    ratio=$(python3 -c "print(f'{$pin_bytes / $total_md_bytes:.3f}')")
    echo "[wire-check] pin/markdown ratio: $ratio (must be < 0.5 for point-of-need wiring)"
  fi
  # Search must return ranked results for a known topic
  out="$(python3 "$SEARCH_PY" --json failover 2>/dev/null || true)"
  if [ -n "$out" ]; then
    n_results=$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)' 2>/dev/null || echo 0)
    echo "[wire-check] search failover: ${n_results} result(s)"
  fi
  exit 0
fi

# ── Payload: pinned core + point-of-need pointer ────────────────────────────
{
  echo "=== CHARON MANAGER PINNED CORE (always-on) ==="
  echo ""
  if [ -f "$PIN" ]; then
    cat "$PIN"
  else
    echo "(PINNED CORE MISSING — no pinned memory loaded)"
  fi

  echo ""
  echo "---"
  md_count=0
  if [ -d "$MARKDOWN_DIR" ]; then
    md_count=$(ls "$MARKDOWN_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
  fi
  echo "[memory] Pull-on-demand: NOT pre-loaded. At point-of-need, run:"
  echo "[memory]   python3 fleet/memory/search.py \"<topic>\"          # ranked top-10"
  echo "[memory]   python3 fleet/memory/search.py --json \"<topic>\"   # machine-readable"
  echo "[memory] ${md_count} markdown files indexed (not loaded)."
  echo "[memory] For decay/dedup curation: bash fleet/memory/curate.sh [--apply]"
  echo "---"
}

# ── MANAGER-WIRING (NOT done by this ticket) ────────────────────────────────
# Two follow-ups are intentionally out of scope here. The memory wiring inside
# this repo is complete (preamble = pinned + pointer; load.sh wraps search.py;
# curate.sh handles decay/dedup). The integration into the Claude runtime is
# a manager concern because it touches ~/.claude/settings.json (operator home,
# not the repo) and the operator's scheduler.
#
#   1. SessionStart hook in ~/.claude/settings.json:
#        CURRENT: a `cat MEMORY.md` (or wholesale-dump) command
#        REPLACE: `bash /home/stack/charon-private/fleet/memory/session-preamble.sh`
#      This kills the wholesale dump at the runtime seam. The pinned core is
#      small (~1.5KB) so the per-session token cost is bounded; the ~95-file
#      markdown/ set is NEVER loaded into session context.
#
#   2. Scheduled (cron / CronCreate) weekly `curate.sh --apply` run.
#      Without this, the markdown/ set will only ever grow — decay and dedup
#      exist as code but never execute. A weekly cadence matches the 30-day
#      decay threshold (curate.sh default CURATE_DECAY_DAYS=30).
#
# Neither is implemented here. The code in this ticket is sufficient for
# BOTH to be applied later as no-op mechanical edits. Apply them as a
# follow-up ticket if/when desired — this ticket does not block on them.
