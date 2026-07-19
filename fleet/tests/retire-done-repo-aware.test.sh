#!/usr/bin/env bash
# retire-done-repo-aware.test.sh — FAIL-ON-REVERT tests for RETIRE-DONE-REPO-UNAWARE (FIX 2).
#
# THE BUG (2026-07-18): retire-done.sh — the DESTRUCTIVE sweep that archives tickets off the board
# and force-removes their worktrees — hardcoded
#     CHARON="/home/stack/code/charon"
#     wt="$CHARON-fleet-$id"
# The repo-aware verify_merged fix landed in _lib.sh/done.sh but NEVER reached here. A rig ticket
# (`repo: charon-private`) has its worktree at /home/stack/charon-private-wt/<id>, so the sweep
# looked at a path that never exists — and pointed `git -C` at the PRODUCT repo while doing it.
#
# THE RULE: repo AND worktree both come from the ONE canonical per-ticket resolution
# (_lib.sh ticket_repo_path / ticket_worktree_path -> repo-registry.sh repo_resolve). No second
# map. Unresolvable repo -> FAIL CLOSED, remove nothing.
#
# NON-FIXTURE: runs the REAL fleet/retire-done.sh, which sources the REAL _lib.sh and the REAL
# repo-registry.sh, and resolves against the REAL canonical worktree roots. The per-ticket
# worktree it operates on is a real directory created at those real paths under a unique
# test-only id, and the test proves removal/non-removal by observing that directory.
# VERIFY_MERGED_FIXTURE keeps merge-proof offline; the REPO RESOLUTION under test is untouched.
#
# ── FAIL-ON-REVERT ──────────────────────────────────────────────────────────────────────────
#   T1 — retire-done.sh: restore `CHARON="/home/stack/code/charon"` + `wt="$CHARON-fleet-$id"`
#        and pass "$CHARON" to safe_worktree_remove (drop the ticket_repo_path /
#        ticket_worktree_path resolution).                       RED: assertion 1.
#   T2 — retire-done.sh: replace BOTH fail-closed branches (`ticket_repo_path` and
#        `ticket_worktree_path`) with silent `|| repo=/home/stack/code/charon` /
#        `|| wt="$repo-fleet-$id"` fallbacks.                    RED: assertion 2.
#        (Reverting only ONE of the two stays green — the other still fails closed. Both are
#        load-bearing; the revert must remove both.)
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"
F="$D/fleet"; mkdir -p "$F/board/archive" "$F/state/done" "$F/state/needs-push"
cp "$FLEET_SRC/retire-done.sh" "$FLEET_SRC/_lib.sh" "$FLEET_SRC/repo-registry.sh" \
   "$FLEET_SRC/leak-guard.sh" "$F/"

# Unique, test-only ticket ids so nothing real can ever be touched.
RIG_ID="RETIRE-REPOAWARE-RIG-$$"
BAD_ID="RETIRE-REPOAWARE-BOGUS-$$"
# The RIG ticket's canonical worktree path per repo-registry.sh (charon-private -> …-wt/<id>).
RIG_WT="/home/stack/charon-private-wt/$RIG_ID"
cleanup(){ rm -rf "$D" "$RIG_WT"; }
trap cleanup EXIT

cat > "$F/board/$RIG_ID.md" <<EOF
id: $RIG_ID
repo: charon-private
branch: n/a
EOF
cat > "$F/board/$BAD_ID.md" <<EOF
id: $BAD_ID
repo: not-a-real-repo-key
branch: n/a
EOF
printf 'merged:deadbeef\n' > "$F/state/done/$RIG_ID"
printf 'merged:deadbeef\n' > "$F/state/done/$BAD_ID"
# Offline merge proof for BOTH ids, so the ONLY thing under test is repo/worktree resolution.
printf '%s\n%s\n' "$RIG_ID" "$BAD_ID" > "$D/merged.txt"
export VERIFY_MERGED_FIXTURE="$D/merged.txt"

# A real directory at the RIG's real canonical worktree path — this is what the sweep must find.
mkdir -p "$RIG_WT"; : > "$RIG_WT/sentinel"

out="$(bash "$F/retire-done.sh" "$RIG_ID" 2>&1)"

# ── 1. the rig ticket resolves against the RIG repo, so its real worktree IS swept ───────────
if [ ! -e "$RIG_WT" ]; then
  ok "1 rig ticket resolved to the rig worktree root and was swept ($RIG_WT removed)"
else
  bad "1 rig ticket's worktree $RIG_WT was NOT swept — resolution still product-hardcoded: $out"
fi
printf '%s\n' "$out" | grep -q "worktree removed: $RIG_WT" \
  && ok "1b the sweep names the RIG worktree path (not <product>-fleet-<id>)" \
  || bad "1b sweep output does not name $RIG_WT: $out"

# ── 2. an unresolvable `repo:` key FAILS CLOSED (removes nothing, says so) ───────────────────
BAD_WT_PRODUCT="/home/stack/code/charon-fleet-$BAD_ID"   # where the OLD hardcoded path would look
out2="$(bash "$F/retire-done.sh" "$BAD_ID" 2>&1)"
if printf '%s\n' "$out2" | grep -q 'fail-closed'; then
  ok "2 unresolvable repo key FAILS CLOSED with an explicit message"
else
  bad "2 unresolvable repo key did not fail closed: $out2"
fi
[ ! -e "$BAD_WT_PRODUCT" ] \
  && ok "2b nothing was resolved to (or touched at) the product path for an unknown repo key" \
  || bad "2b a product-path worktree exists for the unresolvable ticket: $BAD_WT_PRODUCT"

# ── 3. no-`repo:` ticket keeps the PRODUCT default (back-compat; guards against over-fixing) ─
PROD_ID="RETIRE-REPOAWARE-PROD-$$"
cat > "$F/board/$PROD_ID.md" <<EOF
id: $PROD_ID
branch: n/a
EOF
export FLEET="$F"
# shellcheck source=/dev/null
( source "$F/_lib.sh"
  p="$(ticket_repo_path "$PROD_ID")" && w="$(ticket_worktree_path "$PROD_ID")" || exit 1
  [ "$p" = "/home/stack/code/charon" ] && [ "$w" = "/home/stack/code/charon-fleet-$PROD_ID" ] ) \
  && ok "3 a ticket with no 'repo:' field still resolves to the PRODUCT repo + product worktree" \
  || bad "3 back-compat broken: no-repo ticket no longer resolves to the product repo/worktree"

echo "retire-done-repo-aware: $fails failure(s)"
[ "$fails" -eq 0 ]
