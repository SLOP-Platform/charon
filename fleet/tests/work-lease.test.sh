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

# ═══════════════════════════════════════════════════════════════════════════════════════════
# TICKET-MAP-GATE — the two defects the gate above did NOT close.
#
#   A. LATE ENFORCEMENT. cmd_pre_commit refuses an unmapped branch, but only at COMMIT — after
#      the whole build is done. Measured 2026-07-24: four agents finished complete, tested, green
#      work and could not commit it. Tests 11-14 prove the SAME requirement is now enforced at
#      branch/worktree CREATION (`guard-branch`), and test 15 proves it is actually WIRED into
#      fleet-droid.sh ahead of worktree creation (an unwired gate is inert).
#   B. SPLIT CLAIMS STORE. `fleet/state/*` is .gitignored, so each linked worktree got its OWN
#      empty state/claims/. An `acquire` run from a worktree's copy of work-lease.sh wrote the
#      WORKTREE's store while the pre-commit hook (symlink -> the MAIN checkout's fleet/hooks/*)
#      read the MAIN store: a lease could be acquired successfully and the commit still REFUSED.
#      Tests 16-17 prove the store resolves from `git rev-parse --git-common-dir`, so the main
#      checkout and every linked worktree share ONE store.
#
# REVERTS THAT TURN THESE RED:
#   R1 work-lease.sh: delete cmd_guard_branch / its dispatch arm          -> RED 11,12,13,14
#   R2 work-lease.sh: make cmd_guard_branch `return 0` unconditionally    -> RED 12,13,14
#   R3 fleet-droid.sh: drop the guard-branch call from the dispatch loop  -> RED 15
#   R4 work-lease.sh: restore STATE="$FLEET/state" (drop _state_root)     -> RED 16,17
# ═══════════════════════════════════════════════════════════════════════════════════════════

# ── 11. CREATION gate: a MAPPED branch is allowed (non-vacuous — the gate is not blanket-deny) ─
bash "$WL" guard-branch feat/a >/dev/null 2>&1 \
  && ok "11 guard-branch ALLOWS a branch that maps to a ticket (rc 0)" \
  || bad "11 guard-branch REFUSED a mapped branch — blanket-deny, gate is vacuous"

# ── 12. CREATION gate: an UNMAPPED branch is REFUSED, before any work exists ────────────────
g_out="$(bash "$WL" guard-branch feat/no-such-ticket 2>&1)"; g_rc=$?
if [ "$g_rc" -ne 0 ]; then
  ok "12 guard-branch REFUSES an unmapped branch at creation time (rc $g_rc)"
  printf '%s' "$g_out" | grep -q 'REFUSED' \
    && ok "12b refusal is LOUD (names REFUSED on stderr)" \
    || bad "12b refusal was silent — no REFUSED text"
else
  bad "12 guard-branch ALLOWED an unmapped branch (rc 0) — late refusal at commit is back"
fi

# ── 13. FAIL-CLOSED: a blank branch name refuses (never treated as 'nothing to check') ───────
bash "$WL" guard-branch "" >/dev/null 2>&1 \
  && bad "13 guard-branch PASSED an empty branch name (fail-open)" \
  || ok "13 guard-branch REFUSES an empty branch name (fail-closed)"

# ── 14. FAIL-CLOSED: missing mapping machinery (no board) refuses, never waves through ───────
NOBOARD="$TMP/noboard"; mkdir -p "$NOBOARD/state"
cp "$REAL_FLEET/work-lease.sh" "$NOBOARD/work-lease.sh"
cp "$REAL_FLEET/_lib.sh"       "$NOBOARD/_lib.sh"
bash "$NOBOARD/work-lease.sh" guard-branch feat/a >/dev/null 2>&1 \
  && bad "14 guard-branch PASSED with NO board/ present (fail-open on missing machinery)" \
  || ok "14 guard-branch REFUSES when no board/ is readable (fail-closed)"

# ── 15. WIRED: fleet-droid.sh runs the creation gate BEFORE it creates the worktree ─────────
FD="$REAL_FLEET/fleet-droid.sh"
g_line="$(grep -n 'work-lease.sh" guard-branch' "$FD" | head -1 | cut -d: -f1)"
w_line="$(grep -n 'p0_worktree_setup "\$REPO"' "$FD" | head -1 | cut -d: -f1)"
if [ -n "$g_line" ] && [ -n "$w_line" ] && [ "$g_line" -lt "$w_line" ]; then
  ok "15 fleet-droid.sh calls guard-branch (line $g_line) BEFORE worktree creation (line $w_line)"
else
  bad "15 fleet-droid.sh does NOT gate branch->ticket before worktree creation (guard=${g_line:-none} create=${w_line:-none})"
fi
sed -n "${g_line:-1},$(( ${g_line:-1} + 4 ))p" "$FD" | grep -q 'release.sh' \
  && ok "15b the refusal path RELEASES the claim instead of launching a doomed build" \
  || bad "15b guard-branch failure does not release the claim"

# ── 16/17. ONE STORE ACROSS WORKTREES (resolved from git-common-dir) ────────────────────────
# A REAL rig repo with fleet/ at its root plus a REAL linked worktree — the exact topology that
# split the store. Everything below runs the REAL work-lease.sh, never a transcription.
RIG="$TMP/rig"
git init -q -b master "$RIG"
git -C "$RIG" config user.email t@t; git -C "$RIG" config user.name t
mkdir -p "$RIG/fleet/board" "$RIG/fleet/hooks"
cp "$REAL_FLEET/work-lease.sh" "$RIG/fleet/work-lease.sh"
cp "$REAL_FLEET/_lib.sh"       "$RIG/fleet/_lib.sh"
cp "$REAL_FLEET/hooks/pre-commit" "$RIG/fleet/hooks/pre-commit"
cat > "$RIG/fleet/board/RIGTKT.md" <<'EOF'
repo: charon-private
tier: haiku
branch: feat/rigtkt
depends_on:
EOF
printf 'fleet/state/\n' > "$RIG/.gitignore"     # same ignore rule that split the store
git -C "$RIG" add -A >/dev/null 2>&1; git -C "$RIG" commit -qm seed
RIG_WT="$TMP/rig-wt"
git -C "$RIG" worktree add -q -b feat/rigtkt "$RIG_WT" >/dev/null 2>&1

# acquire using the WORKTREE's OWN copy of work-lease.sh (what an agent in a worktree runs)
( cd "$RIG_WT" && bash "$RIG_WT/fleet/work-lease.sh" acquire RIGTKT sessW "$RIG_WT" ) >/dev/null 2>&1
if [ -f "$RIG/fleet/state/claims/RIGTKT" ] && [ ! -f "$RIG_WT/fleet/state/claims/RIGTKT" ]; then
  ok "16 a worktree-side acquire writes the MAIN checkout's store (single store via git-common-dir)"
else
  bad "16 worktree-side acquire wrote $( [ -f "$RIG_WT/fleet/state/claims/RIGTKT" ] && echo 'the WORKTREE store' || echo 'nowhere') — store still split"
fi

# and the MAIN checkout's script (the one the pre-commit hook symlink resolves to) must agree
( cd "$RIG_WT" && bash "$RIG/fleet/work-lease.sh" check RIGTKT ) >/dev/null 2>&1 \
  && ok "17 the MAIN checkout's work-lease.sh sees the worktree-acquired lease (hook and acquire agree)" \
  || bad "17 acquire succeeded but the hook's script reports NO-LEASE — the acquire/commit split is back"

echo ""
if [ "$fails" -eq 0 ]; then echo "work-lease.test.sh: ALL PASS"; exit 0
else echo "work-lease.test.sh: $fails FAILED"; exit 1; fi
