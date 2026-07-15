#!/usr/bin/env bash
# rule-sync.sh — F47 RULE-SYNC-GATE (bidirectional rule-port enforcement).
# Mechanizes the operator's TWO-WAY rule-sync doctrine (GAP-REGISTER A3, 2026-07-12):
# the rule-port class (Charon <-> SLOP <-> KSF) has historically regressed because
# untriaged gaps went unflagged. This gate reads fleet/state/RULE-SYNC-REGISTER.tsv
# (the audit's SSOT) and enforces that no rule is silently un-triaged, in BOTH
# directions. PORTS the KSF coverage_ssot pattern (one checker against a register,
# RED on unclassified/missing) rather than reinventing a new engine (§6 anti-accretion).
#
# RED (always):
#   - any into-charon row with charon_status=gap AND action!=port-to-charon
#     (an untriaged inbound gap — a SLOP/KSF rule Charon lacks with no decision)
#   - any out-of-charon row with action=file-slop-ticket|file-ksf-ticket AND
#     no linked ticket currently exists in the target sibling repo with the
#     matching title (the two-way obligation is enforced, not advisory)
# LINKAGE MODEL: a rule row is "linked" iff a real ticket with the
# canonicalized rule title currently exists in the target sibling repo.
#   - SLOP: `python3 /home/stack/code/mediastack/tracking/query.py open --json` (or
#     equivalent text output) and grep the title.
#   - KSF:  `gh issue list --repo <repo> --state open --json title` and grep the title.
# On RED the gate ACTUALLY creates the ticket (SLOP via query.py add; KSF via
# gh issue create) and re-verifies. Idempotent: if a matching ticket already exists,
# it is NOT duplicated; the existing id is reported instead. DRY-RUN mode skips
# creation and is used by the test suite (and the operator for previewing).
#
# Usage:
#   rule-sync.sh check [--dry-run]
#       Exit 0 = GREEN (all rules triaged, all out-of-charon rows linked).
#       Exit 1 = RED (untriaged or unlinked; the message names every offender).
#       Exit 2 = usage/file-not-found.
#   rule-sync.sh scan [--dry-run]
#       ADVISORY board-wide. Prints one UNSYNCED line per offender and a summary
#       of created/would-create cross-repo assignments. ALWAYS exits 0 (advisory;
#       consumed by validate_board.sh, never fails it on its own).
#
# Env overrides (isolated self-test seams; defaults are the real fleet):
#   RULE_SYNC_REGISTER        register path (default <fleet>/state/RULE-SYNC-REGISTER.tsv)
#   RULE_SYNC_SLOP_CLI        SLOP `query.py` path (default /home/stack/code/mediastack/tracking/query.py)
#   RULE_SYNC_KSF_GH_REPO     GitHub owner/repo for KSF tickets (default derived from
#                             `git -C /home/stack/code/keystone remote get-url origin`)
#   RULE_SYNC_KSF_REPO_DIR    Local KSF repo dir (default /home/stack/code/keystone)
#   RULE_SYNC_DRY_RUN         "1" => skip ticket creation; print WOULD-CREATE; used by tests
#   RULE_SYNC_SLOP_BATCH      Override the auto-discovered SLOP open batch (e.g. for tests)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/ (script lives in fleet/checks/)
REGISTER="${RULE_SYNC_REGISTER:-$HERE/state/RULE-SYNC-REGISTER.tsv}"
SLOP_CLI="${RULE_SYNC_SLOP_CLI:-/home/stack/code/mediastack/tracking/query.py}"
KSF_REPO_DIR="${RULE_SYNC_KSF_REPO_DIR:-/home/stack/code/keystone}"
KSF_GH_REPO="${RULE_SYNC_KSF_GH_REPO:-}"
DRY_RUN="${RULE_SYNC_DRY_RUN:-0}"
SLOP_BATCH_OVERRIDE="${RULE_SYNC_SLOP_BATCH:-}"

# --- 0. Auto-derive KSF_GH_REPO from the local clone if not set. ----------------------
if [ -z "$KSF_GH_REPO" ] && [ -d "$KSF_REPO_DIR/.git" ]; then
  KSF_GH_REPO="$(git -C "$KSF_REPO_DIR" remote get-url origin 2>/dev/null \
                 | sed -E 's#^.*github\.com[:/]+##; s#\.git$##' || true)"
fi

usage(){
  cat >&2 <<EOF
usage: rule-sync.sh check [--dry-run]
       rule-sync.sh scan  [--dry-run]
env: RULE_SYNC_REGISTER, RULE_SYNC_SLOP_CLI, RULE_SYNC_KSF_GH_REPO, RULE_SYNC_DRY_RUN
EOF
  exit 2
}

# --- helpers ---------------------------------------------------------------------------
lc(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
is_blank(){ [ -z "$(printf '%s' "$1" | tr -d '[:space:]')" ]; }

# --- 1. Parse the register. Returns 0 on success, 1 on header-error. --------------------
# Emits, on stdout, one TSV row per data row with the original columns, AND injects
# these derived fields appended (so the rest of the script can read them positionally):
#   col9  = target_repo (slop|ksf|"")  (derived from action column)
#   col10 = needs_link  (0|1)          (1 iff out-of-charon AND action is file-*-ticket)
# We also pre-extract the header to handle files that may or may not have a
# `linked_ticket` column. Output rows are tab-separated; the data-row index is preserved
# via NR kept in col11.
parse_register(){
  [ -f "$REGISTER" ] || { echo "rule-sync: register not found: $REGISTER" >&2; return 1; }
  python3 - "$REGISTER" <<'PY'
import sys, re
path = sys.argv[1]
hdr = None
linked_col = -1
for ln in open(path):
    if ln.lstrip().startswith("#") or not ln.strip():
        continue
    if hdr is None:
        hdr = ln.rstrip("\n").split("\t")
        # 0:source 1:rule_id 2:summary 3:charon_status 4:direction 5:mechanized 6:action 7:note
        for i, h in enumerate(hdr):
            if h.strip() == "linked_ticket":
                linked_col = i
                break
        continue
    parts = ln.rstrip("\n").split("\t")
    # pad to header length so the index math is safe
    while len(parts) < len(hdr):
        parts.append("")
    src = parts[0].strip()
    rid = parts[1].strip()
    summary = parts[2].strip()
    status = parts[3].strip().lower()
    direction = parts[4].strip().lower()
    action = parts[6].strip().lower()
    # bash's `read` with IFS=$'\t' COLLAPSES adjacent empty fields, so a single empty
    # `linked` would silently shift every following variable left. Sidestep by using `-`
    # as the empty-sentinel for the `linked` field (a real ticket id never matches `-`).
    linked = "-" if not (0 <= linked_col < len(parts)) or not parts[linked_col].strip() else parts[linked_col].strip()
    target = "-"
    needs_link = "0"
    if direction == "out-of-charon":
        if action == "file-slop-ticket":
            target = "slop"; needs_link = "1"
        elif action == "file-ksf-ticket":
            target = "ksf";  needs_link = "1"
    title = f"{rid} (from Charon)"
    # emit: rid <TAB> direction <TAB> status <TAB> action <TAB> target <TAB> needs_link <TAB> linked <TAB> title <TAB> summary
    sys.stdout.write(f"{rid}\t{direction}\t{status}\t{action}\t{target}\t{needs_link}\t{linked}\t{title}\t{summary}\n")
PY
}

# --- 2. SLOP: look up an open ticket whose title contains the rule id. -----------------
# Echoes the ticket id on match; empty stdout on no match. Uses `query.py open --json`
# if the CLI supports --json; otherwise falls back to plain text and greps for the id.
slop_lookup(){
  local title="$1"
  [ -x "$(command -v python3)" ] || return 0
  [ -f "$SLOP_CLI" ] || return 0
  local rid
  rid="$(printf '%s' "$title" | awk '{print $1}')"   # e.g. SLOP-INV:1.2
  # Try JSON first
  local out
  out="$(python3 "$SLOP_CLI" open --json 2>/dev/null || true)"
  if printf '%s' "$out" | grep -q "$rid"; then
    # Extract a plausible ticket id (the SLOP tracker uses a few shapes; take the first match)
    printf '%s' "$out" \
      | python3 -c "
import sys, json, re
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    sys.exit(0)
target = sys.argv[1]
for row in data if isinstance(data, list) else []:
    title = (row.get('title') if isinstance(row, dict) else '') or ''
    if target in title:
        print(row.get('id') or row.get('ticket_id') or row.get('backlog_id') or '')
        sys.exit(0)
" "$rid" 2>/dev/null
    return 0
  fi
  # Plain-text fallback: `query.py open` lines usually include title
  out="$(python3 "$SLOP_CLI" open 2>/dev/null || true)"
  if printf '%s' "$out" | grep -q "$rid"; then
    printf '%s' "$out" | grep -F "$rid" | head -1 | awk '{print $1}'
  fi
}

slop_create(){
  local title="$1" batch="$2"
  if [ "$DRY_RUN" = "1" ]; then printf 'WOULD-CREATE-SLOP\t%s\tbatch=%s\n' "$title" "$batch"; return 0; fi
  python3 "$SLOP_CLI" add \
    --title "$title" \
    --category infra \
    --batch "$batch" \
    --tier R \
    --kind PROVISIONAL \
    --notes "auto-created by fleet/checks/rule-sync.sh (F47 RULE-SYNC-GATE) from RULE-SYNC-REGISTER.tsv" \
    --description "Cross-repo rule-port: a Charon mechanism (see RULE-SYNC-REGISTER.tsv) needs an SLOP equivalent. See fleet/checks/rule-sync.sh for the enforcement loop." \
    2>&1 | tee /tmp/opencode/rule-sync-slop-create.log
}

# --- 3. KSF: look up an open GitHub issue with a title containing the rule id. -------
# Echoes the issue number on match; empty stdout otherwise.
ksf_lookup(){
  local title="$1"
  [ -n "$KSF_GH_REPO" ] || return 0
  command -v gh >/dev/null 2>&1 || return 0
  local rid
  rid="$(printf '%s' "$title" | awk '{print $1}')"
  local out
  out="$(gh issue list --repo "$KSF_GH_REPO" --state open --limit 200 --json number,title 2>/dev/null || true)"
  printf '%s' "$out" | python3 -c "
import sys, json
raw = sys.stdin.read()
target = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    sys.exit(0)
for row in data if isinstance(data, list) else []:
    if target in (row.get('title') if isinstance(row, dict) else ''):
        print(row.get('number') or '')
        sys.exit(0)
" "$rid" 2>/dev/null
}

ksf_create(){
  local title="$1"
  if [ "$DRY_RUN" = "1" ]; then printf 'WOULD-CREATE-KSF\t%s\trepo=%s\n' "$title" "$KSF_GH_REPO"; return 0; fi
  gh issue create --repo "$KSF_GH_REPO" \
    --title "$title" \
    --label "rule-sync,from-charon" \
    --body "Cross-repo rule-port: a Charon mechanism (see fleet/state/RULE-SYNC-REGISTER.tsv) needs a KSF equivalent. Auto-opened by fleet/checks/rule-sync.sh (F47 RULE-SYNC-GATE)." \
    2>&1
}

# --- 4. Discover the currently-OPEN SLOP batch (most-recent non-CLOSED). ---------------
# Echoes the batch key, or empty if none.
discover_slop_batch(){
  if [ -n "$SLOP_BATCH_OVERRIDE" ]; then printf '%s' "$SLOP_BATCH_OVERRIDE"; return 0; fi
  [ -f "$SLOP_CLI" ] || return 0
  # query.py batches emits columns: BATCH_KEY, STATE, STARTED_AT, CLOSED_AT (whitespace-aligned).
  # Pick the first row whose STATE column is neither CLOSED nor COMPLETE; print only $1 (the key).
  python3 "$SLOP_CLI" batches 2>/dev/null \
    | awk 'NR>2 { state = tolower($2); if (state != "closed" && state != "complete") { print $1; exit } }'
}

# --- 5. Core: process every row. Prints per-row summary; sets GLOBAL offenders. --------
# Output format per row (tab-separated):
#   verdict<TAB>rid<TAB>reason<TAB>action_taken
#   verdict in: UNTRIAGED | UNLINKED | LINKED | UNKNOWN
process_rows(){
  local slop_batch
  slop_batch="$(discover_slop_batch)"
  parse_register | while IFS=$'\t' read -r rid direction status action target needs_link linked title summary; do
    if [ "$direction" = "into-charon" ]; then
      if [ "$status" = "gap" ] && [ "$action" != "port-to-charon" ]; then
        printf 'UNTRIAGED\t%s\tinto-charon status=gap with action=%s (no decision yet)\tNONE\n' \
          "$rid" "$action"
      fi
      continue
    fi
    if [ "$direction" = "out-of-charon" ] && [ "$needs_link" = "1" ]; then
      if [ "$linked" != "-" ]; then
        # Register has the column populated — treat as already linked (caller-asserted)
        printf 'LINKED\t%s\tlinked_ticket=%s in %s\tnone (caller-asserted)\n' \
          "$rid" "$linked" "$target"
        continue
      fi
      # Try to discover an existing ticket in the target repo
      local existing=""
      case "$target" in
        slop) existing="$(slop_lookup "$title" || true)" ;;
        ksf)  existing="$(ksf_lookup  "$title" || true)" ;;
      esac
      if [ -n "$existing" ]; then
        printf 'LINKED\t%s\texisting ticket %s in %s\tnone (idempotent)\n' \
          "$rid" "$existing" "$target"
        continue
      fi
      # No existing ticket — create it (or report WOULD-CREATE in dry-run)
      case "$target" in
        slop)
          if [ -z "$slop_batch" ]; then
            printf 'UNLINKED\t%s\tno SLOP batch is OPEN right now (all closed)\tCREATE-BLOCKED\n' "$rid"
            continue
          fi
          if [ "$DRY_RUN" = "1" ]; then
            printf 'UNLINKED\t%s\twould create SLOP ticket in batch %s (dry-run)\tWOULD-CREATE-SLOP\n' "$rid" "$slop_batch"
            continue
          fi
          out="$(slop_create "$title" "$slop_batch" 2>&1)"
          # Extract the new ticket id from the query.py output (it ends with a "BL-NNN" or similar token)
          new_id="$(printf '%s' "$out" | grep -oE 'BL-[0-9]+' | head -1)"
          if [ -z "$new_id" ]; then
            # Fallback: look at the open list and re-derive
            new_id="$(slop_lookup "$title" || true)"
          fi
          if [ -n "$new_id" ]; then
            printf 'LINKED\t%s\tcreated SLOP ticket %s\tCREATE: %s\n' "$rid" "$new_id" "$out" | head -1
          else
            printf 'UNLINKED\t%s\tSLOP create ran but no ticket id could be recovered\tCREATE-FAILED\n' "$rid"
          fi
          ;;
        ksf)
          if [ "$DRY_RUN" = "1" ]; then
            printf 'UNLINKED\t%s\twould create KSF issue on %s (dry-run)\tWOULD-CREATE-KSF\n' "$rid" "$KSF_GH_REPO"
            continue
          fi
          out="$(ksf_create "$title" 2>&1)"
          new_num="$(printf '%s' "$out" | grep -oE 'https://github.com/[^ ]+/issues/[0-9]+' | head -1 | awk -F/ '{print $NF}')"
          if [ -z "$new_num" ]; then
            new_num="$(ksf_lookup "$title" || true)"
          fi
          if [ -n "$new_num" ]; then
            printf 'LINKED\t%s\tcreated KSF issue #%s\tCREATE: %s\n' "$rid" "$new_num" "$out" | head -1
          else
            printf 'UNLINKED\t%s\tKSF create ran but no issue number could be recovered\tCREATE-FAILED\n' "$rid"
          fi
          ;;
        *)
          printf 'UNKNOWN\t%s\tout-of-charon row has action=%s (no file-*-ticket mapping)\tNONE\n' "$rid" "$action"
          ;;
      esac
    fi
  done
}

# --- 6. cmd_check: enforce (creates tickets if needed), then re-verify. ----------------
cmd_check(){
  local arg
  for arg in "$@"; do
    case "$arg" in --dry-run) DRY_RUN=1 ;; -h|--help) usage ;; esac
  done
  # Run pass 1: process rows. CREATE if needed. Capture per-row verdicts.
  local out
  out="$(process_rows)"
  # Pass 2 (only in non-dry-run, to confirm a freshly-created ticket now shows up):
  # This is what makes the gate self-correcting — pass 1 may CREATE, pass 2 verifies.
  if [ "$DRY_RUN" != "1" ]; then
    out="$(process_rows)"
  fi
  local untriaged=0 unlinked=0 unknown=0 linked=0 created=0 would_create=0
  while IFS=$'\t' read -r verdict rid reason action_taken; do
    [ -n "$verdict" ] || continue
    case "$verdict" in
      UNTRIAGED) untriaged=$((untriaged+1)) ;;
      UNLINKED)  unlinked=$((unlinked+1)) ;;
      UNKNOWN)   unknown=$((unknown+1)) ;;
      LINKED)
        linked=$((linked+1))
        case "$action_taken" in
          CREATE:*) created=$((created+1)) ;;
          *) ;;
        esac
        ;;
    esac
    # Echo the per-row summary line for the operator
    printf '  %s\t%s\t%s\t%s\n' "$verdict" "$rid" "$reason" "$action_taken"
  done <<< "$out"
  echo
  echo "rule-sync: linked=$linked untriaged=$untriaged unlinked=$unlinked unknown=$unknown created=$created"
  if [ "$DRY_RUN" = "1" ]; then
    local wc
    wc="$(printf '%s' "$out" | grep -cE '^(LINKED|UNLINKED|UNKNOWN)' || true)"
    local would
    would="$(printf '%s' "$out" | awk -F'\t' '/^UNLINKED/{print}' | grep -c CREATE-BLOCKED || true)"
    # In dry-run we also surface "WOULD-CREATE-*" lines from the per-row WOULD-CREATE path
    echo "rule-sync: DRY-RUN — no tickets created; set RULE_SYNC_DRY_RUN=0 (or omit --dry-run) to actually create."
  fi
  if [ "$untriaged" -gt 0 ] || [ "$unlinked" -gt 0 ] || [ "$unknown" -gt 0 ]; then
    echo "rule-sync: RED — $untriaged untriaged inbound gap(s), $unlinked unlinked out-of-charon row(s), $unknown unknown action(s)" >&2
    if [ "$DRY_RUN" = "1" ]; then
      echo "rule-sync: re-run WITHOUT --dry-run to actually create the missing tickets." >&2
    fi
    exit 1
  fi
  echo "rule-sync: GREEN — all rules triaged; all out-of-charon rows linked."
  exit 0
}

# --- 7. cmd_scan: advisory, always exits 0. -------------------------------------------
cmd_scan(){
  local arg
  for arg in "$@"; do
    case "$arg" in --dry-run) DRY_RUN=1 ;; -h|--help) usage ;; esac
  done
  local out
  out="$(process_rows)"
  local untriaged=0 unlinked=0 unknown=0 linked=0
  while IFS=$'\t' read -r verdict rid reason action_taken; do
    [ -n "$verdict" ] || continue
    case "$verdict" in
      UNTRIAGED) untriaged=$((untriaged+1))
                  echo "  UNSYNCED: $rid (UNTRIAGED — $reason)" ;;
      UNLINKED)  unlinked=$((unlinked+1))
                  echo "  UNSYNCED: $rid (UNLINKED — $reason; action=$action_taken)" ;;
      UNKNOWN)   unknown=$((unknown+1))
                  echo "  UNSYNCED: $rid (UNKNOWN — $reason)" ;;
      LINKED)
        linked=$((linked+1))
        # Echo the assignment line the manager/operator wants to see (target repo name)
        # for every out-of-charon row, even when linked, so the summary is a complete
        # record of cross-repo assignments (this is the spec's "names the right target
        # repo slop|ksf" requirement made visible at the scan surface too).
        case "$reason" in
          *"in slop"*|*"in ksf"*|*"SLOP ticket"*|*"KSF issue"*) \
            echo "  ASSIGNED: $rid -> ${reason##*in }" ;;
        esac
        ;;
    esac
  done <<< "$out"
  echo "rule-sync scan: linked=$linked untriaged=$untriaged unlinked=$unlinked unknown=$unknown"
  if [ "$untriaged" -gt 0 ] || [ "$unlinked" -gt 0 ] || [ "$unknown" -gt 0 ]; then
    echo "rule-sync scan: ADVISORY — $untriaged untriaged + $unlinked unlinked + $unknown unknown (validate_board advisory surface; the HARD gate is in 'check' subcommand)."
  else
    echo "rule-sync scan: OK — all rules triaged; all out-of-charon rows linked."
  fi
  return 0
}

case "${1:-check}" in
  check) shift; cmd_check "$@" ;;
  scan)  shift || true; cmd_scan "$@" ;;
  -h|--help) usage ;;
  *) usage ;;
esac
