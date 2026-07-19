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

# repo_valid_id <id> — 0 only when <id> is safe to INTERPOLATE INTO A PATH.
#
# HIGH-1 (2026-07-18 adversarial review #2). Every RR_WT arm below bare-interpolates $id
# ("/home/stack/charon-private-wt/$id"), and NO caller anywhere in the rig charset-checked it.
# `id=".."` therefore collapsed RR_WT onto the PARENT of the whole worktree family
# (/home/stack), which _lg_wt_canonical then certified as "unambiguously ours to sweep" —
# handing safe_worktree_remove an authorized `rm -rf /home/stack`, destroying both repos and
# the rig itself. Reproduced read-only before this fix:
#   _lg_wt_canonical /home/stack/charon-private /home/stack ".."  -> AUTHORIZED
# The product key refused only incidentally (charon-fleet-.. is not a real component) — luck.
#
# The check lives HERE, in the SSOT, so EVERY consumer inherits it rather than only leak-guard.
# Verified against all 317 real ids on the board (incl. retired/ and archive/) and every
# existing worktree dir: ZERO legitimate ids are rejected.
repo_valid_id(){
  local id="${1-}"
  [ -n "$id" ] || return 1                       # empty would collapse RR_WT onto the parent dir
  case "$id" in
    .|..)   return 1 ;;                          # the classic traversal collapse
    */*)    return 1 ;;                          # any separator escapes the assigned path
    *..*)   return 1 ;;                          # traversal anywhere in the string
  esac
  # Whitelist, not blacklist: also excludes spaces, globs, $, backticks, newlines, leading '-'.
  case "$id" in
    *[!A-Za-z0-9._-]*) return 1 ;;
  esac
  return 0
}

# repo_resolve <key> <id>
#   Resolves a repo KEY (empty -> default) + a ticket id into globals:
#     RR_KEY   canonical key (charon|keystone)
#     RR_PATH  absolute repo checkout path (worktree host)
#     RR_WT    absolute per-ticket worktree path for <id>
#     RR_BASE  base branch to branch/PR off (master|main)
#     RR_GATE  the land-gate command to run FROM the repo root (cwd == repo root)
#   Returns 0 on success, 1 on an unknown key (caller must fail loudly),
#           2 on an UNSAFE id (HIGH-1: would escape the assigned worktree path) — also loud.
#
# HIGH-1 id contract (2026-07-18). A non-empty id that fails repo_valid_id is a HARD REFUSE
# (rc 2, nothing published) — it can only have come from corruption or injection.
# An EMPTY id is DIFFERENT and must NOT hard-fail: _lib.sh's _vm_registry_path calls
# `repo_resolve <key> ""` purely to read RR_PATH (as does verify-merged-repo-aware.test.sh:171),
# a legitimate key->checkout lookup with no worktree involved. For that case we resolve
# everything else normally but publish RR_WT="" — an UNUSABLE path rather than the family
# parent dir. Every RR_WT consumer already fails closed on empty (retire-done.sh:84
# `[ -z "$wt" ]`, _lg_wt_canonical's `[ -n "$wt" ]`), so empty degrades safely; the old
# "/home/stack/charon-private-wt/" did not.
repo_resolve(){
  local key="${1:-}" id="${2:-}"
  [ -n "$key" ] || key="$(repo_default_key)"
  if [ -n "$id" ] && ! repo_valid_id "$id"; then
    echo "repo-registry: REFUSING id '$id' — unsafe to interpolate into a worktree path." >&2
    return 2
  fi
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
  # HIGH-1: an empty id has no worktree. Publish an UNUSABLE RR_WT rather than the bare
  # family-parent directory the interpolation above would otherwise leave behind.
  [ -n "$id" ] || RR_WT=""
  return 0
}

# repo_is_public <key>
#   0 when the key names a PUBLIC repo. The product ships standalone — no build-rig taxonomy
#   (tier names, droid pids, fleet.local addresses) may cross into its published history.
#   Consumed by droid-identity.sh to pick the commit stamp. See MED-3.
#
# MED-4 (2026-07-18 review #2): this used to answer NOT-PUBLIC for "", while repo_resolve maps
# "" -> charon = the PUBLIC product. droid_identity_for_repo declares key="${1:-}", advertising
# empty as legal, so an empty key would have stamped `frontier-25379 <...@fleet.local>` — rig
# tier name + PID — onto a PUBLIC commit. Latent today (fleet-droid.sh:251 passes a
# canonicalised $RR_KEY) but the fail direction was backwards for an absolute rule: the default
# must land on the PUBLIC side so an unknown/empty key yields the NEUTRAL stamp, never leakage.
# Defaulting identically to repo_resolve also keeps the two from drifting apart.
# NOTE `keystone` correctly stays non-public — Nnyan/keystone is genuinely private.
repo_is_public(){
  local key="${1:-}"
  [ -n "$key" ] || key="$(repo_default_key)"
  case "$key" in
    charon|product) return 0 ;;
    *)              return 1 ;;
  esac
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
