#!/usr/bin/env bash
# @covers: ci-infra
# Mutation gate (diff-scoped) — a test that cannot go red is not a test.
#
# diff-cover proves an added line was EXECUTED; it cannot prove anything was
# ASSERTED about it. mutmut breaks the changed code and checks that some test
# notices. A surviving mutant is a mechanically-proven assertion hole: the test
# passed regardless of the mutated line's behaviour.
#
# DIFF-SCOPED ON FILES — mutmut 3.x has no `--paths-to-mutate` flag (the ticket
# wording predates it; verified on 3.6.0). Scoping is the `[tool.mutmut]`
# `source_paths` / `only_mutate` globs mutmut reads from the CWD's
# pyproject.toml, so this gate scopes generation to the changed src files only —
# never full-tree (full-tree runs on a nightly cadence, out of scope here).
#
# WHY AN ISOLATED TREE — the scoped config MUST live in a pyproject.toml, and
# rewriting the repo's own (what an earlier attempt did) mutates a file other
# work holds open and leaves it corrupted if the process is killed mid-run. This
# gate copies the tracked working tree to a temp dir, writes the scoped config
# THERE, and runs mutmut in it. The repo's own pyproject.toml is never opened
# for writing.
#
# FAIL-CLOSED PATHS (each exits non-zero rather than reporting a pass):
#   * mutmut not installed;
#   * base ref unresolvable / no merge-base / untracked src/**.py;
#   * the isolated run tree could not be built;
#   * `mutmut run` fails, times out, or reports it matched nothing — a gate that
#     examined nothing must not read as a pass;
#   * `mutmut results --all` cannot be read (missing tool / empty run);
#   * any mutant of a changed file is not KILLED (survived / no tests / timeout /
#     suspicious / not checked).
#
# `mutmut run` exits 0 even when mutants survive (verified on 3.6.0), so the
# exit code is never the verdict on its own: the gate reads `mutmut results
# --all` and requires every listed mutant to be `killed`.
#
# KNOWN TOOL LIMIT, stated rather than hidden: mutmut 3.x mutates function and
# method bodies only. A change confined to module-level code (imports,
# constants, class-body attributes) has nothing mutmut can mutate; the gate
# prints the changed files and passes. That is a fact about the tool, and it is
# why this gate sits BESIDE diff-cover rather than replacing it.
#
# Usage:
#     tools/mutmut_diff_gate.sh [base-ref]
#
# Env overrides:
#     MUTMUT_BASE      base ref (default origin/master)
#     MUTMUT_TIMEOUT   seconds for the whole mutmut run (default 900)
set -euo pipefail

fail() {
  echo "WORK-UNITS: 0"
  echo "FAIL: mutmut gate — $*" >&2
  exit 1
}

# Reentry guard — same fork-bomb defence as the diff-cover gate.
if [ -n "${PYTEST_CURRENT_TEST:-}" ]; then
  echo "WORK-UNITS: 0"
  echo "mutmut-gate: running inside pytest (reentry guard) — skipped"
  exit 0
fi

BASE_REF="${1:-${MUTMUT_BASE:-origin/master}}"
TIMEOUT_SECS="${MUTMUT_TIMEOUT:-900}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

command -v mutmut >/dev/null 2>&1 || fail "mutmut is not installed (pip install '.[quality]')"
command -v timeout >/dev/null 2>&1 || fail "GNU coreutils 'timeout' is not available"

git rev-parse --verify --quiet "${BASE_REF}^{commit}" >/dev/null 2>&1 \
  || fail "base ref '${BASE_REF}' does not resolve (CI must checkout with fetch-depth: 0)"
MERGE_BASE="$(git merge-base "${BASE_REF}" HEAD)" \
  || fail "no merge-base between '${BASE_REF}' and HEAD"

UNTRACKED="$(git ls-files --others --exclude-standard -- 'src/*.py' 'src/**/*.py' || true)"
if [ -n "$UNTRACKED" ]; then
  fail "untracked python file(s) under src/ are invisible to the diff: $(printf '%s' "$UNTRACKED" | tr '\n' ' ')"
fi

CHANGED_PY="$(git diff --name-only --diff-filter=AMR "${MERGE_BASE}" HEAD -- src/ | grep -E '\.py$' || true)"
if [ -z "$CHANGED_PY" ]; then
  echo "WORK-UNITS: 0"
  echo "mutmut-gate: no added/modified src/*.py in the diff (merge-base ${MERGE_BASE}) — nothing to mutate"
  exit 0
fi

# Build an isolated copy of the tree so the scoped [tool.mutmut] config never
# touches the repo's own pyproject.toml. A real `git clone --local` (not a
# `git ls-files | tar` file copy) so the copy carries its own `.git` — the
# suite's public-clean tests run `git ls-files` and fail closed without one.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; rm -rf .mutmut-cache mutants' EXIT
if ! git clone --quiet --local --no-hardlinks "$REPO_ROOT" "$TMP/src"; then
  fail "could not build the isolated run tree"
fi
TMP_TREE="$TMP/src"

# Merge a diff-scoped [tool.mutmut] into the COPY's pyproject.toml. Any existing
# [tool.mutmut] section is dropped so a wider one cannot shadow the scoped
# config; also_copy= tools/ so tests that import `tools.*` resolve inside
# mutmut's mutants/ sandbox.
if ! python3 - "$TMP_TREE" $CHANGED_PY <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
changed = sys.argv[2:]
pyproject = root / "pyproject.toml"

original = pyproject.read_text(encoding="utf-8") if pyproject.exists() else ""
# drop any pre-existing [tool.mutmut] section (from the first [tool.mutmut] to
# the next top-level key or EOF)
import re
stripped = re.sub(r"\n\[tool\.mutmut\].*?(?=\n\[|\Z)", "\n", original, flags=re.DOTALL)

body = [
    stripped.rstrip(),
    "",
    "# GENERATED by tools/mutmut_diff_gate.sh in a throwaway tree — never committed.",
    "[tool.mutmut]",
    f"source_paths = {changed!r}",
    f"only_mutate = {changed!r}",
    'also_copy = ["tools"]',
    "",
]
pyproject.write_text("\n".join(body), encoding="utf-8")
PY
then
  fail "could not write the scoped mutmut config into the isolated tree"
fi

N_FILES="$(printf '%s\n' "$CHANGED_PY" | grep -c . || true)"
echo "mutmut-gate: mutating ${N_FILES} changed src file(s) (merge-base ${MERGE_BASE})"
RUN_LOG="$(mktemp)"
trap 'rm -rf "$TMP"; rm -rf .mutmut-cache mutants; rm -f "$RUN_LOG"' EXIT

set +e
( cd "$TMP_TREE" && timeout "${TIMEOUT_SECS}s" mutmut run --max-children 1 ) >"$RUN_LOG" 2>&1
RUN_RC=$?
set -e

if [ "$RUN_RC" -ne 0 ]; then
  fail "mutmut run failed (rc $RUN_RC): $(tail -3 "$RUN_LOG" | tr '\n' ' ')"
fi
if grep -q "Filtered for specific mutants, but nothing matches" "$RUN_LOG"; then
  fail "mutmut matched no mutants — the gate examined nothing and will not report a pass"
fi

set +e
RESULTS_ALL="$( cd "$TMP_TREE" && mutmut results --all true 2>/dev/null )"
RESULTS_RC=$?
set -e
if [ "$RESULTS_RC" -ne 0 ] || [ -z "$RESULTS_ALL" ]; then
  fail "could not read 'mutmut results --all' (rc $RESULTS_RC)"
fi

TOTAL="$(printf '%s\n' "$RESULTS_ALL" | grep -E '^\s+\S+__mutmut_[0-9]+\s*:' | wc -l | tr -d ' ')"
NONKILLED="$(printf '%s\n' "$RESULTS_ALL" | grep -E '^\s+\S+__mutmut_[0-9]+\s*:' | grep -vE ':\s*killed\s*$' || true)"

echo "WORK-UNITS: ${TOTAL}"
if [ "$TOTAL" -eq 0 ]; then
  echo "mutmut-gate: no mutatable constructs (function/method bodies) in the changed files — module-level-only change, nothing to mutate"
  exit 0
fi
if [ -n "$NONKILLED" ]; then
  echo "FAIL: mutmut gate — $TOTAL mutant(s) examined, surviving/uncertain:" >&2
  printf '%s\n' "$NONKILLED" >&2
  exit 1
fi
echo "mutmut-gate: OK — all ${TOTAL} mutant(s) of the changed code were killed by the suite"
