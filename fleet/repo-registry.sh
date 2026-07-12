#!/usr/bin/env bash
# repo-registry.sh — MULTI-REPO table for the fleet harness (build-rig only; `source` it).
#
# WHY: fleet-droid.sh / submit.sh used to HARDWIRE the charon product repo
# (CHARON=/home/stack/code/charon, PRs -> SLOP-Platform/charon, base master). A board
# ticket can now name a target repo via a `repo:` field; this table maps that KEY to the
# repo path, the worktree location, the base branch, and the land-gate. PR owner/repo is
# NOT hardwired — it is derived at land time from the repo's own `gh repo view`/origin.
#
# BACK-COMPAT: a ticket with NO `repo:` field resolves to key `charon` and behaves EXACTLY
# as before (same repo path, same worktree `<...>/charon-fleet-<id>`, base master).
#
# ADD A REPO: give it a case arm in repo_resolve below. Nothing else in the harness needs
# to know the repo — everything downstream reads the RR_* globals it sets.

# repo_default_key — the key used when a ticket omits `repo:`.
repo_default_key(){ echo charon; }

# repo_known_keys — every accepted key/alias (for validators / help text).
repo_known_keys(){ echo "charon product keystone ksf charon-private rig fleet"; }

# repo_resolve <key> <id>
#   Resolves a repo KEY (empty -> default) + a ticket id into globals:
#     RR_KEY   canonical key (charon|keystone)
#     RR_PATH  absolute repo checkout path (worktree host)
#     RR_WT    absolute per-ticket worktree path for <id>
#     RR_BASE  base branch to branch/PR off (master|main)
#     RR_GATE  the land-gate command to run FROM the repo root (cwd == repo root)
#   Returns 0 on success, 1 on an unknown key (caller must fail loudly).
repo_resolve(){
  local key="${1:-}" id="${2:-}"
  [ -n "$key" ] || key="$(repo_default_key)"
  case "$key" in
    charon|product)
      RR_KEY=charon
      RR_PATH=/home/stack/code/charon
      RR_WT="/home/stack/code/charon-fleet-$id"
      RR_BASE=master
      RR_GATE='PYTHONPATH=src python3 -m charon.cli gate'
      ;;
    keystone|ksf)
      RR_KEY=keystone
      RR_PATH=/home/stack/code/keystone
      RR_WT="/home/stack/code/keystone-wt/$id"
      RR_BASE=main
      # ksf isn't globally installed (CI does `pip install -e .`); run it in-tree via the
      # module, from the repo root (`--repo-root .`). gate THEN verify-self, same as CI.
      RR_GATE='PYTHONPATH=. python3 -m ksf.cli --repo-root . gate && PYTHONPATH=. python3 -m ksf.cli --repo-root . verify-self'
      ;;
    charon-private|rig|fleet)
      RR_KEY=charon-private
      RR_PATH=/home/stack/charon-private
      RR_WT="/home/stack/charon-private-wt/$id"
      RR_BASE=master
      # rig gate == the board validator, run from the repo root against the fleet dir.
      RR_GATE='bash "$PWD/fleet/validate_board.sh" "$PWD/fleet"'
      ;;
    *)
      return 1
      ;;
  esac
  return 0
}

# repo_owner_repo <repo_path>
#   Prints the owner/repo slug for PR targeting, derived from the repo itself (gh first,
#   then the origin remote). NEVER hardwired. Empty output => could not resolve.
repo_owner_repo(){
  local path="$1" slug=""
  slug="$( (cd "$path" 2>/dev/null && gh repo view --json nameWithOwner -q .nameWithOwner) 2>/dev/null )"
  [ -n "$slug" ] || slug="$(git -C "$path" remote get-url origin 2>/dev/null \
      | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')"
  printf '%s' "$slug"
}
