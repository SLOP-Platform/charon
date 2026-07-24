#!/usr/bin/env bash
# ticket-lifecycle-canary.test.sh — FAIL-ON-REVERT dogfood for TICKET-LIFECYCLE-CANARY
# (the CONTROL-plane full-lifecycle canary; "lifecycle" row of fleet/plane-canary-registry.tsv).
#
# GREEN IS NOT PROOF. Mirrors fleet/tests/flow-canary.test.sh's (DATA-plane) and
# fleet/tests/gate-parity.test.sh's hermetic seed -> RED -> revert pattern, applied to the
# CONTROL plane: mint -> claim -> build -> land -> retire. This test COMPOSES three
# already-built/landing detectors — it re-implements NONE of their logic:
#   fleet/checks/gate-parity.sh      (DONE/master  — GATE-PARITY-LAND-VS-LAUNCH)
#   fleet/reconcile-merged.sh        (DONE/master)
#   fleet/checks/stuck-ticket-loud.sh (STUCK-TICKET-LOUD-VISIBILITY — this canary's real dep)
#
# FULLY HERMETIC: ONE throwaway board+state directory ($D) stands in for the live fleet board
# for ALL THREE composed checks (gate-parity.sh / stuck-ticket-loud.sh via their env-var board
# overrides; reconcile-merged.sh — which has no such override, it derives its own "FLEET" from
# its own script location — via a same-pattern-as-reconcile-merged.test.sh COPY of the script +
# its done.sh/retire-done.sh/leak-guard.sh/_lib.sh/verify-merged.sh dependency set into $D, so
# $D/board and $D/state ARE that copy's board/state too). No live board or PR state is ever
# touched. The real scripts run UNMODIFIED.
#
# Covers (one seed -> RED, fix -> GREEN, revert-the-fix -> RED-again triple per fault, matching
# gate-parity.test.sh's F1a/F1b/F1c pattern):
#   (a) LANDS-UNLAUNCHABLE   — a splittable ticket (difficulty>=3, >1 owned surface) with no
#                              serial_justified reaches LAND -> gate-parity.sh (reused) RED.
#   (b) MERGED-NOT-RETIRED   — a ticket's branch shows up in the merged-PR set but the board
#                              ticket is never retired -> reconcile-merged.sh (reused) auto-
#                              closes it WITH proof; also proves it does NOT silently auto-close
#                              without real merge evidence, and does NOT silently auto-close an
#                              AMBIGUOUS owns-overlap (reused safety behavior).
#   (c) UNCLAIMABLE-P0-SILENT — a P0 ticket depends_on a dissolved (deleted) dependency and an
#                              orphaned state marker with no board ticket -> stuck-ticket-loud.sh
#                              (reused, STUCK-TICKET-LOUD-VISIBILITY) fires LOUD, not silent.
# Then: (d) CLEAN LIFECYCLE -> all three composed checks GREEN together on the same throwaway
# board once every seeded fault is resolved (the "clean lifecycle -> GREEN" baseline).
#
# Run:  bash fleet/tests/ticket-lifecycle-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
GATE="$SRC/checks/gate-parity.sh"
STL="$SRC/checks/stuck-ticket-loud.sh"
RECONCILE_SRC="$SRC/reconcile-merged.sh"
for f in "$GATE" "$STL" "$RECONCILE_SRC"; do
  [ -f "$f" ] || { echo "FAIL: cannot find $f" >&2; exit 1; }
done

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing '$2')
$1"; }
no(){  printf '%s' "$1" | grep -qF -- "$2" && bad "$3 (unexpected '$2')
$1" || ok "$3"; }

# ── the ONE throwaway board+state substrate (never the live board) ─────────────────────────
D="$(mktemp -d)"
mkdir -p "$D/board/archive" "$D/state/done" "$D/state/submitted" "$D/state/claims" \
         "$D/state/needs-push" "$D/state/loop-guard"
# copy reconcile-merged.sh's dependency set alongside it INTO $D so $D itself doubles as that
# script's own "FLEET" (its FLEET var is dirname-of-self, not env-overridable) — exactly the
# pattern fleet/tests/reconcile-merged.test.sh already uses.
cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
   "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$D/"

# isolated product repo with an origin/master ref so `--merged-sha` verification resolves
# offline (same fixture reconcile-merged.test.sh uses).
P="$(mktemp -d)"
git -C "$P" init -q
git -C "$P" commit -q --allow-empty -m base
SHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$SHA"

trap 'rm -rf "$D" "$P"' EXIT

# ── lifecycle helpers: mint -> claim -> build -> land -> retire ────────────────────────────
mint(){ # mint <id> <field-line> ...
  local id="$1"; shift
  : > "$D/board/$id.md"
  local line; for line in "$@"; do printf '%s\n' "$line" >> "$D/board/$id.md"; done
}
retire_mint(){ rm -f "$D/board/$1.md"; }              # off the LIVE board (never the archive here)
claim(){ mkdir -p "$D/state/claims"; touch "$D/state/claims/$1"; }             # CLAIM
release(){ rm -f "$D/state/claims/$1"; touch "$D/state/submitted/$1"; }        # BUILD done -> submit
un_submit(){ rm -f "$D/state/submitted/$1"; }
land_gate_parity(){ # land_gate_parity <id> -> stdout+rc (the LAND gate re-running the launch predicate)
  GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done" bash "$GATE" check "$1" 2>&1
}
run_stuck_loud(){ STL_FLEET_DIR="$D" bash "$STL" 2>&1; }
run_reconcile(){ # run_reconcile <merged-src-tsv>
  DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" RECONCILE_REPO_SLUG="x/y" \
    RECONCILE_MERGED_SRC="$1" bash "$D/reconcile-merged.sh" 2>&1
}
retired(){ [ -e "$D/state/done/$1" ]; }               # RETIRE = a verified done marker exists

# ════════════════════════════════════════════════════════════════════════════════════════════
echo "== (a) LANDS-UNLAUNCHABLE — splittable, unjustified ticket -> gate-parity.sh RED =="
# MINT: difficulty>=3, 2 independent owned surfaces, no serial_justified, not decomposed.
mint LIFECYCLE-A "tier: strong" "difficulty: 4" "priority: 2" "work_class: ci-infra" \
     "branch: feat/lifecycle-a" "owns: src/svc/a.py, src/svc/b.py"
claim LIFECYCLE-A                       # CLAIM
release LIFECYCLE-A                     # BUILD (simulated) -> SUBMIT

out="$(land_gate_parity LIFECYCLE-A)"; rc=$?
[ "$rc" -ne 0 ] && ok "(a-seed) unjustified splittable LIFECYCLE-A -> LAND gate RED (exit $rc)" \
                || bad "(a-seed) unjustified splittable LIFECYCLE-A -> LAND gate GREEN (exit 0 — gap not caught)
$out"
has "$out" "would be refused at launch" "(a-seed) RED names the land-launch parity gap"
has "$out" "LIFECYCLE-A"                "(a-seed) RED names the offending ticket"
has "$out" "SPLITTABLE"                 "(a-seed) RED gives the reason (splittable)"

# FIX: justify the serial run -> LAND gate GREEN -> RETIRE.
retire_mint LIFECYCLE-A
mint LIFECYCLE-A "tier: strong" "difficulty: 4" "priority: 2" "work_class: ci-infra" \
     "branch: feat/lifecycle-a" "owns: src/svc/a.py, src/svc/b.py" \
     "serial_justified: single-operator run, justified"
out="$(land_gate_parity LIFECYCLE-A)"; rc=$?
[ "$rc" -eq 0 ] && ok "(a-fix) justified -> LAND gate GREEN" \
                || bad "(a-fix) justified -> LAND gate still RED (exit $rc — false alarm)
$out"
if [ "$rc" -eq 0 ]; then
  printf '%s\tmerged:local\tbranch:feat/lifecycle-a\n' "$(date -u +%FT%TZ)" > "$D/state/done/LIFECYCLE-A"
fi
retired LIFECYCLE-A && ok "(a-retire) LIFECYCLE-A retired (done marker written) after LAND went GREEN" \
                     || bad "(a-retire) LIFECYCLE-A NOT retired despite GREEN land gate"

# REVERT (fail-on-revert proof): remove the justification -> LAND gate RED again.
retire_mint LIFECYCLE-A
mint LIFECYCLE-A "tier: strong" "difficulty: 4" "priority: 2" "work_class: ci-infra" \
     "branch: feat/lifecycle-a" "owns: src/svc/a.py, src/svc/b.py"
out="$(land_gate_parity LIFECYCLE-A)"; rc=$?
[ "$rc" -ne 0 ] && ok "(a-revert) un-justify -> LAND gate RED again (revert proof, not stuck-GREEN)" \
                || bad "(a-revert) un-justify -> LAND gate GREEN (exit 0 — STUCK-GREEN, revert broken)
$out"
retire_mint LIFECYCLE-A; rm -f "$D/state/done/LIFECYCLE-A" "$D/state/submitted/LIFECYCLE-A"

# ════════════════════════════════════════════════════════════════════════════════════════════
echo
echo "== (b) MERGED-NOT-RETIRED — merged branch, board ticket never retired -> reconcile-merged.sh =="
mint LIFECYCLE-B "tier: economy" "difficulty: 1" "priority: 3" "work_class: ci-infra" \
     "branch: feat/lifecycle-b" "owns: src/svc/lb.py"
claim LIFECYCLE-B; release LIFECYCLE-B    # CLAIM -> BUILD -> SUBMIT

# SEED: a genuine COMPLETION PR (delivers the owns: file, not the ticket's own board file) is
# merged, yet the board ticket is still open and no done marker exists — a lifecycle
# inconsistency that must be flagged/caught, never left silently un-retired.
printf 'feat/lifecycle-b\t%s\tsrc/svc/lb.py\t501\n' "$SHA" > "$D/merged-b.tsv"
if retired LIFECYCLE-B; then bad "(b-seed) LIFECYCLE-B merged upstream but already retired (bad fixture)"
else ok "(b-seed) LIFECYCLE-B merged upstream (branch in the merged-PR set) yet UNRETIRED -> lifecycle RED"
fi

# FIX: run the REAL (reused, unmodified) reconcile-merged.sh against the fixture -> auto-closes
# WITH proof -> RETIRE.
out="$(run_reconcile "$D/merged-b.tsv")"
retired LIFECYCLE-B && ok "(b-fix) reconcile-merged.sh (reused) auto-closed LIFECYCLE-B -> RETIRED" \
                     || bad "(b-fix) reconcile-merged.sh did NOT retire LIFECYCLE-B
$out"
if retired LIFECYCLE-B; then
  marker="$(cat "$D/state/done/LIFECYCLE-B")"
  printf '%s' "$marker" | grep -q "merged:$SHA" \
    && ok "(b-fix) done marker carries merged:<sha> proof (not a bare/--no-verify close)" \
    || bad "(b-fix) done marker missing merged:<sha> proof: $marker"
fi

# REVERT (fail-on-revert proof, part 1): re-seed the identical merged-not-retired state but this
# time feed reconcile-merged.sh an EMPTY merged-PR source (the "compose" input reverted / the
# merge went undiscovered) -> it must NOT silently self-retire without real evidence -> stays RED.
rm -f "$D/state/done/LIFECYCLE-B"
: > "$D/merged-empty.tsv"
out="$(run_reconcile "$D/merged-empty.tsv")"
if retired LIFECYCLE-B; then bad "(b-revert1) reconcile-merged.sh retired LIFECYCLE-B with NO merge evidence — silent auto-close (should stay RED)
$out"
else ok "(b-revert1) no merge evidence -> LIFECYCLE-B stays UNRETIRED (does not silently auto-close, revert proof)"
fi

# REVERT (fail-on-revert proof, part 2): the reused AMBIGUITY safety-net — a merged PR whose
# owns-overlap file is claimed by MORE THAN ONE ticket must NOT be auto-closed by EITHER (the
# old "first glob match wins" bug this guard fixes). Two fresh tickets share one owned file;
# a drifted-branch merge touches it -> neither retires.
mint LIFECYCLE-B2 "tier: economy" "difficulty: 1" "priority: 3" "work_class: ci-infra" \
     "branch: feat/lifecycle-b2-planned" "owns: src/svc/shared.py"
mint LIFECYCLE-B3 "tier: economy" "difficulty: 1" "priority: 3" "work_class: ci-infra" \
     "branch: feat/lifecycle-b3-planned" "owns: src/svc/shared.py"
printf 'feat/DRIFTED-SHARED\t%s\tsrc/svc/shared.py\t509\n' "$SHA" > "$D/merged-ambig.tsv"
out="$(run_reconcile "$D/merged-ambig.tsv")"
if retired LIFECYCLE-B2 || retired LIFECYCLE-B3; then
  bad "(b-revert2) ambiguous shared-owner merge auto-closed a ticket — should have refused (silent auto-close)
$out"
else
  ok "(b-revert2) ambiguous shared-owner merge -> NEITHER ticket auto-closed (reused safety net intact)"
fi
has "$out" "AMBIGUOUS" "(b-revert2) reconcile-merged.sh names the ambiguity, does not silently skip it"

rm -f "$D/board/LIFECYCLE-B.md" "$D/board/LIFECYCLE-B2.md" "$D/board/LIFECYCLE-B3.md" \
      "$D/state/done/LIFECYCLE-B" "$D/state/submitted/LIFECYCLE-B" \
      "$D/merged-b.tsv" "$D/merged-empty.tsv" "$D/merged-ambig.tsv"

# ════════════════════════════════════════════════════════════════════════════════════════════
echo
echo "== (c) UNCLAIMABLE P0 GOES SILENT — dep-dissolved + orphan-marker -> stuck-ticket-loud.sh =="
# MINT: a P0 ticket depending on a dependency that has NO board file / NO archive file / NO
# done marker anywhere — it can NEVER unblock. Never claimed (realistic "went silent" case).
mint LIFECYCLE-C "tier: strong" "difficulty: 2" "priority: 0" "work_class: rig-meta" \
     "branch: feat/lifecycle-c" "depends_on: GHOST-DEP-DISSOLVED"

out="$(run_stuck_loud)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c-seed) P0 with a dissolved dep -> stuck-ticket-loud.sh RED (exit $rc, LOUD)" \
                || bad "(c-seed) P0 with a dissolved dep -> stuck-ticket-loud.sh GREEN (exit 0 — went SILENT)
$out"
has "$out" "STUCK[dep-dissolved]"       "(c-seed) LOUD line names the dep-dissolved category"
has "$out" "LIFECYCLE-C"                "(c-seed) LOUD line names the stuck P0 ticket"
has "$out" "unclaimable ticket(s)"      "(c-seed) summary line confirms it is not silent"

# FIX: the dissolved dependency reappears (mint its board file) -> LIFECYCLE-C is claimable
# again -> stuck-ticket-loud.sh no longer flags it.
mint GHOST-DEP-DISSOLVED "tier: strong" "difficulty: 1" "priority: 1" "work_class: rig-meta" \
     "branch: feat/ghost-dep"
out="$(run_stuck_loud)"; rc=$?
no  "$out" "LIFECYCLE-C"  "(c-fix) dependency restored -> LIFECYCLE-C no longer flagged"
[ "$rc" -eq 0 ] && ok "(c-fix) board clean after fix -> stuck-ticket-loud.sh GREEN (exit 0)" \
                || bad "(c-fix) still RED after fixing the dissolved dep (exit $rc)
$out"

# REVERT (fail-on-revert proof): the dependency disappears again -> RED again.
rm -f "$D/board/GHOST-DEP-DISSOLVED.md"
out="$(run_stuck_loud)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c-revert) dep dissolves again -> stuck-ticket-loud.sh RED again (revert proof)" \
                || bad "(c-revert) dep dissolves again -> stuck-ticket-loud.sh GREEN (exit 0 — STUCK-GREEN, revert broken)
$out"
has "$out" "LIFECYCLE-C" "(c-revert) LOUD line names LIFECYCLE-C again"
rm -f "$D/board/LIFECYCLE-C.md"

echo
echo "-- (c2) orphaned residue: a state marker with NO board ticket -- "
touch "$D/state/claims/GHOST-ORPHAN-MARKER"
out="$(run_stuck_loud)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c2-seed) orphaned claims marker (no board ticket) -> stuck-ticket-loud.sh RED" \
                || bad "(c2-seed) orphaned claims marker -> stuck-ticket-loud.sh GREEN (exit 0 — went SILENT)
$out"
has "$out" "STUCK[orphan-marker]" "(c2-seed) LOUD line names the orphan-marker category"
has "$out" "GHOST-ORPHAN-MARKER"  "(c2-seed) LOUD line names the orphaned marker"

rm -f "$D/state/claims/GHOST-ORPHAN-MARKER"
out="$(run_stuck_loud)"; rc=$?
[ "$rc" -eq 0 ] && ok "(c2-fix) orphan marker removed -> stuck-ticket-loud.sh GREEN" \
                || bad "(c2-fix) orphan marker removed -> still RED (exit $rc)
$out"

touch "$D/state/claims/GHOST-ORPHAN-MARKER"
out="$(run_stuck_loud)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c2-revert) orphan marker reappears -> RED again (revert proof)" \
                || bad "(c2-revert) orphan marker reappears -> GREEN (exit 0 — STUCK-GREEN, revert broken)
$out"
rm -f "$D/state/claims/GHOST-ORPHAN-MARKER"

# ════════════════════════════════════════════════════════════════════════════════════════════
echo
echo "== (d) CLEAN LIFECYCLE — every seeded fault resolved -> all three composed checks GREEN =="
# Board is now empty of every fixture ticket/marker seeded above. Prove ALL THREE checks agree
# it's clean TOGETHER on the SAME throwaway substrate (the "clean lifecycle -> GREEN" baseline
# flow-canary.test.sh's own final revert-to-healthy step proves for the data plane).
gp_out="$(GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done" bash "$GATE" scan 2>&1)"; gp_rc=$?
[ "$gp_rc" -eq 0 ] && ok "(d) clean lifecycle: gate-parity.sh scan GREEN" \
                    || bad "(d) clean lifecycle: gate-parity.sh scan RED (exit $gp_rc)
$gp_out"

stl_out="$(run_stuck_loud)"; stl_rc=$?
[ "$stl_rc" -eq 0 ] && ok "(d) clean lifecycle: stuck-ticket-loud.sh GREEN" \
                     || bad "(d) clean lifecycle: stuck-ticket-loud.sh RED (exit $stl_rc)
$stl_out"

: > "$D/merged-empty2.tsv"
rc_out="$(run_reconcile "$D/merged-empty2.tsv")"; rc_rc=$?
[ "$rc_rc" -eq 0 ] && ok "(d) clean lifecycle: reconcile-merged.sh clean no-op GREEN (exit 0)" \
                    || bad "(d) clean lifecycle: reconcile-merged.sh exit $rc_rc
$rc_out"
printf '%s' "$rc_out" | grep -q "clean (no merged" \
  && ok "(d) reconcile-merged.sh reports clean (nothing left merged-but-open)" \
  || bad "(d) reconcile-merged.sh did not report clean: $rc_out"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL TICKET-LIFECYCLE-CANARY DOGFOOD TESTS PASS"
