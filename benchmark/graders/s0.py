#!/usr/bin/env python3
"""S0 grader — Trivial fix (Tier 0, work_class=bugfix).
Usage: python3 s0.py --worktree <dir> --baseline fixtures/sections/s0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def main():
    worktree, baseline = common.parse_args(sys.argv[1:])

    passed, out = common.run_pytest(worktree)
    if not passed:
        return common.emit(0, "fail", "pytest red: fix did not make the suite pass")

    changed = common.changed_files(baseline, worktree)
    only_providers = changed == ["gateway/providers.py"]

    if not only_providers:
        return common.emit(60, "pass", f"tests pass but touched files beyond providers.py: {changed}")  # noqa: E501

    baseline_content = (baseline / "gateway/providers.py").read_text()
    worktree_content = (worktree / "gateway/providers.py").read_text()
    normalized_expected = baseline_content.replace("chearp", "cheap")

    if worktree_content.strip() == normalized_expected.strip():
        return common.emit(100, "pass", "clean minimal fix: only chearp->cheap changed")
    else:
        return common.emit(60, "pass", "tests pass, diff scoped to providers.py, but other tokens changed too")  # noqa: E501


if __name__ == "__main__":
    main()
