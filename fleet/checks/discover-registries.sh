#!/usr/bin/env bash
# discover-registries.sh — AUTO-DISCOVERY + FAIL-CLOSED DISCOVERY LEG for the
# registry META-CATALOG (REGISTRY-META-CATALOG ticket, 2026-07-24).
#
# WHAT IT IS
#   The firing half of the registry-of-registries. It scans the tree for registry files BY
#   CONVENTION and reconciles what is ON DISK against fleet/state/registry-catalog.tsv (the
#   INDEX). The whole point is that the index cannot silently go stale: a registry that
#   exists on disk but nobody added to the catalog is exactly the "we can't find our
#   registries" problem this ticket exists to end — so it FAILS CLOSED (exit non-zero).
#
# THE DISCOVERY LEG (fail-closed, the primary contract)
#   For every convention-named registry file found on disk: it MUST appear (by path) in the
#   catalog. Any that do NOT -> RED (exit 1), listed as evidence. This is the leg the
#   fail-on-revert test drives: remove a row from the catalog while the file stays on disk,
#   or drop a stray *-registry.tsv into the tree, and this goes RED.
#
# CONVENTION (case-insensitive): *-registry.tsv, *-registry.txt, *-register.tsv,
#   *-pool.txt, *-pool.tsv. Non-convention registries (e.g. tier-models.tsv) are seeded in
#   the catalog by hand so they are findable; they are simply not auto-DISCOVERED (extra
#   catalog rows are always fine — the fail-closed direction is disk -> catalog).
#
# WHAT IT IS NOT
#   It NEVER mutates the catalog or any registry. Read-only. It REPORTS + returns an exit
#   code; a wiring layer (foreman-cadence.sh cadence) fires it. It does not move any
#   registry's DATA into the index — that would be the god-file the operator forbade.
#
# CATALOG-ENTRY-ABSENT-FROM-DISK is ADVISORY, not fatal: a catalogued registry provisioned
#   by a not-yet-landed sibling ticket (e.g. service-registry.tsv from SERVICE-LIVENESS-
#   WATCHDOG) is a PENDING note, never a false RED. The fail-closed direction is disk->catalog.
#
# Test seam: REGISTRY_CATALOG_FLEET=<dir> overrides the fleet root (points at a fleet/ dir).
#
# Usage:
#   bash fleet/checks/discover-registries.sh          # discovery leg (exit 1 = RED)
#   bash fleet/checks/discover-registries.sh --list    # just print the catalogued registries
set -uo pipefail

FLEET="${REGISTRY_CATALOG_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="$(cd "$FLEET/.." && pwd)"                       # repo root (the dir that contains fleet/)
CATALOG="$FLEET/state/registry-catalog.tsv"

say(){ printf '%s\n' "$*"; }

[ -f "$CATALOG" ] || { say "discover-registries: RED — catalog not found at $CATALOG"; exit 1; }

# --- catalogued paths (column 3), skipping comments/blanks --------------------------
catalog_paths(){ awk -F'\t' '/^#/ || NF<3 {next} {print $3}' "$CATALOG"; }

# --- structural INDEX-ONLY guard (fast, in-gate; the test proves it harder) ---------
# Every non-comment, non-blank row must have EXACTLY the 6 index columns. A row with a 7th
# field is the first sign someone started stuffing data values into the index (god-file).
structural_rc=0
while IFS= read -r line; do
  case "$line" in \#*|"") continue;; esac
  n="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
  if [ "$n" -ne 6 ]; then
    say "discover-registries: RED — catalog row has $n columns (expected 6, index-only): $line"
    structural_rc=1
  fi
done < "$CATALOG"

if [ "${1:-}" = "--list" ]; then
  say "== catalogued registries (index-only) =="
  catalog_paths | sed 's/^/  /'
  exit "$structural_rc"
fi

# --- AUTO-DISCOVERY: convention-named registry files on disk ------------------------
mapfile -t found < <(
  find "$FLEET" -type f \
    \( -iname '*-registry.tsv' -o -iname '*-registry.txt' -o -iname '*-register.tsv' \
       -o -iname '*-pool.txt' -o -iname '*-pool.tsv' \) \
    -not -path '*/session-notes/*' -not -path '*/tests/fixtures/*' -not -path '*/.git/*' \
    2>/dev/null | sort
)

say "== registry discovery (convention scan under $FLEET) =="
say "found ${#found[@]} convention-named registry file(s) on disk"

# Build a lookup of catalogued paths for O(1) membership.
declare -A in_catalog=()
while IFS= read -r p; do [ -n "$p" ] && in_catalog["$p"]=1; done < <(catalog_paths)

uncatalogued=()
for f in "${found[@]}"; do
  rel="${f#$ROOT/}"
  if [ -n "${in_catalog[$rel]:-}" ]; then
    say "  OK   $rel"
  else
    say "  MISS $rel   <- on disk, ABSENT from catalog"
    uncatalogued+=("$rel")
  fi
done

# --- ADVISORY: catalogued but not yet on disk (pending sibling) ---------------------
while IFS= read -r p; do
  [ -n "$p" ] || continue
  if [ ! -f "$ROOT/$p" ]; then
    say "  PENDING $p   (catalogued; file not on disk yet — provisioned by a sibling ticket)"
  fi
done < <(catalog_paths)

# --- verdict ------------------------------------------------------------------------
if [ "${#uncatalogued[@]}" -gt 0 ] || [ "$structural_rc" -ne 0 ]; then
  say ""
  say "== DISCOVERY VERDICT: RED =="
  [ "${#uncatalogued[@]}" -gt 0 ] && say "  ${#uncatalogued[@]} registry file(s) on disk are NOT in the catalog — add a row for each to fleet/state/registry-catalog.tsv:"
  for u in "${uncatalogued[@]}"; do say "    - $u"; done
  [ "$structural_rc" -ne 0 ] && say "  catalog structural guard FAILED (a row is not index-only — 6 columns exactly)"
  exit 1
fi

say ""
say "== DISCOVERY VERDICT: GREEN — every convention-named registry on disk is catalogued =="
exit 0
