#!/usr/bin/env bash
# model-scorecard.sh — per-model x per-work-class performance ledger (build-rig only).
# Small file-based store; only a tiny aggregate ever enters session context, on demand.
# Subcommands: append | render | reviewed | --due
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TSV="$HERE/model-scorecard.tsv"
MARK="$HERE/state/last-scorecard-review"
TODAY="$(date +%F)"
TAB=$'\t'

VALID_SOURCE="live bench"
VALID_CLASS="money-path routing ci-infra refactor bugfix tests greenfield-feature docs"
VALID_VERDICT="MERGE FIXES BLOCK"
VALID_GATE="pass fail -"

die() { echo "error: $*" >&2; exit 1; }
in_set() { local x="$1"; shift; for e in "$@"; do [ "$x" = "$e" ] && return 0; done; return 1; }

# count data rows (skip comments/blanks)
row_count() {
  [ -f "$TSV" ] || { echo 0; return; }
  awk -F'\t' '!/^#/ && NF>0 {n++} END{print n+0}' "$TSV"
}

cmd_append() {
  [ $# -ge 9 ] || die "append needs: <date> <source> <ref> <work_class> <tier> <model> <verdict> <gate> <score> <note...>"
  local date="$1" source="$2" ref="$3" wclass="$4" tier="$5" model="$6" verdict="$7" gate="$8" score="$9"
  shift 9
  local note="$*"
  [ -n "$note" ] || note="-"
  case "$note" in *"$TAB"*) die "note must not contain tabs";; esac
  echo "$date" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' || die "date must be YYYY-MM-DD"
  in_set "$source"  $VALID_SOURCE  || die "source must be one of: $VALID_SOURCE"
  in_set "$wclass"  $VALID_CLASS   || die "work_class must be one of: $VALID_CLASS"
  in_set "$verdict" $VALID_VERDICT || die "verdict must be one of: $VALID_VERDICT"
  in_set "$gate"    $VALID_GATE    || die "gate must be one of: $VALID_GATE"
  case "$tier" in 0|1|2|3|4|-) ;; *) die "tier must be 0-4 or -";; esac
  case "$score" in -) ;; ''|*[!0-9]*) die "score must be 0-100 or -";; *) [ "$score" -ge 0 ] && [ "$score" -le 100 ] || die "score 0-100";; esac
  [ -f "$TSV" ] || die "ledger not found: $TSV"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$date" "$source" "$ref" "$wclass" "$tier" "$model" "$verdict" "$gate" "$score" "$note" >> "$TSV"
  echo "appended: $model / $wclass / $verdict (rows now $(row_count))"
}

cmd_render() {
  [ -f "$TSV" ] || die "ledger not found: $TSV"
  awk -F'\t' '
    !/^#/ && NF>0 {
      m=$6; wc=$4; v=$7; src=$2; tier=$5; sc=$9
      key=m SUBSEP wc
      n[key]++
      if(!(key in seen)){ seen[key]=1; order[++ok]=key }
      if(v=="MERGE") merge[key]++
      if(v=="BLOCK") block[key]++
      if(src=="bench" && sc ~ /^[0-9]+$/){
        tk=m SUBSEP tier
        tsum[tk]+=sc; tn[tk]++
        if(!(tk in tseen)){ tseen[tk]=1; torder[++tk_n]=tk }
      }
    }
    END{
      printf "MODEL-SCORECARD  (per model x work_class)\n"
      printf "%-16s %-18s %3s %7s %7s\n","model","work_class","n","merge%","block%"
      printf "%-16s %-18s %3s %7s %7s\n","-----","----------","---","------","------"
      for(i=1;i<=ok;i++){
        k=order[i]; split(k,a,SUBSEP)
        mr=(n[k]?100*merge[k]/n[k]:0); br=(n[k]?100*block[k]/n[k]:0)
        printf "%-16s %-18s %3d %6.0f%% %6.0f%%\n",a[1],a[2],n[k],mr,br
      }
      if(tk_n>0){
        printf "\nBENCH mean score  (per model x tier)\n"
        printf "%-16s %4s %3s %8s\n","model","tier","n","mean"
        printf "%-16s %4s %3s %8s\n","-----","----","---","----"
        for(i=1;i<=tk_n;i++){
          k=torder[i]; split(k,a,SUBSEP)
          printf "%-16s %4s %3d %8.1f\n",a[1],a[2],tn[k],tsum[k]/tn[k]
        }
      }
    }' "$TSV"
}

cmd_reviewed() {
  printf '%s\trows=%s\n' "$TODAY" "$(row_count)" > "$MARK"
  echo "stamped review: $TODAY rows=$(row_count)"
}

# emit 1 if a review is owed, else 0 (on stdout)
owed() {
  local rows; rows="$(row_count)"
  if [ ! -f "$MARK" ]; then
    [ "$rows" -ge 3 ] && echo 1 || echo 0
    return
  fi
  local mdate mrows since new
  mdate="$(awk '{print $1}' "$MARK")"
  mrows="$(sed -n 's/.*rows=\([0-9]*\).*/\1/p' "$MARK")"
  [ -n "$mrows" ] || mrows=0
  new=$(( rows - mrows ))
  # days since last review
  local m_s t_s
  m_s="$(date -d "$mdate" +%s 2>/dev/null || echo 0)"
  t_s="$(date -d "$TODAY" +%s 2>/dev/null || date +%s)"
  since=$(( (t_s - m_s) / 86400 ))
  if [ "$new" -ge 8 ]; then echo 1; return; fi
  if [ "$since" -ge 14 ] && [ "$new" -ge 1 ]; then echo 1; return; fi
  echo 0
}

cmd_due() {
  [ "$(owed)" = "1" ] || exit 0
  local rows new_txt=""
  rows="$(row_count)"
  if [ -f "$MARK" ]; then
    local mrows; mrows="$(sed -n 's/.*rows=\([0-9]*\).*/\1/p' "$MARK")"; [ -n "$mrows" ] || mrows=0
    new_txt=" (+$(( rows - mrows )) new since last review)"
  fi
  echo "NUDGE: model-scorecard review is DUE — $rows rows$new_txt. Skim the pivot below, adjust model tiering if warranted, then run: bash $HERE/model-scorecard.sh reviewed"
  cmd_render
}

case "${1:-}" in
  append)   shift; cmd_append "$@" ;;
  render)   cmd_render ;;
  reviewed) cmd_reviewed ;;
  --due)    cmd_due ;;
  *) echo "usage: $0 {append|render|reviewed|--due}" >&2; exit 1 ;;
esac
