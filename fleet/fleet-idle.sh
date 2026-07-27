#!/usr/bin/env bash
# fleet-idle.sh — is it safe to run work that may INTERRUPT other sessions?
# Exit 0 = IDLE (safe), 1 = BUSY (not safe). Prints why, always.
# Deliberately conservative: anything it cannot prove is idle counts as BUSY.
set -uo pipefail
busy=0

echo "=== live opencode sessions ==="
sessions="$(ps -eo pid,etime,args 2>/dev/null | grep '[o]pencode --model' || true)"
if [ -n "$sessions" ]; then
  echo "$sessions"
  n=$(printf '%s\n' "$sessions" | grep -c .)
  echo "-> $n session(s) RUNNING"
  busy=1
else
  echo "(none)"
fi

echo
echo "=== worktrees with uncommitted work ==="
found=0
for w in /home/stack/charon-wt/* /home/stack/charon-private-wt/*; do
  [ -d "$w/.git" ] || [ -f "$w/.git" ] || continue
  d=$(git -C "$w" status --short 2>/dev/null | grep -c . || true)
  if [ "${d:-0}" -gt 0 ]; then echo "  $(basename "$w"): $d file(s) dirty"; found=1; fi
done
[ "$found" = 0 ] && echo "(none)" || busy=1

echo
echo "=== unlanded commits awaiting review ==="
found=0
for w in /home/stack/charon-wt/* /home/stack/charon-private-wt/*; do
  [ -d "$w" ] || continue
  b=$(git -C "$w" rev-parse --abbrev-ref HEAD 2>/dev/null) || continue
  [ "$b" = "HEAD" ] && continue
  base=master; git -C "$w" rev-parse --verify -q origin/master >/dev/null 2>&1 && base=origin/master
  c=$(git -C "$w" rev-list --count "$base..$b" 2>/dev/null || echo 0)
  if [ "${c:-0}" -gt 0 ]; then echo "  $(basename "$w") [$b]: $c commit(s) unlanded"; found=1; fi
done
[ "$found" = 0 ] && echo "(none)"
# NOTE: unlanded commits do NOT set busy — they are work to LAND, not work in flight.

echo
if [ "$busy" = 0 ]; then
  echo "FLEET IDLE — safe to run interrupt-capable work."
  exit 0
fi
echo "FLEET BUSY — do NOT run work that can interrupt sessions."
echo "A stray interrupt kills live work; landing/reviewing is still safe."
exit 1
