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
# ── AUTO-DONE-ON-MERGE-MISS (2026-08-01): THE ROOT CAUSE THIS FILE HAD ────────────────────────
# This script IS the wired auto-done mechanism (preflight.sh `scan` calls it first, every scan) —
# it was never "unbuilt". It was REPO-BLIND. `REPO_SLUG` was resolved ONCE from the PRODUCT
# checkout's origin remote (SLOP-Platform/charon) and the ONE merged-PR query only ever asked THAT
# repo. The board is MULTI-REPO (`repo:` field; 196 rig tickets vs 75 product tickets at the time
# of this fix), so every ticket with `repo: charon-private` was structurally unreachable: its PR
# merges in Nnyan/charon-private, a repo this script never queried, so no done marker could ever
# be written for it. MEASURED: LEDGER-NO-EVIDENCE-NO-VERDICT merged as Nnyan/charon-private#358 at
# 2026-08-01T19:31:39Z, no marker appeared, and GRADE-MODEL-PROVIDER-PAIR (which depends_on it) was
# refused admission by claim.sh while a droid tab idled. The marker had to be hand-written.
# FIX: query EVERY repo the board actually references (derived from the `repo:` keys through
# _lib.sh's ticket_repo_slug — the SSOT map, NOT a fourth private copy), and SCOPE the PR->ticket
# match to the repo the PR came from, so a product PR can never close a rig ticket that happens to
# share a branch name (the mirror hazard the multi-repo query would otherwise introduce).
#
# ── REST, NOT GraphQL ─────────────────────────────────────────────────────────────────────────
# The merged-PR listing was `gh pr list --json ...`, which goes through GitHub's GraphQL API.
# That quota was fully EXHAUSTED on 2026-08-01, and an exhausted quota made this script print
# "clean (no merged ticket left open)" — indistinguishable from genuinely nothing to do. Both
# halves are fixed: the listing is now `gh api repos/<slug>/pulls` (REST core, a far larger and
# separately-metered quota), and a fetch FAILURE is now LOUD and non-zero instead of "clean".
#
# ── FAIL CLOSED ───────────────────────────────────────────────────────────────────────────────
# A false `done` marker RETIRES a ticket whose work may not exist, and every downstream gate then
# trusts it. So merge state must be PROVEN, never assumed:
#   * a repo whose listing could not be fetched (network / rate-limit / auth) closes NOTHING and is
#     reported LOUDLY with a non-zero exit — a late marker is recoverable, a false one is not;
#   * immediately before any close, the specific PR is re-confirmed via REST
#     `gh api repos/<slug>/pulls/<n>` -> `.merged == true` AND a non-empty `.merged_at`. If that
#     call fails or does not say merged, we REFUSE that ticket and keep going.
# `gh` missing entirely is still a clean no-op (offline rig, nothing to reconcile) — that path
# cannot produce a wrong marker, only no marker.
#
# ── COST ──────────────────────────────────────────────────────────────────────────────────────
# Steady state is ONE REST call per referenced repo (2 today). The PR `files[]` list is NOT in the
# REST listing response, so it is fetched LAZILY per PR — only when the branch match missed (the
# owns-overlap fallback) or when a close is imminent (the creation-PR guard). Already-done branches
# short-circuit before either, so a quiet scan pays zero per-PR calls.
#
# TEST HOOK: RECONCILE_MERGED_SRC=<file>, TSV "<branch>\t<mergeSha>\t<f1,f2,..>\t<pr#>\t<slug>"
# (every field after <branch> optional) injects the merged-PR set instead of gh. A row with an
# EMPTY <slug> is repo-UNSCOPED (back-compat: pre-multi-repo fixtures match any ticket); a row that
# names a slug is scoped exactly like the live REST path. DONE_CHARON_REPO / RECONCILE_DONE_SH
# override the product repo and done.sh path; RECONCILE_REPO_SLUG PINS the queried repo set to a
# single slug for isolated tests.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; DONE="$FLEET/state/done"; TAB=$'\t'
# NOTE: the product-repo path is NO LONGER read here. It existed only to derive the single hardcoded
# REPO_SLUG this fix removes; done.sh reads DONE_CHARON_REPO straight from the environment, so
# passing it through a variable here would just be a second, drift-prone copy of the same override.
DONE_SH="${RECONCILE_DONE_SH:-$FLEET/done.sh}"
# ticket_repo_slug() — the SSOT `repo:`-key -> GitHub-slug map (_lib.sh -> repo-registry.sh). We
# source it rather than re-deriving a slug here: a private copy of that map is exactly the drift
# that produced the phantom REPO-DECL-CENTRAL marker (see _lib.sh H1/H2). _lib.sh requires FLEET.
# shellcheck source=/dev/null
[ -f "$FLEET/_lib.sh" ] && . "$FLEET/_lib.sh"
# How many recently-updated closed PRs to inspect per repo. The REST list endpoint has no
# "merged" filter, so closed-unmerged PRs share the window; 100 (the API max page size) is one
# call and covers far more than one preflight interval's worth of merges. Anything older than the
# window has necessarily already been reconciled by an earlier scan.
RECONCILE_PR_WINDOW="${RECONCILE_PR_WINDOW:-100}"

# FETCH_FAIL_FLAG — records every repo whose merge state could NOT be determined. It is a FILE,
# not a variable, on purpose: the main loop consumes merged_prs() through process substitution
# (`done < <(merged_prs)`), which runs it in a SUBSHELL, so a variable set in there would be
# discarded and the failure would silently become "clean" — the exact fail-open this fix exists to
# remove. Drives the loud, non-zero, explicitly NOT-"clean" exit at the bottom.
FETCH_FAIL_FLAG="$(mktemp)"
trap 'rm -f "$FETCH_FAIL_FLAG"' EXIT

# _rest_merged_for_slug <slug> — merged PRs in <slug> as TSV "branch\tsha\t\tpr\tslug".
# The files column is deliberately EMPTY: REST's list endpoint does not carry files[], and paying
# a per-PR /files call for every merged PR just to satisfy a fallback almost nothing reaches would
# be far more expensive than the GraphQL call this replaces. pr_files() fetches it on demand.
# rc 1 = merge state UNDETERMINED for this repo -> caller must close nothing for it.
_rest_merged_for_slug(){
  local slug="$1" out rc=0
  out="$(gh api "repos/$slug/pulls?state=closed&per_page=$RECONCILE_PR_WINDOW&sort=updated&direction=desc" \
         --jq '.[] | select(.merged_at != null) | [.head.ref, (.merge_commit_sha // ""), "", (.number|tostring)] | @tsv' \
         2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "reconcile-merged: FAIL-CLOSED — could NOT determine merge state for $slug (gh api rc=$rc)." >&2
    echo "                  NOTHING will be auto-closed for that repo's tickets this scan. Detail: $(printf '%s' "$out" | head -2 | tr '\n' ' ')" >&2
    return 1
  fi
  # append the slug column so the main loop can scope the PR->ticket match to the source repo
  printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | sed "s|\$|${TAB}${slug}|" || true
  return 0
}

# merged PRs as TSV "branch\tsha\tfiles\tpr\tslug". Fixture wins (offline); else REST, per repo.
merged_prs(){
  if [ -n "${RECONCILE_MERGED_SRC:-}" ]; then
    [ -f "$RECONCILE_MERGED_SRC" ] && grep -v '^[[:space:]]*$' "$RECONCILE_MERGED_SRC" || true
    return 0
  fi
  # A missing gh is a clean no-op, not a failure: it can only ever produce NO marker, never a
  # wrong one, and preflight must still run on a box without the CLI.
  command -v gh >/dev/null 2>&1 || return 0
  local slug
  for slug in $(target_slugs); do
    _rest_merged_for_slug "$slug" || printf '%s\n' "$slug" >> "$FETCH_FAIL_FLAG"
  done
}

# pr_files <slug> <pr> — the PR's changed paths, comma-joined. LAZY (see COST note above).
# Empty output on any failure: an unknown file list must never be mistaken for "changed nothing",
# and both consumers (owns-overlap, creation-PR guard) already treat empty as "cannot conclude".
pr_files(){
  local slug="$1" pr="$2"
  [ -n "$slug" ] && [ -n "$pr" ] || return 0
  command -v gh >/dev/null 2>&1 || return 0
  gh api "repos/$slug/pulls/$pr/files?per_page=100" --jq '[.[].filename] | join(",")' 2>/dev/null || true
}

# confirm_merged <slug> <pr> — RE-PROVE this exact PR is merged, from the FORGE, right before we
# write a marker. REST per the requirement (`gh api .../pulls/<n>` -> .merged/.merged_at): the
# listing above is a snapshot that could be stale or (in fixture mode) unverified, and this is the
# last gate before a marker that every downstream gate will trust. rc 1 = REFUSE this ticket.
# A fixture row with no slug/pr has nothing to confirm against and is left to done.sh's own proof.
confirm_merged(){
  local slug="$1" pr="$2" out rc=0 m at
  [ -n "$slug" ] && [ -n "$pr" ] || return 0
  command -v gh >/dev/null 2>&1 || return 0
  out="$(gh api "repos/$slug/pulls/$pr" --jq '[(.merged|tostring), (.merged_at // "")] | @tsv' 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "reconcile-merged: FAIL-CLOSED — could NOT confirm merge state of $slug#$pr (gh api rc=$rc); REFUSING to write a done marker for it. Detail: $(printf '%s' "$out" | head -2 | tr '\n' ' ')" >&2
    return 1
  fi
  IFS="$TAB" read -r m at <<< "$out"
  if [ "${m:-}" = true ] && [ -n "${at:-}" ]; then return 0; fi
  echo "reconcile-merged: FAIL-CLOSED — $slug#$pr is NOT merged per REST (.merged=${m:-?} .merged_at=${at:-<empty>}); REFUSING to write a done marker." >&2
  return 1
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
# REPO_KEY_INDEX carries the SAME pre-pass's third field so repo-scoping costs no extra file walk.
# Tickets with NO `repo:` emit no row and resolve to the default key "" (== the product), exactly
# as repo-registry.sh's documented back-compat says they must.
REPO_KEY_INDEX=""   # lines: "<id><TAB><repo-key>"  (only when board meta has a non-empty repo:)
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
      branch = ""; owns = ""; repo = ""
      RS_SAVED = RS; RS = "\n"
      while ((getline line < file) > 0) {
        if      (line ~ /^branch:[[:space:]]*/) { sub(/^branch:[[:space:]]*/, "", line); branch = line }
        else if (line ~ /^owns:[[:space:]]*/)   { sub(/^owns:[[:space:]]*/, "", line);   owns   = line }
        else if (line ~ /^repo:[[:space:]]*/)   { sub(/^repo:[[:space:]]*/, "", line);   repo   = line }
      }
      RS = RS_SAVED
      close(file)
      if (branch != "") print "B\t" id "\t" branch
      if (owns   != "") print "O\t" id "\t" owns
      if (repo   != "") print "R\t" id "\t" repo
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
    R) REPO_KEY_INDEX+="${id}"$'\t'"${val}"$'\n' ;;
  esac
done < "$_idx_rows"
rm -f "$_idx_rows"

# ─── MULTI-REPO: key -> slug, memoised ONCE PER DISTINCT KEY ─────────────────────────────────
# ticket_repo_slug() is the SSOT lookup but it re-reads the ticket's board file, so calling it per
# ticket would be ~270 subshells and would blow the reconcile-merged.test.sh (g) CPU budget that
# exists precisely to catch a re-introduced per-ticket board walk. The `repo:` KEY is all that
# determines the slug, and there are 2-3 distinct keys on the whole board — so resolve once per
# distinct KEY (using any one ticket carrying it as the probe) and memoise. Still zero private
# copies of the map: every entry comes out of ticket_repo_slug.
KEY_SLUG=""   # lines: "<repo-key><TAB><slug>"; the "" key is seeded first (the product default)
_memo_slug(){ local k="$1" kk s; while IFS=$'\t' read -r kk s; do
                [ "$kk" = "$k" ] && { printf '%s' "$s"; return 0; }; done <<< "$KEY_SLUG"; return 1; }
if command -v ticket_repo_slug >/dev/null 2>&1; then
  # The default (no `repo:` field) key. ticket_repo_slug "" is _vm_resolve's documented no-arg
  # back-compat path and yields the PRODUCT slug — the behaviour every pre-multi-repo ticket had.
  KEY_SLUG+=""$'\t'"$(ticket_repo_slug "" 2>/dev/null || true)"$'\n'
  while IFS=$'\t' read -r _kid _kkey; do
    [ -n "${_kkey:-}" ] || continue
    _memo_slug "$_kkey" >/dev/null && continue           # already resolved this key
    # rc 1 = key unknown to repo-registry.sh. Memoise the EMPTY slug: an unresolvable repo is a
    # ticket we must never auto-close (fail closed), and caching that fact keeps it to one probe.
    KEY_SLUG+="${_kkey}"$'\t'"$(ticket_repo_slug "$_kid" 2>/dev/null || true)"$'\n'
  done <<< "$REPO_KEY_INDEX"
fi

# slug_for_id <id> — the GitHub slug this ticket's PR must have merged in. Empty = unresolvable.
slug_for_id(){
  local want="$1" i k
  while IFS=$'\t' read -r i k; do
    [ "$i" = "$want" ] || continue
    _memo_slug "$k"; return
  done <<< "$REPO_KEY_INDEX"
  _memo_slug ""            # no `repo:` field -> the default/product slug
}

# target_slugs — every repo the BOARD actually references, i.e. exactly the repos that can contain
# a merge we care about. Derived from the memo, so adding a repo to repo-registry.sh and using it
# in a `repo:` field is all it takes for merges there to reconcile — nothing to register here.
# RECONCILE_REPO_SLUG pins the set to one slug (isolated tests).
target_slugs(){
  if [ -n "${RECONCILE_REPO_SLUG:-}" ]; then printf '%s\n' "$RECONCILE_REPO_SLUG"; return 0; fi
  printf '%s' "$KEY_SLUG" | cut -f2 | grep -v '^[[:space:]]*$' | sort -u
}

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
#
# REPO SCOPING (AUTO-DONE-ON-MERGE-MISS, 2026-08-01): a THIRD argument, the slug the PR merged in.
# Now that we query more than one repo, `branch:`/`owns:` alone stop being unique keys — the rig
# and the product both have `fix/*` branches and both have a `fleet/`-shaped tree in their
# histories, so an unscoped match would let a PRODUCT merge write a real `merged:<sha>` onto a RIG
# ticket that had not landed. Every candidate must therefore belong to the repo the PR came from.
# An EMPTY slug argument disables scoping (pre-multi-repo RECONCILE_MERGED_SRC fixtures).
# A candidate whose OWN slug is unresolvable is REFUSED, not waved through: an unknown `repo:` key
# means we cannot say which origin/master would prove it, which is the fail-closed rule done.sh
# already applies at the marker-writing end.
_slug_matches(){                       # <candidate-id> ; uses $PR_SLUG from the enclosing scope
  local id="$1" tslug
  [ -n "${PR_SLUG:-}" ] || return 0    # unscoped fixture row -> legacy behaviour
  tslug="$(slug_for_id "$id")"
  [ -n "$tslug" ] || { echo "reconcile-merged: $id has an UNRESOLVABLE repo: key — NOT auto-closing (cannot prove which repo's master a merge would be in)." >&2; return 1; }
  [ "$tslug" = "$PR_SLUG" ]
}
ticket_for_pr(){
  # NOTE: named pr_paths, NOT pr_files — pr_files is now a FUNCTION (the lazy REST fetch), and a
  # local of the same name reads as a shadow to anyone editing this block.
  local want_branch="$1" pr_paths="$2"
  PR_SLUG="${3:-}"
  # 1) exact branch match
  if [ -n "$want_branch" ]; then
    local line id
    while IFS=$'\t' read -r line id; do
      [ "$line" = "$want_branch" ] || continue
      _slug_matches "$id" || continue          # branch name collides ACROSS repos -> not this one
      printf '%s' "$id"; return 0
    done <<< "$BRANCH_INDEX"
  fi
  [ -n "$pr_paths" ] || return 1
  # 2) owns-overlap. For each PR file, collect matching ids; reject if a path maps to >1 ticket
  # OR if the union contains more than one id.
  local id matches="" cnt=0
  local pr_path
  local _oldIFS="$IFS"; IFS=','
  for pr_path in $pr_paths; do
    pr_path="$(printf '%s' "$pr_path" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$pr_path" ] || continue
    # O(1) lookup: for this single path, find every id that owns it. If multiple ids own it, the
    # path alone is enough to mark this PR ambiguous (same rule as the old loop's final >1 check).
    local path_ids="" path_cnt=0
    while IFS=$'\t' read -r line id; do
      [ "$line" = "$pr_path" ] || continue
      # Scope BEFORE counting: an owner in a DIFFERENT repo is not a competing claim on this
      # merge, so it must not be able to manufacture a false AMBIGUOUS and suppress a real close.
      _slug_matches "$id" || continue
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
# FIELD SPLITTING: the rows are read on a UNIT-SEPARATOR (\037), not on the TAB they are written
# with. TAB is an IFS *whitespace* character, so `IFS=$'\t' read` COLLAPSES a run of tabs into one
# delimiter and silently drops empty fields. The REST listing emits an EMPTY files column (files[]
# is not in the list response — pr_files fetches it lazily), so reading on TAB shifted every later
# field left: `pr` received the slug and `slug` came back empty, which quietly disabled BOTH
# fail-closed guards below (confirm_merged and pr_files no-op on an empty slug/pr) while still
# LOOKING like it worked. \037 is not IFS whitespace, so empty fields survive; it also cannot occur
# in a branch name or a path, so converting the tabs is lossless for the fixture rows too.
while IFS=$'\037' read -r branch sha files pr slug; do
  [ -n "${branch:-}" ] || continue
  seen=$((seen+1))
  # PERF: short-circuit when the PR's branch is already covered by a done marker (no board scan).
  if [ -n "$branch" ] && grep -Fxq -- "$branch" <<< "$DONE_BRANCHES"; then continue; fi
  # LAZY FILES (REST): the listing carries no files[]. Try the CERTAIN branch match first — it
  # needs none — and only pay a /files call when that misses and the owns-overlap fallback is the
  # last chance to identify the ticket. On a quiet scan this is never reached.
  if ! id="$(ticket_for_pr "$branch" "${files:-}" "${slug:-}")"; then
    [ -z "${files:-}" ] || continue                           # already had files and still no map
    files="$(pr_files "${slug:-}" "${pr:-}")"
    [ -n "$files" ] || continue
    id="$(ticket_for_pr "$branch" "$files" "${slug:-}")" || continue
  fi
  _done_id "$id" && continue                                  # already done -> idempotent no-op
  # The creation-PR guard below needs the file list too, and a close is now imminent, so this is
  # the point where paying for it is justified. Skipping the guard when files are unavailable
  # would re-open the false-close-on-creation hole, so an unfetchable list REFUSES the close.
  if [ -z "${files:-}" ]; then
    files="$(pr_files "${slug:-}" "${pr:-}")"
    if [ -z "$files" ] && [ -n "${slug:-}" ]; then
      echo "reconcile-merged: FAIL-CLOSED — could not read the changed-file list for $slug#${pr:-?} ($id); the creation-PR guard cannot run, so NOT auto-closing." >&2
      continue
    fi
  fi
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
  # LAST GATE BEFORE THE MARKER: re-prove THIS PR is merged, from the forge, over REST. Everything
  # above came from a list snapshot; the marker written below is what every downstream gate (and
  # retire-done's destructive sweep) will treat as ground truth. If the forge cannot confirm it,
  # this ticket is skipped — never closed on assumption.
  confirm_merged "${slug:-}" "${pr:-}" || continue
  echo "reconcile-merged: merged PR (branch=$branch${slug:+ in $slug}) maps to $id — auto-closing WITH proof."
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
done < <(merged_prs | tr "$TAB" '\037')

if [ "$reconciled" -gt 0 ]; then
  echo "reconcile-merged: auto-closed $reconciled merged-but-open ticket(s) with recorded proof."
fi
# FAIL CLOSED, LOUDLY. A repo we could not query may well contain merges whose tickets are still
# sitting in `submitted` blocking their dependents — which is EXACTLY the defect this script is
# the safety-net for. Reporting "clean" in that state is the fail-open that let an exhausted
# GraphQL quota look like a quiet board. Say the word UNDETERMINED and exit non-zero.
if [ -s "$FETCH_FAIL_FLAG" ]; then
  echo "reconcile-merged: NOT CLEAN — merge state UNDETERMINED for $(tr '\n' ' ' < "$FETCH_FAIL_FLAG")" >&2
  echo "                  Tickets in those repos were NOT auto-closed and may still be blocking dependents." >&2
  echo "                  Re-run after fixing gh auth / rate limit: bash fleet/reconcile-merged.sh" >&2
  exit 1
fi
if [ "$reconciled" -eq 0 ]; then
  echo "reconcile-merged: clean (no merged ticket left open; scanned $seen merged PR(s) across $(target_slugs | tr '\n' ' '))."
fi
exit 0
