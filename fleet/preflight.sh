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
VERIFY_MERGED_SH="$HERE/verify-merged.sh"
BOARD_RED_ID="board-validator-red"
# shared merge-verification helper (verify_merged) — the ONE source of truth for G2/G3a.
FLEET="$HERE"
# shellcheck source=/dev/null
source "$HERE/_lib.sh"
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

# --- executor_gate: MECHANIZES [route-work-to-charon-not-claude] for the FLEET WORK EXECUTOR.
# Runs checks/no-claude-executor.sh EVERY preflight (identical machinery to board_gate): FAIL LOUD if
# fleet-droid.sh (or any work executor) would run `claude -p/--bg` as the droid work agent (routes to
# Anthropic = burns Claude tokens) instead of running OFF Claude through the gateway ($CHARON_AGENT_CMD).
# On RED it AUTO-REOPENS the tracked red 'fleet-executor-hits-anthropic' BEFORE cmd_scan, so a
# reintroduced claude-executor BLOCKS preflight; the red self-closes when the check goes green again.
EXECUTOR_RED_ID="fleet-executor-hits-anthropic"
EXECUTOR_CHECK="$HERE/checks/no-claude-executor.sh"
_executor_red_status(){ awk -F"$TAB" -v id="$EXECUTOR_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_executor_red_ensure_open(){
  local st; st="$(_executor_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$EXECUTOR_RED_ID" P1 routing \
      "fleet work executor invokes 'claude -p/--bg' (routes to Anthropic, burns Claude tokens) instead of routing OFF Claude through the gateway" \
      "bash $EXECUTOR_CHECK" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$EXECUTOR_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
executor_gate(){
  [ -f "$EXECUTOR_CHECK" ] || { echo "executor_gate: no-claude-executor.sh not found at $EXECUTOR_CHECK"; return 0; }
  local out rc; out="$(bash "$EXECUTOR_CHECK" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "executor_gate: fleet work runs OFF Claude via the gateway client (no claude -p executor)"
    [ "$(_executor_red_status)" = open ] && \
      cmd_close "$EXECUTOR_RED_ID" --override "auto: no-claude-executor GREEN" >/dev/null 2>&1 || true
  else
    _executor_red_ensure_open
    echo "executor_gate: FLEET EXECUTOR LEAK — AUTO-REGISTERED tracked red '$EXECUTOR_RED_ID' (blocks preflight until the work executor routes off Claude via \$CHARON_AGENT_CMD)"
    printf '%s\n' "$out" | grep -i leak | head -4 | sed 's/^ *//; s/^/    /'
  fi
}

# --- handoff_gate: MECHANIZES [mechanized-handoff-gate] (MANAGER-OPERATING-RULES.md). The newest
# HANDOFF-*.md in fleet/ MUST pass `bash fleet/handoff-check.sh <file>`; a red handoff is a recurring
# failure mode (poor/inaccurate/incomplete handoffs stranded work for multiple sessions) so a bad
# handoff is wired as a BLOCKING P1 red 'handoff-fails-gate' that auto-closes the moment a passing
# handoff is on disk. This is the active detector — without it the rule was an unenforceable bullet
# in the operating doc; with it a missing/partial handoff BLOCKS preflight like a red board.
# Identical machinery to board_gate / executor_gate: registered BEFORE cmd_scan, so a red handoff
# makes preflight exit non-zero (it does not get dismissed as an advisory).
HANDOFF_RED_ID="handoff-fails-gate"
HANDOFF_CHECK="$HERE/handoff-check.sh"
_handoff_red_status(){ awk -F"$TAB" -v id="$HANDOFF_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_handoff_red_ensure_open(){
  local st desc; st="$(_handoff_red_status)"
  desc="newest fleet/HANDOFF-*.md fails handoff-check.sh (incomplete/inaccurate) — fix it (re-run handoff.sh + handoff-check.sh) or it blocks preflight"
  if [ -z "$st" ]; then
    cmd_add "$HANDOFF_RED_ID" P1 gate "$desc" \
      "bash '$HANDOFF_CHECK' \"\$(ls -1t $HERE/HANDOFF-*.md 2>/dev/null | grep -v 'SESSION-HANDOFF' | head -1)\" >/dev/null 2>&1" \
      >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$HANDOFF_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
_handoff_red_close_if_open(){
  [ "$(_handoff_red_status)" = open ] && \
    cmd_close "$HANDOFF_RED_ID" --override "auto: newest HANDOFF-*.md passes handoff-check.sh" >/dev/null 2>&1 || true
}
handoff_gate(){
  [ -f "$HANDOFF_CHECK" ] || { echo "handoff_gate: handoff-check.sh not found at $HANDOFF_CHECK"; return 0; }
  # Pick the newest HANDOFF-*.md (NOT SESSION-HANDOFF-*.md — those are per-session bootstrap
  # docs whose freshness is covered by the SESSION start hook). SESSION-HANDOFF files use
  # `## Bootstrap` patterns and would false-positive the bootstrap one-liner check.
  local latest
  latest="$(ls -1t "$HERE"/HANDOFF-*.md 2>/dev/null | grep -v 'SESSION-HANDOFF' | head -1)"
  if [ -z "$latest" ]; then
    echo "handoff_gate: no HANDOFF-*.md in $HERE (skipped — bootstrap with the first one after this session)"
    return 0
  fi
  local out rc
  out="$(bash "$HANDOFF_CHECK" "$latest" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "handoff_gate: $latest PASSES handoff-check.sh"
    _handoff_red_close_if_open
  else
    _handoff_red_ensure_open
    echo "handoff_gate: $latest FAILS handoff-check.sh — AUTO-REGISTERED tracked red '$HANDOFF_RED_ID' (blocks preflight until the handoff is repaired)"
    printf '%s\n' "$out" | grep -E '^  ✗|MISSING|PATH NOT FOUND|SHA NOT FOUND|STALE' | head -8 | sed 's/^/    /'
    [ "$(printf '%s\n' "$out" | grep -cE '^  ✗')" -gt 8 ] && echo "    +more — run: fleet/handoff-check.sh $latest"
  fi
}

# --- detect_needs_push: MECHANIZES [never-ignore-preexisting-issues] for STRANDED PUSHES (#3).
# submit.sh writes state/needs-push/<id> when a droid committed work but no PR opened, and a
# later re-claim's `git worktree remove --force` can DESTROY that committed work (CI-WORKFLOW-
# POLICY-GATE sat stranded since 2026-07-09). This AUTO-REGISTERS a tracked reds.tsv red per live
# marker (identical machinery to board_gate) so a stranded push BLOCKS preflight until landed —
# it can no longer be silently missed. The red self-closes when the marker goes away (landed).
# A marker whose ticket is already state/done (merged) is stale cruft -> cleaned + red closed.
NEEDS_PUSH_DIR="$HERE/state/needs-push"
DONE_DIR="$HERE/state/done"
_red_status(){ awk -F"$TAB" -v id="$1" '$1==id{print $7; exit}' "$TSV"; }
_np_red_id(){ printf 'needs-push-%s' "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\{1,\}/-/g; s/^-//; s/-$//')"; }
_np_red_ensure_open(){
  local rid="$1" id="$2" marker="$3" st; st="$(_red_status "$rid")"
  if [ -z "$st" ]; then
    cmd_add "$rid" P1 gate \
      "needs-push STRANDED: $id committed but unlanded — land it (fleet/land-needs-push.sh $id) or it blocks preflight" \
      "test ! -e '$marker'" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$rid" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
detect_needs_push(){
  [ -d "$NEEDS_PUSH_DIR" ] || { echo "clean: needs-push (no markers)"; return 0; }
  _vm_refresh   # M1: refresh the product ref once so a stale local ref cannot mis-decide the clear.
  # (1) auto-close any needs-push-* red whose marker is gone (the work landed).
  awk -F"$TAB" '$7=="open" && $1 ~ /^needs-push-/{print $1 "\t" $6}' "$TSV" | \
  while IFS="$TAB" read -r rid chk; do
    [ -n "$rid" ] || continue
    run_check "$chk" && cmd_close "$rid" --override "auto: needs-push landed" >/dev/null 2>&1 || true
  done
  # (2) per live marker: clear ONLY when the ticket is MERGE-VERIFIED (HIGH #1 fix); else keep the
  #     blocking red. A `done` marker is NOT proof-of-merge — a false/legacy done must NEVER again
  #     silently delete the guard protecting committed-but-unlanded work. `done` + `needs-push` +
  #     NOT-verified is the exact contradiction danger case: keep the guard, let a human resolve.
  local m id rid n=0
  for m in "$NEEDS_PUSH_DIR"/*; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"; rid="$(_np_red_id "$id")"
    if [ -e "$DONE_DIR/$id" ] && verify_merged "$id"; then
      rm -f "$m"
      [ "$(_red_status "$rid")" = open ] && cmd_close "$rid" --override "auto: merge-verified; stale needs-push cleared" >/dev/null 2>&1 || true
      echo "needs-push: $id merge-verified — stale marker cleared"
      continue
    fi
    [ -e "$DONE_DIR/$id" ] && \
      echo "needs-push: $id has BOTH done + needs-push but is NOT merge-verified — keeping guard (contradiction: verify the PR actually merged)"
    n=$((n+1))
    _np_red_ensure_open "$rid" "$id" "$m"
    echo "needs-push: $id STRANDED — AUTO-REGISTERED red '$rid' (blocks preflight until landed: fleet/land-needs-push.sh $id)"
  done
  [ "$n" -eq 0 ] && echo "clean: needs-push (no stranded markers)"
  return 0
}

# --- done_merge_gate: G2 BACKFILL detector — "a done marker can't lie" (DONE-AUDIT 2026-07-10).
# For EVERY state/done/<id> marker, re-run the merge-verification (verify_merged) rather than
# trusting the marker's mere existence. A marker that FAILS verification AUTO-REGISTERS a blocking
# P1 reds.tsv red 'done-unmerged-<id>' whose check_cmd re-runs verify-merged.sh, so it SELF-CLOSES
# the instant the ticket actually lands. Identical machinery to detect_needs_push/board_gate: it
# lands in reds.tsv BEFORE cmd_scan, so a lying done marker BLOCKS preflight exactly like a red
# board. Offline-tolerant (verify_merged prefers local git checks). Override markers are a RECORDED
# exception (not a lie) -> surfaced, never red. This closes the bypass that stranded
# CI-WORKFLOW-POLICY-GATE and fired 32x historically.
_dm_red_id(){ printf 'done-unmerged-%s' "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\{1,\}/-/g; s/^-//; s/-$//')"; }
_dm_red_ensure_open(){
  local rid="$1" id="$2" st; st="$(_red_status "$rid")"
  if [ -z "$st" ]; then
    cmd_add "$rid" P1 gate \
      "done marker for $id is NOT merge-verified — refuse to trust it; land/prove it (done.sh $id --merged-sha <sha>) or override, or it blocks preflight" \
      "bash '$VERIFY_MERGED_SH' '$id'" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$rid" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
done_merge_gate(){
  [ -d "$DONE_DIR" ] || { echo "clean: done-merge-gate (no done markers)"; return 0; }
  _vm_refresh   # M1: one best-effort fetch so a stale local ref cannot false-negative a fresh merge.
  local can_verify=1; _verification_available || can_verify=0
  # (1) auto-close any done-unmerged-* red whose ticket now verifies merged (POSITIVE proof only).
  awk -F"$TAB" '$7=="open" && $1 ~ /^done-unmerged-/{print $1 "\t" $6}' "$TSV" | \
  while IFS="$TAB" read -r rid chk; do
    [ -n "$rid" ] || continue
    run_check "$chk" && cmd_close "$rid" --override "auto: done marker now merge-verified" >/dev/null 2>&1 || true
  done
  # (2) per done marker: override -> surface; POSITIVELY verified -> ok; owns-content-present -> weak
  #     ADVISORY (informational, non-blocking — H1: owns-present is NOT proof, never blocks/closes on
  #     it); cannot verify (gh/network down) -> ONE 'verification-unavailable' advisory (M1/M2, not a
  #     per-marker blocking red); otherwise (no proof, no owns, verification available) -> blocking red.
  local m id rid unmerged=0 ov=0 adv=0 unavail=0
  for m in "$DONE_DIR"/*; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"; rid="$(_dm_red_id "$id")"
    if grep -q 'override:' "$m" 2>/dev/null; then
      ov=$((ov+1)); echo "done-merge-gate: $id closed by OPERATOR OVERRIDE —$(sed -n 's/.*override:/ /p' "$m" | head -1)"
      [ "$(_red_status "$rid")" = open ] && cmd_close "$rid" --override "auto: override recorded on marker" >/dev/null 2>&1 || true
      continue
    fi
    if verify_merged "$id"; then
      [ "$(_red_status "$rid")" = open ] && cmd_close "$rid" --override "auto: done marker merge-verified" >/dev/null 2>&1 || true
      continue
    fi
    if verify_merged_owns_advisory "$id"; then
      adv=$((adv+1))
      echo "done-merge-gate: $id — owns-content present in origin/master but THIS ticket's merge is NOT positively proven (ADVISORY, weak, NOT blocking). Prove it: done.sh $id --merged-sha <sha>."
      continue
    fi
    if [ "$can_verify" -eq 0 ]; then
      unavail=$((unavail+1)); continue
    fi
    unmerged=$((unmerged+1))
    _dm_red_ensure_open "$rid" "$id"
    echo "done-merge-gate: $id done but NOT merge-verified — AUTO-REGISTERED blocking red '$rid' (prove: done.sh $id --merged-sha <sha>, or override)"
  done
  [ "$unavail" -gt 0 ] && echo "done-merge-gate: verification-unavailable — gh/network absent; $unavail done marker(s) could not be positively checked (ADVISORY, NOT blocking; re-run when online)."
  [ "$unmerged" -eq 0 ] && echo "done-merge-gate: clean ($ov override(s), $adv owns-advisory, $unavail unverifiable; all other done markers merge-verified)"
  return 0
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

# Surface scheduled/done work so a session never re-specs or collides with prior
# work (the [project-start-audit-and-resequence] safeguard). Terse here; the full
# map + per-ticket collision check live in fleet/project-audit.sh.
detect_inflight_landscape(){
  local script="$HERE/project-audit.sh"
  [ -x "$script" ] || { echo "inflight-audit: project-audit.sh not found/executable"; return 0; }
  local tickets unmerged
  tickets=$(ls "$HERE/board" 2>/dev/null | grep '\.md$' | grep -vc '\.parked$')
  # count AHEAD *and* UNKNOWN-base branches — an unresolvable base must not read as 0-stranded
  unmerged=$(bash "$script" 2>/dev/null | grep -cE 'AHEAD \(unmerged!\)|UNKNOWN\(')
  echo "inflight-audit: ${tickets:-0} active board ticket(s), ${unmerged:-0} unmerged/unknown branch(es)"
  echo "    -> BEFORE authoring any brief / launching a build: fleet/project-audit.sh <TICKET>"
  echo "    -> full in-flight map: fleet/project-audit.sh"
}

# Wake-trigger for the DEFERRED gateway contract-injection (PROPOSAL step-3): if
# CG-attributed discipline failures cross the threshold, static-doc doctrine is
# not steering CG and the deferred fix is warranted. cg-drift.sh owns the tally.
detect_cg_drift(){
  local script="$HERE/cg-drift.sh"
  [ -x "$script" ] || { echo "cg-drift: cg-drift.sh not found/executable"; return 0; }
  bash "$script" check || true
}

# Stale-env warning: CHARON_GATEWAY_TOKEN (shell profile) can drift out of sync
# with the ACTUAL working gateway token in ~/.config/opencode/opencode.json
# (provider.charon.options.apiKey) — a session that trusts the stale env var
# gets "missing or invalid bearer token" even though opencode itself works fine.
# Nothing load-bearing in the product or fleet reads this env var on the
# opencode-client path (charon-run.sh execs `opencode run`, which resolves its
# own credentials from opencode.json) — so this is a non-fatal WARN, not a
# rewrite. opencode.json is always the authoritative source.
detect_gateway_token_drift(){
  local env_tok="${CHARON_GATEWAY_TOKEN:-}"
  [ -n "$env_tok" ] || { echo "clean: gateway-token-drift (CHARON_GATEWAY_TOKEN not set)"; return 0; }
  local cfg="$HOME/.config/opencode/opencode.json"
  [ -f "$cfg" ] || { echo "gateway-token-drift: CHARON_GATEWAY_TOKEN is set but $cfg not found — cannot compare"; return 0; }
  command -v python3 >/dev/null 2>&1 || { echo "gateway-token-drift: python3 not found — cannot compare"; return 0; }
  local cfg_tok
  cfg_tok="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("provider", {}).get("charon", {}).get("options", {}).get("apiKey", ""))
except Exception:
    print("")
' "$cfg" 2>/dev/null)"
  if [ -n "$cfg_tok" ] && [ "$env_tok" != "$cfg_tok" ]; then
    echo "WARN: gateway-token-drift — CHARON_GATEWAY_TOKEN (shell env) differs from"
    echo "    the token in $cfg (provider.charon.options.apiKey)."
    echo "    opencode.json is authoritative; a stale env var can surface as"
    echo "    'missing or invalid bearer token'. Non-fatal — update your shell"
    echo "    profile to match opencode.json, or unset CHARON_GATEWAY_TOKEN."
  else
    echo "clean: gateway-token-drift (env var matches opencode.json or opencode.json has no token)"
  fi
}

# --- detect_config_drift: MECHANIZES the operator's "config siloed + drifts INVISIBLY" fix.
# Provider/model config lives in multiple sources (LOCAL ~/.charon + the 4-LOM CG deploy) and a
# provider added to ONE (e.g. NVIDIA NIM) strands there unseen. config-drift.sh reconciles every
# source in state/CONFIG-SOURCES.tsv and flags every provider present-in-one/absent-in-another or
# base_url/key_env mismatch. ADVISORY at boot (--advisory forces exit 0): it PRINTS + COUNTs so the
# operator is no longer blind, without hard-blocking startup. The non-zero exit is reserved for
# explicit gate use (fleet/config-drift.sh with no flag). Read-only; compares key_env names only.
detect_config_drift(){
  local script="$HERE/config-drift.sh"
  [ -x "$script" ] || { echo "config-drift: detector not found/executable at $script"; return 0; }
  bash "$script" --advisory 2>&1 | grep -E '^(== |  WARN:|  [a-z0-9].*<< DRIFT|DRIFT:|UNREACHABLE:|  NOTE:|  only-in-)' || true
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
  detect_inflight_landscape
  detect_cg_drift
  detect_gateway_token_drift
  detect_config_drift
  echo "--- end detectors ---"
  bash "$HERE/access-check.sh" || true
  return 0
}

show_operator_actions(){
  echo "--- OPERATOR ACTIONS (things the manager needs YOU to do/decide) ---"
  bash "$HERE/pending.sh" list
  echo "--- end operator actions ---"
  return 0
}

# Dispatch ONLY when run directly. When SOURCED (fleet/tests/needs-push-gate.test.sh) the
# functions above are exposed with NO side effects.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
case "${1:-scan}" in
  scan|"") bash "$HERE/reconcile-merged.sh"; board_gate; executor_gate; handoff_gate; done_merge_gate; detect_needs_push; bash "$HERE/retire-done.sh"; cmd_scan; scan_rc=$?; cmd_detect; show_operator_actions; exit $scan_rc ;;
  add)     shift; cmd_add "$@" ;;
  close)   shift; cmd_close "$@" ;;
  list)    shift; cmd_list "$@" ;;
  detect)  shift; cmd_detect "$@" ;;
  *) echo "usage: $0 {scan|add <id> <sev> <area> \"<desc>\" \"<check>\"|close <id> [--override r|--evidence t]|list [open|closed|all]|detect [--full]}" >&2; exit 1 ;;
esac
fi
