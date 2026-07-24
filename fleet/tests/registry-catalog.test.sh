#!/usr/bin/env bash
# registry-catalog.test.sh — proves the registry META-CATALOG contracts
# (REGISTRY-META-CATALOG ticket). Two lanes:
#
#   REAL lane (against the shipped catalog + tree):
#     (A) BASELINE GREEN — every convention-named registry on disk is catalogued.
#     (B) ANTI-GOD-FILE — the catalog is INDEX-ONLY: exactly 6 columns per row, and NO
#         catalogued registry's DATA VALUE leaks into the index (structural + content).
#
#   HERMETIC lane (synthetic temp fleet via REGISTRY_CATALOG_FLEET seam):
#     (C) FAIL-ON-REVERT — remove a registry's row from the catalog while it stays on disk
#         -> discovery goes RED. (Proves the RRED comes from THIS gate.)
#     (D) STRAY REGISTRY — drop a new *-registry.tsv into the tree, absent from the catalog
#         -> discovery goes RED and NAMES it.
#     (E) RECONCILE -> GREEN — add the stray to the catalog -> discovery GREEN again.
#     (F) INDEX-ONLY STRUCTURAL RED — a 7-column (data-bearing) row -> RED.
#
# Run:  bash fleet/tests/registry-catalog.test.sh   (exit 0 = all pass)
set -uo pipefail
FLEET_REAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$FLEET_REAL/checks/discover-registries.sh"
CATALOG_REAL="$FLEET_REAL/state/registry-catalog.tsv"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ============================ REAL lane =============================================
echo "== (A) BASELINE GREEN (real catalog + tree) =="
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "A1 real discovery exits $rc, expected 0 (GREEN). out=$out"
[ "$rc" -eq 0 ] && ok "A1 real discovery GREEN — no uncatalogued registries on disk"
case "$out" in *"DISCOVERY VERDICT: GREEN"*) ok "A2 prints GREEN verdict";; *) bad "A2 no GREEN verdict";; esac

echo "== (B) ANTI-GOD-FILE (index-only) =="
# B1: every non-comment row has EXACTLY 6 tab-columns (no data-value column, structurally).
badrows="$(awk -F'\t' '/^#/ || NF==0 {next} NF!=6 {print NR": "NF" cols"}' "$CATALOG_REAL")"
[ -z "$badrows" ] && ok "B1 every catalog row is exactly 6 index columns" || bad "B1 non-6-col rows: $badrows"
# B2: NO catalogued registry's DATA VALUE appears in the catalog. Sample a real data value
#     from two catalogued registries and assert absence — that is the god-file smell.
leak=0
if [ -f "$FLEET_REAL/state/jedi-name-pool.txt" ]; then
  jname="$(grep -m1 -E '^[a-z]' "$FLEET_REAL/state/jedi-name-pool.txt" 2>/dev/null || true)"
  if [ -n "$jname" ] && grep -qF "$jname" "$CATALOG_REAL"; then
    bad "B2 jedi-name-pool DATA value '$jname' leaked into the index (god-file)"; leak=1
  fi
fi
if [ -f "$FLEET_REAL/plane-canary-registry.tsv" ]; then
  pval="$(awk -F'\t' '/^#/||NF<2{next}{print $1; exit}' "$FLEET_REAL/plane-canary-registry.tsv" 2>/dev/null || true)"
  # $1 of plane-canary is a plane like 'data/serving' — a DATA value, must not be in the index.
  if [ -n "$pval" ] && grep -qF "	$pval	" "$CATALOG_REAL"; then
    bad "B2 plane-canary DATA value '$pval' leaked into the index (god-file)"; leak=1
  fi
fi
[ "$leak" -eq 0 ] && ok "B2 no catalogued registry's data value leaked into the index"

# ============================ HERMETIC lane =========================================
# Build a minimal synthetic fleet: fleet/state/registry-catalog.tsv + one convention file.
mk_fleet(){
  local f="$TMP/fleet"; rm -rf "$f"; mkdir -p "$f/state"
  # a convention-named registry ON DISK
  printf '# planeA registry (fixture)\nrowdata\n' > "$f/planeA-registry.tsv"
  # catalog that lists it (6 columns)
  {
    printf '# name\tpurpose\tpath\tschema\towner\tconformance_gate\n'
    printf 'planeA\tfixture registry\tfleet/planeA-registry.tsv\tcol1\tOWNER-X\t-\n'
  } > "$f/state/registry-catalog.tsv"
  echo "$f"
}

echo "== (C) FAIL-ON-REVERT (remove row, keep file) =="
F="$(mk_fleet)"
# sanity: baseline synthetic is GREEN
REGISTRY_CATALOG_FLEET="$F" bash "$GATE" >/dev/null 2>&1 && ok "C0 synthetic baseline GREEN" || bad "C0 synthetic baseline not GREEN"
# revert: strip the planeA row from the catalog while the file stays on disk
grep -v 'planeA' "$F/state/registry-catalog.tsv" > "$F/state/registry-catalog.tsv.new" && mv "$F/state/registry-catalog.tsv.new" "$F/state/registry-catalog.tsv"
out="$(REGISTRY_CATALOG_FLEET="$F" bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "C1 removing the row while file on disk -> RED (rc=$rc)" || bad "C1 expected RED, got GREEN"
case "$out" in *"planeA-registry.tsv"*) ok "C2 RED names the orphaned registry";; *) bad "C2 RED did not name it. out=$out";; esac

echo "== (D) STRAY REGISTRY (add uncatalogued file) =="
F="$(mk_fleet)"
printf '# stray\nx\n' > "$F/state/stray-registry.tsv"
out="$(REGISTRY_CATALOG_FLEET="$F" bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "D1 stray *-registry.tsv on disk -> RED (rc=$rc)" || bad "D1 expected RED, got GREEN"
case "$out" in *"stray-registry.tsv"*) ok "D2 discovery FLAGS the stray by path";; *) bad "D2 stray not named. out=$out";; esac

echo "== (E) RECONCILE -> GREEN (catalog the stray) =="
printf 'stray\tfixture\tfleet/state/stray-registry.tsv\tcol\tOWNER-Y\t-\n' >> "$F/state/registry-catalog.tsv"
REGISTRY_CATALOG_FLEET="$F" bash "$GATE" >/dev/null 2>&1 && ok "E1 cataloguing the stray -> GREEN (reconciled)" || bad "E1 expected GREEN after catalog"

echo "== (F) INDEX-ONLY STRUCTURAL RED (7-col data row) =="
F="$(mk_fleet)"
printf 'planeB\tfixture\tfleet/planeB-registry.tsv\tcol\tOWNER-Z\t-\tLEAKED_DATA_VALUE\n' >> "$F/state/registry-catalog.tsv"
out="$(REGISTRY_CATALOG_FLEET="$F" bash "$GATE" --list 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "F1 a 7-column (data-bearing) row -> RED (anti-god-file structural)" || bad "F1 expected RED on data column, got GREEN"

printf -- '--- %d passed, %d failed ---\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
