#!/usr/bin/env bash
# plane-canary.test.sh — FAIL-ON-REVERT dogfood for PLANE-CANARY-REGISTRY
# (fleet/plane-canary.sh + fleet/plane-canary-registry.tsv, design of record
# fleet/board/PLANE-CANARY-REGISTRY.md).
#
# GREEN IS NOT PROOF. This is load-bearing GATE infra — the reconciliation leg
# that other gates/canaries are judged against — so a fake-green here is worse
# than none. Each class below SEEDS a real fault and PROVES the runner goes RED
# on it, then GREEN when the single seeded field is reverted, then RED AGAIN when
# re-seeded (so no assertion is a tautology).
#
# FULLY HERMETIC / OFFLINE. A throwaway fixture tree under mktemp -d stands in
# for the repo: a fixture registry TSV, fixture canary/dogfood scripts, and
# fixture firing-layer source files. The REAL fleet/plane-canary.sh is run
# UNMODIFIED against it via its env overrides (PC_ROOT / PC_REGISTRY / PC_PLANES /
# PC_SRC_*). No live network, nothing leaves the box. ~1s.
#
# Covers exactly the classes the ticket's accept criteria name:
#   (base) fully-wired+present+proven single plane            -> reconcile GREEN
#   (a)  blank dogfood_test column        -> reconcile RED "proofless"  (fill -> GREEN)
#   (b)  canary_script file absent        -> reconcile RED "proofless"  (create -> GREEN)
#   (c)  wired_in layer does NOT invoke   -> reconcile RED "unwired"     (wire -> GREEN)
#   (c') wired_in names an unknown layer  -> reconcile RED (fail-closed)
#   (e)  declared plane with no row       -> reconcile RED "declared, no canary"
#   (d)  run --hermetic: one dogfood exits non-zero -> run RED + banner  (fix -> GREEN)
#
# Run:  bash fleet/tests/plane-canary.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
RUNNER="$SRC/plane-canary.sh"
[ -f "$RUNNER" ] || { echo "FAIL: cannot find $RUNNER" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
mkdir -p "$D/fleet/checks" "$D/fleet/tests" "$D/layers"

REG="$D/fleet/plane-canary-registry.tsv"
RUNLOG="$D/runlog.tsv"
CI_SRC="$D/layers/ci.sh"
PF_SRC="$D/layers/preflight.sh"
LAND_SRC="$D/layers/land.sh"
TIMER_SRC="$D/layers/timer.sh"
: > "$CI_SRC"; : > "$PF_SRC"; : > "$LAND_SRC"; : > "$TIMER_SRC"

# PCP = the PC_PLANES override the current scenario runs under.
PCP="alpha"

# tab-join one registry row
row(){ printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5"; }

# run the REAL runner against the fixture tree
pc(){
  PC_ROOT="$D" PC_REGISTRY="$REG" PC_RUNLOG="$RUNLOG" PC_PLANES="$PCP" \
  PC_SRC_CI="$CI_SRC" PC_SRC_PREFLIGHT="$PF_SRC" \
  PC_SRC_LAND="$LAND_SRC" PC_SRC_TIMER="$TIMER_SRC" \
    bash "$RUNNER" "$@" 2>&1
}
cap(){ CAP_OUT="$(pc "$@")"; CAP_RC=$?; }
has(){ printf '%s' "$CAP_OUT" | grep -q "$1"; }

# ── fixture reset: a fully-GREEN single-plane 'alpha' baseline ───────────────
reset_green(){
  PCP="alpha"
  rm -f "$RUNLOG"
  : > "$D/fleet/checks/alpha.sh"
  : > "$D/fleet/tests/alpha.test.sh"
  # wire alpha into the CI firing-layer source (a real basename mention)
  printf 'bash fleet/tests/alpha.test.sh   # alpha canary\n' > "$CI_SRC"
  : > "$PF_SRC"; : > "$LAND_SRC"; : > "$TIMER_SRC"
  row alpha fleet/checks/alpha.sh fleet/tests/alpha.test.sh ci ALPHA-TICKET > "$REG"
}

# ── (base) healthy single-plane -> reconcile GREEN ──────────────────────────
reset_green
cap reconcile
[ "$CAP_RC" -eq 0 ] && ok "(base) wired+present single plane: reconcile GREEN (exit 0)" \
                    || bad "(base) healthy fixture reconcile exit $CAP_RC (expected 0)
$CAP_OUT"
has "reconcile: GREEN" && ok "(base) prints GREEN verdict" || bad "(base) no GREEN verdict"

# ── (a) blank dogfood_test column -> proofless RED; fill -> GREEN ────────────
reset_green
row alpha fleet/checks/alpha.sh "" ci ALPHA-TICKET > "$REG"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(a) blank dogfood_test column: reconcile RED" \
                    || bad "(a) blank dogfood column NOT caught (exit 0)
$CAP_OUT"
has "proofless" && ok "(a) RED line names 'proofless'" || bad "(a) no proofless red line"
# fill it back in -> GREEN
row alpha fleet/checks/alpha.sh fleet/tests/alpha.test.sh ci ALPHA-TICKET > "$REG"
cap reconcile
[ "$CAP_RC" -eq 0 ] && ok "(a-revert) filling dogfood_test -> reconcile GREEN" \
                    || bad "(a-revert) filled column still RED (exit $CAP_RC)
$CAP_OUT"

# ── (b) canary_script file absent -> proofless RED; create -> GREEN ─────────
reset_green
row alpha fleet/checks/ghost.sh fleet/tests/alpha.test.sh ci ALPHA-TICKET > "$REG"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(b) missing canary_script file: reconcile RED" \
                    || bad "(b) missing canary file NOT caught (exit 0)
$CAP_OUT"
has "absent on disk" && ok "(b) RED line names the absent file" || bad "(b) no absent-file red line"
# create the file -> GREEN (alpha.test.sh already wired in CI_SRC)
: > "$D/fleet/checks/ghost.sh"
cap reconcile
[ "$CAP_RC" -eq 0 ] && ok "(b-revert) creating the canary file -> reconcile GREEN" \
                    || bad "(b-revert) created file still RED (exit $CAP_RC)
$CAP_OUT"
# re-seed (remove the file) -> RED again: not a tautology
rm -f "$D/fleet/checks/ghost.sh"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(b-reseed) removing the file again -> RED again (not a tautology)" \
                    || bad "(b-reseed) removed file NOT re-caught (exit 0)
$CAP_OUT"

# ── (c) wired_in layer does NOT invoke -> unwired RED; wire -> GREEN ─────────
reset_green
: > "$PF_SRC"   # preflight source is empty: nothing invokes alpha
row alpha fleet/checks/alpha.sh fleet/tests/alpha.test.sh preflight ALPHA-TICKET > "$REG"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(c) wired_in=preflight but preflight source has no invocation: reconcile RED" \
                    || bad "(c) unwired canary NOT caught (exit 0)
$CAP_OUT"
has "unwired" && ok "(c) RED line names 'unwired'" || bad "(c) no unwired red line"
# add a real invocation to the preflight firing-layer source -> GREEN
printf 'bash fleet/tests/alpha.test.sh   # now wired into preflight\n' >> "$PF_SRC"
cap reconcile
[ "$CAP_RC" -eq 0 ] && ok "(c-revert) adding the invocation -> reconcile GREEN" \
                    || bad "(c-revert) wired but still RED (exit $CAP_RC)
$CAP_OUT"
# re-seed (empty the source) -> RED again: not a tautology
: > "$PF_SRC"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(c-reseed) emptying the firing source again -> RED again (not a tautology)" \
                    || bad "(c-reseed) unwiring NOT re-caught (exit 0)
$CAP_OUT"

# ── (c') fail-closed: an UNRECOGNIZED wired_in layer -> RED ─────────────────
reset_green
row alpha fleet/checks/alpha.sh fleet/tests/alpha.test.sh boguslayer ALPHA-TICKET > "$REG"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(c') unknown wired_in layer 'boguslayer': reconcile RED (fail-closed)" \
                    || bad "(c') unknown layer treated as wired (exit 0) — fail-OPEN bug
$CAP_OUT"
has "unknown-layer" && ok "(c') RED line marks the unknown layer" || bad "(c') no unknown-layer marker"

# ── (e) a declared plane with NO registry row -> "declared, no canary" RED ──
reset_green
PCP="alpha bravo"   # bravo is declared but the registry only has alpha
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(e) declared plane 'bravo' with no row: reconcile RED" \
                    || bad "(e) declared-no-canary NOT caught (exit 0)
$CAP_OUT"
has "declared, no canary" && ok "(e) RED line names 'declared, no canary'" || bad "(e) no declared-no-canary line"

# ── (f) proofless-by-last-run: a recorded non-zero dogfood run -> RED ───────
# canary+dogfood files present AND wired, but the last recorded run failed:
# a wired canary whose fault-seed dogfood is currently failing is untrusted.
reset_green
printf 'fleet/tests/alpha.test.sh\t7\t2026-07-23T00:00:00Z\n' > "$RUNLOG"
cap reconcile
[ "$CAP_RC" -ne 0 ] && ok "(f) present+wired but last dogfood run exited 7: reconcile RED" \
                    || bad "(f) failing last-run NOT caught (exit 0)
$CAP_OUT"
has "proofless" && ok "(f) RED line names 'proofless' (failing fault-seed dogfood)" || bad "(f) no proofless red line"
# clear the failing record -> GREEN (not a tautology: value drives it)
printf 'fleet/tests/alpha.test.sh\t0\t2026-07-23T01:00:00Z\n' > "$RUNLOG"
cap reconcile
[ "$CAP_RC" -eq 0 ] && ok "(f-revert) recording a passing run -> reconcile GREEN" \
                    || bad "(f-revert) passing last-run still RED (exit $CAP_RC)
$CAP_OUT"

# ── (d) run --hermetic aggregation: one dogfood exits non-zero -> RED+banner ─
PCP="p_pass p_fail"
rm -f "$RUNLOG"
: > "$D/fleet/checks/x.sh"
printf '#!/usr/bin/env bash\nexit 0\n'  > "$D/fleet/tests/pass.test.sh"
printf '#!/usr/bin/env bash\nexit 3\n'  > "$D/fleet/tests/fail.test.sh"
{ row p_pass fleet/checks/x.sh fleet/tests/pass.test.sh ci T-PASS
  row p_fail fleet/checks/x.sh fleet/tests/fail.test.sh ci T-FAIL; } > "$REG"
cap run --hermetic
[ "$CAP_RC" -ne 0 ] && ok "(d) run --hermetic with a failing dogfood: exits non-zero (RED)" \
                    || bad "(d) failing dogfood NOT aggregated to RED (exit 0)
$CAP_OUT"
has "run: RED" && ok "(d) prints the loud RED run banner" || bad "(d) no RED run banner
$CAP_OUT"
has "fail.test.sh rc=3" && ok "(d) table shows the failing leg's real exit (rc=3, not pipe-masked)" \
                        || bad "(d) failing leg exit not surfaced (pipe-mask?)
$CAP_OUT"
# fix the failing dogfood -> run GREEN
printf '#!/usr/bin/env bash\nexit 0\n' > "$D/fleet/tests/fail.test.sh"
cap run --hermetic
[ "$CAP_RC" -eq 0 ] && ok "(d-revert) fixing the dogfood -> run --hermetic GREEN (exit 0)" \
                    || bad "(d-revert) all-passing run still RED (exit $CAP_RC)
$CAP_OUT"
has "run: GREEN" && ok "(d-revert) prints the GREEN run banner" || bad "(d-revert) no GREEN run banner"
# re-seed the failure -> RED again: not a tautology
printf '#!/usr/bin/env bash\nexit 3\n' > "$D/fleet/tests/fail.test.sh"
cap run --hermetic
[ "$CAP_RC" -ne 0 ] && ok "(d-reseed) re-breaking the dogfood -> run RED again (not a tautology)" \
                    || bad "(d-reseed) re-broken dogfood NOT re-caught (exit 0)
$CAP_OUT"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL PLANE-CANARY DOGFOOD TESTS PASS"
