#!/usr/bin/env bash
# done.sh — MANAGER marks a ticket done AFTER its PR merged -> unblocks dependents.
#
# G1 ("a done marker can't lie"): REFUSE to write the marker unless the merge is VERIFIED, and make
# the marker CARRY THE PROOF so G2/G3 can re-check it offline later. A close is accepted when ANY of:
#   (a) --merged-sha <sha> is supplied and is an ancestor of the product origin/master, OR
#   (b) a MERGED PR exists for the ticket's recorded `branch:` (gh), OR
#   (c) a MERGED PR on ANY branch TOUCHED the ticket's `owns:` files (gh; branch-drift tolerant), OR
#   (d) --override "<reason>" is supplied — reason REQUIRED, recorded in the marker + surfaced by
#       preflight so an exception can never hide. This REPLACES the old bare `--no-verify`.
# Marker body (one self-verifying line):
#   <iso>\tmerged:<sha|#pr>\tbranch:<actual-branch>   (verified close)
#   <iso>\toverride:<reason>                           (recorded exception)
#
# Offline/CI hooks: DONE_CHARON_REPO overrides the product-repo path; DONE_MERGED_SRC=<file>
# (TSV lines "<branch>\t<pr#>") injects the merged-PR list instead of gh (see fleet/tests).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
[ -f "$FLEET/gh-cache.sh" ] && source "$FLEET/gh-cache.sh"   # batched merged-PR lookups (O(repos) not O(tickets))
# shellcheck source=/dev/null
source "$FLEET/_lib.sh"   # ticket_repo_slug: the SINGLE `repo:` -> GitHub-slug map (no local copy here)
# NOTE: done.sh redefines canon()/meta() BELOW on purpose — its canon also searches board/archive/.
CHARON_REPO="${DONE_CHARON_REPO:-/home/stack/code/charon}"
REPO_SLUG="$(git -C "$CHARON_REPO" remote get-url origin 2>/dev/null | sed -E 's#(git@[^:]*:|https?://[^/]*/)##; s/\.git$//' || true)"
[ -n "$REPO_SLUG" ] || REPO_SLUG="SLOP-Platform/charon"

canon(){ local w="$1" f b; for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do [ -e "$f" ] || continue
  b="$(basename "$f" .md)"; [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "done.sh: no board ticket matching '$w'" >&2; return 1; }
# best-effort field read: a MISSING file (e.g. an archived-only ticket has no active board/<id>.md)
# must yield "" and exit 0, NOT abort the script under `set -e` before the archive-path fallback runs.
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null || true; }

# merged PR number for head-branch <1>. Fixture hook DONE_MERGED_SRC wins (offline test).
merged_pr_for_branch(){
  local br="$1"; [ -n "$br" ] || return 0
  if [ -n "${DONE_MERGED_SRC:-}" ]; then
    [ -f "$DONE_MERGED_SRC" ] && awk -F'\t' -v b="$br" '$1==b{print $2; exit}' "$DONE_MERGED_SRC"
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 0
  # batched: read from the cached per-repo merged list (ONE gh call/repo) not a per-branch gh call
  if command -v branch_merged_pr >/dev/null 2>&1; then branch_merged_pr "$REPO_SLUG" "$br"
  else gh pr list --repo "$REPO_SLUG" --head "$br" --state merged --json number -q '.[0].number' 2>/dev/null || true; fi
}

# merged PR touching ANY of the ticket's `owns:` files. ZERO `gh --search` calls — the gh-cache
# extracts a "<pr#>\t<path>" index from a SINGLE batched `gh pr list --json number,files` per
# repo (TTL 120s), and this function is a local grep. GitHub's SEARCH API is 30 req/MIN (10x
# tighter than core); a per-owns `gh pr list --search "$path"` was the next-to-burn limit
# (audit: done.sh called it per owns entry in done.gate and retire-done sweeps).
# Offline fixture: GH_MERGED_FILES_FIXTURE=<file> (TSV "<pr#>\t<path>") — used by the
# fail-on-revert test (test_github_limits.sh) to prove ZERO gh calls per owns match.
merged_pr_touching_owns(){
  local owns="$1"; [ -n "$owns" ] || return 0
  # GH_MERGED_FILES_FIXTURE is the test seam; an empty files fixture (or none) returns empty,
  # and we never fall back to the live SEARCH API (the whole point of this rewrite).
  if [ -n "${DONE_MERGED_SRC:-}" ]; then return 0; fi   # legacy branch-only fixture: no files
  command -v gh >/dev/null 2>&1 || return 0
  command -v merged_prs_touching_file >/dev/null 2>&1 || return 0
  local p pr; local IFS=','
  for p in $owns; do
    p="$(printf '%s' "$p" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"; [ -n "$p" ] || continue
    pr="$(merged_prs_touching_file "$REPO_SLUG" "$p" 2>/dev/null || true)"
    [ -n "$pr" ] && { echo "$pr"; return 0; }
  done
  return 0
}

# H2 FIX (2026-07-18 adversarial review): this was `git -C "$CHARON_REPO"` — HARDCODED to the
# PRODUCT repo — while REPO_SLUG below it was already ticket-aware. So for a RIG ticket:
#   done.sh RIG-TICKET --merged-sha <genuine rig sha>   -> exit 3, "NOT an ancestor of
#     Nnyan/charon-private origin/master", having actually checked SLOP-Platform/charon.
#   done.sh RIG-TICKET --merged-sha <product sha>       -> ACCEPTED, printing "verified ...
#     ancestor of Nnyan/charon-private origin/master" and writing merged:<product-sha>.
# The second is how REPO-DECL-CENTRAL's phantom c44e7bda marker was WRITTEN: this is the marker
# WRITER, so a wrong repo here manufactures the lie that every downstream gate then trusts.
# The message named one repo while the check read another — that mismatch WAS the trap.
# VERIFY_REPO is resolved per-ticket below (ticket_repo_path) and printed alongside the slug, so
# the message can only ever name the repo that was actually read.
sha_in_master(){ git -C "$VERIFY_REPO" merge-base --is-ancestor "$1" origin/master 2>/dev/null; }

id_arg="${1:?usage: done.sh <id> [--merged-sha <sha>] [--override \"<reason>\"]}"; shift
merged_sha=""; override=""
while [ $# -gt 0 ]; do
  case "$1" in
    --merged-sha) [ $# -ge 2 ] || { echo "done.sh: --merged-sha needs a <sha>" >&2; exit 2; }; merged_sha="$2"; shift 2;;
    --override)   [ $# -ge 2 ] || { echo "done.sh: --override needs a \"<reason>\" (an exception MUST record WHY)" >&2; exit 2; }; override="$2"; shift 2;;
    --no-verify)  echo "done.sh: --no-verify is REMOVED — use --override \"<reason>\" (records the exception)." >&2; exit 2;;
    *) echo "done.sh: unknown arg: $1" >&2; exit 2;;
  esac
done
id="$(canon "$id_arg")" || exit 2
branch="$(meta branch "$BOARD/$id.md")"; [ -n "$branch" ] || branch="$(meta branch "$BOARD/archive/$id.md")"
owns="$(meta owns "$BOARD/$id.md")";     [ -n "$owns" ]   || owns="$(meta owns "$BOARD/archive/$id.md")"
# repo-aware: read repo field from board, map to GitHub slug, override REPO_SLUG for gh calls
ticket_repo="$(meta repo "$BOARD/$id.md")"
[ -n "$ticket_repo" ] || ticket_repo="$(meta repo "$BOARD/archive/$id.md")"
# The repo PATH used by the ancestry proof and the SLUG used by the gh proofs must come from the
# SAME resolution of the SAME ticket — resolving them separately is what let the printed message
# name one repo while sha_in_master read another (H2).
# DONE_CHARON_REPO (the documented offline/CI hook) still overrides the PRODUCT path: _lib.sh's
# product arm honours VERIFY_MERGED_REPO, so feed it through there rather than re-implementing it.
[ -n "${DONE_CHARON_REPO:-}" ] && export VERIFY_MERGED_REPO="$DONE_CHARON_REPO"
VERIFY_REPO="$CHARON_REPO"
# the map lives ONCE in _lib.sh -> repo-registry.sh (ticket_repo_path/ticket_repo_slug). A copy
# here is exactly the "board-field predicate re-parsed per consumer" drift that broke `parked:`.
if _path="$(ticket_repo_path "$id")" && _slug="$(ticket_repo_slug "$id")"; then
  VERIFY_REPO="$_path"; [ -n "$_slug" ] && REPO_SLUG="$_slug"
else
  # FAIL CLOSED. An unresolvable `repo:` means we cannot say WHICH origin/master a sha would be
  # proven against, and this script WRITES the marker every destructive gate later trusts. Never
  # fall back to the product repo — that is precisely the phantom-marker path.
  echo "done.sh: REFUSED — cannot resolve the target repo for $id (repo: '${ticket_repo:-<none>}')." >&2
  echo "         Add a known repo: key (see fleet/repo-registry.sh) or use --override \"<reason>\"." >&2
  [ -n "$override" ] || exit 3
fi

if [ -n "$override" ]; then
  marker_line="$(date -u +%FT%TZ)"$'\t'"override:$override"
  echo "done.sh: OVERRIDE close for $id — reason recorded: $override" >&2
else
  proof=""
  if [ -n "$merged_sha" ]; then
    # H2: name the repo that was ACTUALLY read (path + slug), not a slug resolved separately.
    if sha_in_master "$merged_sha"; then proof="merged:$merged_sha"
      echo "done.sh: verified $merged_sha is an ancestor of $REPO_SLUG origin/master ($VERIFY_REPO)."
    else
      echo "done.sh: REFUSED — $merged_sha is NOT an ancestor of $REPO_SLUG origin/master ($VERIFY_REPO) (ticket $id)." >&2
      exit 3
    fi
  else
    n="$(merged_pr_for_branch "$branch")"
    if [ -n "$n" ]; then proof="merged:#$n"; echo "done.sh: verified PR #$n (branch $branch) is MERGED."
    else
      n="$(merged_pr_touching_owns "$owns")"
      if [ -n "$n" ]; then proof="merged:#$n"; echo "done.sh: verified MERGED PR #$n touched $id's owns files (branch-drift tolerant)."
      else
        echo "done.sh: REFUSED — no MERGED PR for branch '$branch' and none touching $id's owns files." >&2
        echo "         Merge the PR first, or: done.sh $id --merged-sha <sha> | --override \"<reason>\"." >&2
        exit 3
      fi
    fi
  fi
  marker_line="$(date -u +%FT%TZ)"$'\t'"$proof"$'\t'"branch:$branch"
fi

mkdir -p "$S/done"; printf '%s\n' "$marker_line" > "$S/done/$id"; rm -f "$S/submitted/$id" "$S/claims/$id"
echo "done $id (dependents unblocked)"

# ── scorecard capture (FINAL): a verified-or-overridden close is real ground
# truth (MERGE/pass) -- pairs with the PROVISIONAL row charon-run.sh enqueued
# at run time (same ref, same model) via the grader-safe spool (never writes
# model-scorecard.tsv itself -- see capture/enqueue-capture.sh). Best-effort:
# a missing model-used record (e.g. a hand-closed ticket) skips silently.
CAPTURE_SCRIPT="$FLEET/capture/enqueue-capture.sh"
# Resolve the provisional this ticket's droid run stored. charon-run.sh keys both the
# provisional row AND the model-used record on ${CHARON_JOB_REF:-$LABEL}: fleet-droid.sh
# now sets CHARON_JOB_REF="$id" (bare ticket) so model-used/<id> is the common case, but
# older runs (and any harness that leaves CHARON_JOB_REF unset) key it on the LABEL form
# "<droid>-<id>". Try the bare id first, then fall back to the newest "*-<id>" so a real
# close still finalizes. cap_ref MUST equal the provisional's ref for the daemon to pair.
model_used_file="$FLEET/state/model-used/$id"; cap_ref="$id"
if [ ! -f "$model_used_file" ]; then
  alt="$(ls -1t "$FLEET"/state/model-used/*-"$id" 2>/dev/null | head -1 || true)"
  [ -n "$alt" ] && { model_used_file="$alt"; cap_ref="$(basename "$alt")"; }
fi
if [ -x "$CAPTURE_SCRIPT" ] && [ -f "$model_used_file" ]; then
  model="$(cat "$model_used_file" 2>/dev/null || true)"
  wclass="$(meta work_class "$BOARD/$id.md")"; [ -n "$wclass" ] || wclass="$(meta work_class "$BOARD/archive/$id.md")"
  if [ -n "$model" ]; then
    evid="done.sh verified close: $(printf '%s' "$marker_line" | tr '\t' ' ')"
    if "$CAPTURE_SCRIPT" --model "$model" --claimed-result SUCCESS --ref "$cap_ref" \
      ${wclass:+--work-class "$wclass"} --stage active \
      --actual-verdict MERGE --actual-gate pass --score 100 --evidence "$evid" >/dev/null 2>&1; then
      echo "done.sh: scorecard FINAL enqueued for $id (model=$model, ref=$cap_ref -> MERGE/pass)."
    else
      echo "done.sh: WARN — scorecard FINAL enqueue FAILED for $id (model=$model); outcome NOT recorded." >&2
    fi
  else
    echo "done.sh: WARN — model-used record for $id is empty; scorecard will NOT record this close." >&2
  fi
elif [ -x "$CAPTURE_SCRIPT" ]; then
  # LOUD (was a silent skip): a verified close with no provisional to finalize means this
  # ticket's successful work never reaches the scorecard live lane — the exact "runners not
  # reporting back" failure mode. Surface it so a ref-scheme regression can't silently
  # swallow the outcome again. An OVERRIDE / hand-run ticket legitimately has no provisional.
  if [ -n "$override" ]; then
    echo "done.sh: note — OVERRIDE close for $id; no droid provisional to finalize (scorecard unaffected)." >&2
  else
    echo "done.sh: WARN — verified close for $id but NO model-used provisional found (looked for model-used/$id and *-$id); scorecard will NOT record this outcome. If a droid ran this ticket, its capture ref diverged from done.sh." >&2
  fi
fi
# MECHANIZED CLOSURE: retire the just-completed ticket off the active board (done tickets can never
# accumulate as "active"). retire-done.sh HOLDS any ticket whose marker is not merge-verified.
bash "$FLEET/retire-done.sh" "$id"   # FAST: retire ONLY this ticket, not a full re-verify sweep of all markers
