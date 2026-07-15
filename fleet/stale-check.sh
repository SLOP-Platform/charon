#!/usr/bin/env bash
# stale-check.sh — flag stalled/quarantined fleet sessions, one line each.
#
# Two ground-truth sources (composed, not reimplemented):
#   1. state/claims/<id> marker mtime — the SAME "held-by / age" signal fleet/status.sh's
#      age_of()/BOARD table already renders. A claim marker's mtime does not advance without
#      progress (no separate heartbeat exists in this rig), so "marker older than the stall
#      threshold" == "this live session has made no visible progress in that long".
#   2. state/loop-guard/<id> quarantine markers — the exact file contract fleet/loop-guard.sh's
#      `record` step writes (droid=/count=/threshold=/quarantined=/reason= lines). Read
#      directly here (same convention loop-guard.sh's own `list` subcommand uses) rather than
#      shelling out to it, so this stays hermetically testable via STALE_LOOPGUARD_DIR without
#      ever touching the live board's real quarantine state — loop-guard.sh itself has no such
#      override hook (it derives its state dir from its own script path) and is owned
#      elsewhere, so it is not edited here.
#
# STANDALONE by design: fleet/preflight.sh is owned elsewhere and is NOT edited by this ticket.
# preflight (or the manager, ad hoc) should call `fleet/stale-check.sh` and treat a non-zero
# exit as a red flag, same as any other preflight check.
#
# Usage:
#   stale-check.sh                one line per stale/quarantined session; exit 0 = all clear,
#                                  exit 1 = at least one stale or quarantined session found.
#
# Env overrides (isolated self-test seams; defaults are the real fleet):
#   STALE_STATE          state dir (default <fleet>/state)
#   STALE_CLAIMS_DIR      claims dir (default <state>/claims)
#   STALE_LOOPGUARD_DIR   loop-guard quarantine dir (default <state>/loop-guard)
#   STALE_THRESHOLD_S     stall threshold in seconds (default 900)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # fleet/

case "${1:-}" in
  -h|--help)
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
esac

STATE="${STALE_STATE:-$HERE/state}"
CLAIMS_DIR="${STALE_CLAIMS_DIR:-$STATE/claims}"
LOOPGUARD_DIR="${STALE_LOOPGUARD_DIR:-$STATE/loop-guard}"
THRESHOLD="${STALE_THRESHOLD_S:-900}"

now="$(date +%s)"
hits=0

echo "STALE-CHECK  threshold=${THRESHOLD}s"

# --- 1. live sessions past the stall threshold (state/claims/<id> mtime) ---
if [ -d "$CLAIMS_DIR" ]; then
  shopt -s nullglob
  for cf in "$CLAIMS_DIR"/*; do
    [ -f "$cf" ] || continue
    id="$(basename "$cf")"
    mtime="$(date -r "$cf" +%s 2>/dev/null || echo "$now")"
    age=$((now - mtime))
    if [ "$age" -ge "$THRESHOLD" ]; then
      droid="$(awk 'NR==1{print $1}' "$cf" 2>/dev/null)"
      [ -n "$droid" ] || droid="?"
      echo "STALE  $id  claimed-by=$droid  age=${age}s  threshold=${THRESHOLD}s"
      hits=$((hits + 1))
    fi
  done
  shopt -u nullglob
else
  echo "  (no claims dir: $CLAIMS_DIR)"
fi

# --- 2. loop-guard quarantined tickets (state/loop-guard/<id> markers) ---
if [ -d "$LOOPGUARD_DIR" ]; then
  shopt -s nullglob
  for qf in "$LOOPGUARD_DIR"/*; do
    [ -f "$qf" ] || continue   # skips the runs/ subdir
    id="$(basename "$qf")"
    droid="$(grep -m1 '^droid=' "$qf" 2>/dev/null | cut -d= -f2-)"
    since="$(grep -m1 '^quarantined=' "$qf" 2>/dev/null | cut -d= -f2-)"
    reason="$(grep -m1 '^reason=' "$qf" 2>/dev/null | cut -d= -f2-)"
    [ -n "$reason" ] || reason="(no reason recorded)"
    echo "QUARANTINED  $id  droid=${droid:-?}  since=${since:-?}  reason=$reason"
    hits=$((hits + 1))
  done
  shopt -u nullglob
fi

if [ "$hits" -eq 0 ]; then
  echo "  OK — no stale sessions, no quarantined tickets."
else
  echo "  $hits issue(s) — see line(s) above."
fi
echo "  (NOTE: standalone check — preflight.sh should call this; not wired in here, preflight is owned elsewhere.)"

if [ "$hits" -eq 0 ]; then
  exit 0
else
  exit 1
fi
