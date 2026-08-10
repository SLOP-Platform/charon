#!/usr/bin/env python3
# @covers: diff-coverage
"""Diff-coverage gate — every line this change adds to ``src/`` must be executed.

THE GAP THIS CLOSES (D-005 #3): nothing in this tree proves that NEW PRODUCT
CODE is exercised by a test. ``check_redproof``/``check_no_vacuous`` prove it for
GATES; ``gate_contract`` proves a gate examined something. A new module under
``src/`` could land with no test touching it at all and every check stayed green.

SCOPE — ``src/`` only, and only lines the change adds or modifies. ``src/`` is
the shipped product; ``tools/`` gates are already covered by the redproof and
gate-registry meta-gates, and they run as SUBPROCESSES of their tests, so
in-process coverage cannot see them and gating on them would red every PR that
touches a gate. Whole-tree coverage is REPORTED (see ``--report-total``) and
never gated: measured 87.0% on 2026-08-04, so a whole-tree floor would red
everything.

FAIL-CLOSED PATHS — each of these exits non-zero rather than reporting a pass:
  * the base ref does not resolve, or there is no merge-base (``diff_scope``);
  * an untracked ``src/**.py`` exists — invisible to ``git diff``, so a new
    module could hide from the gate entirely;
  * coverage.py / pytest-cov / diff-cover is not installed;
  * the test run under coverage fails (coverage of a red suite proves nothing);
  * the coverage XML is missing, empty, or unparseable;
  * a changed ``src`` file is ABSENT from the coverage report — the gate cannot
    prove lines it never measured;
  * diff-cover analysed FEWER lines than the diff demonstrably contains;
  * diff-cover reports any uncovered added line (``--fail-under=100``).

The single exemption to "nothing analysed is not a pass" is a PROVABLY empty
scope, and it is printed with its evidence: the merge-base SHA and the list of
changed files, none of which is a ``src/**.py`` carrying an executable added
line. That is a fact about the change, not a failure to measure it.

Usage:
    python3 tools/diff_cover_gate.py [base-ref]
    python3 tools/diff_cover_gate.py --report-total   # whole-tree number only
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_GC_ROOT = Path(__file__).resolve().parent.parent
if str(_GC_ROOT) not in sys.path:
    sys.path.insert(0, str(_GC_ROOT))
from tools.diff_scope import (  # noqa: E402
    DiffScopeError,
    added_lines_by_file,
    changed_files,
    head_is_at_base,
    merge_base,
    repo_root,
    resolve_base,
    running_inside_pytest,
    unified_diff,
    untracked_python_files,
)
from tools.gate_contract import emit_work_units  # noqa: E402

SCOPE = "src"


def _fail(message: str) -> int:
    emit_work_units(0)
    print(f"FAIL: diff-cover gate — {message}", file=sys.stderr)
    return 1


def _missing_tools() -> list[str]:
    missing = []
    for module in ("coverage", "pytest_cov", "xdist", "defusedxml"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if shutil.which("diff-cover") is None:
        missing.append("diff-cover")
    return missing


def _parse_coverage_xml(coverage_xml: Path):  # -> xml.etree.ElementTree.Element
    """Return the root element of a coverage report, parsed with ``defusedxml``.

    defusedxml, NOT the stdlib ``xml.etree.ElementTree`` (bandit B314 / ruff
    S314). The stdlib parser expands entities and honours DTDs, so a report it
    is pointed at can bomb the process (billion-laughs) or read local files via
    an external entity. Today's input is coverage.py XML this gate generated
    itself into its own temp dir, so the live exposure is low — but "the input
    happens to be ours right now" is exactly the assumption that rots (a future
    caller passing a CI-artifact path is one edit away), and the hardened parser
    is a drop-in with identical behaviour on well-formed input. Cheap fix, no
    suppression: this gate does not get to weaken a security check.

    Raises ValueError on any unusable report, so "I could not read the coverage
    data" can never be mistaken for "the coverage data was clean". defusedxml's
    own rejections (``EntitiesForbidden``/``DTDForbidden``/...) already subclass
    ValueError, so a hostile report lands on the same fail-closed path.

    Imported HERE rather than at module scope on purpose: an absent defusedxml
    is then reported by ``_missing_tools()`` with its install line, and merely
    IMPORTING this module (the tests do) never requires the [quality] extra.
    """
    from defusedxml.ElementTree import ParseError, parse

    try:
        return parse(coverage_xml).getroot()
    except ParseError as exc:
        raise ValueError(f"coverage XML {coverage_xml} is unparseable: {exc}") from exc


def measured_lines(coverage_xml: Path) -> dict[str, set[int]]:
    """Map repo-relative path -> statement line numbers present in the report.

    Raises ValueError when the report is unusable, so "I could not read the
    coverage data" can never be mistaken for "the coverage data was clean".
    """
    if not coverage_xml.exists() or coverage_xml.stat().st_size == 0:
        raise ValueError(f"coverage XML {coverage_xml} is missing or empty")
    root = _parse_coverage_xml(coverage_xml)

    repo = repo_root()
    prefixes: list[str] = []
    for source in root.findall("sources/source"):
        raw = (source.text or "").strip()
        if not raw:
            continue
        try:
            prefixes.append(str(Path(raw).resolve().relative_to(repo)))
        except ValueError:
            continue
    if not prefixes:
        raise ValueError(
            f"coverage XML {coverage_xml} declares no <sources> inside {repo} — "
            "its filenames cannot be mapped back to repo paths"
        )

    result: dict[str, set[int]] = {}
    classes = root.findall(".//class")
    if not classes:
        raise ValueError(f"coverage XML {coverage_xml} contains no measured files")
    for cls in classes:
        filename = cls.get("filename")
        if not filename:
            continue
        lines = {
            int(line.get("number", "0"))
            for line in cls.findall("lines/line")
            if line.get("number")
        }
        for prefix in prefixes:
            result.setdefault(f"{prefix}/{filename}", set()).update(lines)
    return result


def whole_tree_percent(coverage_xml: Path) -> float:
    """The standing whole-tree number — REPORTED for grounding, never gated."""
    root = _parse_coverage_xml(coverage_xml)
    valid = int(root.get("lines-valid", "0"))
    covered = int(root.get("lines-covered", "0"))
    return 100.0 * covered / valid if valid else 0.0


def _run_coverage(coverage_xml: Path) -> subprocess.CompletedProcess[str]:
    """Run the suite under coverage, leaving NOTHING behind in the checkout.

    ``COVERAGE_FILE`` points coverage's data files at the temp dir. Without it
    they are written relative to the CWD — the repo root — so every gate run
    drops a ``.coverage`` plus one ``.coverage.<host>.<pid>.<rand>`` per xdist
    worker into the working tree. None of them is gitignored, so the gate would
    dirty the tree it is measuring: cruft this pair of gates exists to keep out.
    """
    env = {**os.environ, "COVERAGE_FILE": str(coverage_xml.parent / ".coverage")}
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-n", "auto",
            f"--cov={SCOPE}", f"--cov-report=xml:{coverage_xml}",
        ],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _run_diff_cover(coverage_xml: Path, diff_file: Path, json_out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "diff-cover", str(coverage_xml),
            "--diff-file", str(diff_file),
            "--fail-under=100",
            "--show-uncovered",
            f"--format=json:{json_out}",
        ],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _report_total() -> int:
    """Measure and print the whole-tree number, then exit. Never a gate."""
    with tempfile.TemporaryDirectory(prefix="diff-cover-gate-") as tmp:
        coverage_xml = Path(tmp) / "coverage.xml"
        run = _run_coverage(coverage_xml)
        if run.returncode != 0 or not coverage_xml.exists():
            print(run.stdout[-3000:], file=sys.stderr)
            return _fail("test suite failed under coverage; no whole-tree number")
        print(f"WHOLE-TREE-COVERAGE: {whole_tree_percent(coverage_xml):.1f}% of {SCOPE}")
        emit_work_units(len(measured_lines(coverage_xml)))
        return 0


# ---------------------------------------------------------------------------
# Pragma gate: refuse unjustified and money-path pragmas added in a diff
# ---------------------------------------------------------------------------

_PRAGMA_RE = re.compile(r'#\s*pragma:\s*no\s*cover')

_PRAGMA_FULL_RE = re.compile(
    r'#\s*pragma:\s*no\s*cover'
    r'(?:\s+#\s*)?'
    r'(.*)$'
)

_MONEY_PATH_PATTERNS = [
    r'\brecord_spend\b',
    r'\bnote_request\b',
    r'\bspend_limiter\b',
    r'\bbalance_tracker\b',
]
_MONEY_PATH_RE = re.compile('|'.join(_MONEY_PATH_PATTERNS))

_HUNK_HEADER_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')

_PRAGMA_CONTEXT_RADIUS = 3


def _check_pragma_violation(
    pragma_line: str, context: list[str], filepath: str, lineno: int
) -> str | None:
    for line in context:
        if _MONEY_PATH_RE.search(line):
            return (
                f"{filepath}:{lineno}: MONEY-PATH PRAGMA REFUSED — "
                f"'# pragma: no cover' on or adjacent to a money-path call site. "
                f"Money-path pragmas are never allowed; no justification can rescue them."
            )

    m = _PRAGMA_FULL_RE.search(pragma_line)
    justification = m.group(1).strip() if m else ''
    if not justification:
        return (
            f"{filepath}:{lineno}: UNJUSTIFIED PRAGMA — "
            f"every added '# pragma: no cover' must carry a one-line justification. "
            f"Add a comment explaining why this line cannot be covered by tests."
        )

    return None


def check_added_pragmas(base_sha: str, scope: str = SCOPE) -> tuple[int, list[str]]:
    diff_text = unified_diff(base_sha, scope, context=_PRAGMA_CONTEXT_RADIUS)

    lines: list[tuple[str, str, int, str]] = []
    current_file: str | None = None
    new_lineno = 0

    for raw in diff_text.splitlines():
        if raw.startswith('--- '):
            continue
        if raw.startswith('+++ '):
            target = raw[4:].strip()
            current_file = target.removeprefix('b/') if target != '/dev/null' else None
            continue
        if current_file is None:
            continue

        m = _HUNK_HEADER_RE.match(raw)
        if m:
            new_lineno = int(m.group(1))
            continue

        if raw.startswith('+'):
            lines.append((current_file, 'add', new_lineno, raw[1:]))
            new_lineno += 1
        elif raw.startswith('-'):
            continue
        elif raw.startswith('\\'):
            continue
        else:
            lines.append((current_file, 'ctx', new_lineno, raw[1:]))
            new_lineno += 1

    pragma_entries: list[tuple[int, str, int, str]] = []
    for i, (fpath, ltype, lno, content) in enumerate(lines):
        if ltype == 'add' and _PRAGMA_RE.search(content):
            pragma_entries.append((i, fpath, lno, content))

    violations: list[str] = []
    for idx, filepath, lineno, pragma_line in pragma_entries:
        context: list[str] = [pragma_line]
        for j in range(idx - 1, max(-1, idx - _PRAGMA_CONTEXT_RADIUS - 1), -1):
            if lines[j][0] != filepath:
                break
            context.insert(0, lines[j][3])
        for j in range(idx + 1, min(len(lines), idx + _PRAGMA_CONTEXT_RADIUS + 1)):
            if lines[j][0] != filepath:
                break
            context.append(lines[j][3])

        violation = _check_pragma_violation(pragma_line, context, filepath, lineno)
        if violation:
            violations.append(violation)

    return len(pragma_entries), violations


def main(argv: list[str]) -> int:
    if running_inside_pytest():
        print(
            "diff-cover gate: REENTRY-GUARD — invoked from inside a running pytest "
            "session. This gate runs the whole suite under coverage, so re-entering "
            "it here would fork-bomb the run. The gate is executed for real by "
            "gate_runner and by CI, where nothing sets PYTEST_CURRENT_TEST."
        )
        emit_work_units(0)
        return 0

    if "--report-total" in argv:
        return _report_total()

    try:
        base = resolve_base(argv[0] if argv else None)
        base_sha = merge_base(base)
        untracked = untracked_python_files(SCOPE)
        scoped_added = {
            path: lines
            for path, lines in added_lines_by_file(base_sha, SCOPE).items()
            if path.endswith(".py")
        }
        all_changed = changed_files(base_sha)
    except DiffScopeError as exc:
        return _fail(str(exc))

    print(f"diff-cover gate: base={base} merge-base={base_sha[:12]}")

    pragma_count, pragma_violations = check_added_pragmas(base_sha, SCOPE)
    if pragma_violations:
        for v in pragma_violations:
            print(f"  {v}", file=sys.stderr)
        return _fail(f"{len(pragma_violations)} pragma violation(s) — "
                     "added '# pragma: no cover' lines must be justified and "
                     "never on money-path call sites")
    if pragma_count:
        print(f"diff-cover gate: {pragma_count} added '# pragma: no cover' "
              "directive(s) — all justified, no money-path adjacency")
    else:
        print("diff-cover gate: no added '# pragma: no cover' directives in this diff")

    if untracked:
        return _fail(
            "untracked Python files under "
            f"{SCOPE}/ — git diff cannot see them, so their lines would silently "
            f"escape this gate: {untracked}. `git add` them and re-run."
        )

    if not scoped_added:
        if head_is_at_base(base_sha):
            print(f"diff-cover gate: HEAD IS the merge-base {base_sha[:12]} — "
                  "this change adds no lines at all (trunk build).")
        else:
            print(f"diff-cover gate: {len(all_changed)} changed file(s), none of them "
                  f"a {SCOPE}/**.py with added lines: {all_changed}")
        emit_work_units(0)
        return 0

    missing = _missing_tools()
    if missing:
        return _fail(
            f"required tooling not installed: {missing}. "
            "Install with: pip install -e '.[quality]'"
        )

    with tempfile.TemporaryDirectory(prefix="diff-cover-gate-") as tmp:
        tmpdir = Path(tmp)
        coverage_xml = tmpdir / "coverage.xml"
        run = _run_coverage(coverage_xml)
        if run.returncode != 0:
            print(run.stdout[-4000:], file=sys.stderr)
            return _fail(
                f"the test suite exited {run.returncode} under coverage — diff "
                "coverage measured against a red suite proves nothing."
            )

        try:
            measured = measured_lines(coverage_xml)
        except ValueError as exc:
            return _fail(str(exc))

        print(f"WHOLE-TREE-COVERAGE: {whole_tree_percent(coverage_xml):.1f}% of {SCOPE} "
              "(reported for grounding — NOT gated)")

        unmeasured = sorted(path for path in scoped_added if path not in measured)
        if unmeasured:
            return _fail(
                f"changed {SCOPE} file(s) absent from the coverage report: {unmeasured}. "
                "The gate cannot prove lines it never measured were exercised."
            )

        executable_added = {
            path: lines & measured[path] for path, lines in scoped_added.items()
        }
        expected = sum(len(lines) for lines in executable_added.values())
        if expected == 0:
            print(
                f"diff-cover gate: {len(scoped_added)} changed {SCOPE} file(s), "
                "0 added lines are executable statements (comments/blank/docstring "
                f"only): { {p: sorted(v) for p, v in scoped_added.items()} }"
            )
            emit_work_units(0)
            return 0

        diff_file = tmpdir / "scope.diff"
        json_out = tmpdir / "diff-cover.json"
        try:
            diff_file.write_text(unified_diff(base_sha, SCOPE, context=0), encoding="utf-8")
        except DiffScopeError as exc:
            return _fail(str(exc))

        result = _run_diff_cover(coverage_xml, diff_file, json_out)
        if result.stdout:
            print(result.stdout)
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr)

        if not json_out.exists() or json_out.stat().st_size == 0:
            return _fail(
                f"diff-cover exited {result.returncode} without writing a JSON report — "
                "no measurement to check."
            )
        try:
            report = json.loads(json_out.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return _fail(f"diff-cover JSON report is unparseable: {exc}")

        analysed = int(report.get("total_num_lines", 0))
        emit_work_units(analysed)

        if analysed < expected:
            return _fail(
                f"diff-cover analysed {analysed} line(s) but the diff contains {expected} "
                "added executable line(s) — the tool measured less than the change "
                "contains, so a green here would be meaningless. "
                f"Expected per file: { {p: sorted(v) for p, v in executable_added.items() if v} }"
            )

        if result.returncode != 0:
            violations = int(report.get("total_num_violations", 0))
            print(
                f"FAIL: diff-cover gate — {violations} of {analysed} added line(s) in "
                f"{SCOPE}/ are never executed by the test suite. Add a test that "
                "exercises them (see the uncovered lines listed above).",
                file=sys.stderr,
            )
            return 1

        print(f"diff-cover gate: OK — all {analysed} added executable line(s) in "
              f"{SCOPE}/ are exercised by the test suite")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
