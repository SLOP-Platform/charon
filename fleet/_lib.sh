# Shared fleet helpers. `source` this AFTER setting FLEET.
# Single home for id canonicalization + dependency checks so the gating scripts
# (claim/board/status) can't diverge again (audit 2026-06-27, THEMEs 1 & 5).
FLEET_LIB_BOARD="${FLEET:?_lib.sh: set FLEET before sourcing}/board"
FLEET_LIB_STATE="$FLEET/state"

# canon <id> -> exact board basename (case-insensitive). Non-zero + stderr if no match.
canon(){ local w="$1" f b; for f in "$FLEET_LIB_BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { printf '%s' "$b"; return 0; }; done
  echo "no board ticket matching '$w'" >&2; return 1; }

# parked_value <ticket-file> -> the raw `parked:` value (first line, lowercased, trimmed).
parked_value(){ awk '/^parked:[[:space:]]*/{sub(/^parked:[[:space:]]*/,"");print tolower($0);exit}' "$1" \
  | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

# is_parked_value <value> -> 0 (parked) / 1 (not parked). THE canonical parked predicate.
# A ticket is PARKED iff `parked:` is present, non-empty, and not an explicit false.
# NOT `== true`: park reasons are written as prose (e.g. BENCH-PROVISIONAL-SCORING's
# "operator-led DEEP-DIVE ... Do NOT route to an SG droid"), and a `== true` test silently
# treats every such operator directive as UNPARKED -> claimable. `parked:` with an EMPTY
# value means NOT parked (MEMORY-INDEX-COMPACTION relies on this).
# claim.sh re-implements this rule INLINE in its indexing awk (it must not spawn a helper
# per file — see the PERF note at claim.sh:26). fleet/tests/parked-semantics.test.sh asserts
# the two implementations agree on shared fixtures; keep them in lockstep.
is_parked_value(){ case "${1:-}" in ""|false|no|0) return 1;; *) return 0;; esac; }

# is_parked <ticket-file> -> 0 if the ticket is parked, else 1.
is_parked(){ is_parked_value "$(parked_value "$1")"; }

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
#
# ── CANONICAL REPO DECLARATIONS (SSOT — REPO-DECL-CENTRAL) ──────────────────────────────
# The rig spans TWO repos. Declare each ONCE here; every consumer reads these instead of
# re-hardcoding a path or re-writing the repo->slug `case` (the "board-field predicate
# re-parsed per consumer" drift class — see the `parked:` incident in parked-semantics.test.sh).
PRODUCT_REPO="${CHARON_PRODUCT_REPO:-/home/stack/code/charon}"
PRODUCT_SLUG="SLOP-Platform/charon"
FLEET_REPO="${CHARON_FLEET_REPO:-/home/stack/charon-private}"
FLEET_SLUG="Nnyan/charon-private"
# Back-compat aliases: VERIFY_MERGED_REPO (many tests) still overrides the PRODUCT path.
VERIFY_MERGED_REPO_DEFAULT="$PRODUCT_REPO"
VERIFY_MERGED_SLUG_DEFAULT="$PRODUCT_SLUG"   # M1 fallback when the local remote is absent
# _vm_meta <key> <file> -> the field's value ("" if absent). Used for `repo`, `branch`, `owns`,
# `base`, `depends_on` (checks/base-integrity.sh).
# H3 FIX (2026-07-18 adversarial review): this used `awk -F': '`, requiring a LITERAL ": "
# separator, while validate_board.sh's field() uses `line.startswith(key+":")` + .strip() —
# strictly MORE tolerant. A board line written `repo:charon-private` (no space) therefore passed
# the board validator as a valid RIG ticket while _vm_meta read "" -> _vm_resolve took the PRODUCT
# default -> verify_merged returned 0 against a PRODUCT-ONLY sha. Board GREEN, destructive gate
# reading the wrong repo. The parse now MATCHES field(): literal "<key>:" prefix, then strip
# surrounding whitespace (which also absorbs the CR of a CRLF board file). A value containing
# further colons (`branch: has: colon`) is preserved — only the FIRST "<key>:" is consumed.
# Keep this in lockstep with validate_board.sh:field() — a parser that is STRICTER than the
# validator is a false-positive generator, which is the whole bug class here.
_vm_meta(){ awk -v k="$1" 'index($0,k ":")==1{sub("^" k ":[[:space:]]*","");sub(/[[:space:]]+$/,"");print;exit}' "$2" 2>/dev/null; }

# ── TICKET-AWARE REPO RESOLUTION ────────────────────────────────────────────────────────
# THE BUG this fixes (2026-07-18): _vm_repo/_vm_slug were ticket-INDEPENDENT, so verify_merged
# proved EVERY ticket against the PRODUCT repo — including the ~71 board/archive tickets that
# carry `repo: charon-private`. Two live failures: (a) FALSE NEGATIVE — SALVAGE-STASH-CHARON-RUN
# carries `merged:#83` (a RIG PR) and was checked against SLOP-Platform/charon, so it could never
# retire; (b) FALSE POSITIVE — REPO-DECL-CENTRAL's marker sha c44e7bd does not exist in the rig at
# all but IS an ancestor of PRODUCT origin/master, so a rig ticket was "merge-proven" by a product
# commit. verify_merged gates DESTRUCTIVE actions, so (b) is the sharp edge.
#
# _vm_ticket_repo_field <id> -> raw `repo:` value (board/<id>.md, then board/archive/<id>.md).
#   rc 0 + value  — board file exists and declares `repo:`.
#   rc 0 + EMPTY  — board file EXISTS but declares no `repo:` (deliberate back-compat -> product),
#                   or the caller passed NO id at all (the no-arg "default repo" callers).
#   rc 1          — M4 FIX (2026-07-18 adversarial review): NO board file at all. A
#                   state/done/<id> marker with neither board/<id>.md nor board/archive/<id>.md
#                   used to yield an empty field, INDISTINGUISHABLE from "board file present, no
#                   repo: field", so it took the PRODUCT default and verify_merged returned 0 on a
#                   product-only sha. That is a FAIL-OPEN on precisely the input most likely to be
#                   a lie — an orphan marker with no board ticket behind it. These two cases are
#                   different and must NOT be collapsed back together.
_vm_ticket_repo_field(){
  local id="${1:-}" b; [ -n "$id" ] || return 0
  b="$FLEET_LIB_BOARD/$id.md"; [ -f "$b" ] || b="$FLEET_LIB_BOARD/archive/$id.md"
  [ -f "$b" ] || return 1
  _vm_meta repo "$b" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}
# ── THE repo KEY MAP LIVES IN repo-registry.sh ──────────────────────────────────────────
# H1 FIX (2026-07-18 adversarial review): _vm_resolve used to carry its OWN `case` over the
# `repo:` keys — a FOURTH copy of a map that already had an SSOT in fleet/repo-registry.sh
# (repo_resolve, keys listed by repo_known_keys). The copies had already DIVERGED: _vm_resolve
# omitted `keystone|ksf`, so a `repo: keystone` ticket returned rc 1 unconditionally -> held
# forever by retire-done.sh and an unclosable `done-unmerged-*` red in preflight.sh.
# _vm_resolve now DELEGATES key->path to repo_resolve. NOTE this converges the two maps that
# feed verify_merged only; validate_board.sh's REPO_ROOTS is a THIRD copy and is deliberately
# left alone (ticket REPO-MAP-CONVERGE).
#
# Sourcing notes (repo-registry.sh is `source`-safe: it defines functions and sets nothing at
# source time, and it does NOT source _lib.sh — so there is no cycle even though _lib.sh is
# sourced by nearly every fleet script):
#   - located next to THIS file (BASH_SOURCE), not via $FLEET, because $FLEET legitimately
#     points at a test fixture dir.
#   - sourced ONCE at _lib.sh source time (not per call) — no per-ticket fork in board sweeps.
#   - repo_resolve is invoked in a SUBSHELL: it publishes RR_KEY/RR_PATH/RR_WT/RR_BASE/RR_GATE
#     as GLOBALS, and fleet-droid.sh / submit.sh / land-needs-push.sh set those up-front and
#     rely on them across long-running work. A verify_merged call must not clobber them.
_VM_REGISTRY="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/repo-registry.sh"
[ -f "$_VM_REGISTRY" ] && . "$_VM_REGISTRY"
# _vm_registry_path <key> -> that key's canonical checkout path. rc 1 = key unknown to the SSOT.
_vm_registry_path(){
  command -v repo_resolve >/dev/null 2>&1 || return 2   # registry absent (minimal test fixture)
  ( repo_resolve "$1" "" >/dev/null 2>&1 || exit 1; printf '%s' "$RR_PATH" )
}
# _vm_resolve [id] -> "<path><TAB><slug>". rc 1 = UNKNOWN/unmappable `repo:`, or a marker with no
# board file at all (FAIL CLOSED — the caller must NOT fall back to the product repo). Called with
# NO id (or an id whose board file carries no `repo:` field) it returns the PRODUCT repo —
# deliberate BACK-COMPAT: that is exactly today's behaviour, and the existing no-arg callers
# (checks/base-integrity.sh, preflight.sh) rely on it.
_vm_resolve(){
  local r p
  # rc 1 here = no board file for this id (M4). Fail closed; do NOT default to product.
  r="$(_vm_ticket_repo_field "${1:-}")" || return 1
  r="${r,,}"
  # The env overrides are read HERE (call time, not source time) — the pre-existing contract every
  # test relies on. They override the path the registry supplies; the registry stays the key map.
  case "$r" in
    ""|charon|product)        p="$(_vm_registry_path charon)"        || p=""
                              printf '%s\t%s' "${VERIFY_MERGED_REPO:-${p:-$PRODUCT_REPO}}" "$PRODUCT_SLUG"; return 0 ;;
    charon-private|fleet|rig) p="$(_vm_registry_path charon-private)" || p=""
                              printf '%s\t%s' "${CHARON_FLEET_REPO:-${p:-$FLEET_REPO}}" "$FLEET_SLUG"; return 0 ;;
  esac
  # Every OTHER key (keystone/ksf today, anything added to repo-registry.sh tomorrow) resolves
  # from the SSOT alone — no arm to add here, which is the point of delegating. An empty slug is
  # SAFE: _vm_pr_merged/_vm_branch_merged both `[ -n "$slug" ] || return 1`, and _vm_slug derives
  # the real slug from that path's own origin remote.
  p="$(_vm_registry_path "$r")" || return 1     # rc 1 = unknown key, rc 2 = no registry -> closed
  [ -n "$p" ] || return 1
  printf '%s\t%s' "$p" ""
}
# ticket_repo_path/ticket_repo_slug: the PUBLIC form of the map. done.sh consumes these instead of
# keeping its own `case` copy — one home, no drift.
ticket_repo_path(){ local p; p="$(_vm_resolve "${1:-}")" || return 1; printf '%s' "${p%%$'\t'*}"; }
# ticket_worktree_path <id> -> that ticket's canonical per-ticket worktree path (RR_WT).
# RETIRE-DONE-REPO-UNAWARE FIX (2026-07-18): retire-done.sh — the DESTRUCTIVE sweep that removes
# tickets from the board and force-removes their worktrees — hardcoded
# CHARON=/home/stack/code/charon and derived "$CHARON-fleet-$id", so for a `repo: charon-private`
# ticket it looked for the wrong path entirely (rig worktrees live at
# /home/stack/charon-private-wt/<id>). The repo-aware verify_merged fix landed in _lib.sh/done.sh
# but never reached the sweep. NO NEW MAP: this delegates to repo-registry.sh's repo_resolve —
# the same SSOT _vm_resolve uses — in a SUBSHELL so the RR_* globals that fleet-droid.sh/submit.sh
# set up-front and rely on across long-running work are NOT clobbered.
# rc 1 = unresolvable (unknown `repo:` key, or a done marker with no board file at all) -> the
# caller MUST fail closed and touch nothing.
ticket_worktree_path(){
  local id="${1:-}" key
  command -v repo_resolve >/dev/null 2>&1 || return 2   # registry absent (minimal test fixture)
  key="$(_vm_ticket_repo_field "$id")" || return 1      # rc 1 = no board file (M4 fail-closed)
  key="$(printf '%s' "$key" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  ( repo_resolve "$key" "$id" >/dev/null 2>&1 || exit 1; printf '%s' "$RR_WT" )
}
ticket_repo_slug(){ local p; p="$(_vm_resolve "${1:-}")" || return 1; printf '%s' "${p#*$'\t'}"; }
_vm_repo(){ ticket_repo_path "${1:-}"; }
# M1: never return an empty slug (a missing/renamed local repo would silently disable the gh
# proofs); fall back to the mapped slug so a stale/absent local ref cannot brick verification.
_vm_slug(){ local p path slug s; p="$(_vm_resolve "${1:-}")" || return 1
            path="${p%%$'\t'*}"; slug="${p#*$'\t'}"
            s="$(git -C "$path" remote get-url origin 2>/dev/null \
              | sed -E 's#(git@[^:]*:|https?://[^/]*/)##; s/\.git$//')"
            [ -n "$s" ] && printf '%s' "$s" || printf '%s' "$slug"; }
# M1: single best-effort refresh of the resolved repo's origin/master ref so a STALE local ref
# cannot false-negative a freshly-merged ticket. Best-effort only (offline/no-remote -> no-op).
# Skipped in the offline fixture mode. Call ONCE per gate pass to avoid hammering the network.
_vm_refresh(){
  [ -n "${VERIFY_MERGED_FIXTURE:-}" ] && return 0
  local r; r="$(_vm_repo "${1:-}")" || return 0
  git -C "$r" fetch origin master --quiet 2>/dev/null || true
}
# _verification_available: can we actually PROVE a merge right now? Fixture mode = deterministic/yes.
# Else we need gh for the PR/branch proofs; if gh is absent the network proofs cannot run, so a
# not-locally-proven marker is "unverifiable", NOT "positively unmerged" (M1/M2 — degrade to advisory).
_verification_available(){
  [ -n "${VERIFY_MERGED_FIXTURE:-}" ] && return 0
  command -v gh >/dev/null 2>&1
}
# Each proof below takes the TICKET ID as an optional trailing arg; omitting it keeps the
# historical product-repo behaviour for the no-arg callers.
_vm_sha_in_master(){ local r; r="$(_vm_repo "${2:-}")" || return 1
                     git -C "$r" merge-base --is-ancestor "$1" origin/master 2>/dev/null; }
_vm_pr_merged(){
  command -v gh >/dev/null 2>&1 || return 1
  local slug m; slug="$(_vm_slug "${2:-}")" || return 1; [ -n "$slug" ] || return 1
  m="$(gh pr view "$1" --repo "$slug" --json mergedAt -q '.mergedAt' 2>/dev/null || true)"
  [ -n "$m" ] && [ "$m" != "null" ]
}
_vm_branch_merged(){
  command -v gh >/dev/null 2>&1 || return 1
  local slug n; slug="$(_vm_slug "${2:-}")" || return 1; [ -n "$slug" ] || return 1
  n="$(gh pr list --repo "$slug" --head "$1" --state merged --json number -q '.[0].number' 2>/dev/null || true)"
  [ -n "$n" ]
}
# every comma-separated `owns:` path exists in origin/master. Empty owns is NOT a positive proof.
_vm_owns_present(){
  local repo owns="$1" p any=0; repo="$(_vm_repo "${2:-}")" || return 1
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
  # FAIL CLOSED: an unknown/unmappable `repo:` value is NOT verifiable. Never silently fall back
  # to the product repo — that is exactly how a rig ticket got "proven" by a product commit.
  _vm_resolve "$id" >/dev/null || return 1
  local marker="$FLEET_LIB_STATE/done/$id" proof val=""
  local bfile="$FLEET_LIB_BOARD/$id.md"
  [ -f "$bfile" ] || bfile="$FLEET_LIB_BOARD/archive/$id.md"
  # 1. local: marker-carried sha ancestry
  if [ -f "$marker" ]; then
    proof="$(grep -oE 'merged:#?[0-9a-fA-F]+' "$marker" 2>/dev/null | head -1)"
    val="${proof#merged:}"; val="${val#\#}"
    if printf '%s' "$val" | grep -qiE '^[0-9a-f]{7,40}$'; then
      _vm_sha_in_master "$val" "$id" && return 0
    fi
  fi
  # 2. network: marker-carried PR number is merged
  if printf '%s' "$val" | grep -qE '^[0-9]+$'; then
    _vm_pr_merged "$val" "$id" && return 0
  fi
  # 3. network: board branch has a merged PR
  if [ -f "$bfile" ]; then
    local branch; branch="$(_vm_meta branch "$bfile")"
    [ -n "$branch" ] && [ "$branch" != "n/a" ] && _vm_branch_merged "$branch" "$id" && return 0
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
  [ -n "$owns" ] && _vm_owns_present "$owns" "$id"
}
