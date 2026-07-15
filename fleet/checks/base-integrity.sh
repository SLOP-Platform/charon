#!/usr/bin/env bash
# base-integrity.sh — LAUNCH-TIME GATE (mechanical). FAIL LOUD if a ticket is about to be built on a
# base branch that does NOT yet contain its declared prerequisites.
#
# THE BUG THIS CATCHES (2026-07-12): origin/master went 17 commits STALE behind an unpushed integration
# branch. Tabs created worktrees off base=origin/master, but that base was MISSING the depends_on
# merges that had only landed on the (off-origin) integration branch -> PRs #56/#57 were base-INVALID
# (built without their prerequisites). NOTHING gated base-integrity at launch. This does.
#
# WHAT IT ASSERTS, for a ticket with `depends_on:`:
#   For each dep D, resolve D's MERGED sha from its done-marker (fleet/state/done/<D>). done.sh writes
#   either `merged:<sha>` (hex) OR a PR-ONLY `merged:#<N>` (no local sha). For a hex sha we require
#   `git merge-base --is-ancestor <sha> <BASE>` — the base actually CONTAINS the prereq. For a PR-only
#   marker we resolve the PR's merge-commit sha (gh) and run the SAME ancestry check.
#   INVARIANT — unverifiable => NOT satisfied: a dep whose containment cannot be proven by a concrete sha
#   (PR sha unresolvable, or a malformed proof) is a MISSING prereq -> RED, EXCEPT when BASE==origin/master,
#   where a merged dep is contained by definition (advisory). A proof sha NOT contained in the base is RED.
#   (This closes a false-GREEN: a `merged:#<N>` PR-only marker used to WARN-and-count-satisfied even when
#   BASE != origin/master, silently admitting an unproven prereq.)
# The base is fetched first (best-effort), so a STALE local origin/master ref cannot false-GREEN.
# It ALSO advises (non-fatal) when an off-origin integration branch is ahead of origin/master
# ("don't hoard integration off-origin").
#
# Exit 0 = GREEN (base contains every declared prereq — safe to launch this ticket).
# Exit 1 = RED  (base is stale / missing a prereq — REFUSE to launch; the build would be base-invalid).
# Exit 2 = usage / cannot resolve the ticket.
#
# Usage:  base-integrity.sh <ticket-id> [--base <ref>]
#   <ticket-id>   board ticket (case-insensitive; canonicalized via _lib.sh canon).
#   --base <ref>  base ref to verify against (default: the ticket's `base:` meta, else origin/master).
#
# Reuse (cite): sources fleet/_lib.sh for `canon` (id->board basename) and `_vm_repo`/`_vm_refresh`
# (product-repo path + single best-effort fetch — same machinery verify_merged uses). The ancestry
# primitive is the same `git merge-base --is-ancestor` that done.sh:sha_in_master / _lib.sh:_vm_sha_in_master
# use; here it is generalized to an arbitrary base ref (an integration branch may be the base, not only
# origin/master), which is why we resolve the dep sha explicitly rather than reuse the boolean verify_merged.
#
# Offline/hermetic: set BASE_INTEGRITY_OFFLINE=1 to skip the network fetch (used by the test).
# Product-repo path override: VERIFY_MERGED_REPO (shared with verify_merged). FLEET is derived from
# this script's location.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$FLEET/_lib.sh"

id_arg="${1:-}"
[ -n "$id_arg" ] || { echo "usage: base-integrity.sh <ticket-id> [--base <ref>]" >&2; exit 2; }
shift
base_override=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || { echo "base-integrity.sh: --base needs a <ref>" >&2; exit 2; }; base_override="$2"; shift 2;;
    *) echo "base-integrity.sh: unknown arg: $1" >&2; exit 2;;
  esac
done

id="$(canon "$id_arg")" || exit 2
bfile="$FLEET/board/$id.md"
[ -f "$bfile" ] || bfile="$FLEET/board/archive/$id.md"
[ -f "$bfile" ] || { echo "base-integrity.sh: no board file for $id" >&2; exit 2; }

repo="$(_vm_repo)"
[ -d "$repo/.git" ] || [ -f "$repo/.git" ] || { echo "base-integrity.sh: product repo not found at $repo (set VERIFY_MERGED_REPO)" >&2; exit 2; }

# Resolve the base ref: --base flag > ticket `base:` meta > origin/master.
base_ref="$base_override"
[ -n "$base_ref" ] || base_ref="$(_vm_meta base "$bfile")"
[ -n "$base_ref" ] || base_ref="origin/master"

# FETCH FIRST — a stale local origin/master ref is the whole failure mode. Best-effort, offline-skippable.
if [ -z "${BASE_INTEGRITY_OFFLINE:-}" ]; then
  _vm_refresh
fi

# Base ref must resolve to a real commit in the product repo, else we cannot verify containment.
if ! git -C "$repo" rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null 2>&1; then
  echo "base-integrity.sh: RED — base ref '$base_ref' does not resolve in $repo (cannot verify prerequisites)." >&2
  exit 1
fi

# dep_proof <dep-id> -> classifies the dep's done-marker `merged:` proof (marker assumed to exist):
#   "sha <hex>"  marker carries a `merged:<sha>` hex proof (7-40 hex)         -> prove containment locally
#   "pr <N>"     marker carries a `merged:#<N>` PR-ONLY proof (no local sha)  -> resolve merge-commit via gh
#   "bad <raw>"  marker carries a `merged:<garbage>` token that is neither    -> UNVERIFIABLE, never trust
#   "none"       marker present but NO `merged:` token (e.g. override close)   -> UNVERIFIABLE
# The `#` discriminator matches how done.sh writes the marker (merged:<sha> vs merged:#<pr>).
dep_proof(){
  local m="$FLEET/state/done/$1" raw val
  raw="$(grep -oE 'merged:[^[:space:]]+' "$m" 2>/dev/null | head -1)"
  [ -n "$raw" ] || { printf 'none'; return 0; }
  val="${raw#merged:}"
  if [ "${val#\#}" != "$val" ]; then                       # had a leading '#': PR-only marker
    val="${val#\#}"
    if printf '%s' "$val" | grep -qE '^[0-9]+$'; then printf 'pr %s' "$val"
    else printf 'bad %s' "$val"; fi
  elif printf '%s' "$val" | grep -qiE '^[0-9a-f]{7,40}$'; then
    printf 'sha %s' "$val"
  else
    printf 'bad %s' "$val"
  fi
}

# pr_merge_sha <pr#> -> prints the MERGE-COMMIT hex sha of a MERGED PR (empty if unresolvable/not merged).
# Repo slug derived exactly as done.sh does (via _lib.sh `_vm_slug`). Test hook BASE_INTEGRITY_PR_SHA_FIXTURE
# = a "<pr>\t<sha>" TSV for deterministic offline resolution; OFFLINE mode does NO network (unresolvable).
pr_merge_sha(){
  local n="$1" slug
  if [ -n "${BASE_INTEGRITY_PR_SHA_FIXTURE:-}" ]; then
    [ -f "$BASE_INTEGRITY_PR_SHA_FIXTURE" ] && awk -v n="$n" '$1==n{print $2; exit}' "$BASE_INTEGRITY_PR_SHA_FIXTURE"
    return 0
  fi
  [ -n "${BASE_INTEGRITY_OFFLINE:-}" ] && return 0
  command -v gh >/dev/null 2>&1 || return 0
  slug="$(_vm_slug)"; [ -n "$slug" ] || return 0
  gh pr view "$n" --repo "$slug" --json mergeCommit,state \
     -q 'select(.state=="MERGED") | (.mergeCommit.oid // "")' 2>/dev/null || true
}

# handle_unverifiable <dep-id> <reason>: a dep whose containment CANNOT be proven by a concrete sha.
# GUIDING INVARIANT: unverifiable => NOT satisfied — EXCEPT base==origin/master, where a dep that is
# merged is contained by definition (advisory only). For any other base we cannot prove containment,
# so it is a HARD RED (the false-GREEN this gate previously emitted via WARN-and-count-satisfied).
handle_unverifiable(){
  if [ "$base_ref" = "origin/master" ]; then
    echo "base-integrity.sh: WARN — dep '$1' proof unresolvable ($2); base is origin/master so a MERGED dep is contained by definition — advisory, counted satisfied." >&2
  else
    echo "base-integrity.sh: RED — dep '$1' proof UNVERIFIABLE ($2); base '$base_ref' != origin/master, cannot prove containment (unverifiable => NOT satisfied)." >&2
    missing+=("$1:unverifiable"); rc=1   # BASE_INTEGRITY_UNVERIFIABLE_GUARD
  fi
}

deps_raw="$(_vm_meta depends_on "$bfile")"
rc=0
missing=()
if [ -n "$deps_raw" ]; then
  for d in $(echo "$deps_raw" | tr ',' ' '); do
    [ -n "$d" ] || continue
    dc="$(canon "$d" 2>/dev/null)" || dc="$d"
    m="$FLEET/state/done/$dc"
    if [ ! -f "$m" ]; then
      echo "base-integrity.sh: RED — dep '$dc' is NOT merged (no done-marker) -> base '$base_ref' cannot contain it." >&2
      missing+=("$dc:unmerged"); rc=1; continue
    fi
    proof="$(dep_proof "$dc")"; kind="${proof%% *}"; pval="${proof#* }"
    sha=""
    case "$kind" in
      sha) sha="$pval" ;;
      pr)
        # PR-only marker (merged:#<N>): resolve the PR's merge-commit sha, then containment-check it
        # against the base like any other sha. If it cannot be resolved -> unverifiable (base-conditional).
        sha="$(pr_merge_sha "$pval")"
        if [ -z "$sha" ] || ! printf '%s' "$sha" | grep -qiE '^[0-9a-f]{7,40}$'; then
          handle_unverifiable "$dc" "PR #$pval merge-commit unresolvable"; continue
        fi ;;
      bad)
        # Garbage/malformed proof token is NEVER a valid proof -> hard RED regardless of base.
        echo "base-integrity.sh: RED — dep '$dc' has a MALFORMED merged proof ('$pval'), not a sha or PR# -> cannot prove base '$base_ref' contains it (unverifiable => NOT satisfied)." >&2
        missing+=("$dc:malformed"); rc=1; continue ;;
      *)
        # Marker present but no merged:<sha|#pr> proof (e.g. override close): unverifiable.
        handle_unverifiable "$dc" "no merged:<sha|#pr> proof (override close)"; continue ;;
    esac
    if git -C "$repo" merge-base --is-ancestor "$sha" "$base_ref" 2>/dev/null; then
      echo "base-integrity.sh: OK — base '$base_ref' contains dep '$dc' ($sha)."
    else
      echo "base-integrity.sh: RED — base '$base_ref' is MISSING prereq '$dc' (merged $sha not an ancestor). STALE base: rebase onto a base that contains '$dc' before launching $id." >&2
      missing+=("$dc:$sha"); rc=1
    fi
  done
fi

# ADVISORY (non-fatal): flag an off-origin integration branch that is AHEAD of origin/master, i.e.
# integration being hoarded off-origin — the condition that let origin/master go stale in the first
# place. Only meaningful when checking against origin/master and not in offline mode.
if [ "$rc" -eq 0 ] && [ -z "${BASE_INTEGRITY_OFFLINE:-}" ] && [ "$base_ref" = "origin/master" ]; then
  ahead="$(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads 2>/dev/null | while read -r b; do
    [ -n "$b" ] || continue
    if ! git -C "$repo" merge-base --is-ancestor "$b" origin/master 2>/dev/null; then printf '%s ' "$b"; fi
  done)"
  ahead="${ahead% }"
  [ -n "$ahead" ] && echo "base-integrity.sh: ADVISORY — local branch(es) ahead of origin/master (integration off-origin?): $ahead. Push integration so bases built on origin/master are current." >&2
fi

if [ "$rc" -eq 0 ]; then
  echo "base-integrity: GREEN — base '$base_ref' contains every declared prerequisite of $id."
else
  echo "base-integrity: RED — $id would build on a base MISSING: ${missing[*]}" >&2
fi
exit "$rc"
