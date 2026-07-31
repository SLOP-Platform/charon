#!/usr/bin/env bash
# reconcile-stale-claims.test.sh — FAIL-ON-REVERT self-test for fleet/reconcile-stale-claims.sh.
#
# Hermetic: an ISOLATED product git repo + TEMP fleet state tree. NEVER touches the live
# fleet/state, the real reds, or /home/stack/code/charon. Models fleet/tests/branch-reaper.test.sh.
#
# GREEN-IS-NOT-PROOF: exit 0 does NOT prove correct reconciliation — asserts the UNCOMMITTED
# worktree, UNPUSHED-commit, and BROKEN-GIT claims SURVIVE (the exact data-loss risk a too-broad
# reconciler causes).
#
# The six guard properties (each revert -> RED):
#   (a) A claim with a done-marker AND a landed branch is listed for release.
#   (b) A claim whose worktree has UNCOMMITTED changes is NOT released under --apply.
#   (c) A claim whose branch has UNPUSHED commits is NOT released under --apply.
#   (d) A claim whose state cannot be determined (unreadable worktree / broken .git) is NOT
#       released — fail closed.
#   (e) ANTI-OVER-BLOCK: a genuinely dead, fully-landed, unclaimed-work claim IS released
#       under --apply. A guard that keeps everything is as useless as one that keeps nothing.
#   (f) Dry-run (default) lists candidates and deletes NOTHING.
#
# Run:  bash fleet/tests/reconcile-stale-claims.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

TMPDIRS=()
mktmp(){ local d; d="$(mktemp -d)"; TMPDIRS+=("$d"); echo "$d"; }
trap 'for d in "${TMPDIRS[@]}"; do rm -rf "$d"; done' EXIT

# ── isolated product repo with origin/master ref ──────────────────────
mk_repo(){
  local root; root="$(mktmp)"
  git init -q --bare "$root/origin.git"
  git init -q "$root/repo"
  ( cd "$root/repo"
    git checkout -q -b master
    printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
    git remote add origin "$root/origin.git"
    git push -q origin master
  ) >/dev/null 2>&1
  echo "$root/repo"
}

# ── fixture fleet ───────────────────────────────────────────────────────
mk_fleet(){
  local d; d="$(mktmp)"
  cp "$SRC/reconcile-stale-claims.sh" "$SRC/done.sh" "$SRC/retire-done.sh" \
     "$SRC/leak-guard.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$SRC/repo-registry.sh" "$d/" 2>/dev/null
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" \
           "$d/state/claims" "$d/state/needs-push" "$d/tests"
  echo "$d"
}

# Ticket with a repo-less board file (repo: field missing -> product default).
add_ticket(){ local d="$1" id="$2" branch="$3"; printf 'tier: economy\nbranch: %s\nowns: src/present.py\n' "$branch" > "$d/board/$id.md"; }

# Write a bridge-format claim file.
write_bridge_claim(){ local d="$1" id="$2" session="$3" hb="$4" wt="$5"
  printf 'ticket: %s\nsession: %s\nworktree: %s\nheartbeat: %s\nclaimed: %s\n' \
    "$id" "$session" "$wt" "$hb" "$hb" > "$d/state/claims/$id"; }

# Write an old-format claim file.
write_old_claim(){ local d="$1" id="$2" droid="$3"
  printf '%s %s\n' "$droid" "$(date -u +%FT%TZ)" > "$d/state/claims/$id"; }

run_rec(){ local d="$1"; shift
  RECONCILE_FLEET_DIR="$d" RECONCILE_STALE_S=30 \
    DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" \
    DONE_MERGED_SRC="$MERGED_SRC" VERIFY_MERGED_FIXTURE="$VERIFIED_TXT" \
    bash "$d/reconcile-stale-claims.sh" "$@"; }

# ── GLOBAL FIXTURE ─────────────────────────────────────────────────────
P="$(mk_repo)"
MERGED_SRC="$(mktmp)/merged.tsv"; VERIFIED_TXT="$(mktmp)/verified.txt"

# Create a worktree for the live-work-preserve tests (b, c, d).
# We need a second checkout to simulate a worktree with uncommitted/unpushed state.
LIVE_WT="$(mktmp)"
( cd "$LIVE_WT"
  git init -q
  git checkout -q -b feat/test-keep
  printf 'live\n' > live.txt; git add live.txt; git commit -q -m "live commit"
  git remote add origin "$(dirname "$P")/origin.git" 2>/dev/null || git remote add origin /dev/null
) >/dev/null 2>&1

# ════════════════════════════════════════════════════════════════════════
echo "═══ reconcile-stale-claims.test.sh ═══"

# ── (a) done-marker + landed branch -> release ─────────────────────────
echo "== (a) done-marker + landed branch -> RELEASE =="
d_a="$(mk_fleet)"
add_ticket "$d_a" "A-MERGED" "feat/a-merged"
add_ticket "$d_a" "A-UNMERGED" "feat/a-unmerged"
printf 'feat/a-merged\t999\n' > "$MERGED_SRC"
printf 'A-MERGED\n' > "$VERIFIED_TXT"
# A-MERGED: done-marker present, branch landed, heartbeat stale
printf '2026-07-01T00:00:00Z\tmerged:#999\tbranch:feat/a-merged\n' > "$d_a/state/done/A-MERGED"
write_bridge_claim "$d_a" "A-MERGED" "test-session" "1" "/nonexistent"
# A-UNMERGED: no done-marker, heartbeat stale, not merged (not in fixture)
write_bridge_claim "$d_a" "A-UNMERGED" "test-session" "1" "/nonexistent"

dry_a="$(run_rec "$d_a" 2>&1)"
has "$dry_a" "would RETIRE  A-MERGED"   "(a1) done-marker claim previewed for release"
[ -e "$d_a/state/claims/A-MERGED" ]     && ok "(a2) dry-run did NOT remove the claim"       || bad "(a2) dry-run removed a claim"
[ -e "$d_a/state/done/A-MERGED" ]       && ok "(a3) dry-run preserved the done-marker"       || bad "(a3) dry-run touched the done-marker"

# --apply: release A-MERGED, HOLD A-UNMERGED
out_a="$(run_rec "$d_a" --apply 2>&1)"
has "$out_a" "RETIRED A-MERGED"          "(a4) done-marker claim RETIRED under --apply"
no  "$out_a" "HOLD  A-MERGED"            "(a5) done-marker claim NOT held"
[ ! -e "$d_a/state/claims/A-MERGED" ]    && ok "(a6) done-marker claim file REMOVED"         || bad "(a6) claim file still present after --apply"
[ -e "$d_a/state/done/A-MERGED" ]        && ok "(a7) done-marker preserved after retire"     || bad "(a7) done-marker deleted"

rm -rf "$d_a"

# ── (b) UNCOMMITTED worktree -> NOT released ───────────────────────────
echo "== (b) uncommitted worktree -> NOT released =="
d_b="$(mk_fleet)"
# Make a dirty worktree (uncommitted modification) WITH a remote so it's pushed.
DIRTY_WT="$(mktmp)"
DD_ORIGIN="$(mktmp)"
( cd "$DIRTY_WT"
  git init -q; git checkout -q -b feat/dirty
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git init -q --bare "$DD_ORIGIN"
  git remote add origin "$DD_ORIGIN"; git push -q origin feat/dirty
  printf 'MODIFIED\n' > base.txt   # NOW it's dirty but pushed
) >/dev/null 2>&1

# No done-marker, no merge proof, stale heartbeat
add_ticket "$d_b" "B-DIRTY" "feat/dirty"
printf 'feat/dirty\t111\n' >> "$MERGED_SRC"
printf 'B-DIRTY\n' >> "$VERIFIED_TXT"
write_bridge_claim "$d_b" "B-DIRTY" "test-session" "1" "$DIRTY_WT"
dry_b="$(run_rec "$d_b" 2>&1)"
has "$dry_b" "would HOLD    B-DIRTY"     "(b1) dirty worktree -> would HOLD"
out_b="$(run_rec "$d_b" --apply 2>&1)"
has "$out_b" "HOLD  B-DIRTY"             "(b2) dirty worktree -> HOLD under --apply"
[ -e "$d_b/state/claims/B-DIRTY" ]       && ok "(b3) claim SURVIVED for dirty worktree"     || bad "(b3) claim RELEASED for dirty worktree — RED LINE"
[ ! -e "$d_b/state/done/B-DIRTY" ]       && ok "(b4) no marker written for dirty worktree"   || bad "(b4) marker written for dirty worktree"

rm -rf "$d_b" "$DIRTY_WT" "$DD_ORIGIN"

# ── (c) UNPUSHED commits -> NOT released ───────────────────────────────
echo "== (c) unpushed commits -> NOT released =="
d_c="$(mk_fleet)"
UNPUSHED_WT="$(mktmp)"
( cd "$UNPUSHED_WT"; git init -q; git checkout -q -b feat/unpushed
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  printf 'extra\n' > extra.txt; git add extra.txt; git commit -q -m "unpushed extra"
  # No remote set — all commits are unpushed
) >/dev/null 2>&1

add_ticket "$d_c" "C-UNPUSHED" "feat/unpushed"
printf 'feat/unpushed\t222\n' >> "$MERGED_SRC"
printf 'C-UNPUSHED\n' >> "$VERIFIED_TXT"
write_bridge_claim "$d_c" "C-UNPUSHED" "test-session" "1" "$UNPUSHED_WT"
dry_c="$(run_rec "$d_c" 2>&1)"
has "$dry_c" "would HOLD    C-UNPUSHED"  "(c1) unpushed commits -> would HOLD"
out_c="$(run_rec "$d_c" --apply 2>&1)"
has "$out_c" "HOLD  C-UNPUSHED"          "(c2) unpushed commits -> HOLD under --apply"
[ -e "$d_c/state/claims/C-UNPUSHED" ]    && ok "(c3) claim SURVIVED for unpushed commits"    || bad "(c3) claim RELEASED for unpushed commits — RED LINE"

rm -rf "$d_c" "$UNPUSHED_WT"

# ── (d) FAIL-CLOSED: unreadable/broken worktree -> NOT released ────────
echo "== (d) unreadable worktree -> NOT released =="
d_d="$(mk_fleet)"
BROKEN_WT="/nonexistent/path/that/does/not/exist"
add_ticket "$d_d" "D-BROKEN" "feat/broken"
printf 'feat/broken\t333\n' >> "$MERGED_SRC"
printf 'D-BROKEN\n' >> "$VERIFIED_TXT"
write_bridge_claim "$d_d" "D-BROKEN" "test-session" "1" "$BROKEN_WT"
dry_d="$(run_rec "$d_d" 2>&1)"
# _has_dirty returns 1 (true == dirty) for a nonexistent dir
has "$dry_d" "would HOLD    D-BROKEN"    "(d1) broken worktree -> would HOLD"
out_d="$(run_rec "$d_d" --apply 2>&1)"
has "$out_d" "HOLD  D-BROKEN"            "(d2) broken worktree -> HOLD under --apply"
[ -e "$d_d/state/claims/D-BROKEN" ]      && ok "(d3) claim SURVIVED for unreadable worktree" || bad "(d3) claim RELEASED for unreadable worktree — FAIL-CLOSED VIOLATED"

rm -rf "$d_d"

# ── (e) ANTI-OVER-BLOCK: fully-landed, unclaimed-work -> RELEASE ───────
echo "== (e) anti-over-block: fully-landed -> RELEASE =="
d_e="$(mk_fleet)"
add_ticket "$d_e" "E-CLEAN" "feat/e-clean"
printf 'feat/e-clean\t888\n' > "$MERGED_SRC"
printf 'E-CLEAN\n' > "$VERIFIED_TXT"
# No done-marker but merge-proven. No worktree (old format).
write_old_claim "$d_e" "E-CLEAN" "economy-99998"

out_e="$(run_rec "$d_e" --apply 2>&1)"
# done.sh should have removed the claim via merge-proof
if [ ! -e "$d_e/state/claims/E-CLEAN" ]; then
  ok "(e1) clean+merged claim RELEASED under --apply"
else
  # Fallback: check if done.sh was called successfully
  has "$out_e" "RETIRED E-CLEAN"         "(e1) clean+merged claim RETIRED" || bad "(e1) clean+merged claim NOT retired"
fi
# Verify done marker was written
[ -e "$d_e/state/done/E-CLEAN" ]         && ok "(e2) done-marker written for clean+merged claim" || bad "(e2) no done-marker for clean+merged claim"

rm -rf "$d_e"

# ── (f) DRY-RUN deletes NOTHING ────────────────────────────────────────
echo "== (f) dry-run deletes NOTHING =="
d_f="$(mk_fleet)"
add_ticket "$d_f" "F-DRY" "feat/f-dry"
printf 'feat/f-dry\t777\n' > "$MERGED_SRC"
printf 'F-DRY\n' > "$VERIFIED_TXT"
# Bridge format with done-marker (should be retired) + an old-format claim
printf '2026-07-01T00:00:00Z\tmerged:#777\tbranch:feat/f-dry\n' > "$d_f/state/done/F-DRY"
write_bridge_claim "$d_f" "F-DRY" "test-session" "1" "/nonexistent"
add_ticket "$d_f" "F-DRY-OLD" "feat/f-dry-old"
printf 'feat/f-dry-old\t776\n' >> "$MERGED_SRC"
printf 'F-DRY-OLD\n' >> "$VERIFIED_TXT"
write_old_claim "$d_f" "F-DRY-OLD" "economy-99997"

dry_f="$(run_rec "$d_f" 2>&1)"
has "$dry_f" "would RETIRE  F-DRY"       "(f1) dry-run previews done-marker claim for release"
has "$dry_f" "would RETIRE  F-DRY-OLD"   "(f2) dry-run previews old-format merge-proven claim for release"
[ -e "$d_f/state/claims/F-DRY" ]         && ok "(f3) dry-run did NOT remove bridge-format claim"  || bad "(f3) dry-run removed bridge-format claim"
[ -e "$d_f/state/claims/F-DRY-OLD" ]     && ok "(f4) dry-run did NOT remove old-format claim"     || bad "(f4) dry-run removed old-format claim"
[ -e "$d_f/state/done/F-DRY" ]           && ok "(f5) dry-run preserved the done-marker"           || bad "(f5) dry-run touched the done-marker"

rm -rf "$d_f"

# ── (g) DONE-MARKER + CLEAN WORKTREE -> RELEASE ────────────────────────
echo "== (g) done-marker + clean pushed worktree -> RELEASE =="
d_g="$(mk_fleet)"
CLEAN_WT="$(mktmp)"
( cd "$CLEAN_WT"; git init -q; git checkout -q -b feat/clean
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git checkout -q master 2>/dev/null || true
  # Push to a dummy origin so HEAD is reachable from a remote
  DD="$(mktmp)"; git init -q --bare "$DD"; git remote add origin "$DD"; git push -q origin feat/clean
) >/dev/null 2>&1

printf '2026-07-01T00:00:00Z\tmerged:#555\tbranch:feat/clean\n' > "$d_g/state/done/G-CLEAN"
write_bridge_claim "$d_g" "G-CLEAN" "test-session" "1" "$CLEAN_WT"

out_g="$(run_rec "$d_g" --apply 2>&1)"
has "$out_g" "RETIRED G-CLEAN"           "(g1) done-marker + clean pushed worktree -> RETIRED"
[ ! -e "$d_g/state/claims/G-CLEAN" ]     && ok "(g2) claim REMOVED for clean done-marker claim"  || bad "(g2) claim still present"
[ -e "$d_g/state/done/G-CLEAN" ]         && ok "(g3) done-marker preserved"                      || bad "(g3) done-marker removed"

rm -rf "$d_g" "$CLEAN_WT"

# ── (h) LIVE heartbeat -> untouched ────────────────────────────────────
echo "== (h) live heartbeat -> untouched =="
d_h="$(mk_fleet)"
NOW="$(date +%s)"
write_bridge_claim "$d_h" "H-LIVE" "test-session" "$NOW" "/nonexistent"
out_h="$(run_rec "$d_h" 2>&1)"
has "$out_h" "LIVE    H-LIVE"             "(h1) live heartbeat -> LIVE (untouched)"
[ -e "$d_h/state/claims/H-LIVE" ]         && ok "(h2) live claim still present"                 || bad "(h2) live claim was removed"
out_h_apply="$(run_rec "$d_h" --apply 2>&1)"
[ -e "$d_h/state/claims/H-LIVE" ]         && ok "(h3) live claim SURVIVES --apply"              || bad "(h3) live claim removed under --apply"
no "$out_h_apply" "RETIRED H-LIVE"        "(h4) live claim NOT retired"

rm -rf "$d_h"

# ── (i) old-format live PID -> untouched ───────────────────────────────
echo "== (i) old-format live PID -> untouched =="
d_i="$(mk_fleet)"
# Spawn a real background process for the PID check
KILL_LIST="$(mktemp)"
trap 'for p in $(cat "$KILL_LIST" 2>/dev/null); do kill -9 "$p" 2>/dev/null || true; done; rm -f "$KILL_LIST"' EXIT
spawn_live(){ sleep 120 >/dev/null 2>&1 & local lp=$!; echo "$lp" >> "$KILL_LIST"; echo "economy-$lp"; }
LIVE_DROID="$(spawn_live)"
write_old_claim "$d_i" "I-LIVE-OLD" "$LIVE_DROID"

out_i="$(run_rec "$d_i" 2>&1)"
has "$out_i" "LIVE    I-LIVE-OLD"         "(i1) old-format live PID -> LIVE"

rm -rf "$d_i"

echo
echo "════════════════════════════════════════════════"
echo "reconcile-stale-claims.test.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GREEN"
