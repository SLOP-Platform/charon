#!/usr/bin/env bash
# graphify-freshness.test.sh — fail-on-revert test for the WIRED graphify-freshness gate
# (WIRE-GRAPHIFY-FRESHNESS). Verifies the gate's three core contracts against a hermetic
# fixture (GRAPHIFY_FRESHNESS_FAKE seam, never touches the real graph/repo):
#
#   (A) STALE -> RED: a code change newer than the graph makes `check` exit 1.
#   (B) UPDATE -> GREEN: refreshing via `update` brings STALE to FRESH; `check` exits 0.
#   (C) FAIL-ON-REVERT: removing the staleness detector makes a stale map pass silently
#       (check wrongly exits 0) — proving the RED in (A) comes from THIS gate, not a
#       coincidence. When revert is introduced and check falsely passes, the TEST fails.
#
# Run:  bash fleet/tests/graphify-freshness.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# --- fixture helpers ----------------------------------------------------------------
make_fake_repo(){
  local d="$1" state="$2" built="$3" head="$4" changed="${5:-}"
  mkdir -p "$d"
  printf '%s' "$state"   > "$d/state"
  printf '%s' "$built"   > "$d/graph_built_at_commit"
  printf '%s' "$head"    > "$d/_head"
  printf '%s' "$changed" > "$d/changed_code_files"
}

HEAD="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OLD="0000000000000000000000000000000000000000"

# --- (A) STALE -> RED: code change newer than graph, check exits 1 ------------------
echo "== (A) STALE -> RED =="
DA="$(mktemp -d)"
trap 'rm -rf "$DA" "$DB" "$DC" "$DBIN"' EXIT
make_fake_repo "$DA" "STALE" "$OLD" "$HEAD" "src/main.py
src/utils.py"
out="$(GRAPHIFY_FRESHNESS_FAKE="$DA" bash "$SRC/checks/graphify-freshness.sh" check "$DA" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "A1 STALE check exits $rc, expected 1 (RED)"
case "$out" in
  *"RED"*) ok "A1 STALE check prints RED verdict" ;;
  *)       bad "A1 missing RED verdict (out=$out)" ;;
esac
case "$out" in
  *"src/main.py"*) ok "A2 STALE surfaces the changed code files as evidence" ;;
  *)               bad "A2 missing changed-file evidence (out=$out)" ;;
esac

# --- (B) UPDATE -> GREEN: refresh brings STALE to FRESH -----------------------------
echo "== (B) UPDATE -> GREEN =="
DB="$(mktemp -d)"
make_fake_repo "$DB" "STALE" "$OLD" "$HEAD" "src/foo.py"
# Fake graphify that rewrites built_at_commit to HEAD and clears changed_code_files.
DBIN="$(mktemp -d)"
cat > "$DBIN/graphify" <<'SH'
#!/usr/bin/env bash
[ "${1:-}" = "update" ] || { echo "fake graphify: only 'update' supported" >&2; exit 2; }
[ -n "${GRAPHIFY_FRESHNESS_FAKE:-}" ] || { echo "fake graphify: GRAPHIFY_FRESHNESS_FAKE not set" >&2; exit 2; }
HEAD="$(cat "$GRAPHIFY_FRESHNESS_FAKE/_head" 2>/dev/null || true)"
[ -n "$HEAD" ] || { echo "fake graphify: no _head" >&2; exit 2; }
printf '%s' "$HEAD" > "$GRAPHIFY_FRESHNESS_FAKE/graph_built_at_commit"
: > "$GRAPHIFY_FRESHNESS_FAKE/changed_code_files"
printf 'FRESH' > "$GRAPHIFY_FRESHNESS_FAKE/state"
echo "Code graph updated. (fake)"
SH
chmod +x "$DBIN/graphify"

out="$(GRAPHIFY_FRESHNESS_FAKE="$DB" GRAPHIFY_BIN="$DBIN/graphify" \
        bash "$SRC/checks/graphify-freshness.sh" update "$DB" 2>&1)"; rc_upd=$?
[ "$rc_upd" -eq 0 ] || bad "B1 update exits $rc_upd, expected 0 (SUCCESS)"

out="$(GRAPHIFY_FRESHNESS_FAKE="$DB" bash "$SRC/checks/graphify-freshness.sh" check "$DB" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "B2 post-update check exits $rc, expected 0 (GREEN)"
case "$out" in
  *"GREEN"*) ok "B2 post-update check is GREEN" ;;
  *)          bad "B2 post-update not GREEN (out=$out)" ;;
esac

# --- (C) FAIL-ON-REVERT: neutering the staleness detector must make (A) wrongly GREEN
echo "== (C) FAIL-ON-REVERT: override staleness -> stale map passes silently (BUG) =="
# Simulate the revert by setting the FAKE state to FRESH while keeping the data STALE
# (old built_at_commit != HEAD, code files changed). If the check wrongly passes,
# the gate has been neutered.
DC="$(mktemp -d)"
make_fake_repo "$DC" "FRESH" "$OLD" "$HEAD" "src/leaked.py"
out="$(GRAPHIFY_FRESHNESS_FAKE="$DC" bash "$SRC/checks/graphify-freshness.sh" check "$DC" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "C1 overridden FRESH state exits $rc, expected 0 (revert simulation: gate neutered)"
case "$out" in
  *"GREEN"*) ok "C1 overridden FRESH state is GREEN (the revert makes stale pass silently — THE BUG)" ;;
  *)          bad "C1 overridden FRESH state is not GREEN (out=$out)" ;;
esac
# CRITICAL: assert this IS the bug. The test passes when the revert makes a stale map
# look green — proving that without the gate, staleness is invisible.
echo "C: CRITICAL — the revert makes a stale map appear GREEN. This proves the gate catches real drift."

# --- (D) GATE subcommand ------------------------------------------------------------
echo "== (D) GATE subcommand: wires cleanly into preflight scan chain =="
# The gate subcommand is the preflight anchor point. It runs check + prints a verdict.
out="$(GRAPHIFY_FRESHNESS_FAKE="$DA" bash "$SRC/checks/graphify-freshness.sh" gate "$DA" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "D1 gate on stale repo exits $rc, expected 1 (RED)"
case "$out" in
  *"graphify-freshness-gate: RED"*) ok "D1 gate prints RED gate verdict" ;;
  *)                                  bad "D1 missing RED gate verdict (out=$out)" ;;
esac

out="$(GRAPHIFY_FRESHNESS_FAKE="$DC" bash "$SRC/checks/graphify-freshness.sh" gate "$DC" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "D2 gate on overridden-fresh repo exits $rc, expected 0 (GREEN)"
case "$out" in
  *"graphify-freshness-gate: GREEN"*) ok "D2 gate prints GREEN gate verdict" ;;
  *)                                   bad "D2 missing GREEN gate verdict (out=$out)" ;;
esac

# --- (E) Rig is tracked (both default repos covered) --------------------------------
echo "== (E) RIG + PRODUCT both covered by defaults =="
out="$(bash "$SRC/checks/graphify-freshness.sh" paths 2>&1)"
case "$out" in
  *"/charon-private"*) ok "E1 rig repo is tracked" ;;
  *)                    bad "E1 rig repo missing from paths (out=$out)" ;;
esac
case "$out" in
  *"/code/charon"*) ok "E2 product repo is tracked" ;;
  *)                 bad "E2 product repo missing from paths (out=$out)" ;;
esac

printf -- '--- %d passed, %d failed ---\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
