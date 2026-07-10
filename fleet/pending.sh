#!/usr/bin/env bash
# Operator action list — the running, plain-language list of things the fleet
# MANAGER needs the OPERATOR to do or decide. Mechanized so it PERSISTS across
# sessions (committed file) and is surfaced at every preflight. Each item has a
# STABLE letter (A, B, C…) that does NOT shift when another item is cleared, so
# the operator can reliably answer by letter.
#
#   pending.sh add "<plain-language item>"   # manager appends an item (auto-assigns next free letter)
#   pending.sh done <letter>                 # clear an item once handled (other letters unchanged)
#   pending.sh list                          # show open items (preflight calls this)
#
# Data lives in state/OPERATOR-ACTIONS.md, one item per line: "<LETTER><TAB><text>".
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIST="$HERE/state/OPERATOR-ACTIONS.md"
mkdir -p "$(dirname "$LIST")"
touch "$LIST"

letters=(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)

cmd_list(){
  if ! grep -q '[^[:space:]]' "$LIST" 2>/dev/null; then
    echo "OPERATOR ACTIONS: none pending"
    return 0
  fi
  echo "OPERATOR ACTIONS — things the manager needs you to do/decide (answer by letter):"
  local L T
  while IFS=$'\t' read -r L T; do
    [ -z "$L" ] && continue
    echo "  $L. $T"
  done < "$LIST"
}

next_letter(){
  local used i
  used=$(cut -f1 "$LIST" 2>/dev/null || true)
  for i in "${letters[@]}"; do
    grep -qxF "$i" <<<"$used" || { echo "$i"; return 0; }
  done
  echo "?"; return 1
}

cmd_add(){
  local text="$*"
  [ -z "$text" ] && { echo "usage: pending.sh add \"<plain-language item>\"" >&2; exit 1; }
  local L; L=$(next_letter)
  printf '%s\t%s\n' "$L" "$text" >> "$LIST"
  cmd_list
}

cmd_done(){
  local raw="${1:-}"; [ -z "$raw" ] && { echo "usage: pending.sh done <letter>" >&2; exit 1; }
  local up; up=$(printf '%s' "$raw" | tr '[:lower:]' '[:upper:]')
  if ! cut -f1 "$LIST" | grep -qxF "$up"; then echo "unknown item: $raw" >&2; exit 1; fi
  awk -F'\t' -v t="$up" '$1!=t' "$LIST" > "$LIST.tmp" && mv "$LIST.tmp" "$LIST"
  echo "cleared $up"
  cmd_list
}

case "${1:-list}" in
  add)     shift; cmd_add "$@";;
  done)    shift; cmd_done "$@";;
  list|"") cmd_list;;
  *) echo "usage: $0 {add \"<item>\"|done <letter>|list}" >&2; exit 1;;
esac
