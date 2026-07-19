#!/usr/bin/env bash
# land-gate.test.sh — FAIL-ON-REVERT self-test for the A1 REFUSE-ON-RED gate.
# Tests that land.sh and land-push.sh ABORT on a red gate, proceed on green,
# and that --force bypasses the gate. Uses ISOLATED temp dirs with fake
# git/gh on PATH — NEVER touches the live product repo or fleet/state.
#
# Covers:
#   G1  land-push.sh RED gate (--gate "exit 1")   → exits 4, no push
#   G2  land-push.sh GREEN gate (--gate "exit 0") → gate passes
#   G3  land-push.sh --force bypasses red gate     → push proceeds
#   G4  land.sh RED gate (--gate "exit 1")        → exits 4, no merge
#   G5  land.sh GREEN gate (--gate "exit 0")      → gate passes
#   G6  land.sh --force bypasses red gate          → proceeds
#   G7  land-push.sh REAL ruff failure in repo     → exits 4 (proves gate bites)
#   G8  land.sh REAL ruff failure in repo          → exits 4 (proves gate bites)
#   G9  land-push.sh all gates green (real repo)   → proceeds (exit 0)
#   G10 land.sh all gates green (real repo)        → proceeds (no exit 4)
#
# Run:  bash fleet/tests/land-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ---- fake git: records the call but always succeeds ----
make_fake_bin(){
  local d="$1"
  mkdir -p "$d"
  # LAND-SAFETY-FIX (2026-07-18): land.sh/land-push.sh now RESOLVE the sha they intend to publish
  # and PROVE with `git ls-remote` that the remote became it (push-verify.sh). A stub that answers
  # every command with a bare exit 0 therefore models a git that resolves NOTHING, and the push
  # paths correctly refuse. These G* cases exist to test the GATE, not the push proof (that is
  # fleet/tests/land-safety.test.sh, on real git objects), so the stub now models a CONSISTENT
  # git: rev-parse and ls-remote agree on one sha, so the proof passes and the gate stays the
  # only variable. Do NOT weaken push-verify.sh to accommodate a stub.
  cat > "$d/git" <<'GITSTUB'
#!/usr/bin/env bash
echo "fake-git: $*" >&2
FAKE_SHA=1111111111111111111111111111111111111111
# drop a leading `-C <dir>` so the subcommand is $1
[ "${1:-}" = "-C" ] && shift 2
case "${1:-}" in
  rev-parse)
    case " $* " in
      *" --abbrev-ref "*) echo master ;;   # HEAD is on base, never on the feature branch
      *)                  echo "$FAKE_SHA" ;;
    esac ;;
  ls-remote)     echo "$FAKE_SHA	refs/heads/x" ;;   # remote == what we pushed (proof passes)
  status)        : ;;                                 # clean tree
  worktree)      : ;;                                 # nobody else holds the branch
esac
exit 0
GITSTUB
  cat > "$d/gh" <<'GHSTUB'
#!/usr/bin/env bash
echo "fake-gh: $*" >&2
exit 0
GHSTUB
  chmod +x "$d/git" "$d/gh"
}

# ---- isolated fleet fixture ----
make_fleet(){
  local d; d="$(mktemp -d)"
  # push-verify.sh is a hard dependency of BOTH scripts (they `source` it and must fail closed
  # without it) — the fixture has to carry it.
  cp "$SRC/land.sh" "$SRC/land-push.sh" "$SRC/push-verify.sh" "$d/"
  mkdir -p "$d/state"
  touch "$d/state/AUTONOMOUS"
  make_fake_bin "$d/bin"
  echo "$d"
}

# ---- make a real temp repo with src/ and tests/ so gate auto-detect fires ----
make_real_repo(){
  local d; d="$(mktemp -d)"
  git -C "$d" init -q
  git -C "$d" config user.email t@t && git -C "$d" config user.name t
  mkdir -p "$d/src/charon" "$d/tests"
  # minimal cli.py so auto-detect fires the charon gate
  echo '"""charon cli"""' > "$d/src/charon/cli.py"
  echo 'def gate(): pass' >> "$d/src/charon/cli.py"
  # a clean py file for green case
  echo 'x = 1' > "$d/src/charon/clean.py"
  echo 'import unittest' > "$d/tests/test_clean.py"
  git -C "$d" add -A && git -C "$d" commit -q -m base
  git -C "$d" remote add origin "https://github.com/test/test.git"
  echo "$d"
}

# ============================ land-push.sh (fake-gate tests) ============================
echo "== land-push.sh =="

D="$(make_fleet)"
REPO="$(mktemp -d)"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t && git -C "$REPO" config user.name t
echo x > "$REPO/clean.py" && git -C "$REPO" add -A && git -C "$REPO" commit -q -m base

# G1: RED gate (--gate "exit 1") → must exit 4
PATH="$D/bin:$PATH" bash "$D/land-push.sh" test-branch "$REPO" --gate "exit 1" >/dev/null 2>&1; rc=$?
check "G1 land-push.sh RED gate → exit 4" "$rc" "4"

# G2: GREEN gate (--gate "exit 0") → gate passes (fake git handles push)
PATH="$D/bin:$PATH" bash "$D/land-push.sh" test-branch "$REPO" --gate "exit 0" >/dev/null 2>&1; rc=$?
check "G2 land-push.sh GREEN gate → exit 0" "$rc" "0"

# G3: --force bypasses red gate → push proceeds (exit 0)
PATH="$D/bin:$PATH" bash "$D/land-push.sh" test-branch "$REPO" --gate "exit 1" --force >/dev/null 2>&1; rc=$?
check "G3 land-push.sh --force bypass → exit 0" "$rc" "0"

rm -rf "$D" "$REPO"

# ============================ land.sh (fake-gate tests) ============================
echo "== land.sh =="

D="$(make_fleet)"
REPO="$(mktemp -d)"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t && git -C "$REPO" config user.name t
echo x > "$REPO/clean.py" && git -C "$REPO" add -A && git -C "$REPO" commit -q -m base
git -C "$REPO" remote add origin "https://github.com/test/test.git"

# G4: RED gate (--gate "exit 1") → must exit 4
PATH="$D/bin:$PATH" bash "$D/land.sh" test-branch "$REPO" --gate "exit 1" >/dev/null 2>&1; rc=$?
check "G4 land.sh RED gate → exit 4" "$rc" "4"

# G5: GREEN gate (--gate "exit 0") → gate passes
PATH="$D/bin:$PATH" bash "$D/land.sh" test-branch "$REPO" --gate "exit 0" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 4 ] && ok "G5 land.sh GREEN gate (exit $rc ≠ 4)" \
                || bad "G5 land.sh GREEN gate (got exit 4, gate blocked green)"

# G6: --force bypasses red gate → proceeds (no exit 4)
PATH="$D/bin:$PATH" bash "$D/land.sh" test-branch "$REPO" --gate "exit 1" --force >/dev/null 2>&1; rc=$?
[ "$rc" -ne 4 ] && ok "G6 land.sh --force bypass (exit $rc ≠ 4)" \
                || bad "G6 land.sh --force bypass (got exit 4, force did not bypass)"

rm -rf "$D" "$REPO"

# ============================ REAL ruff failure tests (G7, G8) ============================
echo "== real ruff failure (gate must bite) =="

# G7: land-push.sh with a real ruff error in the repo → exits 4
D="$(make_fleet)"
REPO="$(make_real_repo)"
# Add a file with a deliberate ruff error (unused import)
echo 'import os' > "$REPO/src/charon/bad.py"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "add bad file"
PATH="$D/bin:$PATH" bash "$D/land-push.sh" test-branch "$REPO" >/dev/null 2>&1; rc=$?
check "G7 land-push.sh REAL ruff error → exit 4" "$rc" "4"
rm -rf "$D" "$REPO"

# G8: land.sh with a real ruff error in the repo → exits 4
D="$(make_fleet)"
REPO="$(make_real_repo)"
echo 'import os' > "$REPO/src/charon/bad.py"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "add bad file"
PATH="$D/bin:$PATH" bash "$D/land.sh" test-branch "$REPO" >/dev/null 2>&1; rc=$?
check "G8 land.sh REAL ruff error → exit 4" "$rc" "4"
rm -rf "$D" "$REPO"

# ============================ REAL green tests (G9, G10) ============================
echo "== real green repo (gate must pass) =="

# G9: land-push.sh with clean repo (explicit green gate) → proceeds (exit 0)
D="$(make_fleet)"
REPO="$(make_real_repo)"
PATH="$D/bin:$PATH" bash "$D/land-push.sh" test-branch "$REPO" --gate "true" >/dev/null 2>&1; rc=$?
check "G9 land-push.sh clean repo → exit 0" "$rc" "0"
rm -rf "$D" "$REPO"

# G10: land.sh with clean repo (explicit green gate) → proceeds (no exit 4)
D="$(make_fleet)"
REPO="$(make_real_repo)"
PATH="$D/bin:$PATH" bash "$D/land.sh" test-branch "$REPO" --gate "true" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 4 ] && ok "G10 land.sh clean repo (exit $rc ≠ 4)" \
                || bad "G10 land.sh clean repo (got exit 4, gate blocked clean)"
rm -rf "$D" "$REPO"

# ============================ summary ============================
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LAND-GATE TESTS PASS"
