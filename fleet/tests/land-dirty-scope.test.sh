#!/usr/bin/env bash
# land-dirty-scope.test.sh — FAIL-ON-REVERT self-test for land.sh step 1 dirty scoping.
#
# THE DEFECT GUARDED: land.sh step 1 was a bare `git add -A && git commit` fenced only by
# `[ -n "$(git status --porcelain)" ]`. It ran in $REPO on whatever branch HEAD was, BEFORE the
# gate and BEFORE the branch/holder refusal — so on `master` it committed the entire dirty tree
# onto master and then refused to push, leaving divergence. It really did put 1462 unrelated
# files on master (4ea0a34, incl. graphify-out/graph.json). submit.sh/checkin.sh write
# fleet/session-notes/ continuously, so the tree is dirty on nearly every land.
#
# Assertions (INDEPENDENT fixture each — sibling-state cascades have produced false greens here):
#   D1  dirty file OUTSIDE the ticket's owns: -> exit 9, HEAD UNCHANGED, no commit made at all
#   D2  ONLY owned files dirty                -> still lands normally (anti-over-block positive)
#   D3  --commit-dirty                        -> the ONLY way to sweep unowned files
#
# Run:  bash fleet/tests/land-dirty-scope.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ── fixture ─────────────────────────────────────────────────────────────────────────────
# A REAL git repo (this tests git index/commit behaviour, so a git stub would test nothing) on
# `master`, plus a minimal fleet carrying land.sh and the libs it sources. `gh` is stubbed so the
# test never touches the network; the push at step 5 is expected to fail on the remote-less
# fixture, which is fine — every assertion here is about what got COMMITTED, before that point.
mk(){
  local owns="$1"; local d; d="$(mktemp -d)"
  local F="$d/fleet" R="$d/repo"

  mkdir -p "$F/state" "$F/board" "$d/bin" "$R"
  cp "$SRC/land.sh" "$SRC/push-verify.sh" "$SRC/_lib.sh" "$F/"
  [ -f "$SRC/repo-registry.sh" ] && cp "$SRC/repo-registry.sh" "$F/"
  touch "$F/state/AUTONOMOUS"

  # board ticket: binds branch -> owns:. No `repo:` field, so _vm_resolve takes the PRODUCT arm,
  # which honours $VERIFY_MERGED_REPO — pointed at the fixture repo below. This deliberately
  # exercises the REAL canonical resolution path (ticket_for_branch -> ticket_owns -> _vm_meta).
  { echo "branch: feat/scope-test"
    echo "owns: $owns"
    echo "status: doing"
  } > "$F/board/SCOPE-TEST.md"

  cat > "$d/bin/gh" <<'GHSTUB'
#!/usr/bin/env bash
exit 0
GHSTUB
  chmod +x "$d/bin/gh"

  git -C "$R" init -q -b master
  git -C "$R" config user.email t@t; git -C "$R" config user.name t
  echo original > "$R/fileA.txt"
  git -C "$R" add -A; git -C "$R" commit -q -m base
  echo "$d"
}
# run <dir> [extra land.sh args...] -> land.sh exit code
run(){ local d="$1"; shift
  ( cd "$d/repo" && PATH="$d/bin:$PATH" VERIFY_MERGED_REPO="$d/repo" \
      bash "$d/fleet/land.sh" feat/scope-test "$d/repo" --gate "exit 0" "$@" ) >/dev/null 2>&1
}
head_of(){ git -C "$1/repo" rev-parse HEAD; }
# files touched by every commit made after <base-sha>
new_files(){ git -C "$1/repo" log --name-only --pretty=format: "$2..HEAD" 2>/dev/null | sort -u; }

# ════════════════════════════════════════════════════════════════════════════════════════
# D1: owned fileA.txt dirty + UNRELATED unrelated-note.md dirty -> REFUSE, commit nothing.
# REVERT THAT MUST MAKE THIS RED: in fleet/land.sh, replace the step-1 `land_scope_plan || exit $?`
#   + the step-3.5 `git add "${LAND_STAGE[@]}"` block with the original two lines:
#       if [ -n "$(git status --porcelain)" ]; then
#         git add -A && git commit -q -m "${MSG:-land: $BRANCH}"
#       fi
#   -> land.sh sweeps unrelated-note.md into a commit on master; rc is no longer 9 and HEAD moves.
# ════════════════════════════════════════════════════════════════════════════════════════
D="$(mk 'fileA.txt')"
echo edited          > "$D/repo/fileA.txt"
echo "session note"  > "$D/repo/unrelated-note.md"
BEFORE="$(head_of "$D")"
run "$D"; rc=$?
check "D1a unowned dirty file -> land REFUSES (exit 9)" "$rc" "9"
check "D1b unowned dirty file -> HEAD UNCHANGED (nothing committed on master)" "$(head_of "$D")" "$BEFORE"
if git -C "$D/repo" log --all --name-only --pretty=format: | grep -qx 'unrelated-note.md'; then
  bad "D1c no commit anywhere contains unrelated-note.md"
else ok "D1c no commit anywhere contains unrelated-note.md"; fi
rm -rf "$D"

# ════════════════════════════════════════════════════════════════════════════════════════
# D2 (ANTI-OVER-BLOCK): ONLY owned files dirty -> must still commit normally.
# REVERT THAT MUST MAKE THIS RED: make the scoping unconditional — insert `return 9` as the first
#   line of land_scope_plan() in fleet/land.sh. -> the owned-only land is refused too and no
#   commit containing fileA.txt is created.
# ════════════════════════════════════════════════════════════════════════════════════════
D="$(mk 'fileA.txt')"
echo edited > "$D/repo/fileA.txt"     # ONLY the owned file is dirty
BEFORE="$(head_of "$D")"
run "$D"; rc=$?
[ "$rc" != "9" ] && ok "D2a owned-only dirty -> NOT refused (rc=$rc, not 9)" \
                 || bad "D2a owned-only dirty -> NOT refused (got 9: over-blocking)"
[ "$(head_of "$D")" != "$BEFORE" ] && ok "D2b owned-only dirty -> the work WAS committed" \
                                   || bad "D2b owned-only dirty -> the work WAS committed (HEAD did not move)"
if new_files "$D" "$BEFORE" | grep -qx 'fileA.txt'; then ok "D2c the commit contains fileA.txt"
else bad "D2c the commit contains fileA.txt"; fi
rm -rf "$D"

# ════════════════════════════════════════════════════════════════════════════════════════
# D3 (OPT-IN): --commit-dirty is the ONLY way to sweep unowned files.
# REVERT THAT MUST MAKE THIS RED: delete the `if [ -n "$COMMIT_DIRTY" ]; then ... LAND_STAGE=(-A);
#   return 0; fi` arm from land_scope_plan() in fleet/land.sh. -> even with the flag the land is
#   refused and unrelated-note.md is never committed.
# ════════════════════════════════════════════════════════════════════════════════════════
D="$(mk 'fileA.txt')"
echo edited         > "$D/repo/fileA.txt"
echo "session note" > "$D/repo/unrelated-note.md"
BEFORE="$(head_of "$D")"
run "$D" --commit-dirty; rc=$?
[ "$rc" != "9" ] && ok "D3a --commit-dirty -> NOT refused (rc=$rc, not 9)" \
                 || bad "D3a --commit-dirty -> NOT refused (got 9)"
if new_files "$D" "$BEFORE" | grep -qx 'unrelated-note.md'; then
  ok "D3b --commit-dirty -> unowned file WAS swept in (opt-in works)"
else bad "D3b --commit-dirty -> unowned file WAS swept in (opt-in works)"; fi
rm -rf "$D"

echo
echo "land-dirty-scope: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
