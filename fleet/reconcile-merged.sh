#!/usr/bin/env bash
# reconcile-merged.sh — AUTO-`done` ON MERGE (fleet build-rig only).
#
# MECHANIZES fragility #2 AND the Wave-A HIGH #2 fix: map each MERGED PR back to its board ticket by
# VERIFIED MERGE / `owns`-file OVERLAP — NOT a bare branch-name string match — and close it through
# the HARDENED done.sh with the discovered `--merged-sha`, so the marker carries REAL proof (never
# the old `--no-verify`). This kills two hazards at once:
#   * branch-name reuse can no longer mis-close a re-created ticket (an old merged PR with the same
#     short branch name — e.g. `feat/tick` — would have string-matched the NEW open ticket), and
#   * a merge whose branch DRIFTED from the board meta (SR-1 case) now still auto-closes via owns.
#
# Per-PR mapping precedence:  1) board `branch:` == PR head-branch, else  2) `owns:` files OVERLAP
# the PR's changed files. Close: done.sh <id> --merged-sha <mergeSha> (proof written into marker).
#
# PERF (PERF-AUDIT.md 2026-07-15): ticket_for_pr() previously re-scanned ALL board+archive files via
# per-file `meta()` awk-spawns for EVERY merged PR — O(PRs×files×awk-spawn). Now: one pre-pass builds
# the branch→id and owns-path→id indexes (a single awk over the file list), and ticket_for_pr is
# O(1) lookup. Done-marker branches are also pre-collected so already-closed PRs short-circuit
# without any board scan at all (mirrors done.sh's single-id fast path).
#
# Network-tolerant: gh missing/offline -> empty list -> clean no-op (never blocks preflight).
#
# TEST HOOK: RECONCILE_MERGED_SRC=<file>, TSV "<branch>\t<mergeSha>\t<f1,f2,..>\t<pr#>" (fields after
# <branch> optional) injects the merged-PR set instead of gh. DONE_CHARON_REPO / RECONCILE_DONE_SH /
# RECONCILE_REPO_SLUG override the product repo, done.sh path, and slug for isolated tests.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; DONE="$FLEET/state/done"; TAB=$'\t'
CHARON_REPO="${DONE_CHARON_REPO:-/home/stack/code/charon}"
REPO_SLUG="${RECONCILE_REPO_SLUG:-$(git -C "$CHARON_REPO" remote get-url origin 2>/dev/null | sed -E 's#(git@[^:]*:|https?://[^/]*/)##; s/\.git$//')}"
[ -n "$REPO_SLUG" ] || REPO_SLUG="SLOP-Platform/charon"
DONE_SH="${RECONCILE_DONE_SH:-$FLEET/done.sh}"

# merged PRs as TSV "branch\tsha\tfiles\tpr". Fixture wins (offline); else gh.
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

# ─── PERF: index-once pre-pass ────────────────────────────────────────────────────────────────
# A SINGLE awk invocation across every board+archive file emits, per ticket, its branch meta and
# its (possibly comma-separated) owns list — populating the two lookup tables below in O(files)
# instead of O(PRs×files) re-scans. `print` semantics preserved exactly: per-file "branch:" value
# is what the old `meta branch` would have returned, and likewise for `owns:`. Files with neither
# field (e.g. malformed) emit nothing and stay invisible to the index — matches old behavior where
# `meta` would have returned empty and the loop iteration's `[ -n "$b" ]` / `[ -n "$ownsf" ]` would
# have skipped the file. Globbing is forced to expand (or empty) via `compgen -G` so a non-existent
# `archive/*.md` does not leave a literal pattern in TICKET_FILES.
BRANCH_INDEX=""     # lines: "<branch><TAB><id>"  (only when board meta has a non-empty branch:)
OWNS_INDEX=""       # lines: "<path><TAB><id>"   (one per comma-split owns entry; duplicated ids allowed)
TICKET_FILES=()
while IFS= read -r -d '' f; do TICKET_FILES+=("$f"); done < <(printf '%s\0' "$BOARD"/*.md "$BOARD"/archive/*.md)
# Pipe all file paths NUL-separated on stdin. A single awk reads each file once and prints two
# marker lines per ticket: "B\t<id>\t<branch>" and "O\t<id>\t<owns>". We then split into the two
# index strings in pure shell.
_idx_rows="$(mktemp)"
if [ "${#TICKET_FILES[@]}" -gt 0 ]; then
  # One awk reads each path as a NUL-delimited record off stdin; for each file it then resets RS to
  # "\n" and uses getline to walk the file's lines. This is ONE awk process (vs the old code's
  # ~2 × PRs × files awk-spawns) and preserves identical semantics: only `branch: <value>` and
  # `owns: <value>` lines are extracted; empty/missing fields emit nothing (same as the old
  # `[ -n "$b" ] && ... || continue` and `[ -n "$ownsf" ] || continue` skips).
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
      # val is a comma-separated owns list; split on commas into one <path><TAB><id> line each.
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

# ─── PERF: done-branch short-circuit ─────────────────────────────────────────────────────────
# Pre-build a set of branches that ALREADY have a verified close marker. Any merged PR whose
# branch is in this set is skipped before ticket_for_pr runs — mirrors done.sh's single-id fast
# path. Marker bodies are `<iso>\t<proof>\tbranch:<actual-branch>` (or `<iso>\t<proof>` without
# branch:), so we extract the branch: token. The id-side check `[ -e "$DONE/$id" ]` is also
# pre-collected into a set so a second lookup is O(1).
DONE_BRANCHES=""   # lines: "<branch>"
DONE_IDS=""        # lines: "<id>"
if [ -d "$DONE" ]; then
  for m in "$DONE"/*; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"
    DONE_IDS+="${id}"$'\n'
    # Extract branch: from the marker line (may be absent on override-only markers).
    br="$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i ~ /^branch:/){sub(/^branch:/,"",$i);print $i;exit}}' "$m" 2>/dev/null || true)"
    [ -n "$br" ] && DONE_BRANCHES+="${br}"$'\n'
  done
fi

# map a merged PR (head-branch, changed-files) -> board ticket id. Precedence:
#   1) CERTAIN: board `branch:` == PR head-branch (an exact, unique meta link) -> close.
#   2) owns-file overlap, but ONLY when EXACTLY ONE board ticket overlaps (unambiguous) -> close.
# HIGH #2 FIX (2026-07-10 adversarial review): when a drifted PR's changed file is owned by MORE THAN
# ONE ticket (common under WCI — proxy.py/config.py/gateway.py are each owned by 2-5 tickets), the old
# "first glob match wins" auto-closed the ALPHABETICALLY-FIRST owner — the WRONG ticket — writing a
# real `merged:<sha>` onto un-landed work (which then survives every downstream gate). owns-overlap is
# therefore only trusted when it is UNAMBIGUOUS; an ambiguous (>1-owner) overlap is SURFACED for manual
# resolution and NEVER auto-closed. Empty (no map / ambiguous) -> return 1.
#
# PERF: was O(board+archive files) per call (each iterating awk-spawn meta); now O(1) per call via
# pre-built BRANCH_INDEX / OWNS_INDEX lookups. Semantics identical (same precedence, same ambiguity
# refusal, same stderr wording when ambiguous).
ticket_for_pr(){
  local want_branch="$1" pr_files="$2"
  # 1) exact branch match
  if [ -n "$want_branch" ]; then
    local line id
    while IFS=$'\t' read -r line id; do
      [ "$line" = "$want_branch" ] || continue
      printf '%s' "$id"; return 0
    done <<< "$BRANCH_INDEX"
  fi
  [ -n "$pr_files" ] || return 1
  # 2) owns-overlap. For each PR file, collect matching ids; reject if a path maps to >1 ticket
  # OR if the union contains more than one id.
  local id matches="" cnt=0
  local pr_path
  local _oldIFS="$IFS"; IFS=','
  for pr_path in $pr_files; do
    pr_path="$(printf '%s' "$pr_path" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$pr_path" ] || continue
    # O(1) lookup: for this single path, find every id that owns it. If multiple ids own it, the
    # path alone is enough to mark this PR ambiguous (same rule as the old loop's final >1 check).
    local path_ids="" path_cnt=0
    while IFS=$'\t' read -r line id; do
      [ "$line" = "$pr_path" ] || continue
      path_ids+=" $id"; path_cnt=$((path_cnt+1))
    done <<< "$OWNS_INDEX"
    if [ "$path_cnt" -gt 1 ]; then
      IFS="$_oldIFS"
      echo "reconcile-merged: AMBIGUOUS — merged PR (branch=$want_branch) file $pr_path is owned by $path_cnt tickets:${path_ids} — NOT auto-closing (a shared owned file cannot prove WHICH ticket landed; resolve by hand)." >&2
      return 1
    fi
    # path_cnt is 0 or 1. If 1, record the id; if already in `matches`, no change; else add.
    [ "$path_cnt" -eq 1 ] || continue
    local _id="${path_ids# }"
    case " $matches " in *" $_id "*) ;; *) matches="$matches $_id"; cnt=$((cnt+1));; esac
  done
  IFS="$_oldIFS"
  if [ "$cnt" -eq 1 ]; then
    printf '%s' "${matches# }"; return 0
  elif [ "$cnt" -gt 1 ]; then
    echo "reconcile-merged: AMBIGUOUS — merged PR (branch=$want_branch) owns-overlaps $cnt tickets:${matches} — NOT auto-closing (a shared owned file cannot prove WHICH ticket landed; resolve by hand)." >&2
  fi
  return 1
}

# PERF: O(1) is-done checks (replaces `[ -e "$DONE/$id" ]` per match; id is already in the set).
_done_id(){ grep -Fxq -- "$1" <<< "$DONE_IDS"; }

mkdir -p "$DONE"
reconciled=0; seen=0
while IFS="$TAB" read -r branch sha files pr; do
  [ -n "${branch:-}" ] || continue
  seen=$((seen+1))
  # PERF: short-circuit when the PR's branch is already covered by a done marker (no board scan).
  if [ -n "$branch" ] && grep -Fxq -- "$branch" <<< "$DONE_BRANCHES"; then continue; fi
  id="$(ticket_for_pr "$branch" "${files:-}")" || continue   # no board ticket maps -> ignore
  _done_id "$id" && continue                                  # already done -> idempotent no-op
  # CREATION-PR GUARD (root fix, 2026-07-23): a merged PR that ADDED this ticket's OWN board file is
  # the ticket's CREATION, not its completion — a ticket is not "done" because it was created. Its
  # `branch:`/`owns:` will always match its own creation PR, so without this guard reconcile
  # false-closes brand-new tickets the moment their creation PR lands (bit WORKLOOP-INTEGRITY-STACK-
  # SPIKE then BLAST-TIER-ENFORCEMENT-DESIGN). Detect via the merge adding fleet/board/<id>.md. Only
  # checkable with a merge sha; the no-sha branch-list path below is unaffected (it needs a real
  # completion PR). One `git show` per would-close PR (rare) — no hot-path cost.
  # CREATION-PR GUARD (root fix, 2026-07-23): the gh per-PR `files` list is authoritative regardless
  # of merge-commit shape (git show --diff-filter=A is EMPTY on a merge commit, and a just-merged
  # squash may report no oid — both broke sha-based detection). A CREATION PR touches the ticket's
  # OWN board file but delivers NONE of its `owns:` (the deliverable); a COMPLETION PR delivers owns.
  # Skip a would-close whose files touch fleet/board/<id>.md yet include none of the ticket's owns:.
  if [ -n "${files:-}" ] && printf '%s' "$files" | tr ',' '\n' | grep -qx "fleet/board/$id.md"; then
    _bf="$BOARD/$id.md"; [ -e "$_bf" ] || _bf="$BOARD/archive/$id.md"
    _owns="$(awk -F: '/^owns:/{sub(/^owns:[[:space:]]*/,"");print;exit}' "$_bf" 2>/dev/null)"
    _delivered=""
    if [ -n "$_owns" ]; then
      _oldIFS="$IFS"; IFS=','
      for _op in $_owns; do
        _op="$(printf '%s' "$_op" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [ -n "$_op" ] || continue
        if printf '%s' "$files" | tr ',' '\n' | grep -qx "$_op"; then _delivered=1; break; fi
      done
      IFS="$_oldIFS"
    fi
    if [ -z "$_delivered" ]; then
      echo "reconcile-merged: merged PR (branch=$branch) touched fleet/board/$id.md but delivered NONE of $id's owns: — CREATION PR, NOT auto-closing (created != done)." >&2
      continue
    fi
  fi
  echo "reconcile-merged: merged PR (branch=$branch) maps to $id — auto-closing WITH proof."
  rc=0
  if [ -n "${sha:-}" ]; then
    bash "$DONE_SH" "$id" --merged-sha "$sha" || rc=$?
  else
    # no merge sha available -> hand done.sh a proven merged-branch list so it writes merged:#pr proof.
    tmpsrc="$(mktemp)"; printf '%s\t%s\n' "$branch" "${pr:-0}" > "$tmpsrc"
    DONE_MERGED_SRC="$tmpsrc" bash "$DONE_SH" "$id" || rc=$?
    rm -f "$tmpsrc"
  fi
  if [ "$rc" -eq 0 ]; then reconciled=$((reconciled+1))
  else echo "reconcile-merged: WARNING — done.sh failed for $id (rc=$rc; see above)." >&2; fi
done < <(merged_prs)

if [ "$reconciled" -gt 0 ]; then
  echo "reconcile-merged: auto-closed $reconciled merged-but-open ticket(s) with recorded proof."
else
  echo "reconcile-merged: clean (no merged ticket left open; scanned $seen merged PR(s))."
fi
exit 0
