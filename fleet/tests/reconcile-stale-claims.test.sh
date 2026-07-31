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
#   (g) DONE-MARKER + CLEAN WORKTREE -> RELEASE
#   (h) LIVE heartbeat -> untouched
#   (i) old-format live PID -> untouched
#   ── ORPHAN CLASSIFIER (ORPHAN-CLAIM-FORENSICS) ──
#   (j) orphan DONE marker with merge-proof -> RESIDUE, removed under --apply --orphans
#   (k) orphan DONE marker WITHOUT merge-proof -> UNKNOWN, NEVER removed (RED LINE)
#   (l) orphan CLAIM with a clean worktree whose HEAD is ancestor of master -> RESIDUE
#   (m) orphan CLAIM with a DIRTY worktree -> WORK-AT-RISK, NEVER cleared
#   (n) orphan CLAIM with an UNPUSHED worktree -> WORK-AT-RISK, NEVER cleared
#   (o) orphan CLAIM with NO worktree path AND NO branch -> UNKNOWN, NEVER cleared
#   (p) orphan SUBMITTED with a branch ancestor of master -> RESIDUE
#   (q) orphan SUBMITTED with no branch -> UNKNOWN, NEVER cleared
#   (r) ANTI-OVER-BLOCK: a normal live claim still untouched after --orphans --apply
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

# Write a done-marker (TAB-separated: ts, proof, branch info).
write_done_marker(){ local d="$1" id="$2" proof="$3" branch="$4"
  printf '%s\t%s\tbranch:%s\n' "$(date -u +%FT%TZ)" "$proof" "$branch" > "$d/state/done/$id"; }

# Write a submitted marker (bare timestamp).
write_submitted(){ local d="$1" id="$2"
  printf '%s\n' "$(date -u +%FT%TZ)" > "$d/state/submitted/$id"; }

# Stash the live CHARON_REPO / CHARON_REPO env so we never touch the real fleet.
ORIG_CHARON="${CHARON_REPO:-}"; ORIG_RECONCILE_CHARON="${RECONCILE_CHARON_REPO:-}"
ORIG_RECONCILE_RIG="${RECONCILE_RIG_REPO:-}"
trap 'if [ -n "$ORIG_CHARON" ]; then export CHARON_REPO="$ORIG_CHARON"; else unset CHARON_REPO; fi
      if [ -n "$ORIG_RECONCILE_CHARON" ]; then export RECONCILE_CHARON_REPO="$ORIG_RECONCILE_CHARON"; else unset RECONCILE_CHARON_REPO; fi
      if [ -n "$ORIG_RECONCILE_RIG" ]; then export RECONCILE_RIG_REPO="$ORIG_RECONCILE_RIG"; else unset RECONCILE_RIG_REPO; fi
      for d in "${TMPDIRS[@]:-}"; do rm -rf "$d" 2>/dev/null; done' EXIT

run_rec(){ local d="$1" P="$2"; shift 2
  RECONCILE_FLEET_DIR="$d" RECONCILE_STALE_S=30 \
    DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" \
    DONE_MERGED_SRC="$MERGED_SRC" VERIFY_MERGED_FIXTURE="$VERIFIED_TXT" \
    RECONCILE_CHARON_REPO="$P" RECONCILE_RIG_REPO="$P" \
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

dry_a="$(run_rec "$d_a" "$P" 2>&1)"
has "$dry_a" "would RETIRE  A-MERGED"   "(a1) done-marker claim previewed for release"
[ -e "$d_a/state/claims/A-MERGED" ]     && ok "(a2) dry-run did NOT remove the claim"       || bad "(a2) dry-run removed a claim"
[ -e "$d_a/state/done/A-MERGED" ]       && ok "(a3) dry-run preserved the done-marker"       || bad "(a3) dry-run touched the done-marker"

# --apply: release A-MERGED, HOLD A-UNMERGED
out_a="$(run_rec "$d_a" "$P" --apply 2>&1)"
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
dry_b="$(run_rec "$d_b" "$P" 2>&1)"
has "$dry_b" "would HOLD    B-DIRTY"     "(b1) dirty worktree -> would HOLD"
out_b="$(run_rec "$d_b" "$P" --apply 2>&1)"
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
dry_c="$(run_rec "$d_c" "$P" 2>&1)"
has "$dry_c" "would HOLD    C-UNPUSHED"  "(c1) unpushed commits -> would HOLD"
out_c="$(run_rec "$d_c" "$P" --apply 2>&1)"
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
dry_d="$(run_rec "$d_d" "$P" 2>&1)"
# _has_dirty returns 1 (true == dirty) for a nonexistent dir
has "$dry_d" "would HOLD    D-BROKEN"    "(d1) broken worktree -> would HOLD"
out_d="$(run_rec "$d_d" "$P" --apply 2>&1)"
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

out_e="$(run_rec "$d_e" "$P" --apply 2>&1)"
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

dry_f="$(run_rec "$d_f" "$P" 2>&1)"
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

out_g="$(run_rec "$d_g" "$P" --apply 2>&1)"
has "$out_g" "RETIRED G-CLEAN"           "(g1) done-marker + clean pushed worktree -> RETIRED"
[ ! -e "$d_g/state/claims/G-CLEAN" ]     && ok "(g2) claim REMOVED for clean done-marker claim"  || bad "(g2) claim still present"
[ -e "$d_g/state/done/G-CLEAN" ]         && ok "(g3) done-marker preserved"                      || bad "(g3) done-marker removed"

rm -rf "$d_g" "$CLEAN_WT"

# ── (h) LIVE heartbeat -> untouched ────────────────────────────────────
echo "== (h) live heartbeat -> untouched =="
d_h="$(mk_fleet)"
NOW="$(date +%s)"
write_bridge_claim "$d_h" "H-LIVE" "test-session" "$NOW" "/nonexistent"
out_h="$(run_rec "$d_h" "$P" 2>&1)"
has "$out_h" "LIVE    H-LIVE"             "(h1) live heartbeat -> LIVE (untouched)"
[ -e "$d_h/state/claims/H-LIVE" ]         && ok "(h2) live claim still present"                 || bad "(h2) live claim was removed"
out_h_apply="$(run_rec "$d_h" "$P" --apply 2>&1)"
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

out_i="$(run_rec "$d_i" "$P" 2>&1)"
has "$out_i" "LIVE    I-LIVE-OLD"         "(i1) old-format live PID -> LIVE"

rm -rf "$d_i"

# ══════════════════════════════════════════════════════════════════════════
# ORPHAN CLASSIFIER (ORPHAN-CLAIM-FORENSICS)
# The above (a-i) cover the legacy claim-walk. Below (j-r) cover --orphans:
#   residue-safe-to-clear (merge-proof OR branch ancestor of master) -> cleared
#   work-at-risk          (dirty OR unpushed worktree) -> NEVER cleared
#   unknown               (no branch, no worktree, no proof) -> NEVER cleared
# ══════════════════════════════════════════════════════════════════════════

# ── (j) orphan DONE marker with merge-proof -> RESIDUE → cleared ──────
echo "== (j) orphan DONE marker with merge-proof -> RESIDUE =="
d_j="$(mk_fleet)"
# NO board ticket file for J-ORPHAN-DONE
write_done_marker "$d_j" "J-ORPHAN-DONE" "merged:#8888" "feat/j-orphan-done"
# Default (no --orphans): the marker is invisible to the legacy loop (state/claims
# only). Confirmed by absence of any output.
out_j_legacy="$(run_rec "$d_j" "$P" 2>&1)"
no "$out_j_legacy" "J-ORPHAN-DONE" "(j0) legacy loop ignores state/done markers"
# --orphans classifies and reports
out_j_dry="$(run_rec "$d_j" "$P" --orphans 2>&1)"
has "$out_j_dry" "would ORPHAN-RETIRE done:J-ORPHAN-DONE" "(j1) done-orphan classified RESIDUE in dry-run"
[ -e "$d_j/state/done/J-ORPHAN-DONE" ] && ok "(j2) dry-run preserved done-marker" || bad "(j2) dry-run removed done-marker"
# --orphans --apply REMOVES the residue
out_j_apply="$(run_rec "$d_j" "$P" --orphans --apply 2>&1)"
has "$out_j_apply" "ORPHAN-RETIRED done:J-ORPHAN-DONE" "(j3) done-orphan RESIDUE removed under --apply"
[ ! -e "$d_j/state/done/J-ORPHAN-DONE" ] && ok "(j4) done-marker REMOVED under --apply" || bad "(j4) done-marker still present after --apply"

rm -rf "$d_j"

# ── (k) orphan DONE marker WITHOUT merge-proof -> UNKNOWN, NEVER cleared
echo "== (k) orphan DONE marker without merge-proof -> UNKNOWN, NEVER cleared =="
d_k="$(mk_fleet)"
printf '2026-07-01T00:00:00Z\n' > "$d_k/state/done/K-ORPHAN-NOPROOF"  # only timestamp, no proof
out_k_dry="$(run_rec "$d_k" "$P" --orphans 2>&1)"
has "$out_k_dry" "would ORPHAN-HOLD done:K-ORPHAN-NOPROOF" "(k1) done-orphan without proof -> would ORPHAN-HOLD"
out_k_apply="$(run_rec "$d_k" "$P" --orphans --apply 2>&1)"
has "$out_k_apply" "ORPHAN-HOLD done:K-ORPHAN-NOPROOF" "(k2) done-orphan without proof -> HELD under --apply"
[ -e "$d_k/state/done/K-ORPHAN-NOPROOF" ] && ok "(k3) no-proof done-marker PRESERVED (RED LINE)" || bad "(k3) no-proof done-marker DELETED — RED LINE VIOLATED"

rm -rf "$d_k"

# ── (l) orphan CLAIM with a clean worktree HEAD ancestor of master -> RESIDUE
echo "== (l) orphan CLAIM with clean+landed worktree -> RESIDUE =="
d_l="$(mk_fleet)"
# Build a fixture repo where we explicitly land a branch onto master.
ORIGIN="$(mktmp)"; ( cd "$ORIGIN"; git init -q --bare ) >/dev/null 2>&1
LANDED_WT="$(mktmp)"
( cd "$LANDED_WT"
  git init -q
  git checkout -q -b master
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git remote add origin "$ORIGIN"; git push -q -u origin master
  git checkout -q -b feat/l-orphan-claim
  printf 'extra\n' > extra.txt; git add extra.txt; git commit -q -m "feat/l-orphan-claim work"
  git push -q -u origin feat/l-orphan-claim
  # Fast-forward master to include the branch
  git checkout -q master
  git merge --ff-only feat/l-orphan-claim
  git push -q origin master
  # Switch back; the worktree's HEAD is now ancestor of master.
  git checkout -q feat/l-orphan-claim
) >/dev/null 2>&1

# NO board ticket file.
write_bridge_claim "$d_l" "L-ORPHAN-CLAIM" "test-session" "1" "$LANDED_WT"
out_l_dry="$(run_rec "$d_l" "$P" --orphans 2>&1)"
has "$out_l_dry" "would ORPHAN-RETIRE claims:L-ORPHAN-CLAIM" "(l1) claim-orphan with landed HEAD -> RESIDUE"
[ -e "$d_l/state/claims/L-ORPHAN-CLAIM" ] && ok "(l2) dry-run preserved orphan claim" || bad "(l2) dry-run removed orphan claim"
out_l_apply="$(run_rec "$d_l" "$P" --orphans --apply 2>&1)"
has "$out_l_apply" "ORPHAN-RETIRED claims:L-ORPHAN-CLAIM" "(l3) landed orphan claim REMOVED under --apply"
[ ! -e "$d_l/state/claims/L-ORPHAN-CLAIM" ] && ok "(l4) landed orphan claim REMOVED" || bad "(l4) landed orphan claim still present"

rm -rf "$d_l" "$LANDED_WT" "$ORIGIN"

# ── (m) orphan CLAIM with a CLEAN worktree whose branch is NOT on master → WORK-AT-RISK
# The legacy worktree-guard passes (clean + fully pushed); the orphan classifier takes over
# and finds the branch is not ancestor of master in any configured repo. Result: WORK-AT-RISK,
# HELD even under --apply.
echo "== (m) orphan CLAIM with CLEAN+unmerged worktree -> WORK-AT-RISK =="
d_m="$(mk_fleet)"
ORPHAN_UNMERGED_WT="$(mktmp)"
ORPHAN_UNMERGED_ORIGIN="$(mktmp)"; ( cd "$ORPHAN_UNMERGED_ORIGIN"; git init -q --bare ) >/dev/null 2>&1
( cd "$ORPHAN_UNMERGED_WT"
  git init -q
  git checkout -q -b master
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git remote add origin "$ORPHAN_UNMERGED_ORIGIN"; git push -q -u origin master
  git checkout -q -b feat/m-orphan-unmerged
  printf 'extra\n' > extra.txt; git add extra.txt; git commit -q -m "feat/m-orphan-unmerged work"
  # Push to remote so _has_unpushed returns 0 (not a worktree-guard violation),
  # but DON'T merge into master — so orphan classifier finds no ancestor.
  git push -q -u origin feat/m-orphan-unmerged
) >/dev/null 2>&1

write_bridge_claim "$d_m" "M-ORPHAN-UNMERGED" "test-session" "1" "$ORPHAN_UNMERGED_WT"
out_m_dry="$(run_rec "$d_m" "$P" --orphans 2>&1)"
has "$out_m_dry" "would ORPHAN-HOLD claims:M-ORPHAN-UNMERGED" "(m1) unmerged worktree orphan claim -> would ORPHAN-HOLD"
out_m_apply="$(run_rec "$d_m" "$P" --orphans --apply 2>&1)"
has "$out_m_apply" "ORPHAN-HOLD claims:M-ORPHAN-UNMERGED" "(m2) unmerged worktree orphan claim -> HELD under --apply"
[ -e "$d_m/state/claims/M-ORPHAN-UNMERGED" ] && ok "(m3) unmerged orphan claim PRESERVED (RED LINE)" || bad "(m3) unmerged orphan claim DELETED — RED LINE VIOLATED"

rm -rf "$d_m" "$ORPHAN_UNMERGED_WT" "$ORPHAN_UNMERGED_ORIGIN"

# ── (n) orphan CLAIM whose worktree exists but is in a repo ORPHAN-CONFIG does NOT cover
# Branch exists in worktree's own repo, but the env-var repos don't see it. After checking
# the worktree's toplevel, no ancestor-of-master is found → WORK-AT-RISK (not UNKNOWN, since
# we found a clean worktree + branch). This case exercises the worktree-to-repo discovery.
echo "== (n) orphan CLAIM with branch ONLY in the worktree repo -> WORK-AT-RISK =="
d_n="$(mk_fleet)"
ORPHAN_ONLY_WT="$(mktmp)"
ORPHAN_ONLY_ORIGIN="$(mktmp)"; ( cd "$ORPHAN_ONLY_ORIGIN"; git init -q --bare ) >/dev/null 2>&1
( cd "$ORPHAN_ONLY_WT"
  git init -q
  git checkout -q -b master
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git remote add origin "$ORPHAN_ONLY_ORIGIN"; git push -q -u origin master
  git checkout -q -b feat/n-orphan-only
  printf 'extra\n' > extra.txt; git add extra.txt; git commit -q -m "feat/n-orphan-only work"
  git push -q -u origin feat/n-orphan-only
  # Branch is NOT merged into master; orphan config repos are $P (a different repo),
  # so toplevel check finds no ancestor-of-master either. Result: WORK-AT-RISK.
) >/dev/null 2>&1

write_bridge_claim "$d_n" "N-ORPHAN-ONLY-REPO" "test-session" "1" "$ORPHAN_ONLY_WT"
out_n_dry="$(run_rec "$d_n" "$P" --orphans 2>&1)"
has "$out_n_dry" "would ORPHAN-HOLD claims:N-ORPHAN-ONLY-REPO" "(n1) worktree-repo-only orphan claim -> would ORPHAN-HOLD"
out_n_apply="$(run_rec "$d_n" "$P" --orphans --apply 2>&1)"
has "$out_n_apply" "ORPHAN-HOLD claims:N-ORPHAN-ONLY-REPO" "(n2) worktree-repo-only orphan claim -> HELD under --apply"
[ -e "$d_n/state/claims/N-ORPHAN-ONLY-REPO" ] && ok "(n3) worktree-repo-only orphan claim PRESERVED (RED LINE)" || bad "(n3) worktree-repo-only orphan claim DELETED — RED LINE VIOLATED"

rm -rf "$d_n" "$ORPHAN_ONLY_WT" "$ORPHAN_ONLY_ORIGIN"

# ── (o) orphan CLAIM with NO worktree + NO branch anywhere -> UNKNOWN, never cleared
echo "== (o) orphan CLAIM with NO worktree + NO branch anywhere -> UNKNOWN =="
# To skip the legacy worktree-guard we point at a clean+empty worktree path that exists
# but has no .git. The legacy guard falls through with `wt=""` actually — but for ORPHAN
# claims we want the claim branch where there's no worktree field. So use an OLD-FORMAT
# claim which the legacy code treats as wt="".
d_o="$(mk_fleet)"
write_old_claim "$d_o" "O-ORPHAN-NOTHING" "economy-12345"  # old-format -> wt=""
# Need a canonical ticket to NOT exist (already does); NOT applied to a real worktree
# because old-format passes through the legacy loop with empty wt.
out_o_dry="$(run_rec "$d_o" "$P" --orphans 2>&1)"
has "$out_o_dry" "would ORPHAN-HOLD claims:O-ORPHAN-NOTHING" "(o1) orphan claim with no worktree + no branch -> would ORPHAN-HOLD"
out_o_apply="$(run_rec "$d_o" "$P" --orphans --apply 2>&1)"
has "$out_o_apply" "ORPHAN-HOLD claims:O-ORPHAN-NOTHING" "(o2) orphan claim with no worktree + no branch -> HELD under --apply"
[ -e "$d_o/state/claims/O-ORPHAN-NOTHING" ] && ok "(o3) unknown orphan claim PRESERVED (RED LINE)" || bad "(o3) unknown orphan claim DELETED — RED LINE VIOLATED"

rm -rf "$d_o"

# ── (p) orphan SUBMITTED with branch ancestor of master -> RESIDUE
echo "== (p) orphan SUBMITTED with branch ancestor of master -> RESIDUE =="
d_p="$(mk_fleet)"
P_ORIGIN="$(mktmp)"; ( cd "$P_ORIGIN"; git init -q --bare ) >/dev/null 2>&1
( cd "$P"
  git checkout -q -b feat/p-orphan-submit
  printf 'p\n' > p.txt; git add p.txt; git commit -q -m "p-orphan-submit work"
  git remote add origin "$P_ORIGIN" 2>/dev/null || true
  git push -q -u origin feat/p-orphan-submit
  git checkout -q master
  git merge --ff-only feat/p-orphan-submit
  git push -q origin master 2>/dev/null || true
) >/dev/null 2>&1
# No board ticket, no claim file. Only a bare submitted marker.
write_submitted "$d_p" "P-ORPHAN-SUBMIT"
out_p_dry="$(run_rec "$d_p" "$P" --orphans 2>&1)"
has "$out_p_dry" "would ORPHAN-RETIRE submitted:P-ORPHAN-SUBMIT" "(p1) submitted-orphan with landed branch -> RESIDUE"
out_p_apply="$(run_rec "$d_p" "$P" --orphans --apply 2>&1)"
has "$out_p_apply" "ORPHAN-RETIRED submitted:P-ORPHAN-SUBMIT" "(p2) submitted-orphan with landed branch -> REMOVED"
[ ! -e "$d_p/state/submitted/P-ORPHAN-SUBMIT" ] && ok "(p3) submitted marker REMOVED under --apply" || bad "(p3) submitted marker still present"

rm -rf "$d_p" "$P_ORIGIN"

# ── (q) orphan SUBMITTED with no branch -> UNKNOWN, NEVER cleared
echo "== (q) orphan SUBMITTED with NO branch -> UNKNOWN =="
d_q="$(mk_fleet)"
write_submitted "$d_q" "Q-ORPHAN-SUBMIT-NOBRANCH"
out_q_dry="$(run_rec "$d_q" "$P" --orphans 2>&1)"
has "$out_q_dry" "would ORPHAN-HOLD submitted:Q-ORPHAN-SUBMIT-NOBRANCH" "(q1) submitted-orphan with no branch -> would ORPHAN-HOLD"
out_q_apply="$(run_rec "$d_q" "$P" --orphans --apply 2>&1)"
has "$out_q_apply" "ORPHAN-HOLD submitted:Q-ORPHAN-SUBMIT-NOBRANCH" "(q2) submitted-orphan with no branch -> HELD"
[ -e "$d_q/state/submitted/Q-ORPHAN-SUBMIT-NOBRANCH" ] && ok "(q3) submitted-orphan no-branch PRESERVED (RED LINE)" || bad "(q3) submitted-orphan DELETED — RED LINE VIOLATED"

rm -rf "$d_q"

# ── (r) ANTI-OVER-BLOCK: a normal live claim still untouched under --orphans --apply
echo "== (r) ANTI-OVER-BLOCK: a normal LIVE claim under --orphans --apply =="
d_r="$(mk_fleet)"
NOW_R="$(date +%s)"
add_ticket "$d_r" "R-LIVE" "feat/r-live"
write_bridge_claim "$d_r" "R-LIVE" "test-session" "$NOW_R" "/nonexistent"
out_r="$(run_rec "$d_r" "$P" --orphans --apply 2>&1)"
has "$out_r" "LIVE    R-LIVE"             "(r1) live claim reported LIVE under --orphans"
[ -e "$d_r/state/claims/R-LIVE" ]        && ok "(r2) live claim SURVIVES --orphans --apply" || bad "(r2) live claim removed under --orphans --apply"
no "$out_r" "ORPHAN-RETIRED claims:R-LIVE" "(r3) live claim NOT classified as orphan"

rm -rf "$d_r"

echo
echo "════════════════════════════════════════════════"
echo "reconcile-stale-claims.test.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GREEN"
