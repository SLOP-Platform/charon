#!/usr/bin/env python3
"""S4 grader — Adversarial subtle bug, discriminating test, no regression
(Tier 3, work_class=refactor+tests). Usage:
    python3 s4.py --worktree <dir> --baseline fixtures/sections/s4
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

NAMESPACED_ID_RE = re.compile(r'["\']([\w.\-]+/[\w.\-]+(?:/[\w.\-]+)*)["\']')

FUNCTIONAL_SNIPPET = (
    "import sys; sys.path.insert(0, '.'); "
    "from gateway.normalize import normalize_response; "
    "r = normalize_response({'model': 'deepseek/fireworks/deepseek-v4-pro'}); "
    "print(r['model'])"
)


def functional_check(worktree):
    try:
        proc = subprocess.run([sys.executable, "-c", FUNCTIONAL_SNIPPET],
                               cwd=str(worktree), capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return False, ""
    return proc.returncode == 0 and proc.stdout.strip() == "deepseek-v4-pro", proc.stdout.strip()


def isolates_namespaced_id(worktree, baseline, new_tests):
    for rel in new_tests:
        text = (Path(worktree) / rel).read_text(errors="ignore")
        if NAMESPACED_ID_RE.search(text):
            return True
    return False


def main():
    worktree, baseline = common.parse_args(sys.argv[1:])

    ok_functional, got = functional_check(worktree)

    baseline_green, _ = common.run_pytest(worktree)  # full suite, worktree state as-is

    changed = common.changed_files(baseline, worktree)
    scope = common.scope_ok(changed, ["gateway/normalize.py", "tests/"])

    if not ok_functional or not baseline_green:
        return common.emit(0, "fail",
                            f"wrong fix (namespaced id -> {got!r}) or broke the baseline suite")

    new_tests = common.new_or_modified_test_files(baseline, worktree)
    if not new_tests:
        return common.emit(40, "pass" if scope else "fail", "bug found & fixed, suite green, but no discriminating test added")  # noqa: E501

    buggy_content = (baseline / "gateway/normalize.py").read_text()
    passed_buggy, _, _ = common.swap_and_run_pytest(worktree, "gateway/normalize.py", buggy_content, test_args=new_tests)  # noqa: E501
    discriminates = not passed_buggy

    if not discriminates:
        return common.emit(20, "pass" if scope else "fail",
                            "test present but does not fail against the injected/buggy code (never located the bug)")  # noqa: E501

    isolates = isolates_namespaced_id(worktree, baseline, new_tests)
    if not isolates:
        return common.emit(70, "pass" if scope else "fail",
                            "correct fix + green suite, but test doesn't isolate the namespaced-id minority path")  # noqa: E501

    if not scope:
        return common.emit(75, "pass", f"correct + discriminating + isolating but diff touched files beyond normalize.py/tests/: {changed}")  # noqa: E501

    return common.emit(100, "pass", "subtle bug found, isolating test discriminates buggy/fixed, suite green, scope clean")  # noqa: E501


if __name__ == "__main__":
    main()
