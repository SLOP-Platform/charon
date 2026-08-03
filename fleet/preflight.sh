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
FOREMAN_VERDICT_LINES=""

VALID_SEV="P0 P1 P2"
VALID_AREA="bridge board ci gate routing billing packaging other rig-meta"

die(){ echo "error: $*" >&2; exit 1; }
in_set(){ local x="$1"; shift; for e in "$@"; do [ "$x" = "$e" ] && return 0; done; return 1; }

# run_sync_checkouts — first command of the `scan` dispatch: refresh the LOCAL main checkouts'
# master so every downstream gate evaluates against a current tree. Guarded like
# fleet/hooks/session-start.sh does: a MISSING script gets a clear warning, not a bare
# `bash: ...: No such file` + rc 127 at the top of every scan. Always returns 0 — `scan` is a
# `;` chain and this must never abort it. Covered by fleet/tests/sync-checkouts.test.sh (D).
run_sync_checkouts(){
  local s="$HERE/sync-checkouts.sh"
  if [ -f "$s" ]; then bash "$s"
  else echo "preflight: WARN — sync script not found ($s), skipping checkout sync"; fi
  return 0
}

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

# --- coverage_gate: MECHANIZES §11 (MANAGER-OPERATING-RULES.md) "every rule that CAN be a gate
# MUST be a gate." Runs checks/rule-coverage.sh EVERY preflight (identical machinery to
# board_gate / executor_gate): it re-derives the coverage matrix from RULE-REGISTRY.tsv and the
# live rules doc and FAILS on any un-exempted mechanizable GAP, a fake-green mechanized row
# (artifact missing / not wired), a phantom doc_anchor, or an unclassified rule (completeness
# floor). On RED it AUTO-REGISTERS the tracked red 'rule-coverage-gap' BEFORE cmd_scan, so a
# reintroduced advisory-by-neglect rule BLOCKS preflight; the red self-closes when GREEN again.
COVERAGE_RED_ID="rule-coverage-gap"
COVERAGE_CHECK="$HERE/checks/rule-coverage.sh"
_coverage_red_status(){ awk -F"$TAB" -v id="$COVERAGE_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_coverage_red_ensure_open(){
  local st; st="$(_coverage_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$COVERAGE_RED_ID" P1 rig-meta \
      "coverage meta-gate RED: a mechanizable rule is left advisory/GAP, a mechanized row points at a missing/unwired artifact, or the registry no longer maps 1:1 to MANAGER-OPERATING-RULES.md" \
      "bash $COVERAGE_CHECK" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$COVERAGE_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
coverage_gate(){
  [ -f "$COVERAGE_CHECK" ] || { echo "coverage_gate: rule-coverage.sh not found at $COVERAGE_CHECK"; return 0; }
  local out rc; out="$(bash "$COVERAGE_CHECK" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "coverage_gate: $(printf '%s\n' "$out" | grep -m1 -E 'coverage +:' | sed 's/^ *//')"
    [ "$(_coverage_red_status)" = open ] && \
      cmd_close "$COVERAGE_RED_ID" --override "auto: rule-coverage GREEN" >/dev/null 2>&1 || true
  else
    _coverage_red_ensure_open
    echo "coverage_gate: COVERAGE META-GATE RED — AUTO-REGISTERED tracked red '$COVERAGE_RED_ID' (blocks preflight until every mechanizable rule is a gate or a time-boxed exempt-until)"
    printf '%s\n' "$out" | grep 'RED:' | head -6 | sed 's/^ *//; s/^/    /'
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
    _vm_refresh "$id"
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
    _vm_refresh "$id"
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

# --- hold_reason_gate: MECHANIZES the DRAFT CONVENTION (2026-07-18).
# ROOT CAUSE it fixes: draft state was being read as a hold signal, but draft is the LAUNCHER'S
# UNCONDITIONAL DEFAULT (fleet-droid.sh `gh pr create --draft`, land-needs-push.sh, product
# src/charon/land.py) — every PR opens draft, zero `convert_to_draft` events exist, so draft carries
# NO information. Reading it as a hold would block EVERY PR. The real failure was a hold whose
# REASON was lost between sessions.
# THE CONVENTION: draft = "not yet human-reviewed" (manager clears it with `gh pr ready <n>` at
# merge-gate time). A REAL hold = the `hold` LABEL + a `HOLD: <reason>` comment — a label survives
# sessions and is queryable. THIS GATE: a `hold`-labelled PR with NO `HOLD:` comment is a FAILURE
# (a hold with no recorded reason is exactly the lost-reason bug), auto-registered as a blocking red
# that SELF-CLOSES once the comment exists. Draft PRs are never selected (the query keys on the
# LABEL only), so the anti-regression holds: a normal draft PR is untouched.
# Offline-tolerant: hold_prs_tsv returns non-zero when gh is absent/rate-limited and no cache
# exists -> ONE advisory line, NOT blocking (identical degrade to done_merge_gate's `can_verify`).
_hold_red_id(){ printf 'hold-no-reason-%s-%s' "$(printf '%s' "$1" | tr -c 'a-zA-Z0-9' '-' | tr '[:upper:]' '[:lower:]' | sed 's/-\{1,\}/-/g; s/^-//; s/-$//')" "$2"; }
hold_reason_gate(){
  # shellcheck source=/dev/null
  [ -f "$HERE/gh-cache.sh" ] || { echo "hold_reason_gate: gh-cache.sh not found at $HERE/gh-cache.sh"; return 0; }
  source "$HERE/gh-cache.sh"
  local slugs="" key slug tsv pr flag rid bad=0 okc=0 unavail=0
  if [ -n "${GH_HOLD_FIXTURE:-}" ]; then
    # fixture mode: one synthetic repo, gh never touched (and no slug resolution, which itself
    # shells out to gh) — keeps the test fully offline.
    slugs=" ${HOLD_GATE_SLUG:-fixture/repo}"
  else
    for key in charon charon-private; do
      repo_resolve "$key" >/dev/null 2>&1 || continue
      slug="$(repo_owner_repo "$RR_PATH" 2>/dev/null)"
      [ -n "$slug" ] || continue
      case " $slugs " in *" $slug "*) continue ;; esac
      slugs="$slugs $slug"
    done
  fi
  [ -n "$slugs" ] || { echo "clean: hold-reason-gate (no resolvable repo slug)"; return 0; }
  for slug in $slugs; do
    if ! tsv="$(hold_prs_tsv "$slug")"; then unavail=$((unavail+1)); continue; fi
    while IFS="$TAB" read -r pr flag; do
      [ -n "$pr" ] || continue
      rid="$(_hold_red_id "$slug" "$pr")"
      if [ "$flag" = 1 ]; then
        okc=$((okc+1))
        [ "$(_red_status "$rid")" = open ] && cmd_close "$rid" --override "auto: HOLD: reason comment now present on $slug#$pr" >/dev/null 2>&1 || true
        continue
      fi
      bad=$((bad+1))
      if [ -z "$(_red_status "$rid")" ]; then
        cmd_add "$rid" P1 gate \
          "$slug#$pr carries the 'hold' label with NO 'HOLD: <reason>' comment — a hold with no recorded reason is lost the moment the session ends; comment 'HOLD: <reason>' or drop the label" \
          "bash '$HERE/preflight.sh' hold-check '$slug' '$pr'" >/dev/null 2>&1 || true
      fi
      echo "hold-reason-gate: $slug#$pr is 'hold'-labelled with NO 'HOLD:' comment — AUTO-REGISTERED blocking red '$rid' (record the reason, or remove the label)"
    done <<< "$tsv"
  done
  [ "$unavail" -gt 0 ] && echo "hold-reason-gate: verification-unavailable — gh absent/rate-limited for $unavail repo(s), no cache (ADVISORY, NOT blocking; re-run when online)."
  [ "$bad" -eq 0 ] && echo "hold-reason-gate: clean ($okc hold(s) with a recorded reason, $unavail unverifiable; draft state is NOT read as a hold)"
  return 0
}
# hold_check <slug> <pr> -> 0 when the hold now has a HOLD: reason (or the label is gone). The
# registered red's check_cmd: it SELF-CLOSES the red without any manual assertion.
hold_check(){
  # shellcheck source=/dev/null
  source "$HERE/gh-cache.sh"
  local slug="$1" pr="$2" tsv flag
  tsv="$(hold_prs_tsv "$slug")" || { echo "hold-check: cannot verify $slug#$pr (gh unavailable)"; return 1; }
  flag="$(printf '%s\n' "$tsv" | awk -F"$TAB" -v p="$pr" '$1==p{print $2; exit}')"
  [ -n "$flag" ] || { echo "hold-check: $slug#$pr no longer carries the 'hold' label — resolved"; return 0; }
  [ "$flag" = 1 ] && { echo "hold-check: $slug#$pr has a 'HOLD:' reason comment — resolved"; return 0; }
  echo "hold-check: $slug#$pr still 'hold'-labelled with NO 'HOLD:' comment"; return 1
}

# WCI high-contention-file leg: a file owned by >= N tickets is a DECOMPOSE CANDIDATE
# (collision metric -> refactor trigger). This leg used to PRINT that fact and nothing else;
# it printed it every session for weeks and nobody ever acted on it, which is what an
# advisory that mutates nothing and always returns 0 is worth. It now ACTS:
#   * AUTO-TICKETS each candidate (wci-contention.sh --generate): one board ticket per
#     contended PATH, priority 1, idempotent, board-valid, self-parking when the contention
#     goes away. The recommendation becomes tracked work instead of a wall of text.
#   * FAILS CLOSED: a missing/unrunnable detector, or a detector that REFUSES (rc 2 — bad
#     input, missing board, zero tickets scanned), AUTO-REGISTERS a blocking tracked red
#     instead of returning 0. A blind gate must never read as a clean one.
#
# WCI_AUTOTICKET   1 = generate (default). Set 0 to SUPPRESS ticket writes for a session
#                  (e.g. while another session is reorganising the board).
# WCI_RATCHET_DAYS THE RATCHET SWITCH — 0 = OFF (default). An auto-ticket left open and
#                  unclaimed beyond this many days escalates to a REAL blocking red.
#                  ARM IT BY CHANGING THIS ONE DEFAULT (0 -> 7). It ships OFF on purpose:
#                  fleet/preflight.sh is itself owned by 7 tickets today, so arming it now
#                  would red preflight for the whole fleet before the first auto-ticket
#                  could possibly be actioned.
WCI_AUTOTICKET="${WCI_AUTOTICKET:-1}"
WCI_RATCHET_DAYS="${WCI_RATCHET_DAYS:-0}"
WCI_RED_ID="wci-contention-detector-broken"
WCI_RATCHET_RED_ID="wci-decompose-ticket-ignored"
_wci_red_open(){   # _wci_red_open <id> <desc> <check_cmd>
  local st; st="$(_red_status "$1")"
  if [ -z "$st" ]; then
    cmd_add "$1" P1 board "$2" "$3" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$1" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
_wci_red_close(){ [ "$(_red_status "$1")" = open ] && cmd_close "$1" --override "auto: $2" >/dev/null 2>&1 || true; }
detect_wci_contention(){
  local script="$HERE/wci-contention.sh"
  if [ ! -f "$script" ]; then
    # FAIL-CLOSED (was: `return 0`). A detector that is not there detects nothing; that is
    # the loudest possible finding, not a pass.
    _wci_red_open "$WCI_RED_ID" \
      "wci-contention detector MISSING at $script — the god-file/decompose detector cannot run, so preflight is blind to board contention" \
      "test -f '$script' && bash '$script' >/dev/null 2>&1"
    echo "wci-contention: DETECTOR MISSING at $script — AUTO-REGISTERED tracked red '$WCI_RED_ID' (a blind detector is not a clean one)"
    return 0
  fi
  local args=() out rc n
  [ "$WCI_AUTOTICKET" = 1 ] && args+=(--generate)
  [ "$WCI_RATCHET_DAYS" -gt 0 ] && args+=(--ratchet "$WCI_RATCHET_DAYS")
  out="$(bash "$script" ${args[@]+"${args[@]}"} 2>&1)"; rc=$?
  if [ "$rc" -eq 2 ]; then
    _wci_red_open "$WCI_RED_ID" \
      "wci-contention detector REFUSED (rc 2: bad input / missing board / zero tickets scanned) — the contention metric is undefined, not zero" \
      "bash '$script' >/dev/null 2>&1"
    echo "wci-contention: DETECTOR REFUSED (rc 2) — AUTO-REGISTERED tracked red '$WCI_RED_ID'"
    printf '%s\n' "$out" | grep -m3 'RED' | sed 's/^ */    /'
    return 0
  fi
  _wci_red_close "$WCI_RED_ID" "wci-contention detector runs clean"
  # the teeth: what the detector DID this run (created / already tracked / parked stale).
  printf '%s\n' "$out" | grep -E 'wci-autoticket: (CREATE|STALE|BLOCKED-STALE|COVERED|RED)' | sed 's/^/    /'
  if printf '%s\n' "$out" | grep -q 'DECOMPOSE CANDIDATE'; then
    n="$(printf '%s\n' "$out" | grep -c 'DECOMPOSE CANDIDATE:')"
    if [ "$WCI_AUTOTICKET" = 1 ]; then
      echo "wci-contention: $n DECOMPOSE CANDIDATE file(s) (owned by >= 4 tickets) — AUTO-TICKETED at priority 1 (WCI-DEC-*)"
    else
      echo "DETECTED (unregistered): wci-contention — $n DECOMPOSE CANDIDATE file(s) (owned by >= 4 tickets); auto-ticketing SUPPRESSED (WCI_AUTOTICKET=0)"
    fi
    printf '%s\n' "$out" | grep 'DECOMPOSE CANDIDATE:' | head -5 | sed 's/^ */    /'
    [ "$n" -gt 5 ] && echo "    +$((n-5)) more — run: fleet/wci-contention.sh"
  else
    echo "clean: wci-contention (no file owned by >= 4 tickets)"
  fi
  if [ "$rc" -eq 1 ] && [ "$WCI_RATCHET_DAYS" -gt 0 ]; then
    _wci_red_open "$WCI_RATCHET_RED_ID" \
      "an auto-generated WCI decompose ticket has sat open and unclaimed beyond $WCI_RATCHET_DAYS days — the recommendation is being ignored again" \
      "bash '$script' --ratchet $WCI_RATCHET_DAYS >/dev/null 2>&1"
    echo "wci-contention: RATCHET FIRED — AUTO-REGISTERED tracked red '$WCI_RATCHET_RED_ID' (claim or park the WCI-DEC-* ticket)"
    printf '%s\n' "$out" | grep 'RATCHET ESCALATION' | head -4 | sed 's/^ */    /'
  elif [ "$WCI_RATCHET_DAYS" -gt 0 ]; then
    _wci_red_close "$WCI_RATCHET_RED_ID" "no WCI decompose ticket ignored beyond $WCI_RATCHET_DAYS days"
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
# Stranded-work detector (STRANDED-WORK-AUDIT). The one-shot hand audit ran 2026-07-14; this is
# the RECURRING half the standing [[dynamic-tools-never-on-demand]] directive requires — a tool
# that only runs when a human types its name is not a control. It rides the EXISTING detector
# dispatch (same shape as detect_cg_drift) rather than inventing a scheduler, so it fires on every
# preflight: session start, and every gate/land cycle that preflights.
# ADVISORY (`|| true`): it is REPORT-ONLY and must never block a session on pre-existing backlog.
# The findings surface in the detector block; recovery stays a human/land.sh decision.
#
# ANTI-SILENCE LEG (the reason this function has a second half at all):
#   Running the detector at preflight makes it fire when a SESSION happens. The 96-commit backlog
#   proves that is not enough — no session for two days meant no scan for two days. The cadence
#   therefore lives in cron (fleet/checks/stranded-work-cron.sh), OUTSIDE any session.
#   But a cadence you cannot observe is worse than none: if the crontab entry is deleted, renamed,
#   or points at a path a fresh checkout lacks, the observable is SILENCE — which is
#   indistinguishable from "nothing is stranded". That is §J (a gate marked done that quietly
#   stopped firing) repeating one level up, and it is exactly how this class recurs.
#   So preflight checks the cron leg's HEARTBEAT, not its findings. Stale/missing heartbeat is
#   reported LOUDLY and is never silently green — the wrapper writes that file on EVERY run
#   including its own failures, so a fresh heartbeat means "the cadence fired", never "it was ok".
# Freshness via the watchdog SSOT grammar when it is present (wd_probe_fresh is the rig's ONE
# definition of "file mtime within ttl" — three other consumers already share it, and a second
# private copy of that predicate is the drift class watchdog-lib.sh exists to kill). Inline
# fallback for checkouts that predate the lib, so this leg can never be skipped for lack of it.
_stranded_hb_fresh(){ # 0 fresh | 1 stale | 2 missing
  local hb="$1" ttl="$2" lib="$HERE/watchdog/watchdog-lib.sh"
  if [ -f "$lib" ]; then
    ( # shellcheck source=/dev/null
      . "$lib" >/dev/null 2>&1 && wd_probe_fresh "file:$hb" "$ttl" )
    return $?
  fi
  [ -e "$hb" ] || return 2
  local mt now; mt="$(stat -c %Y "$hb" 2>/dev/null || date -r "$hb" +%s 2>/dev/null)"
  [ -n "$mt" ] || return 2
  now="$(date +%s)"
  [ $(( now - mt )) -le "$ttl" ] && return 0 || return 1
}

detect_stranded_work(){
  local script="$HERE/checks/stranded-work.sh"
  [ -f "$script" ] || { echo "stranded-work: checks/stranded-work.sh not found"; return 0; }
  bash "$script" --quiet || true

  # --- CADENCE LIVENESS, TWO LEGS, BOTH REQUIRED.
  # Leg A alone is THE TRAP: a crontab line whose command does not exist registers perfectly,
  # `crontab -l` shows it, and it has never once executed (cron logs 127 to mail nobody reads).
  # Leg B alone cannot tell "the entry was deleted five minutes ago" from "it is about to run".
  # Only REGISTERED **and** FRESH earns a clean line.
  # TTL resolved HERE, not at file scope: a default that lives outside the function can be lost by
  # any caller that reaches the function another way, and an empty TTL silently reads as "stale".
  local hb="$HERE/state/.stranded-work.heartbeat" rc reg=1 cron_out
  local ttl="${STRANDED_HB_TTL:-5400}"   # 90m: comfortably > the 20m cadence, well under a day
  cron_out="$(${STRANDED_CRONTAB_CMD:-crontab -l} 2>/dev/null || true)"
  printf '%s\n' "$cron_out" | grep -qF 'stranded-work-cron.sh' && reg=0
  _stranded_hb_fresh "$hb" "$ttl"; rc=$?

  if [ "$reg" -eq 0 ] && [ "$rc" -eq 0 ]; then
    echo "clean: stranded-work-cadence (crontab REGISTERED and heartbeat FRESH: $(head -1 "$hb" 2>/dev/null))"
  else
    echo "WARN: stranded-work-cadence NOT PROVEN — the scan only fires when a SESSION starts;"
    echo "    between sessions nothing scans, which is how the 96-commit backlog accumulated."
    [ "$reg" -eq 0 ] && echo "    leg A registered: YES" || echo "    leg A registered: NO  (no crontab entry mentions stranded-work-cron.sh)"
    case "$rc" in
      0) echo "    leg B heartbeat:   FRESH ($(head -1 "$hb" 2>/dev/null))" ;;
      1) if [ "$reg" -eq 0 ]; then
           echo "    leg B heartbeat:   STALE — older than ${ttl}s ($(head -1 "$hb" 2>/dev/null)). REGISTERED BUT NOT EXECUTING."
         else
           echo "    leg B heartbeat:   STALE — older than ${ttl}s ($(head -1 "$hb" 2>/dev/null)); consistent with the entry having been removed."
         fi ;;
      *) echo "    leg B heartbeat:   MISSING — no file at $hb" ;;
    esac
    echo "    Register the cadence (once, as this user, on the box that holds the checkouts):"
    echo "      ( crontab -l 2>/dev/null; echo '*/20 * * * * $HERE/checks/stranded-work-cron.sh >/dev/null 2>&1' ) | crontab -"
  fi
}

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

# --- detect_service_watchdog: SERVICE-LIVENESS-WATCHDOG detection leg on every preflight. Runs the
# monit-independent registry evaluator (alive + freshness) + the unregistered-service discovery leg,
# so a DEAD or HUNG money-path service (the 9-day-stale-grader incident) surfaces at session start
# instead of by tripping over the symptom. ADVISORY here (`|| true`): report-only, never blocks a
# session on a pre-existing dead service (recovery = monit / operator). The config-render drift check
# also runs so a registry edit that was never re-rendered is caught.
detect_service_watchdog(){
  local wd="$HERE/watchdog/discover-services.sh"
  [ -x "$wd" ] || { echo "service-watchdog: discover-services.sh not found/executable at $wd"; return 0; }
  echo "-- service-watchdog (liveness + freshness + discovery) --"
  bash "$wd" --quiet || true
  local gen="$HERE/watchdog/generate-monit-config.sh"
  [ -x "$gen" ] && { bash "$gen" --check >/dev/null 2>&1 || echo "service-watchdog: monit.d DRIFT — registry changed but config not re-rendered (run: fleet/watchdog/generate-monit-config.sh)"; }
  local sw="$HERE/watchdog/monit-selfwatch.sh"
  [ -x "$sw" ] && { bash "$sw" --check >/dev/null 2>&1 || echo "service-watchdog: monit self-watch reports monit NOT healthy or NOT installed (run: fleet/watchdog/monit-selfwatch.sh)"; }
}
# --- detect_fixture_bypass: the "green over a path never run" class (six instances 2026-07-19).
# A suite is fully green while the code it claims to cover is broken or ABSENT, because every test
# takes a fixture/env bypass that returns before the production path is reached. fixture-bypass.sh
# owns the detection; this is the D1 STATIC scan only — pure file inspection, no suite execution,
# no network. ADVISORY (`scan` always exits 0): it is a heuristic, and a heuristic that hard-blocks
# startup is a heuristic that gets disabled [[gates-must-actually-run]]. The hard verdict is
# `fixture-bypass.sh check`, reserved for a future ratchet once the tree is at zero findings.
# The expensive D2 mutation mode (`deep`) is NEVER invoked from here — it re-runs whole suites,
# some of which are hour-long grader runs, and it is reentrancy-guarded against exactly this.
detect_fixture_bypass(){
  local script="$HERE/checks/fixture-bypass.sh"
  [ -x "$script" ] || { echo "fixture-bypass: detector not found/executable at $script"; return 0; }
  bash "$script" scan 2>&1 | grep -E '^(FIXTURE-BYPASS:|     |fixture-bypass:)' || true
}

# --- detect_gate_integrity: THE GATE ON THE GATES. Answers "we put in mechanized gates for this —
# what happened?": a gate can read as protection while providing none (inert, falsely claiming to
# be wired, or with a test that never runs in CI and has never been seen to fail). Nothing checked
# that. gate-integrity.sh owns the detection; this is the STATIC scan — no suite is executed, no
# other gate is invoked, no network. ~2s.
# ADVISORY here (`scan` always exits 0): the rig carries a real legacy backlog of inert/unproven
# gates, and a detector that hard-blocks startup on day one is a detector that gets commented out
# [[gates-must-actually-run]]. The RATCHET verdict is `gate-integrity.sh check`, which reds only on
# findings outside the frozen GI_BASELINE — i.e. on any NEWLY inert / falsely-claimed / unproven
# gate. That is the mode CI should adopt once this has ridden a few PRs.
detect_gate_integrity(){
  local script="$HERE/checks/gate-integrity.sh"
  [ -x "$script" ] || { echo "gate-integrity: detector not found/executable at $script"; return 0; }
  bash "$script" scan 2>&1 | grep -E '^(GATE-INTEGRITY|     |gate-integrity:)' || true
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
  detect_stranded_work
  detect_cg_drift
  detect_gateway_token_drift
  detect_config_drift
  detect_service_watchdog
  detect_fixture_bypass
  detect_gate_integrity
  echo "--- end detectors ---"
  bash "$HERE/access-check.sh" || true
  return 0
}

foreman_advisory(){
  local script="$HERE/foreman.sh"
  [ -x "$script" ] || { echo "foreman: foreman.sh not found/executable at $script"; return 0; }
  echo "--- FOREMAN ADVISORY (report-only, never --fix) ---"
  local out
  out="$(bash "$script" 2>&1)" || true  # never block
  FOREMAN_VERDICT_LINES="$(printf '%s\n' "$out" | grep '^== FOREMAN VERDICT:' || true)"
  printf '%s\n' "$out"
  echo "--- end foreman advisory ---"
  return 0
}

show_operator_actions(){
  echo "--- OPERATOR ACTIONS (things the manager needs YOU to do/decide) ---"
  bash "$HERE/pending.sh" list
  if [ -n "$FOREMAN_VERDICT_LINES" ]; then
    echo ""
    while IFS= read -r line; do
      echo "!! $line !!"
    done <<< "$FOREMAN_VERDICT_LINES"
  fi
  echo "--- end operator actions ---"
  return 0
}

# _summarize_reconcile_merged — cap the reconcile-merged.sh flood by collapsing it into
# one CLASS summary: count of closed/ambiguous/unresolvable, and the distinct shapes of
# ambiguous/unresolvable ones. The "one line per PR" output is noise; what matters is
# how many closed cleanly, how many were ambiguous, and which ones. Runs once in the dispatch
# and saves the summary for the leg-verdicts tail.
_sUMM_MERGED_SUMMARY=""
_summarize_reconcile_merged(){
  local out lines closed=0 ambiguous=0 unresolvable=0 ambiguous_shapes="" unresolvable_shapes="" fail_closed=""
  out="$(bash "$HERE/reconcile-merged.sh" 2>&1)"
  lines="$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$')"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if   printf '%s\n' "$line" | grep -q 'auto-closing WITH proof'; then closed=$((closed+1))
    elif printf '%s\n' "$line" | grep -q 'AMBIGUOUS'; then
      ambiguous=$((ambiguous+1))
      local shape; shape="$(printf '%s\n' "$line" | sed 's/^[^:]*: //; s/ in [^ ]*$//')"
      case "$ambiguous_shapes" in *"$shape"*) ;; *) ambiguous_shapes="${ambiguous_shapes}${ambiguous_shapes:+, }${shape}" ;; esac
    elif printf '%s\n' "$line" | grep -q 'UNRESOLVABLE\|NOT auto-closing'; then
      unresolvable=$((unresolvable+1))
      local shape; shape="$(printf '%s\n' "$line" | sed 's/^[^:]*: //; s/ in [^ ]*$//')"
      case "$unresolvable_shapes" in *"$shape"*) ;; *) unresolvable_shapes="${unresolvable_shapes}${unresolvable_shapes:+, }${shape}" ;; esac
    fi
    [ -z "$fail_closed" ] && printf '%s\n' "$line" | grep -q 'FAIL-CLOSED' && fail_closed="$(printf '%s\n' "$line" | head -1)"
  done <<< "$lines"
  _SUMM_MERGED_SUMMARY="reconcile-merged: ${closed} auto-closed, ${ambiguous} ambiguous, ${unresolvable} unresolvable"
  [ "$ambiguous" -gt 0 ]      && _SUMM_MERGED_SUMMARY="$_SUMM_MERGED_SUMMARY
    ambiguous shapes: ${ambiguous_shapes}"
  [ "$unresolvable" -gt 0 ]    && _SUMM_MERGED_SUMMARY="$_SUMM_MERGED_SUMMARY
    unresolvable shapes: ${unresolvable_shapes}"
  [ -n "$fail_closed" ]        && _SUMM_MERGED_SUMMARY="$_SUMM_MERGED_SUMMARY
    ${fail_closed}"
  echo "$_SUMM_MERGED_SUMMARY"
}

# _summarize_reconcile_stale_claims — same treatment for reconcile-stale-claims.sh.
_SUMM_STALE_SUMMARY=""
_summarize_reconcile_stale_claims(){
  local out lines retired=0 held=0 residue=0
  out="$(bash "$HERE/reconcile-stale-claims.sh" 2>&1)"
  lines="$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$')"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if   printf '%s\n' "$line" | grep -q 'retire-done:'; then retired=$((retired+1))
    elif printf '%s\n' "$line" | grep -q 'HELD\|held';  then held=$((held+1))
    elif printf '%s\n' "$line" | grep -q 'residue\|stale'; then residue=$((residue+1)); fi
  done <<< "$lines"
  if [ "$retired" -eq 0 ] && [ "$held" -eq 0 ] && [ "$residue" -eq 0 ]; then
    _SUMM_STALE_SUMMARY="reconcile-stale-claims: clean (no stale claims)"
  else
    _SUMM_STALE_SUMMARY="reconcile-stale-claims: retired=${retired} held=${held} residue=${residue}"
  fi
  echo "$_SUMM_STALE_SUMMARY"
}

# show_leg_verdicts — ANTI-STARVATION SUMMARY. Every preflight leg prints to stdout as it
# runs; a noisy early leg can drown a late one and the operator's scrollback has a hard cap.
# This summary is printed REGARDLESS of upstream volume: it snapshots every tracked-gate
# result so the operator can find the cadence verdict without scrolling past a flood, and
# no future noisy leg can ever starve the late legs of the operator's attention again.
# RCs from the sub-shells are NOT checked here — the dispatch chain already gates on them;
# this is purely a readable summary printed after everything else.
show_leg_verdicts(){
  echo ""
  echo "===== PREFLIGHT LEG VERDICTS (anti-starvation summary) ====="
  printf '%s\n' "$_SUMM_MERGED_SUMMARY" | sed 's/^/  [reconcile-merged] /'
  printf '%s\n' "$_SUMM_STALE_SUMMARY" | sed 's/^/  [reconcile-stale] /'
  echo "  [board_gate]               → see 'board_gate' line above"
  echo "  [executor_gate]            → see 'executor_gate' line above"
  echo "  [coverage_gate]           → see 'coverage_gate' line above"
  echo "  [handoff_gate]            → see 'handoff_gate' line above"
  echo "  [done_merge_gate]         → see 'clean: done-merge-gate' or 'done-merge-gate: UNMERGED' line above"
  echo "  [hold_reason_gate]        → see 'hold-reason-gate' line above"
  echo "  [detect_needs_push]       → see 'needs-push' lines above"
  echo "  [startup_budget_gate]     → see 'startup_budget_gate' line above"
  echo "  [graphify_freshness_gate] → see 'graphify_freshness_gate' line above"
  echo "  [reconcile_gate_wired_gate] → see 'reconcile_gate_wired_gate' line above"
  echo "  [detect_stranded_work]    → see 'clean: stranded-work-cadence' or 'WARN: stranded-work-cadence' line above"
  echo "  [detect_cg_drift]         → see 'ACTIVE DETECTORS' block above"
  echo "  [detect_gateway_token_drift] → see 'ACTIVE DETECTORS' block above"
  echo "  [detect_config_drift]     → see 'ACTIVE DETECTORS' block above"
  echo "  [detect_service_watchdog] → see 'ACTIVE DETECTORS' block above"
  echo "  [detect_fixture_bypass]  → see 'ACTIVE DETECTORS' block above"
  echo "  [detect_gate_integrity]  → see 'ACTIVE DETECTORS' block above"
  echo "  [cmd_scan]                → see 'REDS PREFLIGHT' block above"
  echo "  [foreman_advisory]        → see 'FOREMAN ADVISORY' block above"
  echo "  [operator_actions]       → see 'OPERATOR ACTIONS' block above"
  echo "===== END VERDICTS ====="
}

# --- graphify_freshness_gate: MECHANIZES the graphify-map-freshness contract (WIRE-GRAPHIFY-FRESHNESS).
# Runs checks/graphify-freshness.sh check EVERY preflight so a stale code map — the root cause of
# the cere-junda handoff reinvention (3-day-stale product graph, absent rig graph) — BLOCKS
# the session. The tracked red auto-registers on RED and self-closes on GREEN, identical
# machinery to board_gate / executor_gate / coverage_gate.
GRAPHIFY_FRESHNESS_RED_ID="graphify-freshness-stale"
GRAPHIFY_FRESHNESS_CHECK="$HERE/checks/graphify-freshness.sh"
_graphify_freshness_red_status(){ awk -F"$TAB" -v id="$GRAPHIFY_FRESHNESS_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_graphify_freshness_red_ensure_open(){
  local st; st="$(_graphify_freshness_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$GRAPHIFY_FRESHNESS_RED_ID" P1 gate \
      "graphify code map is STALE — a stale map causes reuse-check to MISS existing tools -> reinvention. Run: bash fleet/checks/graphify-freshness.sh update" \
      "bash '$GRAPHIFY_FRESHNESS_CHECK' gate >/dev/null 2>&1" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$GRAPHIFY_FRESHNESS_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
_graphify_freshness_red_close_if_open(){
  [ "$(_graphify_freshness_red_status)" = open ] && \
    cmd_close "$GRAPHIFY_FRESHNESS_RED_ID" --override "auto: graphify-freshness gate GREEN" >/dev/null 2>&1 || true
}
graphify_freshness_gate(){
  [ -f "$GRAPHIFY_FRESHNESS_CHECK" ] || { echo "graphify_freshness_gate: graphify-freshness.sh not found at $GRAPHIFY_FRESHNESS_CHECK"; return 0; }
  local out rc; out="$(bash "$GRAPHIFY_FRESHNESS_CHECK" gate 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "graphify_freshness_gate: $(printf '%s\n' "$out" | grep -m1 'GREEN' || echo GREEN)"
    _graphify_freshness_red_close_if_open
  else
    _graphify_freshness_red_ensure_open
    echo "graphify_freshness_gate: GRAPH CODE MAP STALE — AUTO-REGISTERED tracked red '$GRAPHIFY_FRESHNESS_RED_ID' (blocks preflight until the map is refreshed: bash fleet/checks/graphify-freshness.sh update)"
    printf '%s\n' "$out" | grep -E '^  \[.*\].*(STALE|ABSENT)' | head -6 | sed 's/^ */    /'
  fi
}

# --- reconcile_gate_wired_gate: MECHANIZES §1.3 (UNIFIED-RECONCILIATION-GATE-DESIGN.md, PR #178)
# — the built-but-inert META-gate. Runs checks/reconcile-gate-wired.sh EVERY preflight (identical
# machinery to board_gate / coverage_gate / graphify_freshness_gate): it cross-references every
# declared check (fleet/checks/*.sh|*.py, product tools/check_*.py|*.sh, RULE-REGISTRY mechanized
# rows, EVAL-REGISTRY ADOPT rows) against the actual firing layers (this file, land.sh,
# validate_board.sh, hooks/session-start.sh, foreman-cadence.sh, rig+product CI workflows,
# transitively through dispatchers like rig-ci-scope.sh) and REDS on R-G (declared but never
# fired — built-but-inert) or R-H (fired but never declared — unregistered runner). This wiring
# is itself the fix for the meta-gate's own founding complaint: before this line existed,
# reconcile-gate-wired.sh appeared in its OWN R-G report (the detector was built-but-inert).
# NOTE (honest seam, RECONCILE-GATE-WIRED ticket): at wiring time this rig carries a KNOWN
# pre-existing R-G backlog (checks declared but not yet wired into any firing layer) that
# predates this gate and is NOT this ticket's owns:. Closing each of those is RECONCILE-WIRING's
# tracked scope (depends_on this ticket); this tracked red points there, it does not hide it.
RECONCILE_GATE_WIRED_RED_ID="reconcile-gate-wired-gap"
RECONCILE_GATE_WIRED_CHECK="$HERE/checks/reconcile-gate-wired.sh"
_reconcile_gate_wired_red_status(){ awk -F"$TAB" -v id="$RECONCILE_GATE_WIRED_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_reconcile_gate_wired_red_ensure_open(){
  local st; st="$(_reconcile_gate_wired_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$RECONCILE_GATE_WIRED_RED_ID" P1 rig-meta \
      "reconcile-gate-wired meta-gate RED: a declared check is built-but-inert (R-G, never fired from any real firing layer) or a snippet is firing but unregistered (R-H). Run: bash fleet/checks/reconcile-gate-wired.sh — the pre-existing backlog is RECONCILE-WIRING's tracked scope; a NEW regression here is this branch's to fix." \
      "bash $RECONCILE_GATE_WIRED_CHECK" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$RECONCILE_GATE_WIRED_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
reconcile_gate_wired_gate(){
  [ -f "$RECONCILE_GATE_WIRED_CHECK" ] || { echo "reconcile_gate_wired_gate: reconcile-gate-wired.sh not found at $RECONCILE_GATE_WIRED_CHECK"; return 0; }
  local out rc; out="$(bash "$RECONCILE_GATE_WIRED_CHECK" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "reconcile_gate_wired_gate: $(printf '%s\n' "$out" | grep -m1 -E 'VERDICT:' | sed 's/^ *//')"
    [ "$(_reconcile_gate_wired_red_status)" = open ] && \
      cmd_close "$RECONCILE_GATE_WIRED_RED_ID" --override "auto: reconcile-gate-wired GREEN" >/dev/null 2>&1 || true
  else
    _reconcile_gate_wired_red_ensure_open
    echo "reconcile_gate_wired_gate: RECONCILE-GATE-WIRED META-GATE RED — AUTO-REGISTERED tracked red '$RECONCILE_GATE_WIRED_RED_ID' (see: bash fleet/checks/reconcile-gate-wired.sh)"
    printf '%s\n' "$out" | grep -E '^  R-[GH] ' | sed 's/^ */    /'
  fi
}

# --- startup_budget_gate: MECHANIZES §13 startup context budget (MANAGER-OPERATING-RULES.md).
# Tracked startup artifact files with per-file byte budgets. A file exceeding its budget
# AUTO-REGISTERS a blocking P1 red 'startup-budget-exceeded' that self-closes when all files
# drop back within budget. This is the fail-on-revert gate for the context diet.
BUDGET_RED_ID="startup-budget-exceeded"
declare -A STARTUP_BUDGETS=(
  ["MANAGER-OPERATING-RULES.md"]=26000
  ["START-SESSION.md"]=3200
  ["handoff.sh"]=17500
  ["handoff-check.sh"]=6600
  ["preflight.sh"]=36000
)
TOTAL_BUDGET=89500

_startup_budget_red_status(){ awk -F"$TAB" -v id="$BUDGET_RED_ID" '$1==id{print $7; exit}' "$TSV"; }
_startup_budget_red_ensure_open(){
  local st; st="$(_startup_budget_red_status)"
  if [ -z "$st" ]; then
    cmd_add "$BUDGET_RED_ID" P1 gate \
      "startup artifact(s) exceed byte budget — trim MANAGER-OPERATING-RULES.md, START-SESSION.md, handoff.sh, handoff-check.sh, or preflight.sh" \
      "bash '$0' startup-budget-check >/dev/null 2>&1" >/dev/null 2>&1 || true
  elif [ "$st" = closed ]; then
    local tmp; tmp="$(mktemp)"
    awk -F"$TAB" -v OFS="$TAB" -v id="$BUDGET_RED_ID" \
      '/^#/{print;next} $1==id{$7="open";$8=""} {print}' "$TSV" > "$tmp" && mv "$tmp" "$TSV"
  fi
}
_startup_budget_red_close_if_open(){
  [ "$(_startup_budget_red_status)" = open ] && \
    cmd_close "$BUDGET_RED_ID" --override "auto: all startup artifacts within budget" >/dev/null 2>&1 || true
}
startup_budget_check(){
  local fail=0; local total=0; local budget size f
  echo "--- STARTUP BUDGET GATE ---"
  for f in "${!STARTUP_BUDGETS[@]}"; do
    budget="${STARTUP_BUDGETS[$f]}"
    if [ -f "$HERE/$f" ]; then
      size="$(wc -c < "$HERE/$f")"
      total=$((total + size))
      if [ "$size" -gt "$budget" ]; then
        printf '  OVER BUDGET: %s = %d bytes (budget: %d, over by %d)\n' "$f" "$size" "$budget" "$((size - budget))"
        fail=1
      else
        printf '  OK: %s = %d bytes (budget: %d)\n' "$f" "$size" "$budget"
      fi
    else
      printf '  MISSING: %s\n' "$f"
      fail=1
    fi
  done
  printf '  TOTAL: %d bytes (budget: %d)\n' "$total" "$TOTAL_BUDGET"
  if [ "$total" -gt "$TOTAL_BUDGET" ]; then
    printf '  OVER TOTAL BUDGET by %d bytes\n' "$((total - TOTAL_BUDGET))"
    fail=1
  fi
  return $fail
}
startup_budget_gate(){
  local out rc; out="$(startup_budget_check 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    echo "startup_budget_gate: all tracked artifacts within budget"
    _startup_budget_red_close_if_open
  else
    _startup_budget_red_ensure_open
    echo "startup_budget_gate: STARTUP BUDGET EXCEEDED — AUTO-REGISTERED tracked red '$BUDGET_RED_ID' (blocks preflight until files are trimmed)"
    printf '%s\n' "$out" | grep 'OVER BUDGET\|OVER TOTAL' | head -8 | sed 's/^/    /'
  fi
}
# Blade-runner proof: self-test that the budget gate fires when a file exceeds budget.
startup_budget_selftest(){
  local tmpfile; tmpfile="$(mktemp)"
  # Test: write a dummy MANAGER-OPERATING-RULES.md that's too big
  dd if=/dev/zero of="$tmpfile" bs=1 count=50000 2>/dev/null
  # Override HERE temporarily
  local real_here="$HERE"
  HERE="$(dirname "$tmpfile")"
  ln -sf "$tmpfile" "$HERE/MANAGER-OPERATING-RULES.md" 2>/dev/null || true
  local rc=0
  startup_budget_check >/dev/null 2>&1 || rc=$?
  rm -f "$HERE/MANAGER-OPERATING-RULES.md" "$tmpfile"
  HERE="$real_here"
  if [ "$rc" -ne 0 ]; then
    echo "startup-budget-selftest: PASS (gate fires on over-budget file — fail-on-revert verified)"
    return 0
  else
    echo "startup-budget-selftest: FAIL (gate did NOT fire on over-budget file)"
    return 1
  fi
}

# Dispatch ONLY when run directly. When SOURCED (fleet/tests/needs-push-gate.test.sh) the
# functions above are exposed with NO side effects.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
case "${1:-scan}" in
scan|"")
  run_sync_checkouts
  _summarize_reconcile_merged
  _summarize_reconcile_stale_claims
  board_gate; executor_gate; coverage_gate; handoff_gate
  done_merge_gate; hold_reason_gate; detect_needs_push
  startup_budget_gate; graphify_freshness_gate; reconcile_gate_wired_gate
  bash "$HERE/retire-done.sh"
  cmd_scan; scan_rc=$?
  cmd_detect
  foreman_advisory
  show_operator_actions
  show_leg_verdicts
  exit $scan_rc ;;
  add)     shift; cmd_add "$@" ;;
  close)   shift; cmd_close "$@" ;;
  list)    shift; cmd_list "$@" ;;
  detect)  shift; cmd_detect "$@" ;;
  hold-check) shift; hold_check "$@" ;;
  startup-budget-check) startup_budget_check ;;
  startup-budget-selftest) startup_budget_selftest ;;
  *) echo "usage: $0 {scan|add <id> <sev> <area> \"<desc>\" \"<check>\"|close <id> [--override r|--evidence t]|list [open|closed|all]|detect [--full]|hold-check <slug> <pr>|startup-budget-check|startup-budget-selftest}" >&2; exit 1 ;;
esac
fi
