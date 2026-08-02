#!/usr/bin/env bash
# stranded-work-cron.sh — the SESSION-INDEPENDENT CALLER for fleet/checks/stranded-work.sh.
#
# WHY THIS FILE EXISTS
#   The detector and the fail-loud channel BOTH already existed. detect_stranded_work
#   (fleet/preflight.sh) fires the detector, and pending.sh -> OPERATOR-ACTIONS.md surfaces it
#   unconditionally at every preflight. The gap was never detection and never reporting — it was
#   that BOTH legs only ran INSIDE a session. No session for two days meant no scan for two days,
#   which is how a 96-commit backlog accumulated with a working detector installed.
#   [[dynamic-tools-never-on-demand]]: a dynamic-data tool without a cadence is not a control.
#
# WHY cron AND NOT monit/systemd (settled, do not re-litigate)
#   monit is NOT INSTALLED on this box or on 4-LOM (`command -v monit` -> rc 1, no /etc/monit*),
#   and its own SSOT fleet/state/service-registry.tsv does not exist and is not git-tracked: the
#   watchdog is a config GENERATOR with no runtime and no input. There is no systemd user manager
#   either (/run/user/1000 absent; enabling linger needs root). cron IS running (/usr/sbin/cron -f)
#   and needs no root. The cheapest mechanism that actually executes wins [[cost-is-a-heavy-weight]].
#
# THE §L SELF-REFERENTIAL TRAP, HANDLED EXPLICITLY
#   A crontab line pointing at a path that a checkout does not have registers PERFECTLY and then
#   never does anything — cron logs a 127 to mail nobody reads. That is the same false-receipt
#   shape as a green check with an empty body. So: if the detector is missing, this wrapper does
#   NOT no-op. It writes the heartbeat anyway (so "cron fired" stays distinguishable from "cron
#   was removed"), raises a LOUD operator action, and exits non-zero.
#
# ANTI-SILENCE CONTRACT
#   The heartbeat ($HB) is written on EVERY invocation, including failures. Freshness of that file
#   is what preflight checks (detect_stranded_work). Without it, "the crontab entry was deleted"
#   and "there is nothing stranded" produce the IDENTICAL observable — silence — which is §J (a
#   gate marked done that quietly stopped firing) repeating one level up.
#
# DEDUPE — TWO LAYERS, BOTH NEEDED
#   1. STATE-CHANGE HASH: sha256 of the SORTED set of `STRANDED[...]` detail lines, collected with
#      SW_LIMIT=0 so it covers EVERY finding, not the first 5 printed. Unchanged set -> unchanged
#      hash -> pending.sh is not called at all. This is the cheap common case.
#   2. KEYED UPSERT: the hash alone is NOT sufficient and this was measured, not assumed. Three
#      consecutive live runs produced "256 / 259 / 258 finding(s)" because other agents were
#      landing work in between. Every one of those was a REAL state change with different text, so
#      the hash correctly let all three through — and the board grew three rows anyway. A recurring
#      report of a MOVING number is ONE standing item whose value changes. So the announcement is
#      keyed on the literal prefix PEND_KEY and rewritten in place, label preserved: one row.
#
# REPORT-ONLY, exactly like the detector: no rm, no push, no branch mutation.
#
# Usage: fleet/checks/stranded-work-cron.sh
# Exit:  0 ran, nothing stranded        1 ran, stranded work found (advisory)
#        2 detector MISSING (loud)      3 ran, PR state undetermined
# Env:   SWC_FLEET  override fleet dir (tests)   SWC_STATE  override state dir (tests)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="${SWC_FLEET:-$(cd "$HERE/.." && pwd)}"
STATE="${SWC_STATE:-$FLEET/state}"
DETECTOR="$FLEET/checks/stranded-work.sh"
HB="$STATE/.stranded-work.heartbeat"     # anti-silence: mtime == "cron last fired"
HASHF="$STATE/.stranded-work.hash"       # state-change key: only announce on CHANGE
LOG="$STATE/stranded-work-cron.log"
PEND_KEY="STRANDED WORK:"                 # keyed upsert: this caller owns exactly ONE board row
mkdir -p "$STATE" 2>/dev/null

# Heartbeat FIRST and unconditionally. It answers "did the cadence fire?", never "was it clean?" —
# conflating those two is the whole defect this wrapper exists to close.
heartbeat(){ printf '%s rc=%s %s\n' "$(date -Is)" "${1:-?}" "${2:-}" > "$HB"; }
announce(){ bash "$FLEET/pending.sh" add --key "$1" "$1$2" >/dev/null 2>&1 || true; }

if [ ! -f "$DETECTOR" ]; then
  heartbeat 2 "detector-missing"
  echo "stranded-work-cron: FAIL — detector not found at $DETECTOR" | tee -a "$LOG" >&2
  # LOUD, not silent. A cron entry aimed at a path this checkout lacks is the §L trap.
  announce "STRANDED WORK CRON BROKEN:" " registered but its detector is MISSING at $DETECTOR — the scheduled scan has been a no-op. Land fleet/checks/stranded-work.sh or remove the crontab entry."
  exit 2
fi

OUT="$(SW_LIMIT=0 bash "$DETECTOR" --quiet 2>&1)"; RC=$?
printf '%s %s\n' "$(date -Is)" "rc=$RC" >> "$LOG"

# ── state-change key ──────────────────────────────────────────────────────────────────────────
LINES="$(printf '%s\n' "$OUT" | grep '^STRANDED\[' | LC_ALL=C sort || true)"
N="$(printf '%s' "$LINES" | grep -c . || true)"
SUM="$(printf '%s\n' "$LINES" | sha256sum 2>/dev/null | cut -d' ' -f1)"
KEY="rc=$RC n=$N sha=$SUM"
PREV="$(cat "$HASHF" 2>/dev/null || true)"

if [ "$KEY" != "$PREV" ]; then
  printf '%s\n' "$KEY" > "$HASHF"
  if [ "${N:-0}" -gt 0 ] 2>/dev/null; then
    # Per-shape counts, not the raw lines: OPERATOR-ACTIONS.md is a decision list, not a log.
    SHAPES="$(printf '%s\n' "$LINES" | sed -n 's/^STRANDED\[\([^]]*\)\].*/\1/p' \
              | LC_ALL=C sort | uniq -c | awk '{printf "%s x %s, ", $1, $2}' | sed 's/, $//')"
    announce "$PEND_KEY" " $N finding(s) — $SHAPES. Full list: fleet/checks/stranded-work.sh (SW_LIMIT=0). Recover with fleet/land.sh <branch> <repo>; never reap by hand."
  elif [ "$RC" = 3 ]; then
    announce "$PEND_KEY" " scan could not read PR state (gh missing/offline/rate-limited) — this is NOT a clean receipt. Re-run fleet/checks/stranded-work.sh once gh is reachable."
  fi
fi

heartbeat "$RC" "n=$N"
printf '%s\n' "$OUT"
exit "$RC"
