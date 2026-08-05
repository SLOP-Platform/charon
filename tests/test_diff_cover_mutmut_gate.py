"""RED-proof for the two diff-scoped quality gates (tools/diff_cover_gate.py,
tools/mutmut_diff_gate.py).

WHY A FIXTURE REPO AND NOT THIS ONE — both gates measure "the lines this change
adds". Proving they go RED therefore needs a change that is genuinely
unexercised, and this repo's own suite is green by construction: any
red-provoking edit made here would either be reverted before the assertion ran
or leave the tree dirty for every other test. Each test below builds a
throwaway git repo (four files, one function, one test), makes the exact edit
that should trip the gate, and runs the REAL gate script against it. The
fixture is ~3s for diff-cover and ~2s for mutmut, versus ~40s and ~140s for the
same proof taken against this tree.

WHAT IS ASSERTED — the gate's EXIT CODE and its emitted WORK-UNITS count, never
its source text. tests/test_gate_contract.py records why: a gate test that
asserts on the implementation pins the bug, so fixing the gate breaks the test.

THE FOUR FAIL-CLOSED PATHS. Both gates are written to exit non-zero rather than
report a pass when they cannot establish the truth. Four of those routes shipped
never having been executed — an unresolvable base ref, an unparseable coverage
report, absent tooling, and an untracked ``src/**.py`` that ``git diff`` cannot
see. A fail-closed path nobody has run is a fail-OPEN path nobody has noticed,
which is the exact shape this pair of gates exists to catch in product code.

THE REENTRY GUARD. tests/test_gate_contract.py runs every registered gate script
as a subprocess, and both of these gates run the whole test suite. Without the
``PYTEST_CURRENT_TEST`` guard, registering them makes the suite invoke itself
until the box gives out. The guard is load-bearing and is pinned here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import diff_cover_gate, mutmut_diff_gate  # noqa: E402
from tools.gate_contract import parse_work_units  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPTS = ("diff_cover_gate.py", "mutmut_diff_gate.py")

_BASE_MODULE = '''"""Fixture product module."""


def add(a, b):
    return a + b
'''

# Four executable added lines, none of them exercised by the base test.
_ADDED_FUNCTION = '''

def is_even(n):
    if n % 2 == 0:
        return True
    return False
'''

_BASE_TEST = '''from fixturepkg.calc import add


def test_add():
    assert add(2, 3) == 5
'''

# Executes every added line and asserts on BOTH branches -- kills the mutants.
_STRONG_TEST = _BASE_TEST + '''

from fixturepkg.calc import is_even


def test_is_even():
    assert is_even(4) is True
    assert is_even(5) is False
'''

# Executes every added line and asserts nothing about them -- the assertion hole
# diff-coverage cannot see and mutation testing can.
_WEAK_TEST = _BASE_TEST + '''

from fixturepkg.calc import is_even


def test_is_even():
    assert is_even(4) is not None
    assert is_even(5) is not None
'''

# Captured VERBATIM from `python3 -m mutmut run <glob>` on mutmut 3.6.0
# (2026-08-04, the fixture repo below). The denominator on the progress line is
# the only place mutmut reports how many mutants it actually ran.
_MUTMUT_PROGRESS = (
    "    done in 38ms (1 files mutated, 1 ignored, 0 unmodified)\n"
    "Running mutation testing\n"
    "\n"
    "⠸ 0/7  \U0001f389 0 \U0001fae5 0  ⏰ 0  \U0001f914 0  \U0001f641 0  \U0001f507 0\n"
    "⠏ 6/7  \U0001f389 0 \U0001fae5 0  ⏰ 0  \U0001f914 0  \U0001f641 6  \U0001f507 0\n"
    "68.50 mutations/second\n"
)

_CONFTEST = '''import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
'''


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, f"git {args} failed in {root}: {proc.stderr}"
    return proc.stdout


def _build_fixture(root: Path) -> Path:
    """A four-file git repo with the two gate scripts copied in.

    The scripts are copied rather than invoked in place because both resolve
    their own repo root from ``__file__``; running this tree's copy against the
    fixture would make them import this tree's ``tools`` package while measuring
    the fixture's diff.
    """
    (root / "src" / "fixturepkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "tools").mkdir()
    (root / "src" / "fixturepkg" / "__init__.py").write_text("")
    (root / "src" / "fixturepkg" / "calc.py").write_text(_BASE_MODULE)
    (root / "tests" / "test_calc.py").write_text(_BASE_TEST)
    (root / "conftest.py").write_text(_CONFTEST)
    (root / "pyproject.toml").write_text('[project]\nname = "fixturepkg"\nversion = "0"\n')
    for name in ("gate_contract.py", "diff_scope.py", *GATE_SCRIPTS):
        shutil.copy2(REPO_ROOT / "tools" / name, root / "tools" / name)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "fixture@charon.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "fixture base")
    return root


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    return _build_fixture(tmp_path / "repo")


def _gate_env(*, inside_pytest: bool) -> dict[str, str]:
    env = dict(os.environ)
    if inside_pytest:
        env["PYTEST_CURRENT_TEST"] = "tests/test_x.py::test_x (call)"
    else:
        env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _run_gate(root: Path, script: str, *args: str,
              inside_pytest: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a gate script the way gate_runner does: CWD-relative, as a subprocess."""
    return subprocess.run(
        [sys.executable, f"tools/{script}", *args],
        cwd=root, capture_output=True, text=True, env=_gate_env(inside_pytest=inside_pytest),
    )


# --------------------------------------------------------------------------
# The headline contract: an added line no test executes must block the merge
# --------------------------------------------------------------------------

def test_diff_cover_reds_on_an_unexercised_added_line_and_greens_when_covered(
        fixture_repo: Path) -> None:
    """RED -> GREEN -> revert -> RED, against the real gate script.

    The GREEN leg is not decoration: without it a gate that failed
    unconditionally would pass the RED leg, which is how a gate ends up
    blocking merges for a reason nobody can reproduce.
    """
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    test = fixture_repo / "tests" / "test_calc.py"

    module.write_text(_BASE_MODULE + _ADDED_FUNCTION)
    red = _run_gate(fixture_repo, "diff_cover_gate.py", "HEAD")
    assert red.returncode == 1, f"expected RED, got {red.returncode}\n{red.stdout}"
    assert "are never executed by the test suite" in red.stderr
    assert parse_work_units(red.stdout) == 4

    test.write_text(_STRONG_TEST)
    green = _run_gate(fixture_repo, "diff_cover_gate.py", "HEAD")
    assert green.returncode == 0, f"expected GREEN, got {green.returncode}\n{green.stderr}"
    assert "all 4 added executable line(s)" in green.stdout
    assert parse_work_units(green.stdout) == 4

    test.write_text(_BASE_TEST)
    reverted = _run_gate(fixture_repo, "diff_cover_gate.py", "HEAD")
    assert reverted.returncode == 1, "reverting the covering test must re-RED the gate"


def test_diff_cover_leaves_no_coverage_droppings_in_the_checkout(
        fixture_repo: Path) -> None:
    """The gate runs the suite under coverage in the checkout it is measuring.
    coverage writes its data file relative to the CWD, and xdist adds one per
    worker, so without ``COVERAGE_FILE`` redirected the gate dirties the tree on
    every run — untracked cruft, in a repo where an untracked file is itself a
    fail-closed condition for this very gate."""
    (fixture_repo / "src" / "fixturepkg" / "calc.py").write_text(_BASE_MODULE + _ADDED_FUNCTION)
    (fixture_repo / "tests" / "test_calc.py").write_text(_STRONG_TEST)
    assert _run_gate(fixture_repo, "diff_cover_gate.py", "HEAD").returncode == 0

    dropped = [line for line in _git(fixture_repo, "status", "--porcelain").splitlines()
               if ".coverage" in line]
    assert dropped == [], f"the gate dirtied the tree it measures: {dropped}"


def test_mutmut_reds_on_a_surviving_mutant_and_greens_on_a_real_assertion(
        fixture_repo: Path) -> None:
    """The half diff-coverage cannot do: the WEAK test executes every added line,
    so diff-cover is GREEN on it. Only mutation testing sees that it asserts
    nothing. RED -> GREEN -> revert -> RED."""
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    test = fixture_repo / "tests" / "test_calc.py"
    module.write_text(_BASE_MODULE + _ADDED_FUNCTION)

    test.write_text(_WEAK_TEST)
    covered = _run_gate(fixture_repo, "diff_cover_gate.py", "HEAD")
    assert covered.returncode == 0, "the weak test DOES execute every added line"

    red = _run_gate(fixture_repo, "mutmut_diff_gate.py", "HEAD")
    assert red.returncode == 1, f"expected RED, got {red.returncode}\n{red.stdout}"
    assert "were not killed" in red.stderr and "survived" in red.stderr
    assert parse_work_units(red.stdout) == 7

    test.write_text(_STRONG_TEST)
    green = _run_gate(fixture_repo, "mutmut_diff_gate.py", "HEAD")
    assert green.returncode == 0, f"expected GREEN, got {green.returncode}\n{green.stderr}"
    assert "all 7 mutant(s) in the changed functions were killed" in green.stdout

    test.write_text(_WEAK_TEST)
    assert _run_gate(fixture_repo, "mutmut_diff_gate.py", "HEAD").returncode == 1


# --------------------------------------------------------------------------
# Fail-closed paths — every one of these shipped never having been executed
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script", GATE_SCRIPTS)
def test_gate_fails_closed_when_the_base_ref_does_not_resolve(
        fixture_repo: Path, script: str) -> None:
    """The CI shape: a shallow ``actions/checkout`` has no ``origin/master``, so
    "which lines did this change add" has no answer. Returning an empty diff
    there would pass every PR in CI while passing locally for a different
    reason — the failure mode is invisible precisely because it is green."""
    proc = _run_gate(fixture_repo, script, "origin/nonexistent-base")
    assert proc.returncode == 1, f"unresolvable base must FAIL, got {proc.returncode}"
    assert "does not resolve to a commit" in proc.stderr
    assert "fetch-depth: 0" in proc.stderr, "the message must name the CI fix"
    assert parse_work_units(proc.stdout) == 0


@pytest.mark.parametrize("script", GATE_SCRIPTS)
def test_gate_fails_closed_on_an_untracked_source_file(
        fixture_repo: Path, script: str) -> None:
    """``git diff`` cannot see a file that was never ``git add``-ed, so a brand
    new module is invisible to both gates — which is exactly the "new module
    lands with no exercising test" case they were built for. Fail, don't skip."""
    (fixture_repo / "src" / "fixturepkg" / "orphan.py").write_text("def orphan():\n    return 1\n")
    proc = _run_gate(fixture_repo, script, "HEAD")
    assert proc.returncode == 1, f"untracked src/**.py must FAIL, got {proc.returncode}"
    assert "untracked Python files" in proc.stderr
    assert "orphan.py" in proc.stderr
    assert parse_work_units(proc.stdout) == 0


def test_diff_cover_fails_closed_when_the_required_tooling_is_missing(
        fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """No diff-cover on PATH means no measurement. A gate that shrugs and exits 0
    when its own tool is absent is the pip-install-failed-silently shape."""
    monkeypatch.chdir(fixture_repo)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    (fixture_repo / "src" / "fixturepkg" / "calc.py").write_text(_BASE_MODULE + _ADDED_FUNCTION)

    assert diff_cover_gate.main(["HEAD"]) == 1
    out = capsys.readouterr()
    assert "required tooling not installed" in out.err
    assert "diff-cover" in out.err
    assert parse_work_units(out.out) == 0


def test_diff_cover_fails_closed_on_an_unparseable_coverage_report(
        fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """A truncated/garbage coverage.xml must not read as "nothing uncovered".
    The suite is stubbed GREEN here so the only thing that can fail the gate is
    the unreadable report itself."""
    monkeypatch.chdir(fixture_repo)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    (fixture_repo / "src" / "fixturepkg" / "calc.py").write_text(_BASE_MODULE + _ADDED_FUNCTION)

    def _garbage(coverage_xml: Path) -> subprocess.CompletedProcess[str]:
        coverage_xml.write_text("<coverage><truncated")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(diff_cover_gate, "_run_coverage", _garbage)
    assert diff_cover_gate.main(["HEAD"]) == 1
    out = capsys.readouterr()
    assert "unparseable" in out.err
    assert parse_work_units(out.out) == 0


@pytest.mark.parametrize(
    "body,expected",
    [
        pytest.param(None, "missing or empty", id="absent"),
        pytest.param("", "missing or empty", id="empty"),
        pytest.param("<coverage><truncated", "unparseable", id="malformed"),
        pytest.param("<coverage><packages/></coverage>", "no <sources>", id="no-sources"),
    ],
)
def test_measured_lines_refuses_every_unusable_coverage_report(
        tmp_path: Path, body: str | None, expected: str) -> None:
    """"I could not read the coverage data" must never collapse into "the
    coverage data was clean" — they are the same return value otherwise."""
    report = tmp_path / "coverage.xml"
    if body is not None:
        report.write_text(body)
    with pytest.raises(ValueError, match=expected):
        diff_cover_gate.measured_lines(report)


def test_measured_lines_refuses_a_report_that_measured_no_files(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed report with zero <class> elements is a coverage run that
    measured nothing — the zero-work-units failure in XML form."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    report = tmp_path / "coverage.xml"
    report.write_text(
        f"<coverage><sources><source>{tmp_path / 'src'}</source></sources>"
        "<packages/></coverage>"
    )
    with pytest.raises(ValueError, match="no measured files"):
        diff_cover_gate.measured_lines(report)


# --------------------------------------------------------------------------
# The reentry guard — without it, registering these gates fork-bombs the suite
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script", GATE_SCRIPTS)
def test_gate_reentry_guard_exits_zero_when_invoked_from_inside_pytest(
        script: str) -> None:
    """test_gate_contract runs EVERY registered gate script as a subprocess, and
    both of these run the whole suite. Deleting this guard makes that test
    re-enter the suite, which re-enters it again. Run against this repo, where a
    real invocation would cost 40s+ — the guard is proven by the gate returning
    in well under that with an explicit count of zero."""
    proc = _run_gate(REPO_ROOT, script, inside_pytest=True)
    assert proc.returncode == 0, f"guard must not fail the suite: {proc.stderr}"
    assert "REENTRY-GUARD" in proc.stdout
    assert parse_work_units(proc.stdout) == 0


def test_reentry_guard_reads_the_marker_pytest_actually_exports() -> None:
    """The guard keys on ``PYTEST_CURRENT_TEST``, which pytest sets for the
    duration of every test — including this one. Asserting it is set here is
    what stops the guard from being keyed on a variable nothing exports."""
    assert os.environ.get("PYTEST_CURRENT_TEST"), "pytest must export the marker"
    assert mutmut_diff_gate.running_inside_pytest() is True
    assert diff_cover_gate.running_inside_pytest() is True


# --------------------------------------------------------------------------
# Diff scoping — the property that makes these gates affordable at all
# --------------------------------------------------------------------------

def test_changed_function_globs_select_only_the_function_the_diff_touched(
        fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File-level scoping is not diff scoping. Adding one function to a module
    must not put the module's OTHER functions on trial — on a tree with standing
    test-strength debt that reds every PR, and the gate is off within a week."""
    monkeypatch.chdir(fixture_repo)
    module = fixture_repo / "src" / "fixturepkg" / "calc.py"
    module.write_text(_BASE_MODULE + _ADDED_FUNCTION)
    added_line = len(_BASE_MODULE.splitlines()) + 3  # the `def is_even` line

    globs = mutmut_diff_gate.changed_function_globs(
        "src/fixturepkg/calc.py", {added_line})
    assert globs == ["fixturepkg.calc.x_is_even__mutmut_*"]
    assert not any("x_add__mutmut" in g for g in globs), "untouched function on trial"


def test_changed_function_globs_are_empty_for_a_module_level_change(
        fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mutmut 3.x mutates function bodies only. A change confined to imports or
    constants has no mutants BY CONSTRUCTION, and the gate must say so rather
    than treat an empty result set as a clean sheet."""
    monkeypatch.chdir(fixture_repo)
    assert mutmut_diff_gate.changed_function_globs("src/fixturepkg/calc.py", {1}) == []


def test_parse_statuses_drops_mutants_this_run_never_asked_for() -> None:
    """``mutmut results`` prints every non-killed mutant in the whole store,
    including ones this diff-scoped run never selected — they report "not
    checked". Reading those as failures of the current change is a false red,
    and a gate that cries wolf gets switched off."""
    results = (
        "  fixturepkg.calc.x_is_even__mutmut_1: survived\n"
        "  fixturepkg.other.x_unrelated__mutmut_9: not checked\n"
    )
    selected = mutmut_diff_gate.parse_statuses(
        results, ["fixturepkg.calc.x_is_even__mutmut_*"])
    assert selected == {"fixturepkg.calc.x_is_even__mutmut_1": "survived"}


def test_mutant_total_is_read_from_the_progress_format_mutmut_really_prints() -> None:
    """mutmut 3.6.0 exits 0 even when mutants survive (measured on this box, not
    read in a changelog), so the mutant COUNT is the only honest signal. The
    stream below is captured verbatim from ``mutmut run`` 3.6.0 — a hand-invented
    progress string would pin the regex to a format the tool does not emit, and
    the gate would report "0 mutants ran" on every real invocation.

    The generation line is the trap: "1 files mutated, 1 ignored" contains
    countable numbers and no denominator, and reading it as a total would let a
    run that tested nothing report a positive count."""
    assert mutmut_diff_gate.parse_mutant_total(_MUTMUT_PROGRESS) == 7
    generation_only = "    done in 38ms (1 files mutated, 1 ignored, 0 unmodified)\n"
    assert mutmut_diff_gate.parse_mutant_total(generation_only) is None
    assert mutmut_diff_gate.parse_mutant_total("no progress here") is None


def test_scoped_mutmut_config_drops_a_wider_preexisting_section() -> None:
    """A ``[tool.mutmut]`` already in pyproject.toml would silently widen the
    scope back to the whole tree. It is stripped, not merged."""
    original = '[project]\nname = "x"\n\n[tool.mutmut]\nonly_mutate = ["src"]\n'
    scoped = mutmut_diff_gate.scoped_mutmut_config(original, ["src/a.py"], ["tests"])
    assert scoped.count("[tool.mutmut]") == 1
    assert "'src/a.py'" in scoped
    assert 'only_mutate = ["src"]' not in scoped


# --------------------------------------------------------------------------
# The one exemption: a PROVABLY empty scope, printed with its evidence
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script", GATE_SCRIPTS)
def test_gate_passes_with_zero_units_only_when_head_is_the_merge_base(
        fixture_repo: Path, script: str) -> None:
    """The trunk build. Zero is the correct count here — and it is the ONLY
    route to a green zero, which is why the gate prints the merge-base SHA it
    proved it against instead of just exiting 0."""
    proc = _run_gate(fixture_repo, script, "HEAD")
    assert proc.returncode == 0, proc.stderr
    assert "HEAD IS the merge-base" in proc.stdout
    assert parse_work_units(proc.stdout) == 0


def test_coverage_report_maps_filenames_back_to_repo_relative_paths(
        fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The join that decides whether a changed file counts as "measured". If the
    <sources> prefix is dropped, every changed file looks absent from the report
    and the gate reds on a tree that is in fact fully covered."""
    monkeypatch.chdir(fixture_repo)
    report = fixture_repo / "coverage.xml"
    report.write_text(
        "<coverage>"
        f"<sources><source>{fixture_repo / 'src'}</source></sources>"
        '<packages><class filename="fixturepkg/calc.py">'
        '<lines><line number="5"/></lines>'
        "</class></packages></coverage>"
    )

    assert diff_cover_gate.measured_lines(report) == {"src/fixturepkg/calc.py": {5}}
