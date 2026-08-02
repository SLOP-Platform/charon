#!/usr/bin/env bash
# ladder-health.sh — priority-ladder surfacer.
#
# For the top-K (default 10) priority tickets, prints CLAIMABLE or the exact EXCLUSION
# REASON across EVERY claim.sh exclusion cause — so a starved P0 is never invisible again.
#
# Exclusions checked (mirrors claim.sh line-for-line + broader gates):
#   QUARANTINED  — loop-guard marker (age + reason)
#   CLAIMED      — which droid; flagged STALE if droid process is dead
#   SUBMITTED    — submitted marker; flagged STALE if PR is CLOSED/MERGED
#   DONE         — already completed
#   PARKED       — parked field or note: PARKED
#   BLOCKED      — depends_on not done (names each undone dep)
#   TIER         — ticket tier > checker tier
#   BOARD_RED    — validate_board.sh failing blocks ALL claims
#   PARALLELIZABILITY-REFUSED — splittable + serial + unjustified
#
# Env (all optional):
#   LADDER_HEALTH_TOP=N    default 10
#   LADDER_HEALTH_TIER=t   default haiku (lowest; reports TIER skip for anything higher)
#   LADDER_HEALTH_SLUG=s   default SLOP-Platform/charon (for gh PR lookups)
#
# Wired into session-start/status surface — visibility IS the fix for silent priority-starvation.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$FLEET/_lib.sh"

TOP_N="${LADDER_HEALTH_TOP:-10}"
CHECK_TIER="${LADDER_HEALTH_TIER:-haiku}"
GH_SLUG="${LADDER_HEALTH_SLUG:-SLOP-Platform/charon}"

BOARD="$FLEET/board"; STATE="$FLEET/state"; LG="$STATE/loop-guard"

# ── Tier ranks (same source as claim.sh) ──────────────────────────────────────
declare -A RANK; nrank=0
if out="$(charon tier ranks 2>/dev/null)"; then
  while read -r n r; do [ -n "$n" ] && { RANK["$n"]=$r; nrank=$((nrank+1)); }; done <<<"$out"
fi
[ "$nrank" -gt 0 ] || RANK=([opus]=3 [sonnet]=2 [haiku]=1)
rank(){ echo "${RANK[$1]:-0}"; }
drank=$(rank "$CHECK_TIER")

# ── Temp workspace ────────────────────────────────────────────────────────────
TMPDIR="$(mktemp -d)"; trap 'rm -rf "$TMPDIR"' EXIT
INDEX="$TMPDIR/index"

# ── Delimiter: pipe (|) — NOT tab.  Tab is an IFS whitespace character so bash's
# `read` collapses consecutive tabs into a single delimiter, which silently drops
# empty fields (parked="", note="") and shifts all later columns.  Pipe is not IFS
# whitespace; consecutive `||` correctly produce empty fields. ──────────────────

# ── Build per-ticket INDEX (one awk pass, same pattern as claim.sh) ───────────
shopt -s nullglob
TICKET_FILES=("$BOARD"/*.md "$BOARD"/archive/*.md)
shopt -u nullglob

if [ "${#TICKET_FILES[@]}" -gt 0 ]; then
  printf '%s\0' "${TICKET_FILES[@]}" | awk -v rank_lookup="$(for k in "${!RANK[@]}"; do printf '%s=%s\n' "$k" "${RANK[$k]}"; done | LC_ALL=C sort)" '
    BEGIN {
      RS = "\0"
      n = split(rank_lookup, lines, "\n")
      for (i = 1; i <= n; i++) {
        split(lines[i], kv, "=")
        if (kv[1] != "") RANK[kv[1]] = kv[2] + 0
      }
      FS_P="|"
    }
    {
      file = $0
      id = file; sub(/^.*\//, "", id); sub(/\.md$/, "", id)
      is_archive = (file ~ /\/archive\//) ? 1 : 0
      tier = ""; parked = ""; note = ""; deps = ""; prio_raw = ""; owns = ""
      diff_raw = ""; repo = ""
      RS_SAVED = RS; RS = "\n"
      while ((getline line < file) > 0) {
        if      (line ~ /^tier:[[:space:]]*/)        { sub(/^tier:[[:space:]]*/, "", line);        tier   = line }
        else if (line ~ /^parked:[[:space:]]*/)     { sub(/^parked:[[:space:]]*/, "", line);     parked = tolower(line) }
        else if (line ~ /^note:[[:space:]]*/)       { sub(/^note:[[:space:]]*/, "", line);       note   = line }
        else if (line ~ /^depends_on:[[:space:]]*/) { sub(/^depends_on:[[:space:]]*/, "", line); deps   = line }
        else if (line ~ /^priority:[[:space:]]*/)   { sub(/^priority:[[:space:]]*/, "", line);   prio_raw = line }
        else if (line ~ /^owns:[[:space:]]*/)        { sub(/^owns:[[:space:]]*/, "", line);        owns   = line }
        else if (line ~ /^difficulty:[[:space:]]*/)  { sub(/^difficulty:[[:space:]]*/, "", line);  diff_raw = line }
        else if (line ~ /^repo:[[:space:]]*/)         { sub(/^repo:[[:space:]]*/, "", line);         repo   = line }
      }
      RS = RS_SAVED; close(file)
      gsub(/[\t\n]/, " ", tier); gsub(/[\t\n]/, " ", parked); gsub(/[\t\n]/, " ", note)
      gsub(/[\t\n]/, " ", deps); gsub(/[\t\n]/, " ", prio_raw); gsub(/[\t\n]/, " ", owns)
      gsub(/[\t\n]/, " ", diff_raw); gsub(/[\t\n]/, " ", repo)
      rank = (tier in RANK) ? RANK[tier] : 0
      prio = 9999
      if (prio_raw != "") {
        if (match(prio_raw, /-?[0-9]+/)) {
          prio = substr(prio_raw, RSTART, RLENGTH) + 0
          if (prio < 0) prio = 0; if (prio > 5) prio = 5
        }
      }
      blast = 0
      if (owns != "") {
        nowns = split(owns, oa, ",")
        for (oi = 1; oi <= nowns; oi++) {
          ot = oa[oi]; gsub(/^[[:space:]]+|[[:space:]]+$/, "", ot)
          if (ot != "") blast++
        }
      }
      diff = 0
      if (diff_raw != "") {
        if (match(diff_raw, /[0-9]+/)) {
          diff = substr(diff_raw, RSTART, RLENGTH) + 0
          if (diff < 0) diff = 0; if (diff > 5) diff = 5
        }
      }
      nrow++
      f_id[nrow]=id; f_file[nrow]=file; f_tier[nrow]=tier; f_rank[nrow]=rank
      f_parked[nrow]=parked; f_note[nrow]=note; f_deps[nrow]=deps
      f_prio[nrow]=prio; f_blast[nrow]=blast; f_diff[nrow]=diff
      f_archive[nrow]=is_archive; f_repo[nrow]=repo
    }
    END {
      for (i = 1; i <= nrow; i++) {
        if (f_archive[i]) continue
        d = f_deps[i]; if (d == "") continue
        nd = split(d, da, ",")
        for (di = 1; di <= nd; di++) {
          dd = da[di]; sub(/^[[:space:]]+/, "", dd); sub(/[[:space:]]+$/, "", dd)
          if (dd == "") continue
          dl = tolower(dd)
          if (dl in revdep) revdep[dl]++; else revdep[dl] = 1
        }
      }
      for (i = 1; i <= nrow; i++) {
        if (f_archive[i]) continue
        rd = (tolower(f_id[i]) in revdep) ? revdep[tolower(f_id[i])] : 0
        print f_id[i] FS_P f_tier[i] FS_P f_rank[i] FS_P f_parked[i] \
              FS_P f_note[i] FS_P f_deps[i] FS_P f_prio[i] FS_P f_blast[i] \
              FS_P f_diff[i] FS_P rd FS_P f_repo[i]
      }
    }
  ' > "$INDEX" 2>/dev/null || true
fi

# ── Sort: priority ASC, blocking DESC, blast DESC, difficulty DESC, id ASC ───
SORTED="$TMPDIR/sorted"
sort -t'|' -k7,7n -k10,10rn -k8,8rn -k9,9rn -k1,1 "$INDEX" 2>/dev/null > "$SORTED" || true

# ── State-set files (for exclusion lookups) ───────────────────────────────────
CLAIMED_SET="$TMPDIR/claimed"
SUBMITTED_SET="$TMPDIR/submitted"
DONE_SET="$TMPDIR/done"
LG_SET="$TMPDIR/lg"
build_set(){ local dst="$1" src_dir="$2"
  [ -d "$src_dir" ] || { : > "$dst"; return 0; }
  ls -1 "$src_dir" 2>/dev/null | tr 'A-Z' 'a-z' > "$dst" || true
}
build_set "$CLAIMED_SET"   "$STATE/claims"
build_set "$SUBMITTED_SET" "$STATE/submitted"
build_set "$DONE_SET"      "$STATE/done"
build_set "$LG_SET"        "$LG"

# ── Helpers ───────────────────────────────────────────────────────────────────
in_set(){ grep -qix -- "$1" "$2" 2>/dev/null; }

droid_alive(){ local dname="$1"
  ps -eo args= 2>/dev/null | grep -q "[f]leet-droid\.sh.*$dname" 2>/dev/null
}

deps_all_done_check(){ local raw="$1" d
  [ -n "$raw" ] || return 0
  for d in $(echo "$raw" | tr ',' ' '); do
    d="$(printf '%s' "$d" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$d" ] || continue
    in_set "$d" "$DONE_SET" || return 1
  done
  return 0
}

is_parked_check(){ local pv="$1" note="$2"
  case "$pv" in ""|false|no|0) ;; *) return 0;; esac
  case "$note" in *PARKED*) return 0;; esac
  return 1
}

# ── Board RED check ───────────────────────────────────────────────────────────
board_red=false
if ! bash "$FLEET/validate_board.sh" >/dev/null 2>&1; then
  board_red=true
fi

# ── Main surfacer ─────────────────────────────────────────────────────────────
count=0
if [ -s "$SORTED" ]; then
  while IFS='|' read -r id ttier trank parked note deps prio blast diff _ _repo; do
    [ "$count" -ge "$TOP_N" ] && break
    count=$((count+1))

    id_lo="$(printf '%s' "$id" | tr 'A-Z' 'a-z')"
    trank_i=$((trank))
    band="P:$prio"; [ "$prio" -eq 9999 ] && band="P:-"

    reason="CLAIMABLE"
    detail=""

    if [ "$board_red" = true ]; then
      reason="BOARD_RED"
      detail="validate_board.sh failing — ALL claims blocked"
    elif in_set "$id_lo" "$LG_SET"; then
      lg_file="$LG/$id"
      lg_age=""; lg_reason="unknown"
      if [ -f "$lg_file" ]; then
        lg_age="$(grep -o 'quarantined=[^[:space:]]*' "$lg_file" 2>/dev/null | head -1 | sed 's/quarantined=//' || echo "?")"
        lg_reason="$(grep -o 'reason=.*' "$lg_file" 2>/dev/null | head -1 | sed 's/reason=//' || echo "unknown")"
      fi
      reason="QUARANTINED"
      detail="since $lg_age — $lg_reason"
    elif in_set "$id_lo" "$DONE_SET"; then
      reason="DONE"
    elif in_set "$id_lo" "$SUBMITTED_SET"; then
      sub_ts="$(head -1 "$STATE/submitted/$id" 2>/dev/null || echo "-")"
      reason="SUBMITTED"
      detail="at $sub_ts"
      bfile="$BOARD/$id.md"
      if [ -f "$bfile" ] && command -v gh >/dev/null 2>&1; then
        branch="$(_vm_meta branch "$bfile" 2>/dev/null || echo "")"
        if [ -n "$branch" ] && [ "$branch" != "n/a" ]; then
          pr_state="$(gh pr view "$branch" --repo "$GH_SLUG" --json state -q '.state' 2>/dev/null || echo "")"
          case "$pr_state" in
            MERGED|CLOSED) detail="$detail — PR is $pr_state (STALE submitted marker)";;
          esac
        fi
      fi
    elif in_set "$id_lo" "$CLAIMED_SET"; then
      claim_file="$STATE/claims/$id"
      # BOTH claim shapes via the canonical reader (_lib.sh). The bare awk reported every
      # work-lease.sh lease as droid `ticket:` claimed since `<ID>`, which then failed the
      # droid_alive check below and mislabelled a LIVE holder as STALE.
      droid_name="$(claim_owner "$claim_file" 2>/dev/null || echo "UNREADABLE-CLAIM")"
      if claim_is_lease "$claim_file"; then
        claim_ts="$(claim_field claimed "$claim_file" 2>/dev/null || echo "?")"
      else
        claim_ts="$(awk 'NR==1{print $2}' "$claim_file" 2>/dev/null || echo "?")"
      fi
      reason="CLAIMED"
      detail="by $droid_name since $claim_ts"
      # Liveness through the ONE canonical notion (_lib.sh:claim_liveness) — PID-first with a
      # `heartbeat:` fallback for lease owners that carry no PID. droid_alive() alone matched a
      # `fleet-droid.sh` command line, so EVERY work-lease.sh lease (owner = a session name, not
      # a running droid tab) was mislabelled STALE. rc 2 = unreadable, which is a finding, not a
      # verdict — it must never read as either alive or dead.
      # `|| claim_live_rc=$?` (not a bare `; claim_live_rc=$?`) because this script runs under
      # `set -e`: a non-zero command substitution in an assignment aborts the whole script, and
      # claim_liveness returns non-zero for BOTH of its normal verdicts.
      claim_live_rc=0
      claim_live_reason="$(claim_liveness "$claim_file" 2>/dev/null)" || claim_live_rc=$?
      case "$claim_live_rc" in
        1) detail="$detail — STALE ($claim_live_reason)" ;;
        2) detail="$detail — !!!!!! UNREADABLE CLAIM ($claim_live_reason) — held, NOT released" ;;
        *) droid_alive "$droid_name" || detail="$detail — $claim_live_reason" ;;
      esac
    elif is_parked_check "$parked" "$note"; then
      reason="PARKED"
      detail="unclaimable"
    elif [ "$trank_i" -gt "$drank" ]; then
      reason="TIER"
      detail="ticket tier '$ttier' (rank $trank_i) > checker tier '$CHECK_TIER' (rank $drank)"
    elif ! deps_all_done_check "$deps"; then
      undone=""
      for d in $(echo "$deps" | tr ',' ' '); do
        d="$(printf '%s' "$d" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$d" ] || continue
        dl="$(printf '%s' "$d" | tr 'A-Z' 'a-z')"
        if in_set "$dl" "$DONE_SET"; then continue; fi
        if in_set "$dl" "$CLAIMED_SET"; then
          undone="$undone $d(claimed)"
        elif in_set "$dl" "$SUBMITTED_SET"; then
          undone="$undone $d(submitted)"
        elif [ -e "$STATE/done/$d" ]; then
          undone="$undone $d(mis-marked: done-marker-exists)"
        else
          undone="$undone $d"
        fi
      done
      reason="BLOCKED"
      detail="needs$(printf '%s' "$undone" | sed 's/^ //')"
    else
      # parallelizability-refused check: splittable (blast>1, diff>=3) +
      # no serial_justified + not decomposed
      if [ "${blast:-0}" -gt 1 ] && [ "${diff:-0}" -ge 3 ]; then
        bfile="$BOARD/$id.md"
        ser_just=""; children=0
        if [ -f "$bfile" ]; then
          ser_just="$(_vm_meta serial_justified "$bfile" 2>/dev/null || echo "")"
          children=$(for cf in "$BOARD"/*.md; do
            [ -f "$cf" ] || continue
            p="$(_vm_meta parent "$cf" 2>/dev/null || echo "")"
            [ "$(printf '%s' "$p" | tr 'A-Z' 'a-z')" = "$id_lo" ] && echo 1 || true
          done | wc -l || true)
        fi
        if [ -z "$ser_just" ] && [ "${children:-0}" -lt 2 ]; then
          reason="PARALLELIZABILITY-REFUSED"
          detail="splittable (blast=$blast, diff=$diff) — needs serial_justified or decompose"
        fi
      fi
    fi

    marker=""
    [ "$prio" -le 1 ] && [ "$reason" != "CLAIMABLE" ] && marker=" <<<<"
    printf '%-35s %-3s %-22s %s%s\n' "$id" "$band" "$reason" "$detail" "$marker"
  done < "$SORTED"
fi
[ "$count" -eq 0 ] && echo "(no tickets on board)"
exit 0
