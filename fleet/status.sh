#!/usr/bin/env bash
# charon-fleet status — the manager dashboard (the team_status.sh equivalent).
# Unlike mediastack's (heartbeat/token PROXIES), this reports GROUND TRUTH:
#   live droid processes (ps) · board + claim age (state/) · open PRs + CI (gh).
# No heartbeat/warden/token-meter — Charon-Fleet is ephemeral-per-ticket, so a droid
# is "working" iff its launcher process is alive and holds a claim.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
B="$FLEET/board"; S="$FLEET/state"; REPO_SLUG="SLOP-Platform/charon"
source "$FLEET/_lib.sh"
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
now=$(date +%s)
age_of(){ [ -e "$1" ] || { echo "-"; return; }; local m s; m=$(date -r "$1" +%s 2>/dev/null||echo "$now")
  s=$((now-m)); if [ "$s" -lt 3600 ]; then printf '%dm' $((s/60)); else printf '%dh%02dm' $((s/3600)) $(((s%3600)/60)); fi; }

printf '\n  CHARON-FLEET STATUS @ %s\n' "$(date -u +%FT%TZ)"

# --- KEY SERVICES: delegate liveness to the service-watchdog (do NOT re-implement it here).
# SERVICE-LIVENESS-WATCHDOG owns the registry + probes; status.sh just surfaces its verdict.
WATCHDOG="$FLEET/watchdog/discover-services.sh"
if [ -x "$WATCHDOG" ]; then
  printf '\n  KEY SERVICES (registry-driven; fleet/watchdog/)\n'
  bash "$WATCHDOG" --health --no-dark 2>/dev/null | grep -vE '^-- ' | sed 's/^/  /' \
    || printf '  (watchdog error — run: fleet/watchdog/discover-services.sh)\n'
fi

# --- DROIDS: live launcher tabs (one per `fleet-droid.sh <tier>`) ---
printf '\n  DROIDS (live tabs)        %-7s %-9s %s\n' TIER UPTIME 'WORKING-ON'
ndroid=0
while read -r pid etime args; do
  [ -n "${pid:-}" ] || continue
  tier="$(grep -oE 'fleet-droid\.sh +[a-z]+' <<<"$args" | awk '{print $2}')"
  [ -n "$tier" ] || continue
  droid="$tier-$pid"; on="(idle/claiming)"
  for cf in "$S"/claims/*; do [ -e "$cf" ] || continue
    [ "$(awk 'NR==1{print $1}' "$cf")" = "$droid" ] && { on="$(basename "$cf")"; break; }; done
  printf '  %-25s %-7s %-9s %s\n' "$droid" "$tier" "$etime" "$on"; ndroid=$((ndroid+1))
done < <(ps -eo pid=,etime=,args= 2>/dev/null | grep '[f]leet-droid\.sh')
[ "$ndroid" -eq 0 ] && printf '  (no droid tabs running)\n'

# --- BOARD: every ticket + state + who/how-long ---
printf '\n  BOARD\n  %-6s %-7s %-9s %-22s %s\n' ID TIER STATE BRANCH 'HELD-BY / NOTE'
ready=0; claimed=0; propen=0; rdone=0; blocked=0; nparked=0
for f in "$B"/*.md; do
  [ -e "$f" ] || continue; id="$(basename "$f" .md)"
  tier="$(meta tier "$f")"; br="$(meta branch "$f")"; dep="$(meta depends_on "$f")"
  # PARKED is reported BELOW the real progress states (a parked ticket that is already
  # submitted is still PR-OPEN) but ABOVE blocked/ready — an unclaimable ticket must never
  # print as `ready`, or the manager plans a wave around work no droid can take.
  # Predicate lives in _lib.sh (is_parked) and mirrors claim.sh's skip rule.
  if   [ -e "$S/done/$id" ];      then st=DONE;    note="-"; rdone=$((rdone+1))
  elif [ -e "$S/submitted/$id" ]; then st=PR-OPEN; note="$(age_of "$S/submitted/$id") ago"; propen=$((propen+1))
  elif [ -e "$S/needs-push/$id" ]; then st=NEEDS-PUSH; note="committed, NO PR — land-needs-push.sh $id"
  elif [ -e "$S/claims/$id" ];    then st=claimed; note="$(awk 'NR==1{print $1}' "$S/claims/$id") · $(age_of "$S/claims/$id")"; claimed=$((claimed+1))
  elif is_parked "$f"; then st=PARKED
    pv="$(parked_value "$f")"
    # A bare `parked: true` carries no reason — the reason (if any) lives in note:. A prose
    # park IS its own reason, so echo it: that is the operator directive the manager must see.
    case "$pv" in true|yes|1) note="unclaimable — see note:";; *) note="unclaimable — ${pv:0:44}";; esac
    nparked=$((nparked+1))
  elif ! deps_done "$dep"; then st=blocked; note="needs $dep"; blocked=$((blocked+1))
  else st=ready; note="-"; ready=$((ready+1)); fi
  printf '  %-6s %-7s %-9s %-22s %s\n' "$id" "$tier" "$st" "$br" "$note"
done

# --- PRs + CI gate (ground truth that work actually landed green) ---
printf '\n  OPEN PRs (draft → operator merges)\n'
if command -v gh >/dev/null 2>&1; then
  gh pr list --repo "$REPO_SLUG" --json number,headRefName,isDraft \
    -q '.[] | "  #\(.number)  \(.headRefName)  [\(if .isDraft then "draft" else "READY-TO-MERGE" end)]"' 2>/dev/null \
    || echo "  (gh error — try: gh auth status)"
  printf '  (CI per PR:  gh pr checks <n> --repo %s)\n' "$REPO_SLUG"
else echo "  (gh not installed)"; fi

printf '\n  SUMMARY  droids:%d   ready:%d  claimed:%d  PR-open:%d  done:%d  blocked:%d  parked:%d\n\n' \
  "$ndroid" "$ready" "$claimed" "$propen" "$rdone" "$blocked" "$nparked"
printf '  (token/usage is NOT faked here — see Claude'\''s own /usage. board.sh = the quick view.)\n\n'
