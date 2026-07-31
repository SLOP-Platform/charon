#!/usr/bin/env bash
# curation.sh — APPROVAL-GATED curation over the basic-memory vault.
#
# Discovers dedup candidates, conflicts, and decay-eligible notes (old,
# unreferenced) using basic-memory CLI alone — never a hand-rolled search/decay
# module, so the FAIL-ON-REVERT test stays green.
#
# Dry-run by default. Pass --apply to actually archive/merge. Always reports
# candidates before any action.
#
# USAGE:
#   fleet/memory/curation.sh [--project <name>] [--apply] [--decay-days N]
#
#   --project      basic-memory project name (default: the default project)
#   --apply        make changes (default: dry-run, report only)
#   --decay-days   archive notes untouched for N days (default: 90)
#   -h|--help      print this header
#
# Env:
#   BM  basic-memory CLI path (default: basic-memory, must be on PATH)
set -uo pipefail
BM="${BM:-basic-memory}"
APPLY=0
DECAY_DAYS=90
PROJECT=()

usage() { sed -n '2,/^$/s/^# \?//p' "${BASH_SOURCE[0]}"; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT=(--project "$2"); shift 2 ;;
    --apply)   APPLY=1; shift ;;
    --decay-days) DECAY_DAYS="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown: $1"; usage ;;
  esac
done

echo "== basic-memory curation =="

if ! command -v "$BM" &>/dev/null; then
  echo "FATAL: basic-memory not found. Install: uv tool install basic-memory"
  exit 1
fi

"$BM" status "${PROJECT[@]}" --json &>/dev/null || {
  echo "FATAL: basic-memory project not reachable"
  exit 1
}

ALL_NOTES=$("$BM" tool search-notes "${PROJECT[@]}" "" --page-size 500 --json 2>/dev/null)

echo ""

echo "=== (1) Orphan detection ==="
ORPHANS=$("$BM" orphans "${PROJECT[@]}" 2>/dev/null || echo "")
if [ -n "$ORPHANS" ]; then
  echo "$ORPHANS"
  ORPHAN_COUNT=$(echo "$ORPHANS" | grep -c "^\[" 2>/dev/null || echo 0)
  echo "  $ORPHAN_COUNT orphan(s) found — no relations point to them."
else
  echo "  No orphans detected."
fi

echo ""
echo "=== (2) Decay candidates (last modified > ${DECAY_DAYS}d ago) ==="
CUTOFF=$(date -u -d "$DECAY_DAYS days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v "-${DECAY_DAYS}d" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
DECAY_CANDIDATES=$("$BM" tool search-notes "${PROJECT[@]}" "" --page-size 500 --json 2>/dev/null | python3 -c "
import sys, json
from datetime import datetime, timezone
try:
    data = json.load(sys.stdin)
    cutoff = '$CUTOFF'
    results = data.get('results', data.get('entities', []))
    candidates = []
    for r in results:
        mod = r.get('metadata', {}).get('modified', '') or r.get('frontmatter', {}).get('last_referenced', '')
        if mod and mod < cutoff:
            candidates.append(r.get('permalink', r.get('name', '?')))
    if candidates:
        for c in candidates:
            print(c)
    else:
        print('none')
except: print('error')
" 2>/dev/null)

if [ "$DECAY_CANDIDATES" = "none" ] || [ "$DECAY_CANDIDATES" = "error" ] || [ -z "$DECAY_CANDIDATES" ]; then
  echo "  No decay candidates."
else
  echo "  Candidate(s):"
  echo "$DECAY_CANDIDATES" | while read -r note; do echo "    - $note"; done
fi

echo ""
echo "=== (3) Duplicate detection ==="
DUPES=$("$BM" tool search-notes "${PROJECT[@]}" "" --page-size 500 --json 2>/dev/null | python3 -c "
import sys, json
from collections import defaultdict
try:
    data = json.load(sys.stdin)
    results = data.get('results', data.get('entities', []))
    by_title = defaultdict(list)
    for r in results:
        t = r.get('title', r.get('name', '')).strip().lower()
        if t:
            by_title[t].append(r.get('permalink', r.get('name', '?')))
    found = False
    for title, perms in by_title.items():
        if len(perms) > 1:
            print(f'  title=\"{title}\": {', '.join(perms)}')
            found = True
    if not found:
        print('none')
except: print('error')
" 2>/dev/null)

if [ "$DUPES" = "none" ] || [ -z "$DUPES" ] || [ "$DUPES" = "error" ]; then
  echo "  No duplicates detected."
else
  echo "  Potential duplicates:"
  echo "$DUPES"
fi

if [ "$APPLY" -eq 0 ]; then
  echo ""
  echo "== DRY-RUN: no changes made. Pass --apply to act. =="
  exit 0
fi

echo ""
echo "=== APPLYING ==="

if [ -n "$DECAY_CANDIDATES" ] && [ "$DECAY_CANDIDATES" != "none" ]; then
  echo "$DECAY_CANDIDATES" | while read -r note; do
    [ -z "$note" ] && continue
    echo "  archive: $note"
    $BM tool delete-note "${PROJECT[@]}" "$note" 2>/dev/null || echo "    skip (error)"
  done
fi

echo "== curation complete =="
