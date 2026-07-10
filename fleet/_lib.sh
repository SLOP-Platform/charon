# Shared fleet helpers. `source` this AFTER setting FLEET.
# Single home for id canonicalization + dependency checks so the gating scripts
# (claim/board/status) can't diverge again (audit 2026-06-27, THEMEs 1 & 5).
FLEET_LIB_BOARD="${FLEET:?_lib.sh: set FLEET before sourcing}/board"
FLEET_LIB_STATE="$FLEET/state"

# canon <id> -> exact board basename (case-insensitive). Non-zero + stderr if no match.
canon(){ local w="$1" f b; for f in "$FLEET_LIB_BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { printf '%s' "$b"; return 0; }; done
  echo "no board ticket matching '$w'" >&2; return 1; }

# deps_done <comma-separated-list> -> 0 if EVERY dep is done, else 1. Empty list = 0 (no deps).
# Splits on commas (multi-dep) and canonicalizes each id, so `depends_on: E6, FB4` works.
deps_done(){ local raw="${1:-}" d dc; [ -n "$raw" ] || return 0
  for d in $(echo "$raw" | tr ',' ' '); do
    dc="$(canon "$d" 2>/dev/null)" || dc="$d"
    [ -e "$FLEET_LIB_STATE/done/$dc" ] || return 1
  done; return 0; }

# --- verify_merged <id>: THE ONE source of truth for "is <id> genuinely LANDED in the product
# repo's origin/master" (G1 done.sh, G2 preflight done_merge_gate, G3a detect_needs_push, G3b
# reconcile-merged, G3c retire-done). Replaces the old "trust that a `done` marker exists" logic
# that let a lying marker delete the needs-push guard / cascade unblocks over stranded work.
#
# POSITIVE proof precedence (LOCAL/offline checks first, so a full-board sweep does not hammer net):
#   1. marker carries `merged:<sha>`  -> sha is an ancestor of the product origin/master (git, local)
#   2. marker carries `merged:#<pr>`  -> that PR is merged (gh, network)
#   3. board `branch:` has a merged PR (gh, network)
# Returns 0 = merge-verified (POSITIVE proof), 1 = NOT verified. NEVER errors out (each step is
# guarded), so it is safe to call from a `set -e` script AS A CONDITION (always `if verify_merged ...`).
#
# H1 FIX (2026-07-10 adversarial review): `owns:`-content-present is NO LONGER a positive proof here.
# `owns` files merely EXISTING in origin/master is TRUE for ~every ticket that modifies a pre-existing
# file (proxy.py, config.py, …) whether or not THIS ticket's change landed — a false positive. That
# weak signal was gating DESTRUCTIVE actions (deleting the needs-push guard, worktree remove, G2
# auto-close), so a bare/lying `done` on an existing-file ticket could disarm the guard over stranded
# committed work. owns-content now lives in verify_merged_owns_advisory() and may ONLY drive an
# ADVISORY (informational, non-blocking) — never a destructive decision.
#
# TEST HOOK: VERIFY_MERGED_FIXTURE=<file> — when set, returns 0 iff <id> appears (case-insensitive,
# whole line) in that file. Keeps every gate exercisable fully offline. VERIFY_MERGED_REPO overrides
# the product-repo path (default /home/stack/code/charon).
VERIFY_MERGED_REPO_DEFAULT="/home/stack/code/charon"
VERIFY_MERGED_SLUG_DEFAULT="SLOP-Platform/charon"   # M1 fallback when the local remote is absent
_vm_meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null; }
_vm_repo(){ printf '%s' "${VERIFY_MERGED_REPO:-$VERIFY_MERGED_REPO_DEFAULT}"; }
# M1: never return an empty slug (a missing/renamed local product repo would silently disable the
# gh proofs); fall back to the known product slug so a stale/absent local ref cannot brick verification.
_vm_slug(){ local s; s="$(git -C "$(_vm_repo)" remote get-url origin 2>/dev/null \
              | sed -E 's#(git@[^:]*:|https?://[^/]*/)##; s/\.git$//')"
            [ -n "$s" ] && printf '%s' "$s" || printf '%s' "$VERIFY_MERGED_SLUG_DEFAULT"; }
# M1: single best-effort refresh of the product origin/master ref so a STALE local ref cannot
# false-negative a freshly-merged ticket. Best-effort only (offline/no-remote -> no-op). Skipped in
# the offline fixture mode. Call ONCE per gate pass (not per-marker) to avoid hammering the network.
_vm_refresh(){
  [ -n "${VERIFY_MERGED_FIXTURE:-}" ] && return 0
  git -C "$(_vm_repo)" fetch origin master --quiet 2>/dev/null || true
}
# _verification_available: can we actually PROVE a merge right now? Fixture mode = deterministic/yes.
# Else we need gh for the PR/branch proofs; if gh is absent the network proofs cannot run, so a
# not-locally-proven marker is "unverifiable", NOT "positively unmerged" (M1/M2 — degrade to advisory).
_verification_available(){
  [ -n "${VERIFY_MERGED_FIXTURE:-}" ] && return 0
  command -v gh >/dev/null 2>&1
}
_vm_sha_in_master(){ git -C "$(_vm_repo)" merge-base --is-ancestor "$1" origin/master 2>/dev/null; }
_vm_pr_merged(){
  command -v gh >/dev/null 2>&1 || return 1
  local slug m; slug="$(_vm_slug)"; [ -n "$slug" ] || return 1
  m="$(gh pr view "$1" --repo "$slug" --json mergedAt -q '.mergedAt' 2>/dev/null || true)"
  [ -n "$m" ] && [ "$m" != "null" ]
}
_vm_branch_merged(){
  command -v gh >/dev/null 2>&1 || return 1
  local slug n; slug="$(_vm_slug)"; [ -n "$slug" ] || return 1
  n="$(gh pr list --repo "$slug" --head "$1" --state merged --json number -q '.[0].number' 2>/dev/null || true)"
  [ -n "$n" ]
}
# every comma-separated `owns:` path exists in origin/master. Empty owns is NOT a positive proof.
_vm_owns_present(){
  local repo owns="$1" p any=0; repo="$(_vm_repo)"
  local IFS=','
  for p in $owns; do
    p="$(printf '%s' "$p" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$p" ] || continue
    any=1
    git -C "$repo" cat-file -e "origin/master:$p" 2>/dev/null || return 1
  done
  [ "$any" -eq 1 ]
}
# verify_merged: POSITIVE merge proof ONLY (sha-ancestry OR a merged PR). This is what gates every
# DESTRUCTIVE / irreversible decision (needs-push guard delete, worktree remove, retire-off-board,
# G2 done-unmerged auto-close). owns-content is deliberately NOT consulted here (see H1 note above).
verify_merged(){
  local id="$1"
  if [ -n "${VERIFY_MERGED_FIXTURE:-}" ]; then
    [ -f "$VERIFY_MERGED_FIXTURE" ] && grep -qix -- "$id" "$VERIFY_MERGED_FIXTURE" 2>/dev/null
    return $?
  fi
  local marker="$FLEET_LIB_STATE/done/$id" proof val=""
  local bfile="$FLEET_LIB_BOARD/$id.md"
  [ -f "$bfile" ] || bfile="$FLEET_LIB_BOARD/archive/$id.md"
  # 1. local: marker-carried sha ancestry
  if [ -f "$marker" ]; then
    proof="$(grep -oE 'merged:#?[0-9a-fA-F]+' "$marker" 2>/dev/null | head -1)"
    val="${proof#merged:}"; val="${val#\#}"
    if printf '%s' "$val" | grep -qiE '^[0-9a-f]{7,40}$'; then
      _vm_sha_in_master "$val" && return 0
    fi
  fi
  # 2. network: marker-carried PR number is merged
  if printf '%s' "$val" | grep -qE '^[0-9]+$'; then
    _vm_pr_merged "$val" && return 0
  fi
  # 3. network: board branch has a merged PR
  if [ -f "$bfile" ]; then
    local branch; branch="$(_vm_meta branch "$bfile")"
    [ -n "$branch" ] && [ "$branch" != "n/a" ] && _vm_branch_merged "$branch" && return 0
  fi
  return 1
}
# verify_merged_owns_advisory <id>: ADVISORY-ONLY signal (H1). 0 iff every `owns:` path exists in
# origin/master. This is a WEAK signal (true for any existing-file ticket regardless of whether THIS
# ticket landed) — it may ONLY drive an informational, NON-blocking advisory and MUST NEVER authorize
# a destructive action. In deterministic fixture mode it returns 1 (verify_merged fully controls).
verify_merged_owns_advisory(){
  [ -n "${VERIFY_MERGED_FIXTURE:-}" ] && return 1
  local id="$1"; local bfile="$FLEET_LIB_BOARD/$id.md"
  [ -f "$bfile" ] || bfile="$FLEET_LIB_BOARD/archive/$id.md"
  [ -f "$bfile" ] || return 1
  local owns; owns="$(_vm_meta owns "$bfile")"
  [ -n "$owns" ] && _vm_owns_present "$owns"
}
