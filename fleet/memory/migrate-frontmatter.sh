#!/usr/bin/env bash
# migrate-frontmatter.sh — ONE-SHOT frontmatter migration for the REAL basic-memory vault.
#
# Scans every note in the active basic-memory project and ensures tags and
# last_referenced are present in frontmatter. Uses basic-memory CLI to read
# each note and write-note to apply changes — NOT a hand-rolled file walker,
# so the FAIL-ON-REVERT test (asserts no hand-rolled search/decay module) stays
# green.
#
# Safe to run multiple times (idempotent): already-migrated notes are skipped.
#
# USAGE:
#   fleet/memory/migrate-frontmatter.sh [--project <name>] [--dry-run]
#
#   --project   basic-memory project name (default: the default project)
#   --dry-run   show what would change without writing
#   -h|--help   print this header
#
# Env:
#   BM  basic-memory CLI path (default: basic-memory, must be on PATH)
set -uo pipefail
BM="${BM:-basic-memory}"
DRY_RUN=0
PROJECT=()

usage() { sed -n '2,/^$/s/^# \?//p' "${BASH_SOURCE[0]}"; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT=(--project "$2"); shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown: $1"; usage ;;
  esac
done

echo "== basic-memory frontmatter migration =="

if ! command -v "$BM" &>/dev/null; then
  echo "FATAL: basic-memory not found. Install: uv tool install basic-memory"
  exit 1
fi

"$BM" status "${PROJECT[@]}" --json &>/dev/null || {
  echo "FATAL: basic-memory project not reachable (run 'basic-memory doctor')"
  exit 1
}

search_all() {
  "$BM" tool search-notes "${PROJECT[@]}" "" --page-size 500 --json 2>/dev/null
}

notes=$(search_all)
count=$(echo "$notes" | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data.get('results',data.get('entities',[]))))" 2>/dev/null || echo 0)

if [ "$count" -eq 0 ]; then
  echo "No notes found — nothing to migrate."
  exit 0
fi

echo "Found $count note(s). Checking frontmatter..."

migrated=0
skipped=0
failed=0

for permalink in $(echo "$notes" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('results', data.get('entities', [])):
    p = r.get('permalink', r.get('name', ''))
    if p:
        print(p)
" 2>/dev/null); do
  note_json=$("$BM" tool read-note "${PROJECT[@]}" "$permalink" --json 2>/dev/null || true)
  [ -z "$note_json" ] && { failed=$((failed+1)); continue; }

  has_tags=$(echo "$note_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    fm = d.get('frontmatter', d.get('metadata', {}))
    tags = fm.get('tags', fm.get('metadata', {}) if isinstance(fm, dict) else {})
    if isinstance(tags, dict): tags = tags.get('tags', [])
    print('yes' if tags else 'no')
except: print('no')
" 2>/dev/null)

  has_lr=$(echo "$note_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    fm = d.get('frontmatter', d.get('metadata', {}))
    lr = fm.get('last_referenced', None)
    if lr is None and isinstance(fm, dict):
        lr = fm.get('metadata', {}).get('last_referenced', None) if isinstance(fm.get('metadata'), dict) else None
    print('yes' if lr else 'no')
except: print('no')
" 2>/dev/null)

  if [ "$has_tags" = "yes" ] && [ "$has_lr" = "yes" ]; then
    skipped=$((skipped+1))
    continue
  fi

  echo "  migrate: $permalink (tags=$has_tags last_referenced=$has_lr)"

  if [ "$DRY_RUN" -eq 1 ]; then
    migrated=$((migrated+1))
    continue
  fi

  "$BM" tool edit-note "${PROJECT[@]}" "$permalink" --find-replace "permalink:" "tags: []\nlast_referenced: $(date -u +%Y-%m-%dT%H:%M:%SZ)\npermalink:" 2>/dev/null && migrated=$((migrated+1)) || failed=$((failed+1))
done

echo "== done: $migrated migrated, $skipped already-caught up, $failed failed =="
[ "$DRY_RUN" -eq 1 ] && echo "(dry-run — no changes written)"
exit $failed
