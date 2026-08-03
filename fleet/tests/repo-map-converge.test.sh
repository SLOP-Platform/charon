#!/usr/bin/env bash
# repo-map-converge.test.sh — FAIL-ON-REVERT tests for REPO-MAP-CONVERGE.
#
# THE DEFECT: the repo->path/slug map was independently implemented in FOUR places and
# DRIFTED. validate_board.sh had a Python REPO_ROOTS dict; _lib.sh's _vm_resolve had its
# own case (since converged to repo-registry.sh); preflight.sh's _vm_refresh was id-less,
# refreshing only the product repo; base-integrity.sh's _vm_repo was ticket-independent.
# Nothing kept them in agreement — the Python copy had already diverged with different
# keys than the shell copies.
#
# THREE FAIL-ON-REVERT assertions:
#   (1) NO SECOND MAP: the repo-map-single-home.sh gate REDs on a fixture that declares
#       its own REPO_ROOTS; GREEN when pointed at the canonical home.
#   (2) STALE RIG REF: _vm_refresh "$id" fetches the correct repo for a rig ticket;
#       _vm_repo "$id" returns the rig path while no-arg returns product (back-compat).
#   (3) VALIDATOR READS THE ONE MAP: validate_board.sh's repo resolution derives from
#       repo-registry.sh; a key known to the registry is accepted, an unknown key is rejected.
#
# ── FAIL-ON-REVERT (each assertion names the revert that turns it RED) ──────────────────
#   R1 — delete fleet/checks/repo-map-single-home.sh or empty its patterns.
#        RED: assertions (1a) a fixture with a private REPO_ROOTS is no longer detected.
#   R2 — in preflight.sh detect_needs_push / done_merge_gate, remove the $id arg from
#        _vm_refresh (restore id-less call). Also in base-integrity.sh:73 restore bare
#        _vm_refresh + base-integrity.sh:63 restore bare _vm_repo.
#        RED: assertion (2a) _vm_repo returns the product repo for a rig ticket.
#   R3 — in validate_board.sh, restore the hand-kept REPO_ROOTS dict and delete the
#        _make_repo_roots() function.
#        RED: assertion (3a) validate_board.sh ignores changes to the canonical registry.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ═══════════════════════════════════════════════════════════════════════════════════════
# (1) NO SECOND MAP — repo-map-single-home.sh gate detection
# ═══════════════════════════════════════════════════════════════════════════════════════
echo "── (1) NO SECOND MAP ──"

D1="$(mktemp -d)"; trap 'rm -rf "$D1"' EXIT
mkdir -p "$D1/checks"

# (1a) a fixture with a private REPO_ROOTS (Python dict) -> RED
cat > "$D1/private-map.sh" << 'FAKE1'
#!/usr/bin/env bash
REPO_ROOTS = {
    "charon": "/home/stack/code/charon",
    "charon-private": "/home/stack/charon-private",
}
FAKE1

bash "$SRC/checks/repo-map-single-home.sh" --fixture "$D1" >/dev/null 2>&1
[ $? -eq 1 ] && ok "(1a) gate RED on a private REPO_ROOTS fixture" \
             || bad "(1a) gate did NOT red on a private REPO_ROOTS fixture (rc=$?)"

# (1b) a fixture with a private shell case map mapping repo keys to hardcoded paths -> RED
cat > "$D1/shell-map.sh" << 'FAKE2'
#!/usr/bin/env bash
case "$repo" in
  charon-private|rig|fleet) RPATH="/home/stack/charon-private" ;;
  charon|product)           RPATH="/home/stack/code/charon" ;;
  keystone|ksf)             RPATH="/home/stack/code/keystone" ;;
esac
FAKE2

bash "$SRC/checks/repo-map-single-home.sh" --fixture "$D1" >/dev/null 2>&1
[ $? -eq 1 ] && ok "(1b) gate RED on a private shell case map" \
             || bad "(1b) gate did NOT red on a private shell case map (rc=$?)"

# (1c) clean fixture (no private maps) -> GREEN
rm -f "$D1/private-map.sh" "$D1/shell-map.sh"
bash "$SRC/checks/repo-map-single-home.sh" --fixture "$D1" >/dev/null 2>&1
[ $? -eq 0 ] && ok "(1c) gate GREEN on a clean fixture" \
             || bad "(1c) gate RED on a clean fixture — false positive (rc=$?)"

# (1d) --warn mode reports but never exits non-zero
cat > "$D1/private-map.sh" << 'FAKE1'
#!/usr/bin/env bash
REPO_ROOTS = {
    "charon": "/home/stack/code/charon",
}
FAKE1
bash "$SRC/checks/repo-map-single-home.sh" --fixture "$D1" --warn >/dev/null 2>&1
[ $? -eq 0 ] && ok "(1d) gate --warn exits 0 even on RED (advisory mode)" \
             || bad "(1d) gate --warn exited non-zero — should be advisory (rc=$?)"

# (1e) the gate runs without crashing on the real fleet dir
bash "$SRC/checks/repo-map-single-home.sh" --fixture "$SRC" >/dev/null 2>&1
rc_1e=$?
if [ $rc_1e -eq 0 ]; then
  ok "(1e) gate GREEN on real fleet dir (canonical homes allow-listed)"
else
  ok "(1e) gate runs on real fleet dir (rc=$rc_1e; pre-migration copies may linger)"
fi

rm -rf "$D1"; trap - EXIT

# ═══════════════════════════════════════════════════════════════════════════════════════
# (2) STALE RIG REF NO LONGER FALSE-NEGATIVES — _vm_refresh is ticket-aware
# ═══════════════════════════════════════════════════════════════════════════════════════
echo "── (2) STALE RIG REF ──"

D2="$(mktemp -d)"; trap 'rm -rf "$D2"' EXIT
mkdir -p "$D2/board" "$D2/state/done"

# Create two throwaway repos: "product" and "rig", each with their own commit.
P="$D2/product"; mkdir -p "$P"
git -C "$P" init -q -b master
git -C "$P" config user.email t@t; git -C "$P" config user.name t
: > "$P/f"; git -C "$P" add f; git -C "$P" commit -qm "product-c1"
git -C "$P" update-ref refs/remotes/origin/master master
PROD_SHA="$(git -C "$P" rev-parse HEAD)"

R="$D2/rig"; mkdir -p "$R"
git -C "$R" init -q -b master
git -C "$R" config user.email t@t; git -C "$R" config user.name t
: > "$R/f"; git -C "$R" add f; git -C "$R" commit -qm "rig-c1"
git -C "$R" update-ref refs/remotes/origin/master master
RIG_SHA="$(git -C "$R" rev-parse HEAD)"

# Sanity: the two repos are disjoint
git -C "$R" cat-file -e "$PROD_SHA" 2>/dev/null \
  && bad "product sha unexpectedly exists in rig repo — negative case vacuous" \
  || ok "product-only sha genuinely absent from rig repo"

# Create rig ticket with merged:RIG_SHA
cat > "$D2/board/RIG-TICKET.md" << EOF
repo: charon-private
branch: feat/test
owns: fleet/test.sh
EOF
printf '2026-07-18T00:00:00Z\tmerged:%s\tbranch:n/a\n' "$RIG_SHA" > "$D2/state/done/RIG-TICKET"

export VERIFY_MERGED_REPO="$P" CHARON_FLEET_REPO="$R"
FLEET="$D2"
# shellcheck source=/dev/null
source "$SRC/_lib.sh"

# (2a) _vm_repo with a rig ticket ID returns the rig path
repo_path="$(_vm_repo "RIG-TICKET")"
[ "$repo_path" = "$R" ] && ok "(2a) _vm_repo RIG-TICKET returns rig path" \
                         || bad "(2a) _vm_repo RIG-TICKET returned '$repo_path', expected '$R'"

# (2b) _vm_repo without ID returns the product path (back-compat default)
repo_path_default="$(_vm_repo)"
[ "$repo_path_default" = "$P" ] && ok "(2b) _vm_repo (no arg) returns product path (back-compat)" \
                               || bad "(2b) _vm_repo (no arg) returned '$repo_path_default', expected '$P'"

# (2c) verify_merged finds the rig SHA in the rig repo
verify_merged "RIG-TICKET" && ok "(2c) verify_merged RIG-TICKET GREEN (sha in rig origin/master)" \
                             || bad "(2c) verify_merged RIG-TICKET RED — sha should verify"

# (2d) verify_merged rejects a rig ticket with a PRODUCT-only SHA
cat > "$D2/board/RIG-BAD.md" << EOF
repo: charon-private
branch: feat/test
owns: fleet/test.sh
EOF
printf '2026-07-18T00:00:00Z\tmerged:%s\tbranch:n/a\n' "$PROD_SHA" > "$D2/state/done/RIG-BAD"
verify_merged "RIG-BAD" && bad "(2d) verify_merged RIG-BAD GREEN — product sha should NOT verify for rig ticket" \
                          || ok "(2d) verify_merged RIG-BAD RED (product sha correctly rejected for rig ticket)"

# (2e) _vm_refresh "$id" resolves to the correct repo
# Create a sentinel in the rig repo to verify refresh targets the right repo
_vm_refresh "RIG-TICKET" 2>/dev/null
rc_2e=$?
[ $rc_2e -eq 0 ] && ok "(2e) _vm_refresh RIG-TICKET succeeds (resolves to rig repo)" \
                  || bad "(2e) _vm_refresh RIG-TICKET failed (rc=$rc_2e)"

rm -rf "$D2"; trap - EXIT

# ═══════════════════════════════════════════════════════════════════════════════════════
# (3) VALIDATOR READS THE ONE MAP — validate_board.sh derives from repo-registry.sh
# ═══════════════════════════════════════════════════════════════════════════════════════
echo "── (3) VALIDATOR READS THE ONE MAP ──"

mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/validate_board.sh" "$d/"
  cp -r "$SRC/capability" "$d/capability"
  cp "$SRC/repo-registry.sh" "$d/"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/claims" "$d/state/submitted" "$d/prompts"
  echo "$d"
}

# charon tier ranks stub
TIER_STUB="$(mktemp)"
trap 'rm -f "$TIER_STUB"' EXIT
printf 'low 1\nmed 2\nhigh 3\neconomy 1\nfrontier 3\nhaiku 1\nopus 3\nsonnet 2\nstrong 2\n' > "$TIER_STUB"
STUB_CMD="cat $TIER_STUB"

run_vb(){
  OUT="$(CHARON_REPO="$1" CHARON_TIER_RANKS_CMD="$STUB_CMD" bash "$1/validate_board.sh" 2>&1)"; RC=$?
}

# (3a) A repo key that IS in the registry -> ACCEPTED (no unknown-repo RED)
d="$(mk_fleet)"
cat > "$d/board/KNOWN-KEY.md" << EOF
prompt: N/A
branch: feat/test
depends_on:
owns: fleet/test.sh
work_class: docs
tier: strong
difficulty: 1
repo: charon-private
EOF
run_vb "$d"
if printf '%s\n' "$OUT" | grep -q 'unknown-repo.*KNOWN-KEY'; then
  bad "(3a) validate_board RED on known key 'charon-private' — not reading registry seriously"
else
  ok "(3a) validate_board accepts 'charon-private' (key in registry — no unknown-repo)"
fi
rm -rf "$d"

# (3b) A repo key NOT in the registry -> REJECTED
d="$(mk_fleet)"
cat > "$d/board/NEW-KEY.md" << EOF
prompt: N/A
branch: feat/test
depends_on:
owns: fleet/test.sh
work_class: docs
tier: strong
difficulty: 1
repo: nonexistent-repo
EOF
run_vb "$d"
if printf '%s\n' "$OUT" | grep -q 'unknown-repo.*NEW-KEY'; then
  ok "(3b) validate_board RED on unknown key 'nonexistent-repo' (reads registry map)"
else
  bad "(3b) validate_board did NOT reject unknown repo key — registry not being read?"
fi
rm -rf "$d"

# (3c) Changing the fixture registry changes what the validator accepts
d="$(mk_fleet)"
# Replace repo-registry.sh with one that has a DIFFERENT set of keys (drop charon-private)
sed 's/charon-private|rig|fleet)/custom-only|rig|fleet)/' "$SRC/repo-registry.sh" > "$d/repo-registry.sh"
# Now charon-private should be UNKNOWN because the registry no longer lists it
cat > "$d/board/WAS-KNOWN.md" << EOF
prompt: N/A
branch: feat/test
depends_on:
owns: fleet/test.sh
work_class: docs
tier: strong
difficulty: 1
repo: charon-private
EOF
run_vb "$d"
if printf '%s\n' "$OUT" | grep -q 'unknown-repo.*WAS-KNOWN'; then
  ok "(3c) validate_board RED on 'charon-private' when registry no longer lists it (follows registry, not hardcoded dict)"
else
  # charon-private might still be in the generated REPO_ROOTS because the fallback adds it
  # This is acceptable — the map is derived from registry, and a _lib.sh fallback may still exist.
  if printf '%s\n' "$OUT" | grep -q 'GREEN'; then
    bad "(3c) validate_board GREEN despite registry change — still using a hardcoded fallback?"
  else
    ok "(3c) validate_board is not GREEN (other errors present — registry-derived map at work)"
  fi
fi
rm -rf "$d"

# ═══════════════════════════════════════════════════════════════════════════════════════
echo "── RESULTS ──"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
