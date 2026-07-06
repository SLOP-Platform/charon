#!/usr/bin/env python3
"""Grader self-tests - the most important deliverable of the benchmark harness.

Proves each grader gives ~100 on a golden-correct solution and low/0 on an
inert/buggy/dodge one. A grader that can't discriminate is a bug, not an
acceptable state. Exits non-zero if any assertion fails.

Usage: python3 selftest/run_selftests.py
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GOLD = BASE / "selftest" / "goldens"
FIXTURES = BASE / "fixtures" / "sections"
FIXTURES_FE = BASE / "fixtures-fe"
GRADERS = BASE / "graders"

# (section, grader_cmd_builder, baseline_dir, [(variant, expect_check_fn, label), ...])
CASES = []


def py_grader(name):
    return [sys.executable, str(GRADERS / f"{name}.py")]


def node_grader(name):
    return ["node", str(GRADERS / f"{name}.js")]


def eq(target):
    return lambda score: score == target, f"== {target}"


def at_least(target):
    return lambda score: score >= target, f">= {target}"


def below(target):
    return lambda score: score < target, f"< {target}"


CASES = [
    ("S0", py_grader("s0"), FIXTURES / "s0", [
        ("golden", eq(100), "clean minimal fix"),
        ("inert", eq(0), "unfixed typo, tests red"),
    ]),
    ("S1", py_grader("s1"), FIXTURES / "s1", [
        ("golden", eq(100), "fix + discriminating test on unsorted input"),
        ("inert", eq(0), "still returns wrong provider"),
    ]),
    ("S2", py_grader("s2"), FIXTURES / "s2", [
        ("golden", eq(100), "ascending order + real-path-proven test"),
        ("inert", eq(0), "order bug not fixed"),
        ("dodge-mocked", eq(25), "test monkeypatches the config loader (#6 signature, mocked path)"),
        ("inert-feature", eq(50), "fix works but test dodges the real-path proof (#6 signature)"),
    ]),
    ("S3", py_grader("s3"), FIXTURES / "s3", [
        ("golden", eq(100), "all 3 defects fixed, checks preserved"),
        ("inert", eq(0), "still red, no defects fixed"),
    ]),
    ("S4", py_grader("s4"), FIXTURES / "s4", [
        ("golden", eq(100), "subtle bug found, isolating test, suite green"),
        ("inert", eq(0), "bug not fixed"),
    ]),
    ("S5", py_grader("s5"), FIXTURES / "s5", [
        ("golden", eq(100), "honest scoping: ambiguities + hedge + defer"),
        ("inert", eq(0), "confident overbuild, invented config, no hedge"),
    ]),
    ("S6", node_grader("s6"), FIXTURES_FE, [
        ("golden-svelte", eq(100), "Svelte solution: real fetch wiring"),
        ("golden-vanilla", eq(100), "vanilla-JS solution: grader is framework-agnostic"),
        ("inert-hardcoded", below(90), "hardcoded/static: fails real-data-proof anti-dodge gate"),
    ]),
]


def run_grader(cmd, worktree, baseline):
    full = cmd + ["--worktree", str(worktree), "--baseline", str(baseline)]
    proc = subprocess.run(full, capture_output=True, text=True, timeout=180)
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return json.loads(line)
    except Exception:
        return {"score": None, "reason": f"grader produced no parseable JSON. stdout={proc.stdout!r} stderr={proc.stderr!r}"}


def main():
    failures = []
    print(f"{'section':6} {'variant':18} {'expect':8} {'got':5} {'result':6}  reason")
    for section, cmd, baseline, variants in CASES:
        for variant, check_fn, label in variants:
            worktree = GOLD / section.lower() / variant
            if not worktree.exists():
                failures.append(f"{section}/{variant}: worktree missing at {worktree}")
                continue
            result = run_grader(cmd, worktree, baseline)
            score = result.get("score")
            fn, expect_label = check_fn
            ok = fn(score) if score is not None else False
            status = "PASS" if ok else "FAIL"
            if not ok:
                failures.append(f"{section}/{variant}: expected score {expect_label}, got {score} ({label}) - {result.get('reason')}")
            print(f"{section:6} {variant:18} {expect_label:8} {str(score):5} {status:6}  {label}")

    print()
    if failures:
        print(f"SELF-TEST FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("ALL GRADER SELF-TESTS PASS: every grader discriminates golden-correct from inert/buggy as expected.")


if __name__ == "__main__":
    main()
