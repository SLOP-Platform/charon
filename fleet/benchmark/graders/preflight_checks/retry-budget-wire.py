#!/usr/bin/env python3
"""T1 cross-module-wire grader — EXECUTION-reachability, not grep.

PASS iff the daemon drives the REAL entrypoint (dispatch) end-to-end and OBSERVES
the RetryBudget's effect: on an always-retryable upstream, dispatch TERMINATES
(a budget-ignoring loop hangs) and the number of attempts SCALES with the budget
(a hardcoded/constant stub does not). The diff must touch gateway/proxy.py — a
parallel/adjacent helper that leaves the real path unwired FAILs. Full suite green.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pf_common as pf

# Always-429 upstream => retryable forever unless the budget stops it. We record
# attempts for two DIFFERENT budgets; a correct per-retry accounting makes the
# attempt-count delta equal the budget delta (3). A constant stub -> delta 0.
PROBE = r"""
import sys
from gateway.proxy import Upstream, dispatch
from gateway.budget import RetryBudget

def attempts_for(n):
    up = Upstream([429])          # always retryable
    dispatch({"upstream": up, "id": "x"}, budget=RetryBudget(max_retries=n))
    return up.attempts

a2 = attempts_for(2)
a5 = attempts_for(5)

# success passthrough must still work with no budget
ok_up = Upstream([200])
r = dispatch({"upstream": ok_up, "id": "ok"}, budget=None)
assert r["status"] == 200 and ok_up.attempts == 1, "success passthrough broke"

assert a2 > 0 and a5 > 0, "dispatch made no attempts"
assert a5 > a2, f"attempts did not scale with budget (a2={a2} a5={a5}); budget ignored/constant"
assert (a5 - a2) == 3, f"attempt delta {a5-a2} != budget delta 3; budget not consulted per-retry"
print("PROBE_OK", a2, a5)
"""


def _grade():
    wt = pf.parse_worktree(sys.argv[1:])
    base = pf.baseline_dir(__file__)

    changed = pf.changed_files(base, wt)
    if "gateway/proxy.py" not in changed:
        pf.emit_fail(
            "gateway/proxy.py (the real dispatch path) was not modified — a "
            f"parallel/adjacent helper does not wire the budget in. changed={changed}")

    # EXECUTION-reachability: run dispatch with a hard timeout. A budget-ignoring
    # loop on an always-429 upstream never terminates -> timeout -> FAIL.
    ok, out, timed_out = pf.run_probe(wt, PROBE, timeout=8)
    if timed_out:
        pf.emit_fail("dispatch did not terminate on an always-retryable upstream "
                     "— RetryBudget is not consulted (dead/unreachable wire)")
    if not ok:
        pf.emit_fail("execution probe failed — budget effect not observed: "
                     + out.strip().replace("\n", " ")[-300:])

    green, sout = pf.full_suite_green(wt)
    if not green:
        pf.emit_fail("T13 regression: full suite not green after wire: "
                     + sout.strip().splitlines()[-1] if sout.strip() else "no output")

    pf.emit_pass("RetryBudget wired on the real dispatch path; effect observed "
                 "(attempts scale with budget, loop terminates); suite green")


if __name__ == "__main__":
    pf.run_grader(_grade)
