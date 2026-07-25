#!/usr/bin/env bash
# plane-canary-wire.test.sh — FAIL-ON-REVERT dogfood for PLANE-CANARY-WIRE.
#
# WHAT THIS DEFENDS. fleet/plane-canary.sh was a CORRECT detector with ZERO callers: a
# repo-wide grep found only the script itself and its own dogfood. It was not in preflight,
# not in foreman, not in foreman-cadence, not in CI. Meanwhile 8 of its 10 declared
# control/money planes were RED and nobody acted, because nothing surfaced it. This test
# red-proofs the WIRING and the LOUDNESS, not the detector logic (that is
# fleet/tests/plane-canary.test.sh).
#
# Every scenario runs the REAL fleet/plane-canary.sh and the REAL fleet/foreman-cadence.sh
# against a throwaway fleet under `mktemp -d`, driven purely through their documented env
# seams (PC_* / FOREMAN_CADENCE_FLEET / FOREMAN_FLEET). No network, no live state touched,
# nothing written outside the temp dir. ~2s.
#
# Run:  bash fleet/tests/plane-canary-wire.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CADENCE_SRC="$SRC/foreman-cadence.sh"
CANARY_SRC="$SRC/plane-canary.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }
eqrc(){ [ "$1" = "$2" ] && ok "$3" || bad "$3 (want rc=$2, got rc=$1)"; }

cleanup(){ rm -rf "${T:-}"; }
trap cleanup EXIT
T="$(mktemp -d)"

# --- a throwaway fleet: real scripts symlinked in, everything else fixture ---------------
# ROOT resolves to $FLEET/.. so registry paths like `fleet/x.sh` land under $T/<n>/fleet/.
mkfleet(){
  local d; d="$(mktemp -d "$T/fx.XXXXXX")"
  mkdir -p "$d/fleet/fleet" "$d/fleet/state"
  ln -s "$CANARY_SRC"  "$d/fleet/plane-canary.sh"
  ln -s "$CADENCE_SRC" "$d/fleet/foreman-cadence.sh"
  printf '%s' "$d/fleet"
}

# A GREEN plane needs: canary_script + dogfood_test present on disk, and a wired_in layer
# whose SOURCE text mentions one of their basenames. PC_SRC_TIMER is pointed at a fixture
# file containing that basename, so "wired" is satisfied without touching the real rig.
seed_green_plane(){
  local fleet="$1" root; root="$(cd "$fleet/.." && pwd)"
  mkdir -p "$root/fleet"
  : > "$root/fleet/fx-canary.sh"
  : > "$root/fleet/fx-canary.test.sh"
  printf 'fires fx-canary.sh here\n' > "$fleet/fx-timer-src.sh"
  printf '# plane\tcanary_script\tdogfood_test\twired_in\towner_ticket\n' > "$fleet/plane-canary-registry.tsv"
  printf 'fx\tfleet/fx-canary.sh\tfleet/fx-canary.test.sh\ttimer\tFX-TICKET\n' >> "$fleet/plane-canary-registry.tsv"
}

# A RED plane: declared + registered, but its files do not exist -> "proofless canary".
seed_red_plane(){
  local fleet="$1"
  printf '# plane\tcanary_script\tdogfood_test\twired_in\towner_ticket\n' > "$fleet/plane-canary-registry.tsv"
  printf 'fx\tfleet/absent-canary.sh\tfleet/absent-canary.test.sh\ttimer\tFX-TICKET\n' >> "$fleet/plane-canary-registry.tsv"
}

# Drive plane-canary through its own env seams, isolated from the live rig.
pc_env(){
  local fleet="$1" planes="$2"
  PC_ROOT="$(cd "$fleet/.." && pwd)" \
  PC_REGISTRY="$fleet/plane-canary-registry.tsv" \
  PC_RUNLOG="$fleet/state/pc-runlog.tsv" \
  PC_PLANES="$planes" \
  PC_SRC_TIMER="$fleet/fx-timer-src.sh" \
  PC_SRC_CI="$fleet/fx-timer-src.sh" \
  PC_SRC_PREFLIGHT="$fleet/fx-timer-src.sh" \
  PC_SRC_LAND="$fleet/fx-timer-src.sh" \
  "${@:3}"
}

echo "== (a) THE WIRING ITSELF: foreman-cadence.sh really invokes plane-canary.sh =="
# REVERT LINE (foreman-cadence.sh): delete the `PLANE_CANARY_SH="$FLEET/plane-canary.sh"`
# assignment or the `bash "$PLANE_CANARY_SH" surface` call in cmd_plane_canary -> (a1)/(a2) RED.
# This is the assertion that would have caught the original bug: a detector with no caller.
cad_txt="$(cat "$CADENCE_SRC")"
has "$cad_txt" 'PLANE_CANARY_SH="$FLEET/plane-canary.sh"' "(a1) cadence resolves the plane-canary detector path"
has "$cad_txt" '"$PLANE_CANARY_SH" surface'               "(a2) cadence really EXECUTES the detector (not a comment/TODO)"

# REVERT LINE (foreman-cadence.sh): drop any of these calls from the trigger bodies -> RED.
# The point of the ticket is that the surface rides EVERY trigger, not one inert leg.
for trig in session-start post-land cadence handoff; do
  has "$cad_txt" "cmd_plane_canary \"$trig\"" "(a3) trigger '$trig' carries the plane-canary surface"
done
has "$cad_txt" 'pout="$(cmd_plane_canary "handoff" 2>&1)"' "(a4) handoff leg captures the surface for the handoff markdown (the only leg with a live caller)"

echo "== (b) NO RC MASKING: the wiring is not swallowed by || true =="
# REVERT LINE (foreman-cadence.sh): change the capture to `bash "$PLANE_CANARY_SH" surface || true`
# or append `|| true` to a cmd_plane_canary call -> (b1)/(b2) RED. This is the exact defect
# class the sibling graphify/watchdog legs still carry (`... || true`, rc discarded).
no "$cad_txt" '"$PLANE_CANARY_SH" surface 2>&1 || true' "(b1) detector rc is not discarded with || true"
no "$cad_txt" 'cmd_plane_canary "session-start" || true' "(b2) session-start does not discard the plane rc"
no "$cad_txt" 'cmd_plane_canary "cadence" || true'       "(b3) cadence does not discard the plane rc"
has "$cad_txt" 'set -uo pipefail'                        "(b4) pipefail is set (a masked pipe rc is a silent pass)"

echo "== (c) A RED PLANE PRODUCES A LOUD, NON-ZERO, VISIBLE SIGNAL =="
FR="$(mkfleet)"; seed_red_plane "$FR"
out_c="$(pc_env "$FR" "fx" bash "$FR/plane-canary.sh" surface 2>&1)"; rc_c=$?
eqrc "$rc_c" 1 "(c1) a RED plane exits NON-ZERO"
has "$out_c" "PLANE-CANARY RED:"  "(c2) RED emits the loud banner (not a buried WARN line)"
has "$out_c" "RED planes: fx"     "(c3) the banner NAMES the offending plane"
has "$out_c" "████"               "(c4) banner is visually distinct from surrounding warnings"

# ...and it propagates all the way through the cadence trigger a session actually runs.
out_c5="$(FOREMAN_CADENCE_FLEET="$FR" FOREMAN_FLEET="$FR" \
          pc_env "$FR" "fx" bash "$FR/foreman-cadence.sh" plane-canary 2>&1)"; rc_c5=$?
eqrc "$rc_c5" 1 "(c5) RED propagates through foreman-cadence (rc=1, not masked)"
has "$out_c5" "PLANE-CANARY RED:" "(c6) the banner survives the cadence layer"

echo "== (d) GREEN IS EARNED, NOT ASSUMED: a wired+present plane exits 0 =="
FG="$(mkfleet)"; seed_green_plane "$FG"
out_d="$(pc_env "$FG" "fx" bash "$FG/plane-canary.sh" surface 2>&1)"; rc_d=$?
eqrc "$rc_d" 0 "(d1) a fully wired+present plane exits 0"
has "$out_d" "PLANE-CANARY surface: GREEN" "(d2) GREEN says so explicitly"
no  "$out_d" "PLANE-CANARY RED:"           "(d3) GREEN does not emit the RED banner"

echo "== (e) FAIL-CLOSED: a missing / unrunnable detector is RED, never 'skipped' =="
# REVERT LINE (foreman-cadence.sh): replace cmd_plane_canary's
#   `[ ! -f "$PLANE_CANARY_SH" ] && ... return 1`
# with the sibling legs' fail-OPEN shape (`|| { say "not found"; return 0; }`) -> (e1) RED.
FM="$(mkfleet)"; seed_green_plane "$FM"; rm -f "$FM/plane-canary.sh"
out_e="$(FOREMAN_CADENCE_FLEET="$FM" FOREMAN_FLEET="$FM" \
         bash "$FM/foreman-cadence.sh" plane-canary 2>&1)"; rc_e=$?
eqrc "$rc_e" 1 "(e1) a MISSING detector exits NON-ZERO (fail-closed, not skipped)"
has "$out_e" "detector MISSING" "(e2) the missing detector is named loudly"
no  "$out_e" "skip"             "(e3) a missing detector is never reported as a skip"

echo "== (f) NON-VACUOUS: nothing examined is RED, never a silent pass =="
# REVERT LINE (plane-canary.sh): delete cmd_surface's zero-plane / zero-row guards -> (f1)-(f4)
# RED. An empty plane-set cannot fail, so a GREEN from it is a vacuous pass.
FV="$(mkfleet)"; seed_green_plane "$FV"
out_f="$(pc_env "$FV" "" bash "$FV/plane-canary.sh" surface 2>&1)"; rc_f=$?
eqrc "$rc_f" 1 "(f1) ZERO declared planes exits NON-ZERO"
has "$out_f" "ZERO planes declared" "(f2) the vacuous plane-set is named"

# registry present but with no data rows at all
FE="$(mkfleet)"
printf '# plane\tcanary_script\tdogfood_test\twired_in\towner_ticket\n' > "$FE/plane-canary-registry.tsv"
out_f3="$(pc_env "$FE" "fx" bash "$FE/plane-canary.sh" surface 2>&1)"; rc_f3=$?
eqrc "$rc_f3" 1 "(f3) ZERO registry rows exits NON-ZERO"
has "$out_f3" "ZERO plane rows" "(f3b) the empty scan is named as such"

# registry absent entirely
FN="$(mkfleet)"
out_f4="$(pc_env "$FN" "fx" bash "$FN/plane-canary.sh" surface 2>&1)"; rc_f4=$?
eqrc "$rc_f4" 1 "(f4) an UNREADABLE registry exits NON-ZERO (fail-closed)"
has "$out_f4" "registry unreadable" "(f4b) the unreadable registry is named"

echo "== (g) REMOVING THE WIRING MAKES IT SILENT AGAIN (the revert this test exists for) =="
# Proves the wiring is load-bearing: strip the cmd_plane_canary calls out of a COPY of
# foreman-cadence.sh and the same RED fixture produces no banner and rc 0 — which is exactly
# the state the rig was in before this ticket.
FS="$(mkfleet)"; seed_red_plane "$FS"
rm -f "$FS/foreman-cadence.sh"
sed 's/^\( *\)cmd_plane_canary /\1: # UNWIRED /' "$CADENCE_SRC" > "$FS/foreman-cadence.sh"
out_g="$(FOREMAN_CADENCE_FLEET="$FS" FOREMAN_FLEET="$FS" \
         pc_env "$FS" "fx" bash "$FS/foreman-cadence.sh" cadence 2>&1)"; rc_g=$?
no "$out_g" "PLANE-CANARY RED:" "(g1) with the wiring removed the RED banner disappears"
[ "$rc_g" -eq 0 ] && ok "(g2) with the wiring removed the RED plane is silent (rc=0) — this is the bug being fixed" \
                  || bad "(g2) unwired variant returned rc=$rc_g (expected the silent 0 it used to give)"

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL PLANE-CANARY-WIRE TESTS PASS" || exit 1
