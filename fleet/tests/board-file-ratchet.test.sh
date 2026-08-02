#!/usr/bin/env bash
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$SRC/checks/board-file-ratchet.sh"
SCOPE="$SRC/checks/rig-ci-scope.sh"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0
FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

repo(){
  local d
  d="$(mktemp -d)"
  git -C "$d" init -q -b master
  mkdir -p "$d/fleet/board/archive"
  printf 'seed\n' > "$d/README"
  git -C "$d" add -A
  git -C "$d" commit -q -m seed
  printf '%s' "$d"
}
run(){ RATCHET_ROOT="$1" RATCHET_BASE="$2" RATCHET_HEAD="$3" bash "$CHECK" 2>&1; }

r1="$(repo)"
printf 'ticket\n' > "$r1/fleet/board/DROPPED.md"
git -C "$r1" add -A
git -C "$r1" commit -q -m 'board: add DROPPED'
b1="$(git -C "$r1" rev-parse HEAD)"
tree="$(git -C "$r1" rev-parse HEAD~1^{tree})"
merge="$(printf 'merge stale board tree\n' | git -C "$r1" commit-tree "$tree" -p "$b1" -p "$b1~1")"
out="$(run "$r1" "$b1" "$merge")"; rc=$?
printf '%s\n' "$out"
if [ "$rc" -ne 0 ] && grep -q 'RED: DROPPED.md disappeared' <<<"$out" && [ -z "$(git -C "$r1" log --full-history --diff-filter=D --format=%H -- fleet/board/DROPPED.md)" ]; then
  ok "merge-result-only board drop is RED and names the ticket"
else
  bad "merge-result-only drop was not detected (rc=$rc): $out"
fi

r2="$(repo)"
printf 'ticket\n' > "$r2/fleet/board/RETIRED.md"
git -C "$r2" add -A; git -C "$r2" commit -q -m add
b2="$(git -C "$r2" rev-parse HEAD)"
git -C "$r2" mv fleet/board/RETIRED.md fleet/board/archive/RETIRED.md
git -C "$r2" commit -q -m 'board-hygiene: archive RETIRED'
out="$(run "$r2" "$b2" HEAD)"; rc=$?
[ "$rc" -eq 0 ] && ok "archive move is GREEN" || bad "archive move failed: $out"

r3="$(repo)"
printf 'ticket\n' > "$r3/fleet/board/DECLARED.md"
git -C "$r3" add -A; git -C "$r3" commit -q -m add
b3="$(git -C "$r3" rev-parse HEAD)"
git -C "$r3" rm -q fleet/board/DECLARED.md
git -C "$r3" commit -q -m 'board-hygiene: retire DECLARED'
out="$(run "$r3" "$b3" HEAD)"; rc=$?
[ "$rc" -eq 0 ] && ok "declared retire is GREEN" || bad "declared retire failed: $out"

r4="$(repo)"
b4="$(git -C "$r4" rev-parse HEAD)"
printf 'code\n' >> "$r4/README"
git -C "$r4" commit -qam code
out="$(run "$r4" "$b4" HEAD)"; rc=$?
[ "$rc" -eq 0 ] && ok "non-board change is GREEN" || bad "non-board change failed: $out"
b4="$(git -C "$r4" rev-parse HEAD)"
printf 'new\n' > "$r4/fleet/board/ADDED.md"
git -C "$r4" add -A; git -C "$r4" commit -q -m add
out="$(run "$r4" "$b4" HEAD)"; rc=$?
[ "$rc" -eq 0 ] && ok "board addition is GREEN" || bad "board addition failed: $out"

if bash "$SCOPE" suites | grep -Fxq board-file-ratchet.test.sh; then
  ok "suite is registered in the CI allowlist"
else
  bad "suite is absent from the CI allowlist"
fi

wire="$(mktemp -d)"
mkdir -p "$wire/fleet/checks" "$wire/fleet/tests"
cp "$SCOPE" "$wire/fleet/checks/rig-ci-scope.sh"
cp "$CHECK" "$wire/fleet/checks/board-file-ratchet.sh"
cat > "$wire/fleet/tests/board-file-ratchet.test.sh" <<'PROBE'
#!/usr/bin/env bash
echo RATCHeT_EXECUTED
exit 23
PROBE
# RE-ENTRANCY (repaired 2026-08-01). This probe is a WIRING assertion: it stands up a throwaway
# tree containing ONLY a stub suite and asks the real rig-ci-scope.sh to run it, proving the
# allowlist is actually executed and a suite's rc is actually propagated.
#
# IT WAS FAILING ON EVERY PR, and the failure was a FALSE SIGNAL. In CI this file is itself run BY
# `rig-ci-scope.sh tests`, which exports RIG_CI_TESTS_ACTIVE=1 as its fork-bomb guard
# [[fleet-selfcheck-forkbomb-class]]. The env var is inherited by everything below it, so the probe's
# nested run short-circuited with "already inside a suite run — skipping nested re-entry" and rc 0,
# and the assertion reported "registered suite did not execute". The guard was doing its job; the
# probe was reading a CORRECT REFUSAL as a wiring defect.
#
# The guard is process-global (an env var) while the recursion hazard is per-TREE. `$wire` is a
# different tree that contains exactly one (stub) suite and cannot recurse into this repo, so the
# probe clears the inherited flag for that ONE hermetic call. This does NOT weaken the guard: the
# guard is not modified, it is not bypassed for the real tree, and the same-tree short-circuit is
# now itself red-proofed immediately below.
out="$(env -u RIG_CI_TESTS_ACTIVE RIG_CI_ROOT="$wire" bash "$wire/fleet/checks/rig-ci-scope.sh" tests 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && grep -q RATCHeT_EXECUTED <<<"$out" && grep -q 'suite FAILED (rc=23): fleet/tests/board-file-ratchet.test.sh' <<<"$out"; then
  ok "rig-ci tests command actually executes the ratchet suite and propagates RED"
else
  bad "registered suite did not execute through rig-ci tests: $out"
fi

# FAIL-ON-REVERT for the FORK-BOMB GUARD ITSELF. Nothing asserted this before, which is why the
# `env -u` above could have been mistaken for a way to disarm it. REVERT LINE:
# fleet/checks/rig-ci-scope.sh cmd_tests -- the `if [ -n "${RIG_CI_TESTS_ACTIVE:-}" ]` short-circuit
# and the `export RIG_CI_TESTS_ACTIVE=1` beneath it. Delete either and the same-tree nested run
# below EXECUTES the stub instead of refusing, i.e. the self-referential
# rig-ci-scope -> rig-ci.test -> rig-ci-scope cycle is unguarded again (the ~18,900-proc class).
out="$(RIG_CI_TESTS_ACTIVE=1 RIG_CI_ROOT="$wire" bash "$wire/fleet/checks/rig-ci-scope.sh" tests 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && grep -q 'already inside a suite run' <<<"$out" && ! grep -q RATCHeT_EXECUTED <<<"$out"; then
  ok "fork-bomb guard intact: a nested run short-circuits (rc 0) and executes NO suite"
else
  bad "RIG_CI_TESTS_ACTIVE no longer short-circuits a nested run (rc=$rc): $out"
fi

printf '%s\n' "board-file-ratchet tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
