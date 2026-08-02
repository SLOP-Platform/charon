#!/usr/bin/env bash
# fleet/checks/sandbox-containment.sh — merge-blocking guard for the 2026-08-01 incident class.
#
# Two independent defects put test sandboxes inside the repo and then let a test write to the
# LIVE checkout. Both are cheap to detect statically, and neither is detectable by any existing
# gate (the fleet suite itself went GREEN through the whole incident — one reviewer even
# returned a spurious green while ~118 tests were being killed). Full incident writeup:
# fleet/tests/lib/sandbox.sh.
#
#   CHECK 1 — TRAP-EXPANSION / TMPDIR-SHADOWING.
#     `TMPDIR="$(mktemp -d)"; trap 'rm -rf "$TMPDIR"' EXIT`
#     A single-quoted trap body is expanded when the trap FIRES, not when it is defined. If the
#     variable was `local`, or was reassigned, or simply went out of scope, the trap resolves
#     "$TMPDIR" to the INHERITED temp root and rm -rf's the caller's entire scratch space —
#     every concurrent test sandbox with it. Assigning to TMPDIR at all is the aggravating half:
#     it is the variable mktemp/pytest/python/git all read. Measured blast radius: fleet/gate.sh
#     unrunnable, ~118 tests "killed (no exit status recorded)".
#     RULE: no fleet script may assign to TMPDIR, and no trap body may expand a variable at
#     fire time to decide what to delete. Capture the path in a distinct name and expand it at
#     TRAP-DEFINITION time (double quotes + printf %q).
#
#   CHECK 2 — IN-TREE SANDBOX RESIDUE.
#     Fixtures created inside the work tree are what a blanket `git add` sweeps up, producing
#     `warning: adding embedded git repository:` / `does not have a commit checked out` and a
#     fatal exit 128 that kills the droid tab outright. This check FAILS if any such residue is
#     present in the work tree, so the condition is caught by the gate instead of by a dead tab.
#     It is deliberately a live filesystem check, not a grep: the residue is the observable, and
#     it appears no matter WHICH tool created it.
#
# Exit 0 = clean, 1 = violation.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ROOT = the work tree being CHECKED, which is the one the caller is standing in — not the one
# this script happens to live in. Those differ whenever the check is run from another checkout
# (e.g. a manager auditing the main checkout with a worktree's copy of the script), and defaulting
# to the script's own parent silently scanned the WRONG tree and reported a clean bill of health.
# NOTE the braces: `a || b && c` parses as `(a || b) && c`, so the obvious one-liner printed BOTH
# the toplevel and the cwd, handing `find` a two-line path that silently matched nothing — a
# false GREEN in the check whose entire job is to not be falsely green.
ROOT="${SANDBOX_CHECK_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || { cd "$FLEET/.." && pwd; })}"
SCAN_DIR="${SANDBOX_CHECK_SCAN_DIR:-$FLEET}"
RC=0
say(){ printf 'sandbox-containment: %s\n' "$*"; }

# ── CHECK 1: TMPDIR assignment + fire-time trap expansion ────────────────────────────
# Scanned as two separate signals so the message names the actual defect.
shopt -s nullglob
scripts=("$SCAN_DIR"/*.sh "$SCAN_DIR"/checks/*.sh "$SCAN_DIR"/hooks/*.sh)
shopt -u nullglob

# `code_lines <file>` — the file with comment-only lines blanked but LINE NUMBERS PRESERVED,
# so a doc comment describing the defect (this file, and the two fixed call sites, all do)
# can never be reported as the defect.
code_lines(){ sed 's/^[[:space:]]*#.*$//' "$1"; }

for f in "${scripts[@]}"; do
  [ -f "$f" ] || continue

  # 1a. Any assignment to TMPDIR. Reading it is fine and `TMPDIR="${TMPDIR:-/tmp}"`-style
  #     defaulting is fine; TAKING IT OVER is the defect, because it is the temp root every
  #     child (mktemp/pytest/python/git) inherits.
  while IFS= read -r ln; do
    [ -n "$ln" ] || continue
    say "VIOLATION $f:$ln — assigns TMPDIR. Use a distinct variable name: TMPDIR is the temp"
    say "          root every child process inherits, so an EXIT trap that deletes it destroys"
    say "          every concurrently running test's sandbox, not just this script's."
    RC=1
  #     Anchored at line start OR after a `;` — `local TMPDIR; TMPDIR="$(mktemp -d)"` (the
  #     literal review-pool.sh line) puts the assignment mid-line, and a start-only anchor
  #     silently missed the very defect this check exists for. A bare `local TMPDIR`
  #     declaration counts too: shadowing alone already breaks every child's temp root.
  done < <(code_lines "$f" \
             | grep -nE '(^|;)[[:space:]]*((local|export|declare)[[:space:]]+)?TMPDIR([=;]|[[:space:]]*$)' \
             | grep -vE 'TMPDIR=(")?\$\{TMPDIR:-' | cut -d: -f1 | sort -un)

  # 1b. A single-quoted EXIT-trap body that expands a variable which is ALSO declared `local`
  #     somewhere in the file. Two narrowings, both load-bearing — without either, the check
  #     reports correct code and would be turned off:
  #       * SCOPE. Only EXIT is flagged. A `local` is GONE by the time an EXIT trap runs, so
  #         the single-quoted body re-resolves to the INHERITED value and the rm -rf lands
  #         there — the exact review-pool.sh defect. A RETURN/ERR trap fires while the
  #         function scope is still alive (see fleet/deploy.sh:102) and is correct. A
  #         script-scope global also still resolves to the same value, so those ~10 correct
  #         call sites are not flagged either.
  #       * WORD BOUNDARY. `$t` must not match `$tmp`. Matching on substrings reported
  #         deploy.sh's correct `trap 'rm -rf "$tmp"' RETURN` because the file happens to
  #         declare an unrelated `local t` 200 lines away.
  locals="$(code_lines "$f" | grep -oE '^[[:space:]]*local[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' \
              | awk '{print $NF}' | sort -u)"
  [ -n "$locals" ] || continue
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    ln="${hit%%:*}"; body="${hit#*:}"
    for v in $locals; do
      grep -qE "\\\$\{?$v\}?([^A-Za-z0-9_]|$)" <<<"$body" || continue
      case "$body" in
        *"\$$v"*|*"\${$v}"*)
          say "VIOLATION $f:$ln — trap body is single-quoted and expands \$$v, which is declared"
          say "          \`local\` in this file. A single-quoted trap body is expanded when the trap"
          say "          FIRES — after the function scope is gone — so \$$v resolves to whatever the"
          say "          INHERITED value is, and the rm -rf lands there instead."
          say "          Fix: trap \"rm -rf \$(printf '%q' \"\$$v\")\" EXIT   (expand at definition time)"
          RC=1
          break ;;
      esac
    done
  done < <(code_lines "$f" | grep -nE "trap[[:space:]]+'[^']*rm[[:space:]]+-rf[^']*\\\$[^']*'[[:space:]]+EXIT")
done

# ── CHECK 2: in-tree sandbox residue ─────────────────────────────────────────────────
# Names are the ones actually observed, plus the generic pytest basetemp prefix. Anchored to
# directories so a doc mentioning the name in prose can never trip it.
residue=()
while IFS= read -r d; do
  [ -n "$d" ] && residue+=("$d")
done < <(find "$ROOT" \
           -name .git -prune -o \
           \( -type d \( -name 'pytest-of-*' -o -name 'pytmp*' -o -name 'tmpdir-land' \
                         -o -name 'fleet-copy' -o -name 'fleet-sandbox.*' \) \) -print 2>/dev/null)

if [ "${#residue[@]}" -gt 0 ]; then
  say "VIOLATION — test sandbox residue found INSIDE the work tree $ROOT:"
  for d in "${residue[@]}"; do say "    $d"; done
  say "          These are what a blanket \`git add\` sweeps in, producing"
  say "          'adding embedded git repository' / 'does not have a commit checked out'"
  say "          and a fatal exit 128 that kills the droid tab. Sandboxes belong outside the"
  say "          work tree — source fleet/tests/lib/sandbox.sh and use sandbox_mk."
  RC=1
fi

[ "$RC" -eq 0 ] && say "clean (no TMPDIR capture, no fire-time trap expansion, no in-tree sandbox residue)"
exit "$RC"
