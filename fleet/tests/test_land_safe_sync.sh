#!/usr/bin/env bash
# test_land_safe_sync.sh — FAIL-ON-REVERT self-test for LAND-SH-SAFE-SYNC.
#
# Guards the HARD INVARIANT: land.sh's step-7 base sync must NEVER destroy uncommitted or
# untracked work. The old code did `git checkout base && git reset --hard origin/base`, which
# wiped a whole session's dirty tree. These cases drive the real sync path (land.sh --sync-only)
# against isolated fixture repos with a REAL uncommitted tracked edit + a REAL untracked file
# and assert BOTH SURVIVE. Revert safe_sync_base() to `reset --hard` (+ `clean -fd`) and the
# dirty work is destroyed → these go RED.
#
# Cases:
#   T1  dirty ON base  → sync SKIPPED loudly; tracked edit + untracked file both survive
#   T2  dirty off base (feature branch, origin base AHEAD) → stash→FF→pop; both survive AND
#       local base fast-forwarded to origin
#   T3  clean tree, origin base AHEAD → base fast-forwards (positive path, no reset)
#   T4  clean tree, local base DIVERGED from origin → abort loudly, ref NOT force-moved
#
# Run:  bash fleet/tests/test_land_safe_sync.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAND="$SRC/land.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

DIRTY_LINE="uncommitted-edit-must-survive"
UNTRACKED_MARK="untracked-must-survive"

# Build: bare origin + a working clone. `base_ahead=1` pushes an extra commit to origin so the
# local base is strictly behind (a real fast-forward is possible).
make_fixture(){
  local base_ahead="${1:-}"
  local root; root="$(mktemp -d)"
  local origin="$root/origin.git" work="$root/work"
  git init -q --bare "$origin"
  git clone -q "$origin" "$work" 2>/dev/null
  git -C "$work" config user.email t@t; git -C "$work" config user.name t
  git -C "$work" checkout -q -b master 2>/dev/null || git -C "$work" checkout -q master
  printf 'base\n' > "$work/tracked.txt"
  git -C "$work" add -A && git -C "$work" commit -q -m base
  git -C "$work" push -q -u origin master 2>/dev/null
  if [ -n "$base_ahead" ]; then
    # advance origin/master by one commit, then rewind local master so it lags behind origin.
    printf 'base\nremote-advance\n' > "$work/remote.txt"
    git -C "$work" add -A && git -C "$work" commit -q -m advance
    git -C "$work" push -q origin master 2>/dev/null
    git -C "$work" reset -q --hard HEAD~1   # local master now 1 behind origin/master
  fi
  echo "$work"
}

dirty_it(){  # add an uncommitted tracked edit + an untracked file to $1
  printf 'base\n%s\n' "$DIRTY_LINE" >> "$1/tracked.txt"
  printf '%s\n' "$UNTRACKED_MARK" > "$1/untracked.txt"
}
has_dirty_edit(){  grep -q "$DIRTY_LINE" "$1/tracked.txt" 2>/dev/null; }
has_untracked(){   [ -f "$1/untracked.txt" ] && grep -q "$UNTRACKED_MARK" "$1/untracked.txt" 2>/dev/null; }

# ---- T1: dirty ON base — sync must SKIP and preserve everything ----
W="$(make_fixture)"
dirty_it "$W"
( cd "$W" && bash "$LAND" --sync-only "$W" master >/dev/null 2>&1 )
has_dirty_edit "$W" && ok "T1 dirty-on-base: tracked edit survived" || bad "T1 dirty-on-base: tracked edit DESTROYED"
has_untracked  "$W" && ok "T1 dirty-on-base: untracked file survived" || bad "T1 dirty-on-base: untracked file DESTROYED"
rm -rf "$(dirname "$W")"

# ---- T2: dirty off base (feature branch), origin base AHEAD — stash→FF→pop ----
W="$(make_fixture ahead)"
git -C "$W" checkout -q -b feature
dirty_it "$W"
before="$(git -C "$W" rev-parse master)"
( cd "$W" && bash "$LAND" --sync-only "$W" master feature >/dev/null 2>&1 )
has_dirty_edit "$W" && ok "T2 dirty-off-base: tracked edit survived" || bad "T2 dirty-off-base: tracked edit DESTROYED"
has_untracked  "$W" && ok "T2 dirty-off-base: untracked file survived" || bad "T2 dirty-off-base: untracked file DESTROYED"
after="$(git -C "$W" rev-parse master)"
origin_master="$(git -C "$W" rev-parse origin/master)"
[ "$after" = "$origin_master" ] && [ "$after" != "$before" ] \
  && ok "T2 dirty-off-base: local master fast-forwarded to origin" \
  || bad "T2 dirty-off-base: master not fast-forwarded (before=$before after=$after origin=$origin_master)"
rm -rf "$(dirname "$W")"

# ---- T3: clean tree, origin base AHEAD — positive FF path ----
W="$(make_fixture ahead)"
before="$(git -C "$W" rev-parse master)"
( cd "$W" && bash "$LAND" --sync-only "$W" master >/dev/null 2>&1 ); rc=$?
check "T3 clean FF: exit 0" "$rc" "0"
after="$(git -C "$W" rev-parse master)"
[ "$after" = "$(git -C "$W" rev-parse origin/master)" ] && [ "$after" != "$before" ] \
  && ok "T3 clean FF: master advanced to origin" || bad "T3 clean FF: master not advanced"
rm -rf "$(dirname "$W")"

# ---- T4: clean tree, local base DIVERGED — must abort loudly, NOT force the ref ----
W="$(make_fixture ahead)"
# create a local-only commit on master so it diverges from origin (non-fast-forward)
printf 'local-only\n' > "$W/local.txt"
git -C "$W" add -A && git -C "$W" commit -q -m local-divergence
diverged="$(git -C "$W" rev-parse master)"
out="$( cd "$W" && bash "$LAND" --sync-only "$W" master 2>&1 )"
after="$(git -C "$W" rev-parse master)"
[ "$after" = "$diverged" ] && ok "T4 divergence: local master NOT force-reset (work preserved)" \
                           || bad "T4 divergence: local master was moved (lost local commit!)"
echo "$out" | grep -qi "DIVERGED" && ok "T4 divergence: warned loudly" || bad "T4 divergence: no loud warning"
rm -rf "$(dirname "$W")"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LAND-SAFE-SYNC TESTS PASS"
