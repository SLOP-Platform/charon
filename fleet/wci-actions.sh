#!/usr/bin/env bash
# wci-actions.sh — MECHANIZED WCI actions report. Recomputes the objective, reality-tracking parts
# (collision hotspots from live `owns`, board-coverage blind spots) from the CURRENT board every run,
# so it never goes stale. The JUDGMENT parts (placement moves, ranked prose) live in the curated
# state/ROADMAP-WCI-AUDIT.md — refresh those by re-running the WCI-audit subsession (a pointer is printed).
#
# Usage: bash fleet/wci-actions.sh
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"
ROADMAP="$FLEET/state/ROADMAP.tsv"
AUDIT="$FLEET/state/ROADMAP-WCI-AUDIT.md"
TS="$(date -u +%FT%TZ 2>/dev/null || echo now)"

echo "WCI ACTIONS — live board reality @ $TS"
echo "=================================================================="

echo
echo "## 1. COLLISION HOTSPOTS  (a file owned by >=2 tickets = that set CANNOT parallelize)"
# file <TAB> ticket, from every board/*.md 'owns:' comma-list; ticket = board filename stem
awk '
  FNR==1 { n=split(FILENAME,a,"/"); t=a[n]; sub(/\.md.*$/,"",t) }
  /^owns:/ { s=$0; sub(/^owns:[[:space:]]*/,"",s);
             m=split(s,paths,","); for(i=1;i<=m;i++){ p=paths[i]; gsub(/^[ \t]+|[ \t]+$/,"",p);
             if(p!="") print p "\t" t } }
' "$BOARD"/*.md 2>/dev/null \
| sort \
| awk -F'\t' '{ c[$1]++; w[$1]=w[$1] (w[$1]?", ":"") $2 }
              END { for(f in c) if(c[f]>=2) printf "%d\t%s\t%s\n", c[f], f, w[f] }' \
| sort -rn \
| awk -F'\t' '{ printf "  [%s owners] %s\n            <- %s\n", $1, $2, $3 }'
echo "  (none = every board ticket owns a disjoint file)"

echo
echo "## 2. BOARD-COVERAGE BLIND SPOTS  (roadmap tickets with NO board file = collisions uncomputable)"
RT=$(grep -cvE '^#|^[[:space:]]*$' "$ROADMAP" 2>/dev/null)
BF=$(ls "$BOARD"/*.md 2>/dev/null | wc -l | tr -d ' ')
printf "  roadmap tickets: %s   |   board files: %s\n" "$RT" "$BF"
ks_rt=$(grep -cE $'\tKS[0-9]' "$ROADMAP" 2>/dev/null); ks_bf=$(ls "$BOARD" 2>/dev/null | grep -icE '^ks[0-9]')
b_rt=$(grep -cE $'\tB[0-9]' "$ROADMAP" 2>/dev/null);   b_bf=$(ls "$BOARD" 2>/dev/null | grep -icE '^b[0-9]')
printf "  KEYSTONE: %s roadmap tickets / %s board files  %s\n" "$ks_rt" "$ks_bf" "$([ "$ks_bf" -lt "$ks_rt" ] && echo '<-- BLIND: add owns/difficulty board files' )"
printf "  BRIDGE:   %s roadmap tickets / %s board files  %s\n" "$b_rt" "$b_bf" "$([ "$b_bf" -lt "$b_rt" ] && echo '<-- BLIND: add owns/difficulty board files' )"

echo
echo "## 3. PLACEMENT + RANKED ACTIONS  (judgment layer — refresh via the WCI-audit subsession)"
if [ -f "$AUDIT" ]; then
  echo "  curated report: $AUDIT"
  echo "  --- current top actions (from that file) ---"
  awk '/^## RANKED ACTIONS/{p=1} p&&/^[0-9]+\./{print "  "$0}' "$AUDIT" | head -12
else
  echo "  (no curated audit yet — run the WCI-audit subsession to generate $AUDIT)"
fi
echo
echo "note: sections 1-2 are LIVE (recomputed from the board); section 3 is judgment — re-run the audit to refresh."
