#!/usr/bin/env python3
"""S1 grader — Localized money-path bugfix + obvious test (Tier 1, work_class=money-path).
Usage: python3 s1.py --worktree <dir> --baseline fixtures/sections/s1
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FUNCTIONAL_SNIPPET = (
    "import sys; sys.path.insert(0, '.'); "
    "from gateway.providers import Provider, cheapest_provider; "
    "providers = [Provider('a','u','cheap',5), Provider('b','u','cheap',1), Provider('c','u','cheap',9)]; "  # noqa: E501
    "print(cheapest_provider(providers).name)"
)


def functional_check(worktree):
    try:
        proc = subprocess.run([sys.executable, "-c", FUNCTIONAL_SNIPPET],
                               cwd=str(worktree), capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "b"


def main():
    worktree, baseline = common.parse_args(sys.argv[1:])

    ok_a = functional_check(worktree)
    if not ok_a:
        return common.emit(0, "fail", "cheapest_provider still wrong on unsorted input")

    changed = common.changed_files(baseline, worktree)
    new_tests = common.new_or_modified_test_files(baseline, worktree)
    scope = common.scope_ok(changed, ["gateway/providers.py", "tests/"])

    if not new_tests:
        gate = "pass" if scope else "fail"
        return common.emit(40, gate, "code fixed but no discriminating test added")

    passed_fixed, _ = common.run_pytest(worktree, args=new_tests)
    buggy_content = (baseline / "gateway/providers.py").read_text()
    passed_buggy, _, _ = common.swap_and_run_pytest(worktree, "gateway/providers.py", buggy_content, test_args=new_tests)  # noqa: E501

    discriminates = passed_fixed and not passed_buggy

    if discriminates and scope:
        return common.emit(100, "pass", "fix correct, new test fails on buggy code / passes on fixed, scope clean")  # noqa: E501
    if not scope:
        return common.emit(70 if discriminates else 40, "pass",
                            f"correct fix{' + discriminating test' if discriminates else ''} but diff touched files beyond providers.py/tests/: {changed}")  # noqa: E501
    return common.emit(70, "pass", "fix correct and scoped, but new test does not distinguish buggy vs fixed code")  # noqa: E501


if __name__ == "__main__":
    main()
