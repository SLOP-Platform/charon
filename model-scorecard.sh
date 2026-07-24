#!/usr/bin/env bash
# model-scorecard.sh — per-model x per-work-class performance ledger (build-rig only).
# Small file-based store; only a tiny aggregate ever enters session context, on demand.
# Subcommands: append | render | reviewed | --due
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# TSV-APPEND-UNIFY (TOOL-AUDIT-REDUNDANCY finding 6): cmd_append below is the
# ONE validate+append implementation. capability/auto_append.py is a thin
# Python delegator that invokes `append` here with CHARON_SCORECARD_TSV set
# to its caller's ledger path — the env var exists for that delegation and
# for hermetic tests; unset means the real ledger next to this script.
TSV="${CHARON_SCORECARD_TSV:-$HERE/model-scorecard.tsv}"
MARK="$HERE/state/last-scorecard-review"
TODAY="$(date +%F)"
TAB=$'\t'

# bench2 = BENCHMARK-V2-DESIGN.md's tokens-in-scope efficiency-scored
# harness rows (source tag only - the scoring math itself lives entirely
# in benchmark/lib/{efficiency,close_season,tier_chart}.py, none of it
# here). A bench2 row uses the EXACT same 15-column shape as a bench row
# (tokens_in/tokens_out at cols 14/15, same as any post-TOKEN-CAPTURE
# bench row) - only the `source` value differs, so cmd_append needed no
# other change to accept it.
VALID_SOURCE="live bench bench2"
VALID_CLASS="money-path routing ci-infra refactor bugfix tests greenfield-feature docs frontend"
VALID_VERDICT="MERGE FIXES BLOCK"
VALID_GATE="pass fail -"
# PROVISIONAL-vs-ACTIVE (#20 BENCH-PROVISIONAL-SCORING — pivot plan §2/§8 Q4).
# A row's `stage` (16th trailing column) is the TRUST axis, orthogonal to the
# `source` provenance axis: `active` rows feed live grades/tier; `provisional`
# rows (a not-yet-promoted unit's data) are COLLECTED but excluded from every
# grade until benchmark/promote.py flips the unit. A row with no 16th column
# (every legacy 13/15-col row) defaults to `active`, so nothing historical
# shifts. Follows the tokens_in/out trailing-column pattern exactly.
VALID_STAGE="provisional active"

die() { echo "error: $*" >&2; exit 1; }
in_set() { local x="$1"; shift; for e in "$@"; do [ "$x" = "$e" ] && return 0; done; return 1; }

# count data rows (skip comments/blanks)
row_count() {
  [ -f "$TSV" ] || { echo 0; return; }
  awk -F'\t' '!/^#/ && NF>0 {n++} END{print n+0}' "$TSV"
}

# THE single appender implementation (TSV-APPEND-UNIFY): both the shell CLI
# (`bash model-scorecard.sh append ...`) and capability/auto_append.py's
# Python API funnel through this one validate+append path.
cmd_append() {
  [ $# -ge 12 ] || die "append needs: <date> <source> <ref> <work_class> <tier> <model> <verdict> <gate> <score> <time_s> <cost_usd> <corrections> <note...>"
  local date="$1" source="$2" ref="$3" wclass="$4" tier="$5" model="$6" verdict="$7" gate="$8" score="$9"
  shift 9
  local time_s="$1" cost_usd="$2" corrections="$3"
  shift 3
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
  case "$time_s" in -) ;; ''|*[!0-9.]*) die "time_s must be a non-negative number of seconds or -";; esac
  case "$cost_usd" in -) ;; ''|*[!0-9.]*) die "cost_usd must be a non-negative number or -";; esac
  case "$corrections" in -) ;; ''|*[!0-9]*) die "corrections must be a non-negative integer or -";; esac
  # TOKEN-CAPTURE: tokens_in/tokens_out, when the caller has them, ride along
  # in optional env vars set right before invoking `append` (see
  # benchmark/bench.sh) rather than as new positional args - `note` above is
  # variadic ("$*", already consumed every remaining arg above), so there is
  # no positional slot left after it for more required args without an
  # incompatible reshuffle. Appended as NEW TRAILING COLUMNS (14, 15) so
  # every existing reader keeps working unchanged on both legacy 13-column
  # rows already in the ledger and these new 15-column ones: tier_chart.py's
  # `load_rows`/`bench_rows_for` only ever unpack `cols[:13]`, and
  # `cmd_render` below only ever addresses $1-$12. Defaults to "-" (never
  # guessed) for any caller that doesn't set them - e.g. one written before
  # this change, or a provider/response that doesn't report tokens.
  local tokens_in="${CHARON_SCORECARD_TOKENS_IN:--}"
  local tokens_out="${CHARON_SCORECARD_TOKENS_OUT:--}"
  case "$tokens_in" in -) ;; ''|*[!0-9]*) die "tokens_in must be a non-negative integer or -";; esac
  case "$tokens_out" in -) ;; ''|*[!0-9]*) die "tokens_out must be a non-negative integer or -";; esac
  # PROVISIONAL-vs-ACTIVE (#20): `stage` rides along in CHARON_SCORECARD_STAGE
  # (same optional-env-var channel as the token vars above — `note` is variadic
  # so there's no positional slot left), appended as the NEW 16th trailing
  # column. Defaults to `active` (never guessed provisional) so any caller that
  # doesn't set it — every existing bench/live path today — keeps writing
  # active rows exactly as before. bench.sh looks the unit's current stage up
  # in benchmark/units.tsv and sets this before calling `append`.
  local stage="${CHARON_SCORECARD_STAGE:-active}"
  in_set "$stage" $VALID_STAGE || die "stage must be one of: $VALID_STAGE"
  [ -f "$TSV" ] || die "ledger not found: $TSV"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$date" "$source" "$ref" "$wclass" "$tier" "$model" "$verdict" "$gate" "$score" \
    "$time_s" "$cost_usd" "$corrections" "$note" "$tokens_in" "$tokens_out" "$stage" >> "$TSV"
  echo "appended: $model / $wclass / $verdict (rows now $(row_count))"
}

cmd_render() {
  [ -f "$TSV" ] || die "ledger not found: $TSV"
  awk -F'\t' '
    !/^#/ && NF>0 {
      # PROVISIONAL-vs-ACTIVE (#20): stage is the 16th column; a row with no
      # 16th field (legacy 13/15-col) defaults to active. Provisional rows are
      # COLLECTED but NOT COUNTED into any aggregate below — they are tallied
      # separately and surfaced in a clearly-labeled "PROVISIONAL (not counted)"
      # block at the end so they are visible but can never move a live number.
      st=(NF>=16 && $16!="" ? $16 : "active")
      if(st=="provisional"){ prov[$6 SUBSEP $4]++; provtot++; next }
      m=$6; wc=$4; v=$7; src=$2; tier=$5; sc=$9; ts=$10; cu=$11; co=$12
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
      if(!(m in eseen)){ eseen[m]=1; eorder[++en]=m }
      if(ts ~ /^[0-9.]+$/){ tssum[m]+=ts; tsn[m]++ }
      if(cu ~ /^[0-9.]+$/){ cusum[m]+=cu; cun[m]++ }
      if(co ~ /^[0-9]+$/){ cosum[m]+=co; con[m]++ }
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
      if(en>0){
        printf "\nEFFICIENCY mean  (per model, rows with data only; \"-\" = no data)\n"
        printf "%-16s %9s %10s %11s\n","model","mean_s","mean_$","mean_corr"
        printf "%-16s %9s %10s %11s\n","-----","------","------","---------"
        for(i=1;i<=en;i++){
          m=eorder[i]
          mt=(tsn[m]?sprintf("%9.1f",tssum[m]/tsn[m]):sprintf("%9s","-"))
          mc=(cun[m]?sprintf("%10.4f",cusum[m]/cun[m]):sprintf("%10s","-"))
          mo=(con[m]?sprintf("%11.1f",cosum[m]/con[m]):sprintf("%11s","-"))
          printf "%-16s %s %s %s\n",m,mt,mc,mo
        }
      }
      if(provtot>0){
        printf "\nPROVISIONAL (not counted — unpromoted units, #20)\n"
        printf "%-16s %-18s %3s\n","model","work_class","n"
        printf "%-16s %-18s %3s\n","-----","----------","---"
        for(k in prov){ split(k,a,SUBSEP); printf "%-16s %-18s %3d\n",a[1],a[2],prov[k] }
        printf "(promote a unit with: benchmark/promote.py --unit <id>)\n"
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
