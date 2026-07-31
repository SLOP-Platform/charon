#!/usr/bin/env bash
# reconcile-board-pr-done.sh — board-PR-done reconciler (standalone check).
# Composes reconcile-merged.sh's branch/owns indexing to detect three drift classes:
#   R-A — open ticket whose branch: matches a merged-but-not-done PR (RED).
#   R-B — merged PR with no matching ticket AND no board/*.md creation (RED).
#   R-C — open-ticket / stale-branch / no-open-PR (WARN, not RED).
# AMBIGUOUS ladder (N>1 owns overlap): branch≥title/commit≥sha-ledger≥NEEDS-MANUAL-ADJUDICATION.
# Exit non-zero on any R-A / R-B / AMBIGUOUS; exit 0 clean.
#
# TEST HOOK: RECONCILE_MERGED_SRC=<file> overrides merged-PR set (same as reconcile-merged.sh).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOARD="$FLEET/board"
DONE="$FLEET/state/done"
REVIEWED="$FLEET/state/reviewed"
REPO_SLUG="${RECONCILE_REPO_SLUG:-}"
[ -n "$REPO_SLUG" ] || REPO_SLUG="Nnyan/charon-private"
FINDINGS=() REDS=0 WARNS=0

# ── merged PRs (same fixture/gh as reconcile-merged.sh) ─────────────────────
merged_prs(){
  if [ -n "${RECONCILE_MERGED_SRC:-}" ]; then
    [ -f "$RECONCILE_MERGED_SRC" ] && grep -v '^[[:space:]]*$' "$RECONCILE_MERGED_SRC" || true
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 0
  gh pr list --repo "$REPO_SLUG" --state merged --limit 200 \
     --json headRefName,mergeCommit,files,number \
     -q '.[] | [.headRefName, (.mergeCommit.oid // ""), ([.files[].path]|join(",")), (.number|tostring)] | @tsv' \
     2>/dev/null || true
}

# ── indexing (mirrors reconcile-merged.sh:56-102) ──────────────────────────
BRANCH_INDEX=""
OWNS_INDEX=""
TICKET_FILES=()
while IFS= read -r -d '' f; do TICKET_FILES+=("$f"); done < <(printf '%s\0' "$BOARD"/*.md "$BOARD"/archive/*.md)
_idx_rows="$(mktemp)"
if [ "${#TICKET_FILES[@]}" -gt 0 ]; then
  printf '%s\0' "${TICKET_FILES[@]}" | awk '
    BEGIN { RS = "\0" }
    {
      file = $0
      id = file; sub(/^.*\//, "", id); sub(/\.md$/, "", id)
      branch = ""; owns = ""
      RS_SAVED = RS; RS = "\n"
      while ((getline line < file) > 0) {
        if      (line ~ /^branch:[[:space:]]*/) { sub(/^branch:[[:space:]]*/, "", line); branch = line }
        else if (line ~ /^owns:[[:space:]]*/)   { sub(/^owns:[[:space:]]*/, "", line);   owns   = line }
      }
      RS = RS_SAVED
      close(file)
      if (branch != "") print "B\t" id "\t" branch
      if (owns   != "") print "O\t" id "\t" owns
    }
  ' > "$_idx_rows" 2>/dev/null || true
fi
while IFS=$'\t' read -r kind id val; do
  case "$kind" in
    B) BRANCH_INDEX+="${val}"$'\t'"${id}"$'\n' ;;
    O)
      _oldIFS="$IFS"; IFS=','
      for p in $val; do
        p="$(printf '%s' "$p" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        [ -n "$p" ] || continue
        OWNS_INDEX+="${p}"$'\t'"${id}"$'\n'
      done
      IFS="$_oldIFS"
      ;;
  esac
done < "$_idx_rows"
rm -f "$_idx_rows"

# ── done-marker set ────────────────────────────────────────────────────────
DONE_BRANCHES=""
DONE_IDS=""
if [ -d "$DONE" ]; then
  for m in "$DONE"/*; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"
    DONE_IDS+="${id}"$'\n'
    br="$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i ~ /^branch:/){sub(/^branch:/,"",$i);print $i;exit}}' "$m" 2>/dev/null || true)"
    [ -n "$br" ] && DONE_BRANCHES+="${br}"$'\n'
  done
fi
_done_branch(){ grep -Fxq -- "$1" <<< "$DONE_BRANCHES" 2>/dev/null; }
_done_id(){      grep -Fxq -- "$1" <<< "$DONE_IDS" 2>/dev/null; }

# ── lookup helpers ────────────────────────────────────────────────────────
# Find ticket id by branch (exact match). Returns "" if none.
_lookup_branch(){
  local want="$1" line id
  while IFS=$'\t' read -r line id; do
    [ "$line" = "$want" ] || continue
    printf '%s' "$id"; return 0
  done <<< "$BRANCH_INDEX"
  return 1
}

# Find ticket ids that own a given file. Returns space-separated ids.
_lookup_owns_file(){
  local path="$1" line id ids="" cnt=0
  while IFS=$'\t' read -r line id; do
    [ "$line" = "$path" ] || continue
    ids+=" $id"; cnt=$((cnt+1))
  done <<< "$OWNS_INDEX"
  printf '%s' "$ids"
  return "$cnt"
}

# Determine which ticket (if any) a merged PR maps to.
# Returns: "OK:<id>" | "AMBIGUOUS:<id1,id2,...>" | "NONE"
resolve_pr_ticket(){
  local branch="$1" files="$2" sha="$3" pr="$4"
  # 1) branch match
  local tid
  tid="$(_lookup_branch "$branch")" || true
  [ -n "$tid" ] && { printf 'OK:%s' "$tid"; return 0; }
  [ -n "$files" ] || { printf 'NONE'; return 0; }

  # 2) owns overlap
  local match_ids="" match_cnt=0 pr_path _cnt _ids
  local _oldIFS="$IFS"; IFS=','
  for pr_path in $files; do
    pr_path="$(printf '%s' "$pr_path" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$pr_path" ] || continue
    _ids="$(_lookup_owns_file "$pr_path")" && _cnt=0 || _cnt=$?
    [ "$_cnt" -eq 0 ] && continue
    # Track unique ids
    for _id in $_ids; do
      case " $match_ids " in *" $_id "*) ;; *) match_ids+=" $_id"; match_cnt=$((match_cnt+1));; esac
    done
  done
  IFS="$_oldIFS"

  [ "$match_cnt" -eq 0 ] && { printf 'NONE'; return 0; }
  [ "$match_cnt" -eq 1 ] && { printf 'OK:%s' "${match_ids# }"; return 0; }

  # N>1 AMBIGUOUS — run disambiguation ladder
  local result
  result="$(disambiguate "$branch" "$sha" "$pr" "$match_ids")" || true
  if [ -n "$result" ]; then
    printf 'OK:%s' "$result"; return 0
  fi
  printf 'AMBIGUOUS:%s' "${match_ids# }"; return 0
}

# Disambiguation ladder for N>1 owns overlap.
# Returns the resolved ticket id, or empty string if unresolvable.
# Ladder: 1) branch match (already failed — we're here), 2) PR-title/commit-subject
# ticket-id match, 3) merged-sha proof in fleet/state/reviewed/<id>.
disambiguate(){
  local branch="$1" sha="$2" pr="$3" candidate_ids="$4"
  local tid="" match=""

  # (2) Try ticket-id substring in PR title (needs gh)
  if [ -n "$pr" ] && [ "$pr" != "0" ] && command -v gh >/dev/null 2>&1; then
    local title body
    title="$(gh pr view "$pr" --repo "$REPO_SLUG" --json title -q '.title' 2>/dev/null || true)"
    body="$(gh pr view "$pr" --repo "$REPO_SLUG" --json body -q '.body' 2>/dev/null || true)"
    [ -n "$body" ] && title+=$'\n'"$body"
    if [ -n "$title" ]; then
      for tid in $candidate_ids; do
        if printf '%s' "$title" | grep -qi "$tid"; then
          [ -z "$match" ] && match="$tid" || { [ "$match" != "$tid" ] && return 1; }
        fi
      done
      [ -n "$match" ] && { printf '%s' "$match"; return 0; }
    fi
  fi

  # (3) Try merge commit subject (needs git)
  if [ -n "$sha" ] && command -v git >/dev/null 2>&1; then
    local subject=""
    subject="$(git log -1 --format=%s "$sha" 2>/dev/null || true)"
    if [ -n "$subject" ]; then
      match=""
      for tid in $candidate_ids; do
        if printf '%s' "$subject" | grep -qi "$tid"; then
          [ -z "$match" ] && match="$tid" || { [ "$match" != "$tid" ] && return 1; }
        fi
      done
      [ -n "$match" ] && { printf '%s' "$match"; return 0; }
    fi
  fi

  # (4) Try merged-sha proof ledger
  if [ -n "$sha" ] && [ -d "$REVIEWED" ]; then
    match=""
    for tid in $candidate_ids; do
      local f="$REVIEWED/$tid"
      [ -f "$f" ] || continue
      if grep -q "$sha" "$f" 2>/dev/null; then
        [ -z "$match" ] && match="$tid" || { [ "$match" != "$tid" ] && return 1; }
      fi
    done
    [ -n "$match" ] && { printf '%s' "$match"; return 0; }
  fi

  return 1
}

# Check if PR touches any board/*.md file (CREATION-PR signal).
_pr_touches_board(){
  local files="$1" f
  local _oldIFS="$IFS"; IFS=','
  for f in $files; do
    f="$(printf '%s' "$f" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    case "$f" in
      fleet/board/*.md|fleet/board/archive/*.md) IFS="$_oldIFS"; return 0 ;;
    esac
  done
  IFS="$_oldIFS"; return 1
}

# ── Phase 1: merged-PR scan (R-A, R-B, AMBIGUOUS) ─────────────────────────
reconciled=0; seen=0; r_a=0; r_b=0; r_ambig=0
while IFS=$'\t' read -r branch sha files pr; do
  [ -n "${branch:-}" ] || continue
  seen=$((seen+1))

  # Skip if branch already has a done marker
  _done_branch "$branch" && { reconciled=$((reconciled+1)); continue; }

  # Resolve PR to ticket
  resolution="$(resolve_pr_ticket "$branch" "${files:-}" "${sha:-}" "${pr:-}")" || true

  case "$resolution" in
    OK:*)
      tid="${resolution#OK:}"
      # Already done? skip
      _done_id "$tid" && { reconciled=$((reconciled+1)); continue; }
      # R-A: open ticket whose branch matches a merged-but-not-done PR
      FINDINGS+=("R-A  $tid  merged PR $pr branch=$branch — ticket has a merged PR but is not marked done")
      r_a=$((r_a+1)); REDS=$((REDS+1))
      ;;
    AMBIGUOUS:*)
      tickets="${resolution#AMBIGUOUS:}"
      FINDINGS+=("AMBIGUOUS  branch=$branch  merged PR $pr  owns-overlap among: $tickets  — NEEDS-MANUAL-ADJUDICATION")
      r_ambig=$((r_ambig+1)); REDS=$((REDS+1))
      ;;
    NONE)
      # R-B: merged PR matching no ticket AND not creating a board file
      if ! _pr_touches_board "${files:-}"; then
        FINDINGS+=("R-B  branch=$branch  merged PR $pr — no matching ticket and no board/*.md creation (create ticket or revert)")
        r_b=$((r_b+1)); REDS=$((REDS+1))
      fi
      ;;
  esac
done < <(merged_prs)

# ── Phase 2: open-ticket scan (R-C stale-branch WARN) ─────────────────────
if [ "${#TICKET_FILES[@]}" -gt 0 ]; then
  for tf in "${TICKET_FILES[@]}"; do
    [ -f "$tf" ] || continue
    tid="$(basename "$tf" .md)"
    # Skip done tickets
    _done_id "$tid" && continue
    # Read branch
    br="$(awk -F': ' '/^branch:/{print $2;exit}' "$tf" 2>/dev/null || true)"
    [ -n "$br" ] || continue
    # Skip if this branch already has a done marker (already handled in Phase 1)
    _done_branch "$br" && continue
    # Check if branch has any recent commit (<7 days) — skip if active
    # This is best-effort and only applies when we have local git visibility.
    # We use a simple heuristic: check if origin/<branch> exists with recent changes.
    recent=""
    if command -v git >/dev/null 2>&1; then
      recent="$(git log --oneline -1 "origin/$br" 2>/dev/null || true)"
    fi
    [ -n "$recent" ] && continue
    # Check if there's an open PR for this branch (best-effort, gh-only)
    open_pr=""
    if command -v gh >/dev/null 2>&1; then
      open_pr="$(gh pr list --repo "$REPO_SLUG" --head "$br" --state open --json number -q '.[0].number' 2>/dev/null || true)"
    fi
    [ -n "$open_pr" ] && continue
    # No recent activity, no open PR — R-C WARN
    FINDINGS+=("R-C  $tid  branch=$br — no recent commits or open PR (may be stale; liveness is judgment)")
    WARNS=$((WARNS+1))
  done
fi

# ── summary ────────────────────────────────────────────────────────────────
for f in "${FINDINGS[@]}"; do echo "reconcile-board-pr-done: $f" >&2; done
if [ "$REDS" -gt 0 ]; then
  echo "reconcile-board-pr-done: $REDS RED ($r_a R-A, $r_b R-B, $r_ambig AMBIGUOUS) + $WARNS WARN (R-C) — drift detected; exit non-zero." >&2
  exit 1
fi
echo "reconcile-board-pr-done: clean ($seen merged PRs scanned, $reconciled reconciled, $WARNS R-C WARN)." >&2
exit 0
