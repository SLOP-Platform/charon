#!/usr/bin/env bash
# selftest/test_grep_code_only.sh — fail-on-revert guard for lib/grep-code-only.sh.
#
# Confirmed real bug (2026-07-13 Path C ranking audit): the PROVIDER-URL-HELPER
# ticket's DOGFOOD_TEST_CMD used a naive `grep -RnE '<pattern>' <files>` "no
# leftover" accept-check. It false-matched glm-5.2's own DOCSTRING text (a
# Sphinx-style `` ``code``  `` quote of the OLD inline expression, left behind
# as documentation after glm-5.2 correctly deduplicated the real code), producing
# a false FIXES-NEEDED for an otherwise-clean candidate. Fixtures below are
# reconstructed verbatim from the real diff captured in
# fleet/state/dogfood-eval/results/dogfood-PROVIDER-URL-HELPER-glm-5.2-*.diff
# (docstring case) and the real leftover line in minimax-m2.7's diff at
# src/charon/discover.py:34 (genuine real-code miss that must still be caught).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(cd "$HERE/.." && pwd)"
GREP_CODE_ONLY="$BENCH_DIR/lib/grep-code-only.sh"
PATTERN='rstrip\("/"\)[[:space:]]*\+[[:space:]]*"/(v1/)?(models|chat/completions)"'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0

# ---- case 1: glm-5.2's real docstring-only "leftover" — must PASS (exit 0, no
# real-code leftover) ----
cat > "$TMP/providers_docstring_only.py" <<'PYEOF'
def models_url(base_url: str) -> str:
    """Resolve the ``/models`` URL for a provider base. Use when the base
    already includes the ``/v1`` prefix (``strip_v1=True``). Equivalent to
    ``base_url.rstrip("/") + "/models"``."""
    return join_endpoint(base_url, "/models")


def chat_url(base_url: str) -> str:
    """Resolve the ``/chat/completions`` URL. Equivalent to
    ``base_url.rstrip("/") + "/chat/completions"``."""
    return join_endpoint(base_url, "/chat/completions")
PYEOF

if "$GREP_CODE_ONLY" "$PATTERN" "$TMP/providers_docstring_only.py"; then
  echo "ok: docstring-only text (glm-5.2 real case) -> no leftover, exit 0"
else
  echo "FAIL: docstring-only text was wrongly treated as a real-code leftover"
  fail=1
fi

# ---- case 2: minimax-m2.7's real genuine leftover at discover.py — must FAIL
# (exit 1, a real-code leftover remains) ----
cat > "$TMP/discover_real_leftover.py" <<'PYEOF'
def discover_provider(base_url, strip_v1):
    if strip_v1:
        url = models_url(base_url)
    else:
        url = base_url.rstrip("/") + "/v1/models"
    return url
PYEOF

if "$GREP_CODE_ONLY" "$PATTERN" "$TMP/discover_real_leftover.py"; then
  echo "FAIL: a genuine real-code leftover (minimax's incomplete dedup) was NOT caught"
  fail=1
else
  echo "ok: genuine real-code leftover (minimax-m2.7 real case) -> still caught, exit 1"
fi

# ---- case 3: a `#`-comment mention must not count as a real leftover either ----
cat > "$TMP/comment_only.py" <<'PYEOF'
def models_url(base_url):
    # old code used to do: base_url.rstrip("/") + "/models" — now delegates to _join_endpoint
    return _join_endpoint(base_url, "/models")
PYEOF
if "$GREP_CODE_ONLY" "$PATTERN" "$TMP/comment_only.py"; then
  echo "ok: comment-only mention -> no leftover, exit 0"
else
  echo "FAIL: a comment mentioning the old expression was wrongly treated as a leftover"
  fail=1
fi

# ---- fail-on-revert: prove the OLD naive grep (no docstring/comment filter)
# reproduces the false positive, so this selftest actually exercises the fix ----
naive_leftover="$(grep -RnE "$PATTERN" "$TMP/providers_docstring_only.py" 2>/dev/null)"
if [ -n "$naive_leftover" ]; then
  echo "ok (fail-on-revert control): the naive unfiltered grep DOES false-positive on the docstring fixture — confirms the filter in grep-code-only.sh is load-bearing"
else
  echo "FAIL: the docstring fixture no longer reproduces the naive false-positive — fixture is stale, test no longer proves anything"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "GREP-CODE-ONLY SELFTEST: FAILED — see FAIL lines above."
  exit 1
fi
echo
echo "ALL GREP-CODE-ONLY SELFTESTS PASS: docstring/comment prose never counts as a"
echo "real-code leftover; a genuine leftover is still caught."
