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
echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL FOREMAN TESTS PASS" || exit 1
