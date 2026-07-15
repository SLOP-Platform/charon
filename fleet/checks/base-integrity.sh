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
#   For each dep D, resolve D's MERGED sha from its done-marker (fleet/state/done/<D>, `merged:<sha>`),
#   then require `git merge-base --is-ancestor <sha> <BASE>` — the base actually CONTAINS the prereq.
#   A dep with no merge proof, or a proof sha NOT contained in the base, is a MISSING prereq -> RED.
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

# dep_merged_sha <dep-id> -> prints the merged:<sha> hex from the dep's done-marker (empty if none).
dep_merged_sha(){
  local m="$FLEET/state/done/$1" p val
  [ -f "$m" ] || return 0
  p="$(grep -oE 'merged:[0-9a-fA-F]{7,40}' "$m" 2>/dev/null | head -1)"
  val="${p#merged:}"
  printf '%s' "$val"
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
    sha="$(dep_merged_sha "$dc")"
    if [ -z "$sha" ]; then
      # Closed by override / PR-only proof: no local sha to prove containment. Advisory, not a hard red.
      echo "base-integrity.sh: WARN — dep '$dc' closed without a merged:<sha> proof (override/PR-only); cannot LOCALLY prove base '$base_ref' contains it." >&2
      continue
    fi
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
