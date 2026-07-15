#!/usr/bin/env bash
# curate.sh — Curation pass over the memory store.
#
# DEDUPS near-identical notes (sha256 content hash),
# FLAGS conflicting/contradicting facts (shared-tag heuristic),
# DECAYS unreferenced-in-N-days notes to archive/ (using last_referenced frontmatter).
#
# APPROVAL-GATED: default mode is DRY-RUN (propose only). --apply executes.
# NEVER silently deletes — always proposes actions for operator review.
#
# Usage:
#   curate.sh [--notes-dir <path>] [--decay-days <N>] [--apply]
#
# Environment hooks (for testing):
#   CURATE_NOTES_DIR        — notes directory (default: <fleet-root>/../memory)
#   CURATE_DECAY_DAYS       — decay threshold in days (default: 30)
#   CURATE_DEDUP_DISABLE=1  — skip dedup check (simulates reverted dedup logic)
#   CURATE_DECAY_DISABLE=1  — skip decay check (simulates reverted decay logic)
#   CURATE_CONFLICT_DISABLE=1 — skip conflict check

set -euo pipefail
SCRIPT="curate"
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NOTES_DIR="${CURATE_NOTES_DIR:-$(cd "$FLEET/.." && pwd)/memory}"
ARCHIVE_SUBDIR="archive"
DECAY_DAYS="${CURATE_DECAY_DAYS:-30}"
DECAY_SECONDS=$(( DECAY_DAYS * 86400 ))

APPLY=0
DEDUP_DISABLE="${CURATE_DEDUP_DISABLE:-0}"
DECAY_DISABLE="${CURATE_DECAY_DISABLE:-0}"
CONFLICT_DISABLE="${CURATE_CONFLICT_DISABLE:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --notes-dir) NOTES_DIR="$2"; shift 2 ;;
    --decay-days) DECAY_DAYS="$2"; DECAY_SECONDS=$(( DECAY_DAYS * 86400 )); shift 2 ;;
    --apply) APPLY=1; shift ;;
    --help|-h)
      echo "Usage: curate.sh [--notes-dir <path>] [--decay-days <N>] [--apply]"
      echo "Curation pass: dedup, conflict-flag, decay-archive. Default dry-run."
      exit 0 ;;
    *) echo "curate: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

[ -d "$NOTES_DIR" ] || { echo "curate: notes dir '$NOTES_DIR' not found" >&2; exit 1; }

ARCHIVE_DIR="$NOTES_DIR/$ARCHIVE_SUBDIR"
NOW=$(date +%s)

# --- helpers ---
note_name() { basename "$1" .md; }

# Read a flat frontmatter field (key: value).
frontmatter_field() {
  awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null
}

# Compute content hash ignoring runtime-mutable frontmatter fields.
content_hash() {
  grep -vE '^(last_referenced|learned_at|valid_from|valid_until):' "$1" | sha256sum | cut -d' ' -f1
}

echo "--- $SCRIPT: curation pass ---"
echo "  notes: $NOTES_DIR  archive: $ARCHIVE_DIR  decay: ${DECAY_DAYS}d  mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo ""

# Gather all note files (skip archive/ subdir).
NOTES=()
while IFS= read -r -d '' f; do
  NOTES+=("$f")
done < <(find "$NOTES_DIR" -maxdepth 1 -name '*.md' -type f -print0 2>/dev/null || true)

[ ${#NOTES[@]} -eq 0 ] && { echo "  (no notes found)"; echo "--- done ---"; exit 0; }

echo "  ${#NOTES[@]} note(s) scanned"
echo ""

HAS_PROPOSAL=0

# =============================================
# 1. DEDUP — group by content hash
# =============================================
if [ "$DEDUP_DISABLE" -eq 0 ]; then
  echo "== 1. DEDUP =="
  declare -A HASH_MAP
  declare -A HASH_NAMES

  for f in "${NOTES[@]}"; do
    h="$(content_hash "$f")"
    n="$(note_name "$f")"
    if [ -n "${HASH_MAP[$h]:-}" ]; then
      HASH_NAMES["$h"]="${HASH_NAMES[$h]:-${HASH_MAP[$h]}} $n"
    else
      HASH_MAP[$h]="$n"
    fi
  done

  DUP_COUNT=0
  for h in "${!HASH_NAMES[@]}"; do
    names="${HASH_NAMES[$h]}"
    # Pick the most recently referenced as the keeper
    keeper=""
    keeper_ts=0
    for n in $names; do
      nf="$NOTES_DIR/$n.md"
      ts="$(frontmatter_field last_referenced "$nf" || echo 0)"
      [ "${ts:-0}" -gt "$keeper_ts" ] && { keeper="$n"; keeper_ts=$ts; }
    done
    echo "  DUPLICATE group (hash=$h):$names"
    echo "    -> keep: $keeper"
    for n in $names; do
      [ "$n" = "$keeper" ] && continue
      echo "    -> DEDUP: merge '$n' into '$keeper'"
      HAS_PROPOSAL=1
      DUP_COUNT=$((DUP_COUNT + 1))
      if [ "$APPLY" -eq 1 ]; then
        mkdir -p "$ARCHIVE_DIR"
        mv "$NOTES_DIR/$n.md" "$ARCHIVE_DIR/${n}.md.duplicate-of-${keeper}"
        echo "       (archived: $n.md)"
      fi
    done
  done
  [ "$DUP_COUNT" -eq 0 ] && echo "  (no duplicates found)"
  echo ""
fi

# =============================================
# 2. CONFLICT — flag notes sharing tags
# =============================================
if [ "$CONFLICT_DISABLE" -eq 0 ]; then
  echo "== 2. CONFLICT FLAG =="
  declare -A TAG_NOTES
  for f in "${NOTES[@]}"; do
    n="$(note_name "$f")"
    tags="$(frontmatter_field tags "$f" || true)"
    [ -z "$tags" ] && continue
    IFS=',' read -ra TAGLIST <<< "$tags"
    for t in "${TAGLIST[@]}"; do
      t="$(echo "$t" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
      [ -n "$t" ] || continue
      TAG_NOTES["$t"]="${TAG_NOTES[$t]:-} $n"
    done
  done

  CONFLICT_COUNT=0
  for t in "${!TAG_NOTES[@]}"; do
    notes="${TAG_NOTES[$t]}"
    # Count distinct notes sharing this tag
    read -ra NLIST <<< "$notes"
    [ ${#NLIST[@]} -le 1 ] && continue
    echo "  TAG '$t' shared by:${notes}"
    CONFLICT_COUNT=$((CONFLICT_COUNT + 1))
    HAS_PROPOSAL=1
    # Conflict flag is informational-only (no --apply action for conflicts)
  done
  [ "$CONFLICT_COUNT" -eq 0 ] && echo "  (no tag-based conflicts found)"
  echo ""
fi

# =============================================
# 3. DECAY — unreferenced-in-N-days -> archive
# =============================================
if [ "$DECAY_DISABLE" -eq 0 ]; then
  echo "== 3. DECAY =="
  STALE_COUNT=0
  for f in "${NOTES[@]}"; do
    n="$(note_name "$f")"
    lr="$(frontmatter_field last_referenced "$f" || true)"
    if [ -z "$lr" ]; then
      echo "  SKIP '$n' (no last_referenced — cannot assess decay)"
      continue
    fi
    age=$(( NOW - lr ))
    if [ "$age" -gt "$DECAY_SECONDS" ]; then
      days_old=$(( age / 86400 ))
      echo "  STALE '$n' (last_referenced ${days_old}d ago, threshold ${DECAY_DAYS}d)"
      echo "    -> propose archive: $n.md"
      HAS_PROPOSAL=1
      STALE_COUNT=$((STALE_COUNT + 1))
      if [ "$APPLY" -eq 1 ]; then
        mkdir -p "$ARCHIVE_DIR"
        mv "$NOTES_DIR/$n.md" "$ARCHIVE_DIR/${n}.md"
        echo "       (archived: $n.md)"
      fi
    fi
  done
  [ "$STALE_COUNT" -eq 0 ] && echo "  (no stale notes found)"
  echo ""
fi

# =============================================
# Summary
# =============================================
echo "--- $SCRIPT: curation complete ---"
if [ "$HAS_PROPOSAL" -eq 1 ] && [ "$APPLY" -eq 0 ]; then
  echo "  Proposals above. Re-run with --apply to execute."
fi
if [ "$HAS_PROPOSAL" -eq 0 ]; then
  echo "  No curation actions needed."
fi
