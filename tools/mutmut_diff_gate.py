#!/usr/bin/env python3
# @covers: mutation
"""Mutation gate (diff-scoped) — a test that cannot go red is not a test.

THE GAP THIS CLOSES (D-005 #2): diff-coverage proves an added line was
EXECUTED. It cannot prove anything was ASSERTED about it. ``assert result is not
None`` executes every line and detects no behaviour at all. mutmut breaks the
changed code and checks that some test notices; a surviving mutant is a
mechanically-proven assertion hole, which is the replacement D-005 asks for over
hand-written "this gate can go red" claims.

DIFF-SCOPED ON TWO AXES, because one is not enough:
  * FILES — mutmut 3.x has no ``--paths-to-mutate`` flag (the ticket's wording
    predates it). Scoping is ``only_mutate`` globs under ``[tool.mutmut]``, read
    from ``pyproject.toml`` in the CWD (``mutmut/configuration.py``, verified on
    3.6.0), so only the changed files get mutants generated.
  * FUNCTIONS — file scoping alone is NOT diff-scoping. Adding one function to a
    600-line module would mutate the whole module and judge the PR on mutants of
    code it never touched; on a tree with a standing test-strength deficit that
    reds every PR and the gate is off within a week. ``mutmut run <name-glob>``
    filters by mutant key (fnmatch, verified on 3.6.0), so this gate runs and
    judges ONLY mutants of the functions the diff actually changed.

WHY AN ISOLATED TREE — the scoped config MUST live in a ``pyproject.toml``, and
rewriting the repo's own (what a first attempt at this did) mutates a file
thirteen other work items hold open and leaves it corrupted if the process is
killed mid-run. This gate copies the tracked working tree to a temp dir, writes
the generated config THERE, and runs mutmut in it. The repo's own
``pyproject.toml`` is never opened for writing.

FAIL-CLOSED PATHS — each exits non-zero rather than reporting a pass:
  * base ref unresolvable / no merge-base / untracked ``src/**.py``;
  * mutmut not installed;
  * the isolated run tree could not be built;
  * mutmut exceeded the timeout — a gate that cannot finish is a FAILURE, not a
    slow pass; it is the same green-by-omission this gate exists to kill;
  * changed lines DO sit inside functions but the name globs matched ZERO
    mutants — the scoping is broken, and an empty result set proves nothing;
  * any mutant of a changed function is not KILLED (survived / timeout /
    suspicious / no tests).

``mutmut run`` exits 0 even when mutants survive (verified on 3.6.0), so the
exit code is never the verdict on its own: the gate parses ``mutmut results``,
filters it to the mutants it actually asked for (unrun mutants report "not
checked" and must not be read as failures of THIS change), and requires a
positive mutant count before it will report a pass.

KNOWN TOOL LIMIT, stated rather than hidden: mutmut 3.x mutates function and
method bodies only. A change confined to module-level code (imports, constants,
class-body attributes) has nothing mutmut can mutate; the gate says so, prints
the lines, and passes. That is a fact about the tool, and it is why this gate
sits BESIDE diff-cover rather than replacing it.

Usage:
    python3 tools/mutmut_diff_gate.py [base-ref]
"""
from __future__ import annotations

import ast
import importlib.util
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
    untracked_python_files,
)
from tools.gate_contract import emit_work_units  # noqa: E402

SCOPE = "src"
DEFAULT_TIMEOUT_SECONDS = 1800
TIMEOUT_ENV_VAR = "CHARON_MUTMUT_TIMEOUT"

# mutmut's own class-name separator inside a mutant key (U+01C1), verified on
# 3.6.0: top-level -> "pkg.mod.x_func__mutmut_1"
#        method    -> "pkg.mod.xǁClassǁmethod__mutmut_1"
CLASS_SEPARATOR = "ǁ"

# Progress tail: "⠦ 12/37  \U0001f389 12 ..." — the denominator is how many
# mutants were actually run under the name filter.
_PROGRESS_RE = re.compile(r"(?P<done>\d+)/(?P<total>\d+)\s")
# `mutmut results` prints "    <key>: <status>" for every NON-killed mutant.
_STATUS_RE = re.compile(r"^\s+(?P<key>\S+):\s*(?P<status>.+?)\s*$")
# mutmut's own assertion when a name filter selects nothing.
_NO_MATCH_MARKER = "Filtered for specific mutants, but nothing matches"

# Every status mutmut prints is a non-kill; enumerated so the failure message can
# name the shape rather than echoing an opaque token.
KNOWN_BAD_STATUSES = ("survived", "no tests", "timeout", "suspicious", "not checked")


def _fail(message: str) -> int:
    emit_work_units(0)
    print(f"FAIL: mutmut gate — {message}", file=sys.stderr)
    return 1


def _timeout_seconds() -> int:
    raw = os.environ.get(TIMEOUT_ENV_VAR, "")
    if raw.strip():
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_SECONDS


def module_dotted_name(path: str) -> str:
    """``src/charon/gate_runner.py`` -> ``charon.gate_runner`` (mutmut key prefix)."""
    rel = Path(path).relative_to(SCOPE).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def changed_function_globs(path: str, lines: set[int]) -> list[str]:
    """Mutant-name globs for the functions/methods *lines* fall inside.

    Returns ``[]`` when no changed line lands in a function body — mutmut 3.x
    mutates function bodies only, so module-level changes have no mutants by
    construction (see the module docstring's KNOWN TOOL LIMIT).
    """
    source = (repo_root() / path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)
    dotted = module_dotted_name(path)
    globs: set[str] = set()

    def visit(node: ast.AST, class_name: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                end = child.end_lineno or child.lineno
                if any(start <= line <= end for line in lines):
                    if class_name:
                        mangled = f"x{CLASS_SEPARATOR}{class_name}{CLASS_SEPARATOR}{child.name}"
                    else:
                        mangled = f"x_{child.name}"
                    globs.add(f"{dotted}.{mangled}__mutmut_*")
                # do NOT descend: mutmut mutates the OUTERMOST function as a unit
                continue
            if isinstance(child, ast.ClassDef):
                visit(child, child.name)
                continue
            visit(child, class_name)

    visit(tree, None)
    return sorted(globs)


def scoped_mutmut_config(original: str, changed: list[str], also_copy: list[str]) -> str:
    """Return *original* pyproject text with a diff-scoped ``[tool.mutmut]``.

    Any pre-existing ``[tool.mutmut]`` section is dropped first, so a wider one
    already in the file cannot shadow the scoped one this gate depends on.
    """
    stripped = re.sub(r"\n\[tool\.mutmut\].*?(?=\n\[|\Z)", "\n", original, flags=re.DOTALL)
    body = [
        "",
        "# GENERATED by tools/mutmut_diff_gate.py in a throwaway tree — never committed.",
        "[tool.mutmut]",
        f"source_paths = {[SCOPE]!r}",
        f"only_mutate = {changed!r}",
        f"also_copy = {also_copy!r}",
    ]
    return stripped.rstrip() + "\n" + "\n".join(body) + "\n"


def build_isolated_tree(destination: Path, changed: list[str]) -> list[str]:
    """Copy the tracked working tree into *destination* and scope the config.

    mutmut runs the suite from a ``mutants/`` subdirectory into which it copies
    only ``source_paths`` plus ``also_copy``. This repo's tests import ``tools.*``
    and read repo files, so every top-level tracked entry except the mutated
    source root has to be listed, or the baseline suite fails for reasons that
    have nothing to do with mutation.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root(), capture_output=True, text=True, check=False,
    )
    if listing.returncode != 0:
        raise DiffScopeError(f"git ls-files failed: {listing.stderr.strip()!r}")
    tracked = [entry for entry in listing.stdout.split("\0") if entry]
    if not tracked:
        raise DiffScopeError("git ls-files listed no tracked files")

    for rel in tracked:
        source = repo_root() / rel
        if not source.is_file():
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    also_copy = sorted(
        {rel.split("/")[0] for rel in tracked if "/" in rel and not rel.startswith(f"{SCOPE}/")}
        | {rel for rel in tracked if "/" not in rel}
    )
    pyproject = destination / "pyproject.toml"
    if not pyproject.is_file():
        raise DiffScopeError("no pyproject.toml in the isolated tree — mutmut has no config home")
    pyproject.write_text(
        scoped_mutmut_config(pyproject.read_text(encoding="utf-8"), changed, also_copy),
        encoding="utf-8",
    )
    return also_copy


def parse_mutant_total(run_stdout: str) -> int | None:
    """How many mutants mutmut actually ran, or None if it never reported."""
    totals = [int(total) for _done, total in _PROGRESS_RE.findall(run_stdout.replace("\r", "\n"))]
    return max(totals) if totals else None


def parse_statuses(results_stdout: str, globs: list[str]) -> dict[str, str]:
    """``{mutant key: status}`` for the mutants THIS run asked for.

    Keys outside *globs* are dropped: mutants that were never selected report
    "not checked", and reading those as failures of the current change is the
    same false-red that gets a gate switched off.
    """
    import fnmatch

    selected: dict[str, str] = {}
    for line in results_stdout.splitlines():
        match = _STATUS_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if any(fnmatch.fnmatch(key, glob) for glob in globs):
            selected[key] = match.group("status").strip()
    return selected


def _run(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def main(argv: list[str]) -> int:
    if running_inside_pytest():
        print(
            "mutmut gate: REENTRY-GUARD — invoked from inside a running pytest "
            "session. This gate runs the suite once per mutant, so re-entering it "
            "here would fork-bomb the run. The gate is executed for real by "
            "gate_runner and by CI, where nothing sets PYTEST_CURRENT_TEST."
        )
        emit_work_units(0)
        return 0

    positional = [arg for arg in argv if not arg.startswith("-")]
    try:
        base = resolve_base(positional[0] if positional else None)
        base_sha = merge_base(base)
        untracked = untracked_python_files(SCOPE)
        added = {
            path: lines
            for path, lines in added_lines_by_file(base_sha, SCOPE).items()
            if path.endswith(".py")
        }
        all_changed = changed_files(base_sha)
    except DiffScopeError as exc:
        return _fail(str(exc))

    print(f"mutmut gate: base={base} merge-base={base_sha[:12]}")

    if untracked:
        return _fail(
            f"untracked Python files under {SCOPE}/ — git diff cannot see them, so "
            f"their mutants would never be generated: {untracked}. `git add` them."
        )

    if not added:
        if head_is_at_base(base_sha):
            print(f"mutmut gate: HEAD IS the merge-base {base_sha[:12]} — this change "
                  "adds no source at all (trunk build).")
        else:
            print(f"mutmut gate: {len(all_changed)} changed file(s), none of them a "
                  f"{SCOPE}/**.py: {all_changed}")
        emit_work_units(0)
        return 0

    changed = sorted(added)
    try:
        globs = sorted({g for path in changed for g in changed_function_globs(path, added[path])})
    except (OSError, SyntaxError, ValueError) as exc:
        return _fail(f"could not map changed lines onto functions: {exc}")

    if not globs:
        print(
            f"mutmut gate: {len(changed)} changed {SCOPE} file(s) {changed}, but no "
            "changed line lies inside a function or method body. mutmut 3.x mutates "
            "function bodies only, so there is nothing it can mutate here. "
            f"Changed lines: { {p: sorted(v) for p, v in added.items()} }"
        )
        emit_work_units(0)
        return 0

    if importlib.util.find_spec("mutmut") is None:
        return _fail("mutmut is not installed. Install with: pip install -e '.[quality]'")

    timeout = _timeout_seconds()
    print(f"mutmut gate: {len(changed)} changed file(s), {len(globs)} changed function(s) "
          f"{globs} (timeout {timeout}s)")

    with tempfile.TemporaryDirectory(prefix="mutmut-diff-gate-") as tmp:
        tree = Path(tmp) / "tree"
        tree.mkdir()
        try:
            build_isolated_tree(tree, changed)
        except (DiffScopeError, OSError) as exc:
            return _fail(f"could not build the isolated run tree: {exc}")

        try:
            run = _run([sys.executable, "-m", "mutmut", "run", *globs], tree, timeout)
            results = _run([sys.executable, "-m", "mutmut", "results"], tree, timeout)
        except subprocess.TimeoutExpired:
            return _fail(
                f"mutmut did not finish within {timeout}s for {len(globs)} changed "
                "function(s). A gate that cannot finish is a FAILURE, not a slow pass "
                f"— shrink the change, or raise ${TIMEOUT_ENV_VAR} deliberately."
            )

    combined = (run.stdout + "\n" + run.stderr).replace("\r", "\n")
    for line in [ln for ln in combined.splitlines() if ln.strip()][-6:]:
        print(line)

    if _NO_MATCH_MARKER in combined:
        return _fail(
            f"mutmut generated NO mutants for the changed function(s) {globs}. The "
            "diff scoping matched nothing, so an empty result set is a "
            "misconfiguration, not a clean sheet."
        )

    total = parse_mutant_total(run.stdout)
    statuses = parse_statuses(results.stdout, globs)
    print(f"mutmut gate: mutants_run={total} run_rc={run.returncode} "
          f"non_killed={len(statuses)}")

    if not total:
        return _fail(
            f"mutmut ran 0 mutants for {len(globs)} changed function(s) (run exited "
            f"{run.returncode}) — no measurement was taken, so this is not a pass."
        )

    emit_work_units(total)

    if statuses:
        print(
            f"FAIL: mutmut gate — {len(statuses)} of {total} mutant(s) in the CHANGED "
            "functions were not killed. A mutant that survives is a line whose "
            "behaviour no test asserts on:",
            file=sys.stderr,
        )
        for key, status in sorted(statuses.items()):
            known = "" if status in KNOWN_BAD_STATUSES else " (unrecognised status)"
            print(f"    {key}: {status}{known}", file=sys.stderr)
        return 1

    if run.returncode != 0:
        return _fail(
            f"mutmut run exited {run.returncode} with no scored mutants — that is an "
            "error, not a clean sheet."
        )

    print(f"mutmut gate: OK — all {total} mutant(s) in the changed functions were killed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
