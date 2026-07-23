#!/usr/bin/env bash
# gh-cache.test.sh — offline test of the batched merged-PR cache (no gh / rate-limit-safe).
# Proves: branch_merged_pr reads the fixture/cache without a per-branch gh call, and that a
# repeated lookup over N branches makes ZERO extra gh calls (the whole point: O(repos) not O(N)).
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SRC/gh-cache.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
printf 'feat/alpha\t101\nfeat/beta\t202\nfix/gamma\t303\n' > "$D/merged.tsv"
export GH_MERGED_FIXTURE="$D/merged.tsv"

# a merged branch resolves to its PR number
[ "$(branch_merged_pr Nnyan/charon-private feat/beta)" = "202" ] && ok "(a) merged branch -> PR number" || bad "(a) merged branch -> PR number"
# a non-merged branch resolves to empty
[ -z "$(branch_merged_pr Nnyan/charon-private feat/not-there)" ] && ok "(b) non-merged branch -> empty" || bad "(b) non-merged branch -> empty"
# an empty branch is a safe no-op
[ -z "$(branch_merged_pr Nnyan/charon-private '')" ] && ok "(c) empty branch -> empty (safe)" || bad "(c) empty branch -> empty"

# pr_number_is_merged: exit-code contract over the same cached set (member->0, non-member->1, empty->1)
if pr_number_is_merged Nnyan/charon-private 202; then ok "(e) merged PR number -> 0"; else bad "(e) merged PR number -> 0"; fi
if pr_number_is_merged Nnyan/charon-private 999; then bad "(f) non-merged PR number -> 1"; else ok "(f) non-merged PR number -> 1"; fi
if pr_number_is_merged Nnyan/charon-private ''; then bad "(g) empty PR number -> 1"; else ok "(g) empty PR number -> 1"; fi

# fail-on-revert crux: prove the lookup does NOT shell out to gh per branch. Put a POISONED gh on
# PATH that fails loudly; with the fixture/cache in play, 100 lookups must still succeed (0 gh calls).
mkdir -p "$D/bin"; printf '#!/bin/sh\necho "GH-CALLED" >&2; exit 42\n' > "$D/bin/gh"; chmod +x "$D/bin/gh"
poisoned=0
PATH="$D/bin:$PATH"
for i in $(seq 1 100); do
  out="$(branch_merged_pr Nnyan/charon-private feat/alpha 2>"$D/err")"
  [ "$out" = "101" ] || poisoned=1
  grep -q GH-CALLED "$D/err" 2>/dev/null && poisoned=1
done
[ "$poisoned" -eq 0 ] && ok "(d) 100 lookups, ZERO gh calls (batched, not per-branch)" || bad "(d) a lookup shelled out to gh (revert of batching)"

# (h) pr_number_is_merged also makes ZERO gh calls under the poisoned PATH (same batched cache)
: > "$D/err"
if pr_number_is_merged Nnyan/charon-private 202 2>"$D/err" && ! grep -q GH-CALLED "$D/err" 2>/dev/null; then
  ok "(h) pr_number_is_merged: ZERO gh calls (poisoned PATH)"
else
  bad "(h) pr_number_is_merged shelled out to gh"
fi

rm -rf "$D"
echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL GH-CACHE TESTS PASS" || exit 1
