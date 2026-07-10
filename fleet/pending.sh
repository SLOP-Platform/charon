#!/usr/bin/env bash
# Operator action list — the running, plain-language list of things the fleet
# MANAGER needs the OPERATOR to do or decide. Mechanized so it PERSISTS across
# sessions (local state) and is surfaced at every preflight. Each item has a
# STABLE label that (a) does NOT shift when another item is cleared, and (b) is
# NEVER REUSED — once a label is handed out it is retired forever (monotonic
# high-water mark), so "answer C" can never mean two different things over time.
#
#   pending.sh add "<plain-language item>"   # append; auto-assigns the next never-used label
#   pending.sh done <label>                  # clear an item (other labels unchanged, label retired)
#   pending.sh list                          # show open items (preflight calls this)
#
# Data: state/OPERATOR-ACTIONS.md, one line per item "<LABEL><TAB><text>".
# High-water mark: state/.operator-actions.hw (largest label index ever assigned).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIST="$HERE/state/OPERATOR-ACTIONS.md"
HW="$HERE/state/.operator-actions.hw"
mkdir -p "$(dirname "$LIST")"
touch "$LIST"

letters=(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)

label_for(){ local i="$1"; if [ "$i" -lt 26 ]; then echo "${letters[$i]}"; else echo "#$((i-25))"; fi; }

cmd_list(){
  if ! grep -q '[^[:space:]]' "$LIST" 2>/dev/null; then
    echo "OPERATOR ACTIONS: none pending"
    return 0
  fi
  echo "OPERATOR ACTIONS — things the manager needs you to do/decide (answer by label):"
  local L T
  while IFS=$'\t' read -r L T; do
    [ -z "$L" ] && continue
    echo "  $L. $T"
  done < "$LIST"
}

cmd_add(){
  local text="$*"
  [ -z "$text" ] && { echo "usage: pending.sh add \"<plain-language item>\"" >&2; exit 1; }
  local hw idx; hw="$(cat "$HW" 2>/dev/null || echo -1)"; idx=$((hw+1))
  echo "$idx" > "$HW"
  printf '%s\t%s\n' "$(label_for "$idx")" "$text" >> "$LIST"
  cmd_list
}

cmd_done(){
  local raw="${1:-}"; [ -z "$raw" ] && { echo "usage: pending.sh done <label>" >&2; exit 1; }
  local up; up=$(printf '%s' "$raw" | tr '[:lower:]' '[:upper:]')
  if ! cut -f1 "$LIST" | grep -qxF "$up"; then echo "unknown item: $raw" >&2; exit 1; fi
  awk -F'\t' -v t="$up" '$1!=t' "$LIST" > "$LIST.tmp" && mv "$LIST.tmp" "$LIST"
  echo "cleared $up (label retired, never reused)"
  cmd_list
}

case "${1:-list}" in
  add)     shift; cmd_add "$@";;
  done)    shift; cmd_done "$@";;
  list|"") cmd_list;;
  *) echo "usage: $0 {add \"<item>\"|done <label>|list}" >&2; exit 1;;
esac
