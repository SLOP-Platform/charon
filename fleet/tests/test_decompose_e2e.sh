#!/usr/bin/env bash
# test_decompose_e2e.sh — DEC-E2E. Prove the FULL decomposer pipeline (fleet/decompose.sh
# driving decompose_surface + decompose_planner + intake.assert_disjoint_waves) splits one
# real, R46-shaped BROAD ticket into >=2 DISJOINT, single-file, dependency-chained board
# sub-tickets — end to end, not just the driver's synthetic validate/emit unit tests
# (see fleet/tests/test_dec_driver.sh, which this complements rather than duplicates).
#
# Fixture: fleet/tests/fixtures/e2e-broad-ticket.md — modeled on fleet/board/R46-BALANCE-WIRE.md
# ("wire an object through build_server + a config module, into a decrement path"), but
# using dedicated non-existent `_e2e_fixture_*` paths rather than the REAL gateway.py /
# balance.py — those real files are currently owned (no dep ordering to us) by other live
# tickets (GRACEFUL-DEGRADE, PRICING-LIMITS-CHECKER, PROVIDER-PROBE-FIX, R46-BALANCE-WIRE
# itself), so emitting fixture sub-tickets that also own them would produce a genuine
# validate_board.sh owns-collision against the LIVE board — same reason
# test_dec_driver.sh's fixtures are `_decdrv_fixture_alpha/beta.py`, not real files.
#
# The live model needed for the REAL decompose_planner is not always configured (CI has
# none), so by default this test drives the pipeline with a DETERMINISTIC MOCK plan via
# decompose.sh's DEC_PLAN_CMD seam — a realistic R46-style 2-way split (decrement-path
# module first, build_server/config-wiring module depends_on it). Everything downstream
# of the plan (step-3 validate, step-4 emit) is the REAL fleet/decompose.sh code; only the
# plan SOURCE is swapped, exactly like test_dec_driver.sh.
#
# `--live` (opt-in, not run in CI / by default): additionally invokes the REAL
# decompose_planner (no DEC_PLAN_CMD) against the same fixture, IF a trusted, non-detained
# planner model is configured (WORK-DECOMPOSER's own requirement) — dogfood only,
# best-effort (WARN, not FAIL, on a live hiccup); skipped cleanly with no model configured.
#
# FAIL-ON-REVERT: case (i)'s ">=2 disjoint single-file" assertions go RED if the driver's
# split/validate/emit logic ever regresses (e.g. collapses to one god-ticket, or lets
# overlapping owns through); case (ii) directly proves the overlap-refusal path using this
# same fixture's files. Any board fixtures emitted (mocked or live) are removed on exit;
# the live board is left at its baseline validate_board.sh state.
#
# Run:  bash fleet/tests/test_decompose_e2e.sh          (mocked only, CI-safe, deterministic)
#       bash fleet/tests/test_decompose_e2e.sh --live   (+ dogfood the real planner, opt-in)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"      # the fleet/ dir
DRIVER="$SRC/decompose.sh"
REAL_BOARD="$SRC/board"
FIXTURE="$SRC/tests/fixtures/e2e-broad-ticket.md"
CHARON_SRC="${CHARON_SRC:-/home/stack/code/charon/src}"
CHARON_REPO="${CHARON_REPO:-/home/stack/code/charon}"
TICKET_ID="E2E-FIXTURE-BROAD"
PREFIX="e2e-fixture-"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

[ -f "$FIXTURE" ] || { echo "test_decompose_e2e.sh: FATAL: fixture missing: $FIXTURE" >&2; exit 2; }

TMP="$(mktemp -d)"
LIVE_EMITTED=()
# Any children emitted into the REAL board (mocked case (i), or a --live run) are removed
# here no matter how the test exits — never leave fixtures on the live board.
cleanup(){
  rm -f "$REAL_BOARD/$PREFIX"*.md
  for f in "${LIVE_EMITTED[@]:-}"; do [ -n "$f" ] && rm -f "$f"; done
  rm -rf "$TMP"
}
trap cleanup EXIT

FIX_BAL="src/charon/_e2e_fixture_balance_decrement.py"
FIX_GW="src/charon/_e2e_fixture_gateway_wire.py"

echo "=== (i) GREEN: mocked R46-style 2-way split, full pipeline through decompose.sh ==="

# ---- deterministic mock plan (what a real DEC-PLANNER would return for this fixture) --
cat > "$TMP/plan_ok.json" <<EOF
{"units":[
  {"id":"e2e-fixture-balance-seed","goal":"seed the decrement-path module from provider config","accept":["revert the balance decrement seeding -> RED"],"owns":["$FIX_BAL"],"depends_on":[],"tier":"med"},
  {"id":"e2e-fixture-gateway-wire","goal":"wire build_server's config object to construct + pass the balance tracker","accept":["revert the build_server construction -> RED"],"owns":["$FIX_GW"],"depends_on":["e2e-fixture-balance-seed"],"tier":"med"}
]}
EOF

# baseline validate_board exit BEFORE emitting anything into the real board
CHARON_REPO="$CHARON_REPO" bash "$SRC/validate_board.sh" >/dev/null 2>&1; base_rc=$?

out="$(TICKET_FILE="$FIXTURE" BOARD_DIR="$REAL_BOARD" \
       DEC_PLAN_CMD="cat '$TMP/plan_ok.json'" \
       bash "$DRIVER" "$TICKET_ID" 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "mocked split: driver exits 0" || bad "mocked split: driver exits 0 (got $rc: $out)"

n=$(ls "$REAL_BOARD/$PREFIX"*.md 2>/dev/null | wc -l)
[ "$n" -ge 2 ] && ok "mocked split: emitted >=2 board sub-tickets (got $n)" || bad "mocked split: emitted >=2 board sub-tickets (got $n)"

BAL_FILE="$REAL_BOARD/e2e-fixture-balance-seed.md"
GW_FILE="$REAL_BOARD/e2e-fixture-gateway-wire.md"
if [ -f "$BAL_FILE" ] && [ -f "$GW_FILE" ]; then
  has "$(cat "$BAL_FILE")" "parent: $TICKET_ID" "balance-seed sub-ticket has parent set"
  has "$(cat "$GW_FILE")" "parent: $TICKET_ID" "gateway-wire sub-ticket has parent set"

  bal_owns="$(grep '^owns:' "$BAL_FILE" | cut -d: -f2-)"
  gw_owns="$(grep '^owns:' "$GW_FILE" | cut -d: -f2-)"
  case "$bal_owns" in
    *,*) bad "balance-seed owns exactly one file (got: $bal_owns)" ;;
    *) [ -n "${bal_owns// /}" ] && ok "balance-seed owns exactly one file" || bad "balance-seed owns is empty" ;;
  esac
  case "$gw_owns" in
    *,*) bad "gateway-wire owns exactly one file (got: $gw_owns)" ;;
    *) [ -n "${gw_owns// /}" ] && ok "gateway-wire owns exactly one file" || bad "gateway-wire owns is empty" ;;
  esac

  has "$bal_owns" "$FIX_BAL" "balance-seed owns its own fixture file"
  has "$gw_owns" "$FIX_GW" "gateway-wire owns its own fixture file"

  # disjoint owns: each fixture file must appear in ONLY its own sub-ticket
  grep -q -- "$FIX_GW" "$BAL_FILE" && bad "owns are disjoint (gateway-wire file leaked into balance-seed)" \
    || ok "owns are disjoint (gateway-wire file not in balance-seed)"
  grep -q -- "$FIX_BAL" "$GW_FILE" && bad "owns are disjoint (balance-seed file leaked into gateway-wire)" \
    || ok "owns are disjoint (balance-seed file not in gateway-wire)"

  has "$(cat "$GW_FILE")" "depends_on: e2e-fixture-balance-seed" "dependency chain preserved (gateway-wire -> balance-seed)"
  has "$(cat "$GW_FILE")" "dep-kind: build" "gateway-wire's real dep is marked (WCI dep-kind: build)"
else
  bad "expected both balance-seed + gateway-wire sub-ticket files to exist"
fi

# The emitted sub-tickets must be BOARD-VALID: validate_board must not regress from baseline.
CHARON_REPO="$CHARON_REPO" bash "$SRC/validate_board.sh" >/dev/null 2>&1; after_rc=$?
[ "$after_rc" = "$base_rc" ] && ok "emitted sub-tickets keep validate_board at baseline (rc=$after_rc)" \
  || bad "emitted sub-tickets regressed validate_board (baseline=$base_rc, after=$after_rc)"

rm -f "$REAL_BOARD/$PREFIX"*.md

echo
echo "=== (ii) FAIL-ON-REVERT: overlapping-owns split of the SAME fixture MUST be refused ==="
# Isolated temp board so a (wrongly) emitted ticket cannot reach the live board.
mkdir -p "$TMP/board2"
cat > "$TMP/plan_overlap.json" <<EOF
{"units":[
  {"id":"e2e-fixture-balance-seed","goal":"own shared","accept":["x"],"owns":["$FIX_GW"],"depends_on":[],"tier":"med"},
  {"id":"e2e-fixture-gateway-wire","goal":"own shared too","accept":["y"],"owns":["$FIX_GW"],"depends_on":[],"tier":"med"}
]}
EOF
out="$(TICKET_FILE="$FIXTURE" BOARD_DIR="$TMP/board2" \
       DEC_PLAN_CMD="cat '$TMP/plan_overlap.json'" \
       bash "$DRIVER" "$TICKET_ID" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "overlap variant: driver REFUSES (non-zero exit)" \
  || bad "overlap variant: driver REFUSES (got rc=0 — validate step reverted?)"
n=$(ls "$TMP/board2"/*.md 2>/dev/null | wc -l)
[ "$n" = "0" ] && ok "overlap variant: emitted ZERO sub-tickets" \
  || bad "overlap variant: emitted ZERO sub-tickets (got $n — overlapping owns leaked to board)"

echo
echo "=== (iii) --live: real decompose_planner dogfood (opt-in; skipped w/o --live or a configured model) ==="
if [ "${1:-}" != "--live" ]; then
  echo "SKIP: pass --live to run the REAL decompose_planner against this fixture (not run by default / in CI)"
else
  trusted="$(PYTHONPATH="$CHARON_SRC" python3 -c '
try:
    from charon.recommend import _find_trusted_models
    from charon import secrets
    print(len(_find_trusted_models(secrets.config_dir())))
except Exception:
    print(0)
' 2>/dev/null)"
  trusted="${trusted:-0}"
  if ! [ "$trusted" -ge 1 ] 2>/dev/null; then
    echo "SKIP: --live requested but no trusted, non-detained planner model is configured (WORK-DECOMPOSER requires one) — mocked case (i) above already proves the pipeline"
  else
    echo "live: $trusted trusted model(s) configured — invoking the REAL decompose_planner"
    CHARON_REPO="$CHARON_REPO" bash "$SRC/validate_board.sh" >/dev/null 2>&1; live_base_rc=$?
    out="$(TICKET_FILE="$FIXTURE" BOARD_DIR="$REAL_BOARD" CHARON_SRC="$CHARON_SRC" \
           bash "$DRIVER" "$TICKET_ID" 2>"$TMP/live.err")"; rc=$?
    if [ "$rc" = "0" ] && [ -n "$out" ]; then
      mapfile -t LIVE_EMITTED <<<"$out"
      n=${#LIVE_EMITTED[@]}
      echo "live: real planner emitted $n sub-ticket(s):"
      printf '  %s\n' "${LIVE_EMITTED[@]}"
      # Disjointness is already ENFORCED by the driver itself (fail-loud on overlap, see
      # case (ii)); this is a dogfood sanity read, not a second hard CI gate.
      if [ "$n" -ge 2 ]; then
        echo "PASS (dogfood): real planner split the fixture into >=2 sub-tickets"
      else
        echo "WARN (dogfood): real planner returned $n unit(s) for a 2-module fixture (non-blocking)"
      fi
      CHARON_REPO="$CHARON_REPO" bash "$SRC/validate_board.sh" >/dev/null 2>&1; live_after_rc=$?
      [ "$live_after_rc" = "$live_base_rc" ] \
        && echo "PASS (dogfood): live-emitted sub-tickets keep validate_board at baseline" \
        || echo "WARN (dogfood): live-emitted sub-tickets changed validate_board's exit ($live_base_rc -> $live_after_rc)"
    else
      echo "WARN (dogfood): real planner run failed (rc=$rc) — non-blocking, see below:"
      sed 's/^/  /' "$TMP/live.err" 2>/dev/null
    fi
  fi
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DEC-E2E TESTS PASS"
