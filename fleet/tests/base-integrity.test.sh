#!/usr/bin/env bash
# base-integrity.test.sh — FAIL-ON-REVERT tests for checks/base-integrity.sh (the launch-time gate that
# REFUSES to build a ticket on a base that does not yet contain its declared prerequisites).
#
# Models the real bug: origin/master went STALE behind an unpushed integration branch, so a dep's merge
# (which only landed on that off-origin integration branch) is NOT an ancestor of base=origin/master.
# Fully hermetic/offline: an ISOLATED product git repo (never the real one; no gh/network via
# BASE_INTEGRITY_OFFLINE=1) + a throwaway fleet fixture. NEVER touches the live fleet/state.
#
# Covers:
#   (1) base CONTAINS the prereq          -> GREEN (exit 0).
#   (2) base MISSING the prereq (stale)   -> RED (exit 1), names the missing dep.   <- the load-bearing case
#   (3) dep not merged at all (no marker) -> RED (exit 1).
#   (4) ticket with no depends_on         -> GREEN (exit 0).
#   (5) --base <integration-ref> that DOES contain the prereq -> GREEN (base ref is honored).
#   (6) FAIL-ON-REVERT: neutering the `merge-base --is-ancestor` core check makes the STALE ticket
#       wrongly GREEN — proving (2)'s RED is produced BY that check. Reverting the gate flips (2)->green.
#
# Run:  bash fleet/tests/base-integrity.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ---- isolated product repo with an origin/master ref (offline sha-ancestry) ----
P="$(mktemp -d)"
git -C "$P" init -q
git -C "$P" commit -q --allow-empty -m base
# GREEN prereq: a commit that IS on origin/master.
git -C "$P" commit -q --allow-empty -m okdep
OKSHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$OKSHA"
# STALE prereq: a commit on an off-origin integration branch — merged, but NOT pushed to origin/master
# (exactly the "17 commits stale" condition). origin/master stays at OKSHA.
git -C "$P" checkout -q -b integration
git -C "$P" commit -q --allow-empty -m staledep
STALESHA="$(git -C "$P" rev-parse HEAD)"

# ---- throwaway fleet fixture ----
d="$(mktemp -d)"
mkdir -p "$d/checks" "$d/board/archive" "$d/state/done"
cp "$SRC/checks/base-integrity.sh" "$d/checks/"
cp "$SRC/_lib.sh" "$d/"

mk_ticket(){ printf 'tier: strong\nbranch: feat/%s\ndepends_on: %s\nowns: x/%s.py\nwork_class: ci-infra\n' \
             "$1" "$2" "$1" > "$d/board/$1.md"; }
mk_dep(){    printf 'tier: strong\nbranch: feat/%s\nowns: x/%s.py\nwork_class: ci-infra\n' \
             "$1" "$1" > "$d/board/$1.md"; }
mk_marker(){ printf '2026-01-01T00:00:00Z\tmerged:%s\tbranch:feat/%s\n' "$2" "$1" > "$d/state/done/$1"; }

mk_dep DEP-OK;    mk_marker DEP-OK "$OKSHA"
mk_dep DEP-STALE; mk_marker DEP-STALE "$STALESHA"
mk_dep DEP-NONE   # no done-marker => not merged
mk_ticket TICK-OK    "DEP-OK"
mk_ticket TICK-STALE "DEP-STALE"
mk_ticket TICK-NOMARK "DEP-NONE"
printf 'tier: strong\nbranch: feat/free\nowns: x/free.py\nwork_class: ci-infra\n' > "$d/board/TICK-FREE.md"

run(){ VERIFY_MERGED_REPO="$P" BASE_INTEGRITY_OFFLINE=1 bash "$d/checks/base-integrity.sh" "$@"; }

# (1) base contains the prereq -> GREEN
rc=0; out="$(run TICK-OK 2>&1)" || rc=$?
[ "$rc" = 0 ] && ok "1 base contains prereq -> GREEN" || bad "1 base contains prereq -> GREEN (exit $rc)"
printf '%s\n' "$out" | grep -q "GREEN" || bad "1 emits GREEN line"

# (2) base MISSING the prereq (stale integration) -> RED, names the dep   [LOAD-BEARING]
rc=0; out="$(run TICK-STALE 2>&1)" || rc=$?
[ "$rc" = 1 ] && ok "2 stale base missing prereq -> RED" || bad "2 stale base missing prereq -> RED (exit $rc)"
printf '%s\n' "$out" | grep -q "DEP-STALE" && ok "2 RED names the missing dep DEP-STALE" \
                                           || bad "2 RED names the missing dep DEP-STALE"

# (3) dep never merged (no marker) -> RED
rc=0; out="$(run TICK-NOMARK 2>&1)" || rc=$?
[ "$rc" = 1 ] && ok "3 unmerged dep -> RED" || bad "3 unmerged dep -> RED (exit $rc)"
printf '%s\n' "$out" | grep -qi "not merged" || bad "3 RED explains dep not merged"

# (4) no depends_on -> GREEN
rc=0; run TICK-FREE >/dev/null 2>&1 || rc=$?
[ "$rc" = 0 ] && ok "4 no-deps ticket -> GREEN" || bad "4 no-deps ticket -> GREEN (exit $rc)"

# (5) --base <ref containing the prereq> -> GREEN (base ref is honored, not hardcoded to origin/master)
rc=0; run TICK-STALE --base integration >/dev/null 2>&1 || rc=$?
[ "$rc" = 0 ] && ok "5 --base integration (contains prereq) -> GREEN" || bad "5 --base integration -> GREEN (exit $rc)"

# (6) FAIL-ON-REVERT: neuter the merge-base ancestry check -> STALE ticket wrongly passes.
rev="$d/checks/base-integrity.reverted.sh"
sed 's#git -C "\$repo" merge-base --is-ancestor "\$sha" "\$base_ref" 2>/dev/null#true#' \
    "$d/checks/base-integrity.sh" > "$rev"
rc=0; VERIFY_MERGED_REPO="$P" BASE_INTEGRITY_OFFLINE=1 bash "$rev" TICK-STALE >/dev/null 2>&1 || rc=$?
[ "$rc" = 0 ] && ok "6 reverting the ancestry check flips STALE to GREEN (check is load-bearing)" \
             || bad "6 reverted gate should pass STALE (got exit $rc) — sed did not neuter the core check"

rm -rf "$d" "$P"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BASE-INTEGRITY TESTS PASS"
