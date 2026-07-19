#!/usr/bin/env bash
# droid-identity.sh — COMMIT-ACTOR-STAMP library (fleet build-rig only; `source` it, runs nothing).
#
# WHY (2026-07-18): every rig commit was authored `sim <sim@sim>`, so a droid commit and a
# manager sub-agent commit are INDISTINGUISHABLE in git history. Today's forensics on a
# wrong-commit merge needed a log-file archaeology dig that a committer name would have answered
# in 30 seconds. A commit is the one artifact that always survives; the actor belongs ON it.
#
# droid_git_identity <droid-id> [email-domain]
#   Exports GIT_AUTHOR_* and GIT_COMMITTER_* for the CURRENT droid session, so EVERY commit made
#   by the launcher, the work client, or the model itself carries the droid id (e.g.
#   `frontier-25379`). The env vars are inherited by every child process — no per-command flag,
#   nothing for a model to forget.
#
#   The values are a REAL git identity (plain name + a syntactically valid address), NOT a marker
#   string: `git log --format=%an/%cn/%ae` and every downstream parser keep working unchanged.
#   Existing `user.name`/`user.email` config stays as the fallback for anything outside a droid
#   session (the manager, the operator) — this only stamps the droid's own process tree.
droid_git_identity(){
  local id="${1:?droid_git_identity: need a droid id}" domain="${2:-fleet.local}"
  # Keep it to characters git and mail addresses both accept; a tier-pid id is already safe, but
  # a caller-supplied id might not be.
  local safe; safe="$(printf '%s' "$id" | tr -c 'A-Za-z0-9._-' '-')"
  export GIT_AUTHOR_NAME="$safe"
  export GIT_AUTHOR_EMAIL="$safe@$domain"
  export GIT_COMMITTER_NAME="$safe"
  export GIT_COMMITTER_EMAIL="$safe@$domain"
  printf '%s' "$safe"
}

# droid_public_git_identity [name] [email]
#   The NEUTRAL stamp used for PUBLIC repos. `frontier-25379 <frontier-25379@fleet.local>` leaks
#   internal rig taxonomy (tier name) and a PID into a published history; the product must ship
#   with no build-rig fingerprints. Overridable via CHARON_PUBLIC_GIT_NAME/EMAIL.
droid_public_git_identity(){
  local name="${1:-${CHARON_PUBLIC_GIT_NAME:-charon-bot}}"
  local email="${2:-${CHARON_PUBLIC_GIT_EMAIL:-charon-bot@users.noreply.github.com}}"
  # Same sanitizer contract as above: keep it to characters git and mail addresses both accept,
  # and fall back to a known-good pair if an override is unusable, so the address stays valid.
  name="$(printf '%s' "$name" | tr -c 'A-Za-z0-9._ -' '-')"
  case "$email" in *?@?*.?*) ;; *) email="charon-bot@users.noreply.github.com" ;; esac
  [ -n "$name" ] || name="charon-bot"
  export GIT_AUTHOR_NAME="$name"    GIT_AUTHOR_EMAIL="$email"
  export GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email"
  printf '%s' "$name"
}

# droid_identity_for_repo <repo_key> <droid_id>
#   THE per-ticket entry point. A droid processes tickets for several repos in one session, so the
#   stamp must be re-picked per ticket, not once at launch: rig ticket -> droid id (forensics),
#   PUBLIC product ticket -> neutral identity (no rig leakage). Falls back to the droid id when
#   repo_is_public is not sourced, so the rig never loses attribution.
droid_identity_for_repo(){
  local key="${1:-}" id="${2:?droid_identity_for_repo: need a droid id}"
  if declare -F repo_is_public >/dev/null 2>&1 && repo_is_public "$key"; then
    droid_public_git_identity
  else
    droid_git_identity "$id"
  fi
}
