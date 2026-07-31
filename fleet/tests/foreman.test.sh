#!/usr/bin/env bash
# foreman.test.sh — e2e test of fleet/foreman.sh against an ISOLATED fixture fleet
# (FOREMAN_FLEET override; real check scripts symlinked, fixture board/state).
# Covers: starving detection, PARKED report-not-clear, STALE quarantine cleared,
# SPLITTABLE quarantine KEPT (won't re-spin), and a claimable tier reported fed.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qiF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qiF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

D="$(mktemp -d)"
# symlink real scripts foreman + its callees need; fixture board/ + state/ are our own
for x in foreman.sh claim.sh _lib.sh repo-registry.sh loop-guard.sh validate_board.sh \
         model-detention.sh leak-guard.sh tier-models.tsv wci-contention.sh; do
  [ -e "$SRC/$x" ] && ln -s "$SRC/$x" "$D/$x"
done
ln -s "$SRC/checks" "$D/checks"
mkdir -p "$D/board" "$D/state/done" "$D/state/loop-guard" "$D/state/claims" "$D/state/submitted"

mk(){ # mk <id> <tier> <difficulty> <owns> [extra-line]
  { echo "repo: charon-private"; echo "tier: $2"; echo "difficulty: $3"; echo "work_class: rig-meta"
    echo "branch: feat/${1,,}"; echo "owns: $4"; echo "depends_on:"; [ -n "${5:-}" ] && echo "$5"; } > "$D/board/$1.md"; }

# a genuinely claimable strong ticket (single surface) -> strong is FED
mk FED-OK strong 2 "fleet/a.sh"
# a parked frontier ticket -> reported, never cleared
mk PARKED-ONE frontier 2 "fleet/b.sh" "parked: true"
# a STALE quarantine on a single-surface ticket (passes gate) -> --fix CLEARS
mk STALE-Q economy 2 "fleet/c.sh"; : > "$D/state/loop-guard/STALE-Q"
# a SPLITTABLE quarantine (diff>=3, 2 real source surfaces, unjustified) -> --fix KEEPS
mk SPLIT-Q economy 4 "src/x.py, src/y.py"; : > "$D/state/loop-guard/SPLIT-Q"

out="$(FOREMAN_FLEET="$D" bash "$D/foreman.sh" --fix 2>&1)"

has "$out" "FED-OK"                 "(a) claimable ticket surfaces / tier fed"
has "$out" "[LOW]" "(a2) almost-empty tier flagged LOW (proactive)"
has "$out" "PARKED-ONE"             "(b) parked ticket is reported"
no  "$out" "cleared quarantine PARKED-ONE" "(b) parked ticket is NOT auto-cleared"
has "$out" "DID: cleared quarantine STALE-Q"    "(c) stale single-surface quarantine IS cleared"
[ ! -e "$D/state/loop-guard/STALE-Q" ] && ok "(c) STALE-Q loop-guard marker removed" || bad "(c) STALE-Q marker still present"
has "$out" "SPLIT-Q" "(d) splittable quarantine is flagged KEEP (won't re-spin)"
[ -e "$D/state/loop-guard/SPLIT-Q" ] && ok "(d) SPLIT-Q marker preserved" || bad "(d) SPLIT-Q marker wrongly removed"
# fail-on-revert crux: the smart-clear gate. If foreman cleared blindly (revert), (d) flips.

rm -rf "$D"

# --- (e)(f)(g) EXIT-CODE CONTRACT -------------------------------------------------------------
# A starving tier is a SUPPLY state, not a gate failure; it used to return the SAME rc=1 as a
# genuine failure, so every naive `if foreman.sh; then` caller read "nothing queued" as "broken".
# Each case below builds its OWN fixture fleet: sibling state (a leftover claim, a cleared
# quarantine) has repeatedly produced false greens here, so no case may inherit another's dir.
mkfleet(){ # mkfleet -> prints a fresh isolated fleet dir
  local d; d="$(mktemp -d)"
  for x in foreman.sh claim.sh _lib.sh repo-registry.sh loop-guard.sh validate_board.sh \
           model-detention.sh leak-guard.sh tier-models.tsv wci-contention.sh; do
    [ -e "$SRC/$x" ] && ln -s "$SRC/$x" "$d/$x"
  done
  ln -s "$SRC/checks" "$d/checks"
  mkdir -p "$d/board" "$d/state/done" "$d/state/loop-guard" "$d/state/claims" "$d/state/submitted"
  printf '%s' "$d"
}
mkt(){ # mkt <dir> <id> <tier> <difficulty> <owns>
  { echo "repo: charon-private"; echo "tier: $3"; echo "difficulty: $4"; echo "work_class: rig-meta"
    echo "branch: feat/${2,,}"; echo "owns: $5"; echo "depends_on:"; } > "$1/board/$2.md"; }

# (e) STARVING board -> must NOT return the error rc, but MUST still report starvation loudly.
# REVERT LINE (foreman.sh): in the verdict block, change the starving branch back to
#   `say "== FOREMAN VERDICT: [FAIL] STARVING TIERS:$starving =="; rc=1`
# -> (e1) goes RED (rc becomes 1) while (e2)/(e3) stay green, proving (e1) fails for its OWN reason.
E="$(mkfleet)"   # empty board: every tier starves, no collision, no quarantine
out_e="$(FOREMAN_FLEET="$E" bash "$E/foreman.sh" 2>&1)"; rc_e=$?
[ "$rc_e" -ne 1 ] && ok "(e1) starving board does NOT return the ERROR rc (got $rc_e)" \
                  || bad "(e1) starving board returned the ERROR rc 1 -- supply state read as failure"
has "$out_e" "[STARVE]"  "(e2) starving board still PRINTS the loud per-tier starvation report"
has "$out_e" "[ADVISORY] STARVING TIERS" "(e3) verdict names starvation as an ADVISORY, not a FAIL"
# (e4) the opt-in: blocking on starvation must be explicit, never a side effect of the rc.
# REVERT LINE (foreman.sh): delete `[ "$STRICT_SUPPLY" = 1 ] && [ "$rc" = "$EXIT_OK" ] && rc="$EXIT_SUPPLY"`
S="$(mkfleet)"
FOREMAN_FLEET="$S" bash "$S/foreman.sh" --strict-supply >/dev/null 2>&1; rc_s=$?
[ "$rc_s" -eq 10 ] && ok "(e4) --strict-supply opts IN to a distinct supply rc (10)" \
                   || bad "(e4) --strict-supply did not return 10 (got $rc_s)"
rm -rf "$E" "$S"

# (f) GENUINE error -> MUST return the error rc, distinguishable from starvation.
# REVERT LINE (foreman.sh): delete the `[ -d "$BOARD" ] || die ...` / `[ -r "$BOARD" ] ... || die`
# preconditions -> (f1)/(f2) go RED (an unreadable board silently reports as merely starved).
F1="$(mkfleet)"; rm -rf "$F1/board"          # board absent
FOREMAN_FLEET="$F1" bash "$F1/foreman.sh" >/dev/null 2>&1; rc_f1=$?
[ "$rc_f1" -eq 1 ] && ok "(f1) absent board returns the ERROR rc 1" \
                   || bad "(f1) absent board did not return rc 1 (got $rc_f1)"
F2="$(mkfleet)"; chmod 000 "$F2/board"       # board unreadable
FOREMAN_FLEET="$F2" bash "$F2/foreman.sh" >/dev/null 2>&1; rc_f2=$?
chmod 755 "$F2/board"
[ "$rc_f2" -eq 1 ] && ok "(f2) unreadable board returns the ERROR rc 1" \
                   || bad "(f2) unreadable board did not return rc 1 (got $rc_f2)"
# (f3) bad input is an error too.
# REVERT LINE (foreman.sh): change the arg-loop `*) die "unknown argument ...` back to ignoring it.
F3="$(mkfleet)"; mkt "$F3" FED-A strong 2 "fleet/a.sh"
FOREMAN_FLEET="$F3" bash "$F3/foreman.sh" --bogus-flag >/dev/null 2>&1; rc_f3=$?
[ "$rc_f3" -eq 1 ] && ok "(f3) unknown flag returns the ERROR rc 1" \
                   || bad "(f3) unknown flag was silently ignored (got $rc_f3)"
rm -rf "$F1" "$F2" "$F3"

# (g) HEALTHY board -> success. Needs >LOW_WATER claimable in EVERY tier or a tier starves.
# REVERT LINE (foreman.sh): set `rc="$EXIT_ERROR"` unconditionally in the verdict block
# -> (g1) goes RED on its own fed fixture (no starvation, no collision present to blame).
G="$(mkfleet)"
for t in frontier strong economy; do
  for i in 1 2 3; do mkt "$G" "FED-${t}-$i" "$t" 2 "fleet/${t}$i.sh"; done
done
out_g="$(FOREMAN_FLEET="$G" bash "$G/foreman.sh" 2>&1)"; rc_g=$?
[ "$rc_g" -eq 0 ] && ok "(g1) healthy fed board returns success rc 0" \
                  || bad "(g1) healthy fed board returned rc $rc_g"
no "$out_g" "[STARVE]" "(g2) healthy board raises no false starvation"
rm -rf "$G"

# (h) the cadence dispatcher must MIRROR the contract, not re-derive it from the text.
# REVERT LINE (foreman-cadence.sh): restore the old text-sniff
#   `if printf '%s\n' "$out" | grep -qiE '\[STARVE\]|\[COLLISION\]'; then ... return 1`
# -> (h1) goes RED (starvation makes every trigger report failure again).
CAD="$(mkfleet)"; [ -e "$SRC/foreman-cadence.sh" ] && ln -s "$SRC/foreman-cadence.sh" "$CAD/foreman-cadence.sh"
# PLANE-CANARY-WIRE: every foreman-cadence trigger now also carries a FAIL-CLOSED plane-canary
# surface, so a fixture fleet that does not provision the detector is RED BY DESIGN (an absent
# detector is not a pass — that is the entire point of the wiring). Seed a self-contained GREEN
# plane via plane-canary.sh's documented PC_* seams so this case keeps measuring what it is
# actually about: a mere SUPPLY state must not read as a failure.
[ -e "$SRC/plane-canary.sh" ] && ln -s "$SRC/plane-canary.sh" "$CAD/plane-canary.sh"
: > "$CAD/fx-canary.sh"; : > "$CAD/fx-canary.test.sh"
printf 'this layer fires fx-canary.sh\n' > "$CAD/fx-timer-src.sh"
printf 'fx\tfx-canary.sh\tfx-canary.test.sh\ttimer\tFX-FIXTURE\n' > "$CAD/plane-canary-registry.tsv"
out_h="$(FOREMAN_CADENCE_FLEET="$CAD" FOREMAN_FLEET="$CAD" \
         PC_ROOT="$CAD" PC_REGISTRY="$CAD/plane-canary-registry.tsv" \
         PC_RUNLOG="$CAD/state/pc-runlog.tsv" PC_PLANES="fx" \
         PC_SRC_TIMER="$CAD/fx-timer-src.sh" \
         bash "$CAD/foreman-cadence.sh" session-start 2>&1)"; rc_h=$?
[ "$rc_h" -eq 0 ] && ok "(h1) cadence session-start on a starving board does NOT fail (rc 0)" \
                  || bad "(h1) cadence returned rc $rc_h on a mere supply state"
has "$out_h" "[STARVE]" "(h2) cadence still surfaces the loud starvation report"
rm -rf "$CAD"

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL FOREMAN TESTS PASS" || exit 1
