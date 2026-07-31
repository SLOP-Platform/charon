#!/usr/bin/env bash
# fleet-idle.sh — is it safe to run work that may INTERRUPT other sessions?
# Exit 0 = IDLE (safe), 1 = BUSY (not safe). Prints why, always.
# Deliberately conservative: anything it cannot prove is idle counts as BUSY.
set -uo pipefail
busy=0

echo "=== live opencode sessions ==="
# Match BOTH spawn forms:
#   opencode --model charon/X                 (legacy)
#   opencode --port N --model charon/X         (fleet-spawn-worker.sh's exec)
# The original `[o]pencode --model` REQUIRES the two tokens to be adjacent in ps output
# and so NEVER matched a spawned worker — fleet-idle then printed `(none)` while the
# fleet was actively working, and exited 0 (safe to interrupt). That was bug 1.
#
# Anti-over-match discipline (the grep must not catch everything):
#   * `[o]pencode` keeps the regex from matching the grep process itself.
#   * `.*` between `opencode` and `--model` is bounded only by the literal `--model`
#     anchor (no leading space, so `.*` can match empty -> `opencode --model` adjacent
#     also matches, AS WELL AS `opencode --port N --model` with stuff between). An argv
#     like `grep opencode` has no `--model` substring -> never matches, and a path like
#     `.../opencode/spawn-worker.sh` doesn't reach `--model` either.
#   * FLEET_IDLE_PS overrides ps for the test suite to drive fake argvs hermetically.
#
# THE SEAM MUST NOT BREAK THE DEFAULT. A previous version of this fix wrote:
#     ps_cmd="${FLEET_IDLE_PS:-ps -eo pid,etime,args}"; "$ps_cmd" ...
# Quoting a MULTI-WORD default as a single word makes bash look for a command
# literally named `ps -eo pid,etime,args`; it fails with "command not found",
# `|| true` swallows it, and $sessions is ALWAYS empty — so fleet-idle reported
# IDLE with three live workers running. That is the ORIGINAL bug reintroduced in
# a worse form (silently, rather than by a wrong pattern). Every test passed,
# because every test SET FLEET_IDLE_PS to a single-word stub path and so never
# exercised the default branch at all.
# Keep the default as a REAL command invocation, not a string to be re-parsed.
if [ -n "${FLEET_IDLE_PS:-}" ]; then
  sessions="$("$FLEET_IDLE_PS" 2>/dev/null | grep -E '[o]pencode.*--model' || true)"
else
  sessions="$(ps -eo pid,etime,args 2>/dev/null | grep -E '[o]pencode.*--model' || true)"
fi
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
# FLEET_IDLE_SKIP_WT_CHECK lets the test suite exercise ONLY the process-detection
# branch without its assertions being shadowed by dirty work in the live worktrees.
if [ "${FLEET_IDLE_SKIP_WT_CHECK:-0}" = 1 ]; then
  echo "(skipped — FLEET_IDLE_SKIP_WT_CHECK=1)"
else
  for w in /home/stack/charon-wt/* /home/stack/charon-private-wt/*; do
    [ -d "$w/.git" ] || [ -f "$w/.git" ] || continue
    d=$(git -C "$w" status --short 2>/dev/null | grep -c . || true)
    if [ "${d:-0}" -gt 0 ]; then echo "  $(basename "$w"): $d file(s) dirty"; found=1; fi
  done
  [ "$found" = 0 ] && echo "(none)" || busy=1
fi

echo
echo "=== unlanded commits awaiting review ==="
found=0
if [ "${FLEET_IDLE_SKIP_WT_CHECK:-0}" = 1 ]; then
  echo "(skipped — FLEET_IDLE_SKIP_WT_CHECK=1)"
else
  for w in /home/stack/charon-wt/* /home/stack/charon-private-wt/*; do
    [ -d "$w" ] || continue
    b=$(git -C "$w" rev-parse --abbrev-ref HEAD 2>/dev/null) || continue
    [ "$b" = "HEAD" ] && continue
    base=master; git -C "$w" rev-parse --verify -q origin/master >/dev/null 2>&1 && base=origin/master
    c=$(git -C "$w" rev-list --count "$base..$b" 2>/dev/null || echo 0)
    if [ "${c:-0}" -gt 0 ]; then echo "  $(basename "$w") [$b]: $c commit(s) unlanded"; found=1; fi
  done
  [ "$found" = 0 ] && echo "(none)"
fi
# NOTE: unlanded commits do NOT set busy — they are work to LAND, not work in flight.

echo
if [ "$busy" = 0 ]; then
  echo "FLEET IDLE — safe to run interrupt-capable work."
  exit 0
fi
echo "FLEET BUSY — do NOT run work that can interrupt sessions."
echo "A stray interrupt kills live work; landing/reviewing is still safe."
exit 1
