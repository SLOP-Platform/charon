#!/usr/bin/env bash
# work-lease.test.sh — FAIL-ON-REVERT tests for the universal WORK-LEASE gate.
#
# THE BUG THIS GATE CLOSES (2026-07-23, a real clobber): two builders (a manager subagent AND an
# off-Claude droid, or two subs) could both be DISPATCHED onto the same ticket. Only the SECOND
# commit was refused — the wasted parallel build already happened, and an un-leased / main-checkout
# commit could slip through when the hooks were never installed or the branch mapped to no ticket.
#
# WHAT IS PROVEN (each assertion names the revert that turns it RED):
#   1 DISPATCH gate — a second `acquire`/`dispatch` on a held ticket is REFUSED (not just the 2nd
#     commit). Revert: drop the `[ -f "$f" ]` conflict branch in cmd_acquire.            -> RED 1/5
#   2 ONE STORE — a work-lease acquire writes claim.sh's state/claims/<t>, NOT a parallel
#     state/leases/. And the two paths are mutually exclusive: claim.sh's claim makes acquire
#     REFUSE, and an acquired ticket is SKIPPED by claim.sh. Revert: point LEASES back at
#     state/leases.                                                                       -> RED 2/3/4
#   3 COMMIT gate — pre-commit REFUSES an un-leased worktree commit and ALLOWS a leased one.
#     Revert: make cmd_pre_commit `return 0` unconditionally.                             -> RED 6/7
#   4 FAIL-CLOSED — a worktree whose branch maps to NO ticket is REFUSED (the old `|| return 0`
#     passed it SILENTLY). Revert: restore `ticket=... || return 0`.                      -> RED 8
#   5 STALE reclaim — a dead (stale) holder never permanently blocks; a LIVE holder is not stolen.
#
# Hermetic: runs the REAL work-lease.sh / claim.sh / _lib.sh (copied verbatim into a temp FLEET so
# state + hooks are isolated — the CODE is the real code, never a transcription) against REAL git
# worktrees under mktemp -d. No network, no stubs. ~2s.
set -uo pipefail

REAL_FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── build a hermetic FLEET with the REAL scripts ────────────────────────────────────────────
FLEET="$TMP/fleet"
mkdir -p "$FLEET/hooks" "$FLEET/board" "$FLEET/state"
cp "$REAL_FLEET/work-lease.sh" "$FLEET/work-lease.sh"
cp "$REAL_FLEET/claim.sh"      "$FLEET/claim.sh"
cp "$REAL_FLEET/_lib.sh"       "$FLEET/_lib.sh"
cp "$REAL_FLEET/release.sh"    "$FLEET/release.sh" 2>/dev/null || true
cp "$REAL_FLEET/hooks/pre-commit" "$FLEET/hooks/pre-commit"
cp "$REAL_FLEET/hooks/commit-msg" "$FLEET/hooks/commit-msg"
chmod +x "$FLEET"/*.sh "$FLEET"/hooks/* 2>/dev/null || true
WL="$FLEET/work-lease.sh"

mkboard() { # mkboard <id> <tier> <branch>
  cat > "$FLEET/board/$1.md" <<EOF
repo: charon-private
tier: $2
branch: $3
depends_on:
EOF
}
mkboard CLAIMME haiku feat/claimme
mkboard TCKT-A  haiku feat/a

# ── 1. DISPATCH gate: acquire refuses a second holder ───────────────────────────────────────
bash "$WL" acquire CLAIMME sessA "$TMP/wtA" >/dev/null 2>&1 \
  && ok "acquire (1st) succeeds" || bad "acquire (1st) failed unexpectedly"
if bash "$WL" acquire CLAIMME sessB "$TMP/wtB" >/dev/null 2>&1; then
  bad "acquire (2nd, different wt) SUCCEEDED — double-claim NOT refused (dispatch gate broken)"
else
  ok "acquire (2nd, different wt) REFUSED — dispatch double-claim gate holds"
fi

# ── 2. ONE STORE: the lease lives in state/claims, not a parallel state/leases ──────────────
[ -f "$FLEET/state/claims/CLAIMME" ] \
  && ok "lease written to claim.sh's store (state/claims/CLAIMME)" \
  || bad "lease NOT in state/claims — store not converged"
[ ! -d "$FLEET/state/leases" ] \
  && ok "no parallel state/leases/ store created" \
  || bad "parallel state/leases/ store exists — two stores (not converged)"
bash "$WL" release CLAIMME >/dev/null 2>&1

# ── 3. cross-path: claim.sh's claim makes a work-lease acquire REFUSE ───────────────────────
if bash "$FLEET/claim.sh" haiku droid1 both >/dev/null 2>&1 && [ -f "$FLEET/state/claims/CLAIMME" ]; then
  ok "claim.sh claimed CLAIMME into the shared store"
  if bash "$WL" acquire CLAIMME sessX "$TMP/wtX" >/dev/null 2>&1; then
    bad "work-lease acquire IGNORED an existing claim.sh claim — stores disjoint"
  else
    ok "work-lease acquire REFUSED a ticket claim.sh already holds — single store"
  fi
else
  bad "claim.sh could not claim the fixture ticket (test setup issue)"
fi

# ── 4. cross-path: an acquired ticket is SKIPPED by claim.sh (single store, other direction) ─
bash "$FLEET/release.sh" CLAIMME >/dev/null 2>&1 || rm -f "$FLEET/state/claims/CLAIMME"
bash "$WL" acquire CLAIMME sessY "$TMP/wtY" >/dev/null 2>&1
out="$(bash "$FLEET/claim.sh" haiku droid2 own-only 2>/dev/null || true)"
# TCKT-A is also haiku; CLAIMME is leased, so claim.sh must pick TCKT-A or NONE — never CLAIMME.
if printf '%s' "$out" | grep -q 'CLAIMME'; then
  bad "claim.sh re-claimed CLAIMME despite an active work-lease — stores disjoint"
else
  ok "claim.sh skipped the work-leased ticket (shared claims store)"
fi
bash "$WL" release CLAIMME >/dev/null 2>&1
rm -f "$FLEET/state/claims/TCKT-A"

# ── 5. dispatch REFUSES to launch for a held ticket (launch cmd never runs) ─────────────────
bash "$WL" acquire CLAIMME sessH "$TMP/wtH" >/dev/null 2>&1
marker="$TMP/launched"
if bash "$WL" dispatch CLAIMME sessZ "$TMP/wtZ" -- touch "$marker" >/dev/null 2>&1; then
  bad "dispatch of a leased ticket SUCCEEDED"
else
  [ ! -e "$marker" ] && ok "dispatch of a leased ticket REFUSED + launch cmd did NOT run" \
                     || bad "dispatch refused but launch cmd STILL RAN"
fi
bash "$WL" release CLAIMME >/dev/null 2>&1

# ── git-worktree fixtures for the COMMIT-boundary checks ────────────────────────────────────
REPO="$TMP/repo"
git init -q -b master "$REPO"
git -C "$REPO" config user.email t@t; git -C "$REPO" config user.name t
echo seed > "$REPO/seed"; git -C "$REPO" add -A; git -C "$REPO" commit -qm seed
WT_A="$TMP/wt-a"; git -C "$REPO" worktree add -q -b feat/a "$WT_A" >/dev/null 2>&1
WT_U="$TMP/wt-unmapped"; git -C "$REPO" worktree add -q -b feat/unmapped "$WT_U" >/dev/null 2>&1

# ── 6. COMMIT gate: un-leased worktree commit is REFUSED ────────────────────────────────────
( cd "$WT_A" && bash "$WL" pre-commit >/dev/null 2>&1 ) \
  && bad "pre-commit ALLOWED an un-leased worktree commit" \
  || ok "pre-commit REFUSED an un-leased worktree commit"

# ── 7. COMMIT gate: leased worktree commit is ALLOWED ───────────────────────────────────────
bash "$WL" acquire TCKT-A sessA "$WT_A" >/dev/null 2>&1
( cd "$WT_A" && bash "$WL" pre-commit >/dev/null 2>&1 ) \
  && ok "pre-commit ALLOWED a commit in the worktree that holds the lease" \
  || bad "pre-commit REFUSED a commit even though this worktree holds the lease"
bash "$WL" release TCKT-A >/dev/null 2>&1

# ── 8. FAIL-CLOSED: a worktree whose branch maps to NO ticket is REFUSED ────────────────────
( cd "$WT_U" && bash "$WL" pre-commit >/dev/null 2>&1 ) \
  && bad "pre-commit PASSED an unmapped-branch worktree SILENTLY (fail-open hole)" \
  || ok "pre-commit REFUSED an unmapped-branch worktree (fail-closed)"

# ── 9. holds predicate (the interface CLAIM-LEASE-EXACTLY-ONCE composes with) ───────────────
bash "$WL" acquire TCKT-A sessA "$WT_A" >/dev/null 2>&1
( cd "$WT_A" && bash "$WL" holds TCKT-A ) \
  && ok "holds -> exit 0 when this worktree holds the lease" \
  || bad "holds -> nonzero even though the lease is held here"
( cd "$WT_U" && bash "$WL" holds TCKT-A ) \
  && bad "holds -> exit 0 from a DIFFERENT worktree (leak)" \
  || ok "holds -> nonzero from a worktree that does not hold the lease"
bash "$WL" holds NO-SUCH-TICKET \
  && bad "holds -> exit 0 for a ticket with no lease" \
  || ok "holds -> nonzero for a ticket with no lease"
bash "$WL" release TCKT-A >/dev/null 2>&1

# ── 10. STALE reclaim: a dead holder never permanently blocks; a live one is not stolen ─────
bash "$WL" acquire CLAIMME sessOld "$TMP/wtOld" >/dev/null 2>&1
# LIVE holder -> a different worktree is refused
bash "$WL" acquire CLAIMME sessNew "$TMP/wtNew" >/dev/null 2>&1 \
  && bad "a LIVE lease was stolen" || ok "a LIVE lease is not stolen"
# force the heartbeat far into the past -> now STALE -> reclaimable
sed -i "s/^heartbeat:.*/heartbeat: 1/" "$FLEET/state/claims/CLAIMME"
bash "$WL" acquire CLAIMME sessNew "$TMP/wtNew" >/dev/null 2>&1 \
  && ok "a STALE lease is reclaimable (dead holder never blocks forever)" \
  || bad "a STALE lease was NOT reclaimable — a dead holder permanently blocks"
bash "$WL" release CLAIMME >/dev/null 2>&1

echo ""
if [ "$fails" -eq 0 ]; then echo "work-lease.test.sh: ALL PASS"; exit 0
else echo "work-lease.test.sh: $fails FAILED"; exit 1; fi
