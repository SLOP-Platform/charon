#!/usr/bin/env bash
# lib/grep-code-only.sh — "assert this pattern has NO leftover occurrence in real
# code" check, safe against docstring/comment self-matches.
#
# BUG THIS FILE FIXES (found 2026-07-13 auditing the Path C PROVIDER-URL-HELPER
# ranking): the PICK 2 DOGFOOD_TEST_CMD's naive `grep -RnE '<pattern>' <files>`
# matched glm-5.2's own DOCSTRING text (it quoted the old inline expression in
# Sphinx-style double-backticks as documentation, e.g.
#   """... Equivalent to ``base_url.rstrip("/") + "/models"``."""
# ) and produced a false FIXES-NEEDED even though glm-5.2's real code was fully
# deduplicated. A leftover-pattern check must only match REAL CODE, never prose
# that quotes the pattern for documentation purposes.
#
# Usage: grep-code-only.sh <extended-regex-pattern> <file> [file ...]
# Exit 0  — pattern NOT found in real code (nothing left to fix; safe to '&&' after)
# Exit 1  — pattern found in real, non-doc code (a genuine leftover remains)
#
# Heuristic (intentionally simple, not a full parser): a match is real code
# unless the matched line either (a) is a `#`-prefixed comment, or (b) contains
# a backtick (`` ` ``) — the Sphinx/Markdown code-quote marker used to cite an
# expression inside a docstring, which real Python source never contains.
set -uo pipefail

[ "$#" -ge 2 ] || { echo "usage: grep-code-only.sh <pattern> <file> [file ...]" >&2; exit 2; }
pattern="$1"; shift

leftover="$(grep -RHnE "$pattern" "$@" 2>/dev/null | grep -v '`' | grep -vE ':[[:space:]]*#')"
if [ -n "$leftover" ]; then
  echo "grep-code-only: real-code leftover(s) found:" >&2
  printf '%s\n' "$leftover" >&2
  exit 1
fi
exit 0
