#!/usr/bin/env python3
"""T7 large-context-locate grader — the ONE correct site among decoys.

Five call sites read config.timeout correctly (gateway/proxy,health,retry,streaming);
the legacy adapter (legacy/adapter.py) hardcodes LEGACY_TIMEOUT. PASS iff the edit
lands on the ONE correct site: send_legacy() honors config.timeout DYNAMICALLY
(observed by mutating the config singleton and re-reading), the decoys are left
untouched, and settings.py is unchanged. Editing a decoy / hardcoding to the
current value -> FAIL.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pf_common as pf

DECOYS = ["gateway/proxy.py", "gateway/health.py", "gateway/retry.py",
          "gateway/streaming.py", "gateway/settings.py"]

# Dynamic check: the legacy path must reflect a CHANGED config, not a constant
# that merely equals the default (20).
PROBE = r"""
from gateway.settings import get_config
from legacy.adapter import send_legacy

assert send_legacy({"id": 1})["timeout"] == get_config().timeout, "does not honor config default"
get_config().timeout = 99
assert send_legacy({"id": 2})["timeout"] == 99, "legacy path is hardcoded, not reading config dynamically"
get_config().timeout = 7
assert send_legacy({"id": 3})["timeout"] == 7, "legacy path is hardcoded, not reading config dynamically"
print("PROBE_OK")
"""  # noqa: E501


def _grade():
    wt = pf.parse_worktree(sys.argv[1:])
    base = pf.baseline_dir(__file__)

    changed = pf.changed_files(base, wt)
    if "legacy/adapter.py" not in changed:
        pf.emit_fail("legacy/adapter.py (the ONE correct site) was not modified — "
                     f"the fix landed on the wrong site or nowhere. changed={changed}")
    touched_decoys = [d for d in DECOYS if d in changed]
    if touched_decoys:
        pf.emit_fail(f"decoy call sites edited (already correct, out of scope): {touched_decoys}")

    ok, out, _ = pf.run_probe(wt, PROBE)
    if not ok:
        pf.emit_fail("legacy path does not honor config.timeout dynamically "
                     "(wrong site / hardcoded): " + out.strip().replace("\n", " ")[-300:])

    green, sout = pf.full_suite_green(wt)
    if not green:
        pf.emit_fail("T13 regression: full suite not green")

    pf.emit_pass("legacy/adapter.py now honors config.timeout dynamically; decoys "
                 "untouched; suite green")


if __name__ == "__main__":
    pf.run_grader(_grade)
