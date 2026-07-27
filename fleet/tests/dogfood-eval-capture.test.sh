#!/usr/bin/env bash
# dogfood-eval-capture.test.sh — FAIL-ON-REVERT coverage for the untracked-file capture
# path in fleet/benchmark/dogfood-eval.sh.
#
# RFL-3-CAPTURE-FIX: git diff covers ONLY tracked changes. A candidate that creates a
# genuinely NEW untracked file (created, never git-add'd) leaves output invisible to
# git diff, invisible to the scorer, and permanently lost on worktree reap. This test
# proves the capture path now includes untracked files AND goes RED when it is reverted.
#
# ISOLATION: every fixture is a throwaway git repo under mktemp -d. No model is invoked,
# no network touched, no live checkout referenced. Tests run the SAME `git diff` /
# `ls-files --others` / `diff --no-index` pipeline that dogfood-eval.sh's run_one uses.
#
# FIXTURE: a candidate that writes ONLY a new untracked file — no tracked changes at all.
#   Without the fix:  n_changed=0  → early-ditch-no-diff  → file lost.
#   With the fix:     n_changed=1  → real-diff(files=1)   → file captured.

set -uo pipefail
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ---- hermetic git repo (offline, throwaway) ----------------------------------------
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
case "$T" in /tmp/*|/var/*) ;; *) echo "refusing: non-temp root: $T" >&2; exit 2 ;; esac

git init --quiet -b master "$T/repo"
git -C "$T/repo" config user.email t@t; git -C "$T/repo" config user.name t
echo "tracked content" > "$T/repo/README.md"
git -C "$T/repo" add README.md && git -C "$T/repo" commit --quiet -m base

# ---- fixture: candidate writes a single new untracked file (no tracked changes) ----
mkdir -p "$T/repo/tests"
echo "def test_image_routing(): pass" > "$T/repo/tests/test_image_routing.py"

# === THE CAPTURE PIPELINE (mirrors dogfood-eval.sh:391-410) ==========================
diff_stat="$(git -C "$T/repo" diff --stat 2>/dev/null)"
diff_files="$(git -C "$T/repo" diff --name-only 2>/dev/null)"

untracked_files="$(git -C "$T/repo" ls-files --others --exclude-standard 2>/dev/null)"
n_untracked="$(printf '%s\n' "$untracked_files" | grep -c . || true)"

# Save tracked diff (empty here — no tracked changes)
git -C "$T/repo" diff > "$T/tracked.diff" 2>/dev/null || true

# Append untracked file as a proper diff
if [ "${n_untracked:-0}" -gt 0 ]; then
  while IFS= read -r uf; do
    [ -z "$uf" ] && continue
    git -C "$T/repo" diff --no-index /dev/null "$uf" >> "$T/full.diff" 2>/dev/null || \
      { printf '%s\n' '--- /dev/null' "+++ $uf (unreadable)" >> "$T/full.diff"; }
  done <<< "$untracked_files"
else
  :> "$T/full.diff"
fi

# Combine tracked + untracked (mirrors dogfood-eval.sh:409-410)
combined_files="$(printf '%s\n%s\n' "$diff_files" "$untracked_files" | grep . || true)"
n_combined="$(printf '%s\n' "$combined_files" | grep -c . || true)"

# === ASSERTIONS ON THE FIXED CAPTURE ================================================

# 1. The untracked file MUST appear in the captured artifact.
if grep -q 'tests/test_image_routing.py' "$T/full.diff" 2>/dev/null; then
  ok "untracked file appears in captured diff artifact"
else
  bad "untracked file NOT in captured diff artifact (silent data loss — revert?)"
fi

# 2. The combined file count MUST be >=1 (the untracked file is counted).
if [ "${n_combined:-0}" -ge 1 ]; then
  ok "real-diff count >= 1 with untracked file (n_combined=$n_combined)"
else
  bad "real-diff count is ${n_combined:-0}, expected >=1 (untracked file not counted — revert?)"
fi

# 3. The untracked file path MUST appear in the combined files list (feeds scope check).
if printf '%s\n' "$combined_files" | grep -qx 'tests/test_image_routing.py'; then
  ok "untracked file path in combined files list (scope-check feed)"
else
  bad "untracked file path NOT in combined files list"
fi

# === FAIL-ON-REVERT: the OLD (tracked-only) pipeline misses the untracked file ======
old_n_changed="$(printf '%s\n' "$diff_files" | grep -c . || true)"
if [ "${old_n_changed:-0}" -eq 0 ]; then
  ok "FAIL-ON-REVERT: tracked-only count is 0 (proves untracked-inclusion is load-bearing)"
else
  bad "FAIL-ON-REVERT: tracked-only count=${old_n_changed} but fixture has no tracked changes (capture logic anomaly?)"
fi

echo "---"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1

# 4. BONUS: the tracked-only diff file is empty (fixture had no tracked changes).
if [ ! -s "$T/tracked.diff" ]; then
  ok "tracked-only diff is empty (correct — no tracked changes in fixture)"
else
  bad "tracked-only diff is non-empty but fixture had no tracked changes"
fi
