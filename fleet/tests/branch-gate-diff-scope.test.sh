#!/usr/bin/env bash
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
fails=0
ok(){ printf 'ok %s\n' "$1"; }
bad(){ printf 'FAIL %s\n' "$1"; fails=$((fails+1)); }
gitq(){ git -C "$1" -c user.name=t -c user.email=t@t "${@:2}"; }
mkdir -p "$D/fleet/state" "$D/fleet/checks" "$D/fleet/board"
cp "$SRC/land-push.sh" "$SRC/push-verify.sh" "$D/fleet/"
: > "$D/fleet/state/AUTONOMOUS"; : > "$D/fleet/state/marker"
cat > "$D/fleet/validate_board.sh" <<'EOF'
#!/usr/bin/env bash
echo 'PRE-EXISTING RED: stale whole board'
exit 1
EOF
cat > "$D/fleet/checks/rig-ci-scope.sh" <<'EOF'
#!/usr/bin/env bash
base="${RIG_CI_BASE:?}"
changed="$(git -C "$RIG_CI_ROOT" diff --name-only "$base"..."${RIG_CI_HEAD:-HEAD}" -- fleet/board/)"
if [ -z "$changed" ]; then echo 'board: 0 changed ticket(s) checked; PRE-EXISTING board state excluded'; exit 0; fi
for f in $changed; do
  if grep -q 'BAD' "$RIG_CI_ROOT/$f"; then echo "RED: changed board file $f"; exit 1; fi
done
echo "board: changed files valid: $changed"
EOF
chmod +x "$D/fleet/validate_board.sh" "$D/fleet/checks/rig-ci-scope.sh"
git init -q --bare "$D/remote.git"
git init -q "$D/repo"; R="$D/repo"
mkdir -p "$R/fleet/board" "$R/fleet/state" "$R/fleet/checks"
cp "$D/fleet/validate_board.sh" "$R/fleet/"; cp "$D/fleet/checks/rig-ci-scope.sh" "$R/fleet/checks/"
: > "$R/fleet/state/marker"; echo BAD-preexisting > "$R/fleet/board/old.md"; echo base > "$R/plain"
gitq "$R" add -A; gitq "$R" commit -qm base; gitq "$R" remote add origin "$D/remote.git"; gitq "$R" push -q origin HEAD:master; gitq "$R" fetch -q origin
gitq "$R" checkout -qb feature; echo work >> "$R/plain"; gitq "$R" add -A; gitq "$R" commit -qm work
run(){ bash "$D/fleet/land-push.sh" HEAD:feature "$R" 2>&1; }
out="$(run)"; rc=$?
[ "$rc" -eq 0 ] && [[ "$out" == *'PRE-EXISTING board state excluded'* ]] && ok 'non-board branch allowed and stale RED reported' || bad "non-board branch rc=$rc: $out"
echo BAD-new > "$R/fleet/board/new.md"; gitq "$R" add -A; gitq "$R" commit -qm bad
out="$(run)"; rc=$?
[ "$rc" -eq 4 ] && [[ "$out" == *'fleet/board/new.md'* ]] && ok 'branch-added board RED refused and named' || bad "new RED rc=$rc: $out"
gitq "$R" reset -q --hard HEAD~1; echo GOOD > "$R/fleet/board/old.md"; gitq "$R" add -A; gitq "$R" commit -qm fix
out="$(run)"; rc=$?
[ "$rc" -eq 0 ] && ok 'branch fixing pre-existing RED allowed' || bad "fix rc=$rc: $out"
exit "$fails"
