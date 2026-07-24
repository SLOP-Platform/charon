#!/usr/bin/env bash
# reconcile-stale-claims.test.sh — FAIL-ON-REVERT self-test for fleet/reconcile-stale-claims.sh.
#
# Hermetic: an ISOLATED product git repo (origin/master ref so done.sh's sha/PR proofs resolve
# offline) + a TEMP fleet state tree. NEVER touches the live fleet/state, the real reds, or
# /home/stack/code/charon. Follows the done-gate.test.sh / test_droid_reap.sh harness pattern.
#
# The three guard properties (revert any one -> the matching assertions flip RED):
#   (a) DEAD-PID + MERGED  -> retired-with-proof: done.sh writes the terminal marker AND the stale
#       claim is removed. If the reconciler stopped driving done.sh, no marker + claim lingers.
#   (b) DEAD-PID + UNMERGED -> HELD + LOUD, NEVER released: the claim file SURVIVES --apply, a HOLD
#       warning naming the ticket is emitted, and NO done marker is written. This is the red line
#       (EGRESS-KEY-CANARY class). Revert the HOLD (release the claim) -> (b1)/(b2) flip RED.
#   (c) LIVE-PID claim is UNTOUCHED: claim marker still present after --apply, no marker written.
#   (d) DRY-RUN default: --apply-less run mutates NOTHING (no marker, claim intact) for a merged
#       claim, and previews "would RETIRE" / "would HOLD" correctly.
#   (e) Idempotency: a second --apply over the post-run state retires nothing new and still HOLDs.
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

# ---- isolated product repo: origin/master ref so done.sh sha-ancestry resolves offline ----
P="$(mktemp -d)"
git -C "$P" init -q
mkdir -p "$P/src"; echo x > "$P/src/present.py"
git -C "$P" add -A; git -C "$P" commit -q -m base
git -C "$P" update-ref refs/remotes/origin/master "$(git -C "$P" rev-parse HEAD)"
export DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P"

# Build a fixture fleet: copy the reconciler + the tools it DRIVES (done.sh + its deps,
# verify-merged.sh) into a temp fleet dir so their FLEET root is the fixture, not the real one.
mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/reconcile-stale-claims.sh" "$SRC/done.sh" "$SRC/retire-done.sh" \
     "$SRC/leak-guard.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$SRC/repo-registry.sh" "$d/" 2>/dev/null
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" \
           "$d/state/claims" "$d/state/needs-push" "$d/tests"
  echo "$d"
}
# A ticket with NO repo: field resolves to the product default (like done-gate's TICK-G); the
# branch-proof path is fully offline via DONE_MERGED_SRC / verify_merged fixture.
add_ticket(){ local d="$1" id="$2" branch="$3"
  printf 'tier: economy\nbranch: %s\nowns: src/present.py\n' "$branch" > "$d/board/$id.md"; }
write_claim(){ local d="$1" id="$2" droid="$3"
  printf '%s %s\n' "$droid" "$(date -u +%FT%TZ)" > "$d/state/claims/$id"; }
# Run the reconciler against the fixture fleet.
run_rec(){ local d="$1"; shift
  RECONCILE_FLEET_DIR="$d" DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" \
    DONE_MERGED_SRC="$MERGED_SRC" VERIFY_MERGED_FIXTURE="$VERIFIED_TXT" \
    bash "$d/reconcile-stale-claims.sh" "$@"; }

# live-PID helper: a real background process we can point a claim at, then reap on exit.
KILL_LIST="$(mktemp)"
# shellcheck disable=SC2154  # `p` is the trap-loop var, assigned by the `for` inside the trap body.
trap 'for p in $(cat "$KILL_LIST" 2>/dev/null); do kill -9 "$p" 2>/dev/null || true; done; rm -f "$KILL_LIST"' EXIT
# NOTE: redirect sleep's fds off the command-substitution pipe, else `$(spawn_live)` blocks until
# the sleep exits (the bg job inherits fd1) — which would also leave the PID dead by check time.
spawn_live(){ sleep 120 >/dev/null 2>&1 & local lp=$!; echo "$lp" >> "$KILL_LIST"; echo "economy-$lp"; }

# ════════════════════════════════════════════════════════════════════════════════════════════
# Fixture: 3 dead claims (merged / unmerged) + 1 live claim, in ONE fleet, to also prove the
# reconciler processes a MIXED board correctly (the real board has all 4 shapes at once).
d="$(mk_fleet)"
add_ticket "$d" "REC-MERGED"   "feat/rec-merged"
add_ticket "$d" "REC-UNMERGED" "feat/rec-unmerged"      # EGRESS-KEY-CANARY class: dead + rejected
add_ticket "$d" "REC-LIVE"     "feat/rec-live"
# merge fixtures: only REC-MERGED's branch has a merged PR; REC-UNMERGED is in NEITHER fixture.
MERGED_SRC="$d/merged.tsv"; printf 'feat/rec-merged\t101\n' > "$MERGED_SRC"
VERIFIED_TXT="$d/verified.txt"; printf 'REC-MERGED\n' > "$VERIFIED_TXT"
# claims: dead PIDs (99998/99999 don't exist) for the two dead cases; a real live PID for REC-LIVE.
write_claim "$d" "REC-MERGED"   "economy-99998"
write_claim "$d" "REC-UNMERGED" "strong-99999"
LIVE_DROID="$(spawn_live)"; write_claim "$d" "REC-LIVE" "$LIVE_DROID"

# ── (d) DRY-RUN default mutates nothing, previews correctly ──────────────────────────────────
echo "== (d) DRY-RUN preview =="
dry="$(run_rec "$d" 2>&1)"; drc=$?
check "(d0) dry-run exit 0" "$drc" "0"
has "$dry" "would RETIRE  REC-MERGED"   "(d1) previews merged claim as would-RETIRE"
has "$dry" "would HOLD    REC-UNMERGED" "(d2) previews unmerged claim as would-HOLD"
has "$dry" "LIVE    REC-LIVE"           "(d3) live claim shown LIVE"
[ -e "$d/state/claims/REC-MERGED" ] && ok "(d4) dry-run did NOT remove the merged claim" || bad "(d4) dry-run removed a claim"
[ -e "$d/state/done/REC-MERGED" ]   && bad "(d5) dry-run wrote a marker" || ok "(d5) dry-run wrote NO marker"

# ── APPLY ────────────────────────────────────────────────────────────────────────────────────
echo "== --apply =="
out="$(run_rec "$d" --apply 2>&1)"; arc=$?
check "(apply exit 0)" "$arc" "0"

# (a) DEAD + MERGED -> retired-with-proof
echo "== (a) dead+merged -> retire-with-proof =="
has "$out" "RETIRED REC-MERGED" "(a1) merged claim reported RETIRED"
[ -e "$d/state/claims/REC-MERGED" ] && bad "(a2) merged claim removed" || ok "(a2) stale claim REMOVED"
if [ -e "$d/state/done/REC-MERGED" ]; then
  ok "(a3) terminal done marker WRITTEN"
  grep -q "merged:#101" "$d/state/done/REC-MERGED" && ok "(a4) marker carries the merge proof (merged:#101)" \
    || bad "(a4) marker carries the merge proof"
else bad "(a3) terminal done marker WRITTEN"; fi

# (b) DEAD + UNMERGED -> HELD + LOUD, NEVER released  (THE RED LINE)
echo "== (b) dead+unmerged -> HELD + LOUD, never released =="
[ -e "$d/state/claims/REC-UNMERGED" ] && ok "(b1) unmerged claim HELD (still present after --apply)" \
  || bad "(b1) unmerged claim was RELEASED — RED LINE VIOLATED"
[ -e "$d/state/done/REC-UNMERGED" ] && bad "(b2) NO marker for unmerged work" || ok "(b2) NO done marker for unmerged work"
has "$out" "HOLD  REC-UNMERGED" "(b3) LOUD HOLD warning names the ticket"

# (c) LIVE-PID claim untouched
echo "== (c) live-PID claim untouched =="
[ -e "$d/state/claims/REC-LIVE" ] && ok "(c1) live claim still present after --apply" || bad "(c1) live claim was touched"
[ -e "$d/state/done/REC-LIVE" ] && bad "(c2) no marker for a live claim" || ok "(c2) no marker written for a live claim"
has "$out" "LIVE    REC-LIVE" "(c3) live claim reported LIVE (untouched)"

# (e) Idempotency: re-run --apply. Merged claim is already gone (skipped); unmerged still HELD.
echo "== (e) idempotency =="
out2="$(run_rec "$d" --apply 2>&1)"; erc=$?
check "(e0) second --apply exit 0" "$erc" "0"
no  "$out2" "RETIRED REC-MERGED" "(e1) already-retired claim is not re-retired"
[ -e "$d/state/claims/REC-UNMERGED" ] && ok "(e2) unmerged claim STILL held on re-run" || bad "(e2) unmerged claim released on re-run"
has "$out2" "HOLD  REC-UNMERGED" "(e3) HOLD still LOUD on re-run"

rm -rf "$d"
echo
echo "════════════════════════════════════════════════"
echo "reconcile-stale-claims.test.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GREEN"
