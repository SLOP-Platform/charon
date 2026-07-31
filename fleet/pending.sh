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

# Inverse of label_for: "C" -> 2, "#12" -> 37. Prints nothing for a malformed label.
index_for(){
  local l="$1" i
  case "$l" in
    \#[0-9]*) echo $(( ${l#\#} + 25 ));;
    [A-Z])    for i in "${!letters[@]}"; do [ "${letters[$i]}" = "$l" ] && { echo "$i"; return; }; done;;
  esac
}

# EFFECTIVE high-water mark = max(HW file, highest label actually present in LIST).
#
# WHY THIS IS DERIVED AND NOT JUST READ [[fix-root-cause-never-workaround]]:
# the "labels are never reused" guarantee used to rest ENTIRELY on $HW, but
# fleet/state/* is GITIGNORED while OPERATOR-ACTIONS.md is TRACKED. So any fresh
# checkout, state wipe, or clone lost the counter while KEEPING the live items —
# and the counter restarted straight into labels that were still on the board.
# That is not hypothetical: it issued "#12" TWICE (REAP FOLLOW-UP and
# SEED-PRIOR-REFRESH both carried it), which made `done #12` delete BOTH rows,
# silently clearing an unrelated operator action.
# Deriving the floor from the tracked list makes the invariant survive losing $HW.
hw_effective(){
  local hw best i L
  hw="$(cat "$HW" 2>/dev/null || echo -1)"
  case "$hw" in ''|*[!0-9-]*) hw=-1;; esac
  best="$hw"
  while IFS=$'\t' read -r L _; do
    [ -z "$L" ] && continue
    i="$(index_for "$L")" || continue
    [ -n "$i" ] && [ "$i" -gt "$best" ] && best="$i"
  done < "$LIST"
  echo "$best"
}

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
  local idx; idx=$(( $(hw_effective) + 1 ))
  # Belt AND braces: even with a correct floor, never hand out a label that is
  # currently on the board. An ambiguous label is worse than a skipped one.
  while cut -f1 "$LIST" 2>/dev/null | grep -qxF "$(label_for "$idx")"; do idx=$((idx+1)); done
  echo "$idx" > "$HW"
  printf '%s\t%s\n' "$(label_for "$idx")" "$text" >> "$LIST"
  cmd_list
}

cmd_done(){
  local raw="${1:-}"; [ -z "$raw" ] && { echo "usage: pending.sh done <label>" >&2; exit 1; }
  local up; up=$(printf '%s' "$raw" | tr '[:lower:]' '[:upper:]')
  local n; n=$(cut -f1 "$LIST" | grep -cxF "$up" || true)
  if [ "$n" -eq 0 ]; then echo "unknown item: $raw" >&2; exit 1; fi
  # FAIL CLOSED on ambiguity: `awk '$1!=t'` deletes EVERY row carrying the label,
  # so clearing a duplicated label silently destroys an unrelated operator action.
  # Refuse rather than guess which one was meant.
  if [ "$n" -gt 1 ]; then
    echo "REFUSING: label '$up' is on $n items — clearing it would delete all of them." >&2
    echo "Relabel the duplicates in $LIST first (labels must be unique)." >&2
    exit 1
  fi
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
