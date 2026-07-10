#!/usr/bin/env bash
# preflight.sh — REDS REGISTRY driver (build-rig only).
# Mechanizes two chronic failures: (1) dismissing pre-existing red as "unrelated", and
# (2) ungrounded recommendations. Every known red lives in reds.tsv and is RE-VERIFIED
# deterministically here. THE KEY RULE: a red closes ONLY on a passing check_cmd or an
# explicit RECORDED override — never by assertion.
# Subcommands: scan(default) | add | close | list.  POSIX-ish bash, no deps.
set -uo pipefail   # deliberately NOT -e: a red check_cmd exits non-zero — that is signal, not error.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TSV="$HERE/reds.tsv"
VALIDATE_BOARD="$HERE/validate_board.sh"
BOARD_RED_ID="board-validator-red"
TODAY="$(date +%F)"
TAB=$'\t'

VALID_SEV="P0 P1 P2"
VALID_AREA="bridge board ci gate routing billing packaging other"

die(){ echo "error: $*" >&2; exit 1; }
in_set(){ local x="$1"; shift; for e in "$@"; do [ "$x" = "$e" ] && return 0; done; return 1; }

[ -f "$TSV" ] || die "registry not found: $TSV"

# run a check_cmd. returns 0=GREEN(gone) 1=RED(still) 2=MANUAL. captured output -> $CHECK_OUT.
CHECK_OUT=""
run_check(){
  local cmd="$1"
  case "$cmd" in manual:*) CHECK_OUT="${cmd#manual:}"; return 2;; esac
  CHECK_OUT="$(bash -c "$cmd" 2>&1)"
  return $?
}

cmd_scan(){
  local total=0 red=0 green=0 manual=0 rc state
  echo "REDS PREFLIGHT — re-verifying every open red ($TSV)"
  printf '%-28s · %-3s · %-8s · %-9s · %s\n' "id" "sev" "area" "state" "description"
  while IFS="$TAB" read -r id opened sev area desc check status closed_by; do
    case "$id" in \#*|"") continue;; esac
    [ "$status" = open ] || continue
    total=$((total+1))
    run_check "$check"; rc=$?
    if   [ $rc -eq 2 ]; then state="MANUAL";    manual=$((manual+1))
    elif [ $rc -eq 0 ]; then state="NOW-GREEN"; green=$((green+1))
    else                     state="STILL-RED"; red=$((red+1)); fi
    printf '%-28s · %-3s · %-8s · %-9s · %s\n' "$id" "$sev" "$area" "$state" "$desc"
    [ "$state" = NOW-GREEN ] && printf '    ready to close: preflight.sh close %s\n' "$id"
  done < "$TSV"
  printf -- '--- %d open: %d STILL-RED  %d NOW-GREEN  %d MANUAL ---\n' "$total" "$red" "$green" "$manual"
  if [ $red -gt 0 ]; then
    echo "Address or explicitly DEFER each STILL-RED before proceeding."
    return 1
  fi
  return 0
}

cmd_list(){
  local f="${1:-all}"
  case "$f" in open|closed|all) ;; *) die "list takes: open|closed|all";; esac
  awk -F"$TAB" -v f="$f" '
    /^#/||NF==0{next}
    f=="all"||$7==f {printf "%-28s %-3s %-8s %-6s %s\n",$1,$3,$4,$7,$5}
  ' "$TSV"
}

cmd_add(){
  [ $# -ge 5 ] || die "add needs: <id> <severity> <area> \"<description>\" \"<check_cmd>\""
  local id="$1" sev="$2" area="$3" desc="$4" check="$5"
  echo "$id" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' || die "id must be kebab-case (a-z0-9 with single dashes)"
  in_set "$sev"  $VALID_SEV  || die "severity must be one of: $VALID_SEV"
  in_set "$area" $VALID_AREA || die "area must be one of: $VALID_AREA"
  case "$desc"  in *"$TAB"*) die "description must not contain tabs";; esac
  case "$check" in *"$TAB"*) die "check_cmd must not contain tabs";; esac
  awk -F"$TAB" -v id="$id" '$1==id{f=1} END{exit f?1:0}' "$TSV" || die "id already exists: $id"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$TODAY" "$sev" "$area" "$desc" "$check" "open" "" >> "$TSV"
  echo "added open red: $id ($sev/$area)"
}

cmd_close(){
  local id="" override="" evidence=""
  [ $# -ge 1 ] || die "close needs: <id> [--override \"reason\"] [--evidence \"text\"]"
  id="$1"; shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --override) [ $# -ge 2 ] || die "--override needs a reason"; override="$2"; shift 2;;
      --evidence) [ $# -ge 2 ] || die "--evidence needs text";    evidence="$2"; shift 2;;
      *) die "unknown arg: $1";;
    esac
  done
  local line; line="$(awk -F"$TAB" -v id="$id" '$1==id{print; exit}' "$TSV")"
  [ -n "$line" ] || die "no such id: $id"
  local status check
  status="$(printf '%s' "$line" | cut -f7)"
  check="$(printf '%s' "$line" | cut -f6)"
  [ "$status" = open ] || die "$id is already $status"

  local closure=""
  case "$check" in
    manual:*)
      [ -n "$evidence" ] || die "$id is a manual: red — closing requires --evidence \"<text>\" ($check)"
      closure="$TODAY:manual:$evidence"
      ;;
    *)
      if [ -n "$override" ]; then
        closure="$TODAY:override:$override"
      elif run_check "$check"; then
        closure="$TODAY:auto-verified"
      else
        echo "REFUSED: $id check still FAILS — still red. NOT closing." >&2
        echo "--- check_cmd ---" >&2; echo "$check" >&2
        echo "--- output ---"    >&2; echo "$CHECK_OUT" >&2
        echo "To close anyway (records the reason): preflight.sh close $id --override \"<reason>\"" >&2
        exit 1
      fi
      ;;
  esac

  local tmp; tmp="$(mktemp)"
  awk -F"$TAB" -v OFS="$TAB" -v id="$id" -v cl="$closure" '
    /^#/{print;next}
    $1==id{$7="closed";$8=cl}
    {print}
  ' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  echo "closed: $id -> $closure"
}

# --- detect: ACTIVE detectors for drift/risk NOT yet in reds.tsv. Prints hits,
# never mutates reds.tsv (that stays a human/DTC decision via `add`). ---
CHARON_REPO="/home/stack/code/charon"

# print a DETECTED line + up to 5 examples + "+N more".
report_hits(){
  local class="$1" count="$2" shown_list="$3"
  [ "$count" -gt 0 ] || return 0
  echo "DETECTED (unregistered): $class — $count hit(s)"
  local n=0 line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    [ $n -ge 5 ] && break
    echo "    $line"
    n=$((n+1))
  done <<< "$shown_list"
  [ "$count" -gt "$n" ] && echo "    +$((count-n)) more"
}

detect_untracked_drift(){
  local list count
  list="$(git -C "$HERE" ls-files --others --exclude-standard -- board/ '*.md' 2>/dev/null)"
  count=0
  [ -n "$list" ] && count="$(printf '%s\n' "$list" | grep -c .)"
  report_hits "untracked-drift" "$count" "$list"
}

# allowlist: substrings that suppress known documentation false-positives.
secret_allowlisted(){
  printf '%s' "$1" | grep -qF -e 'password = Phase 2' -e 'scrypt hash' -e '<your-' -e 'example'
}

detect_secret_scan(){
  local pattern='sk-[a-zA-Z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|(api[_-]?key|apikey|password)[[:space:]]*[:=][[:space:]]*.{20,}'
  local files f hits=0 shown=""
  files="$( { git -C "$HERE" ls-files; git -C "$HERE" ls-files --others --exclude-standard; } | sort -u )"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$HERE/$f" ] || continue
    grep -IqE "$pattern" "$HERE/$f" 2>/dev/null || continue
    local hit
    while IFS= read -r hit; do
      [ -n "$hit" ] || continue
      secret_allowlisted "$hit" && continue
      hits=$((hits+1))
      shown="$shown
$f:$hit"
    done < <(grep -InE "$pattern" "$HERE/$f" 2>/dev/null)
  done <<< "$files"
  if [ $hits -gt 0 ]; then
    report_hits "secret-scan" "$hits" "$(printf '%s\n' "$shown" | grep -v '^$')"
  else
    echo "clean: secret-scan (0 unallowlisted matches)"
  fi
}

# unpushed commits + dirty tracked files for one repo (path, label).
detect_repo_drift_one(){
  local path="$1" label="$2" unpushed=0 dirty=0 dirty_list=""
  [ -d "$path/.git" ] || { git -C "$path" rev-parse --git-dir >/dev/null 2>&1; } || {
    echo "repo-drift: $label — no git repo at $path"; return 0; }
  local ahead
  ahead="$(git -C "$path" log '@{u}..HEAD' --oneline 2>/dev/null)"
  unpushed=0; [ -n "$ahead" ] && unpushed="$(printf '%s\n' "$ahead" | grep -c .)"
  dirty_list="$(git -C "$path" status --porcelain -- . 2>/dev/null | grep -v '^??')"
  dirty=0; [ -n "$dirty_list" ] && dirty="$(printf '%s\n' "$dirty_list" | grep -c .)"
  echo "repo-drift: $label — $unpushed unpushed commit(s), $dirty dirty tracked file(s)"
  if [ "$dirty" -gt 0 ]; then
    report_hits "repo-drift:$label:dirty-tracked" "$dirty" "$dirty_list"
  fi
}

detect_repo_drift(){
  detect_repo_drift_one "$HERE" "fleet"
  detect_repo_drift_one "$CHARON_REPO" "charon"
}

# claim-loop signature: the fleet-droid loop-guard writes a durable state/loop-guard/<id>
# marker when the SAME id was claimed+released with ZERO commits >= N times (the
# claim -> no-op -> release -> re-claim spin that starved the board on 2026-07-09). Any such
# marker is an active, unregistered risk: a ticket a droid could not make progress on.
detect_claim_loop(){
  local lg="$HERE/state/loop-guard" list count
  [ -d "$lg" ] || { echo "clean: claim-loop (no loop-guard quarantines)"; return 0; }
  list=""
  for f in "$lg"/*; do
    [ -f "$f" ] || continue   # skips runs/ dir + per-run counters
    list="$list
$(basename "$f"): $(head -1 "$f" 2>/dev/null)"
  done
  list="$(printf '%s\n' "$list" | grep -v '^$')"
  count=0; [ -n "$list" ] && count="$(printf '%s\n' "$list" | grep -c .)"
  if [ "$count" -gt 0 ]; then
    report_hits "claim-loop (droid re-claimed+released same id with 0 commits — quarantined)" "$count" "$list"
    echo "    -> manager: fix the block (park the ticket / correct its deps or prompt), then 'fleet/loop-guard.sh clear <id>'"
  else
    echo "clean: claim-loop (no loop-guard quarantines)"
  fi
}

# --- board_gate: MECHANIZES [never-ignore-preexisting-issues] for the board class.
# Runs validate_board.sh EVERY preflight (not just --full) and AUTO-REGISTERS a tracked
# red into reds.tsv when it is red — so board hygiene issues can never again hide in the
# advisory "DETECTED" section and get dismissed as "not the tracked reds". The umbrella red
# self-closes when validate_board goes green (machine-owned, so machine-closed). Because it
# lands in reds.tsv BEFORE cmd_scan, a red board makes preflight exit non-zero — it blocks
# the session the same way a failing test does, rather than relying on the manager to recall.
_board_red_status(){ awk -F"$TAB" -v id="$BOARD_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_board_red_ensure_open(){
  local st; st="$(_board_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$BOARD_RED_ID" P2 board \
      "validate_board.sh RED — fix or explicitly DEFER each board issue before proceeding" \
      "bash $VALIDATE_BOARD >/dev/null 2>&1" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$BOARD_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
_board_red_close_if_open(){
  [ "$(_board_red_status)" = open ] && \
    cmd_close "$BOARD_RED_ID" --override "auto: validate_board.sh GREEN" >/dev/null 2>&1 || true
}
board_gate(){
  [ -f "$VALIDATE_BOARD" ] || { echo "board_gate: validate_board.sh not found at $VALIDATE_BOARD"; return 0; }
  local out rc; out="$(bash "$VALIDATE_BOARD" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "board_gate: validate_board.sh GREEN"; _board_red_close_if_open
  else
    local n; n="$(printf '%s\n' "$out" | grep -cE '^[[:space:]]*RED')"
    _board_red_ensure_open
    echo "board_gate: validate_board.sh RED ($n issue(s)) — AUTO-REGISTERED as tracked red '$BOARD_RED_ID' (blocks preflight until fixed or DEFERRED)"
    printf '%s\n' "$out" | grep -E '^[[:space:]]*RED' | head -6 | sed 's/^ *//; s/^/    /'
    [ "$n" -gt 6 ] && echo "    +$((n-6)) more — run: fleet/validate_board.sh"
  fi
}

# WCI high-contention-file advisory: a file owned by >= N tickets is a DECOMPOSE
# CANDIDATE (collision metric -> refactor trigger). Informational; never fails preflight.
# Delegates to wci-contention.sh (fleet/WCI-METHOD.md). Top line surfaced here; run the
# script directly for the full owner lists.
detect_wci_contention(){
  local script="$HERE/wci-contention.sh"
  [ -x "$script" ] || { echo "wci-contention: detector not found/executable at $script"; return 0; }
  local out top
  out="$(bash "$script" 2>/dev/null)"
  if printf '%s\n' "$out" | grep -q 'DECOMPOSE CANDIDATE'; then
    local n
    n="$(printf '%s\n' "$out" | grep -c 'DECOMPOSE CANDIDATE')"
    echo "DETECTED (unregistered): wci-contention — $n DECOMPOSE CANDIDATE file(s) (owned by >= 4 tickets)"
    printf '%s\n' "$out" | grep 'DECOMPOSE CANDIDATE:' | head -5 | sed 's/^ */    /'
    [ "$n" -gt 5 ] && echo "    +$((n-5)) more — run: fleet/wci-contention.sh"
    echo "    -> run the WCI pass BEFORE opening tabs on a backlog (fleet/WCI-METHOD.md)"
  else
    echo "clean: wci-contention (no file owned by >= 4 tickets)"
  fi
}

cmd_detect(){
  local full=0
  case "${1:-}" in --full) full=1;; esac
  echo "--- ACTIVE DETECTORS (unregistered risk not yet in reds.tsv) ---"
  detect_untracked_drift
  detect_secret_scan
  detect_repo_drift
  detect_claim_loop
  detect_wci_contention
  echo "--- end detectors ---"
  return 0
}

case "${1:-scan}" in
  scan|"") board_gate; cmd_scan; scan_rc=$?; cmd_detect; exit $scan_rc ;;
  add)     shift; cmd_add "$@" ;;
  close)   shift; cmd_close "$@" ;;
  list)    shift; cmd_list "$@" ;;
  detect)  shift; cmd_detect "$@" ;;
  *) echo "usage: $0 {scan|add <id> <sev> <area> \"<desc>\" \"<check>\"|close <id> [--override r|--evidence t]|list [open|closed|all]|detect [--full]}" >&2; exit 1 ;;
esac
