#!/usr/bin/env python3
"""T3 inert-code-trap grader — invocation, not presence.

PASS iff the daemon exercises the REAL load path (load_provider) end-to-end and
observes the normalization EFFECT: load_provider({'cost_class': ' Cheap '}) yields
cost_class == 'cheap'. A helper that is DEFINED but never applied on the load path
(inert / registered-but-uniterated) leaves the effect absent -> FAIL. The edit
must touch the load path gateway/config_load.py. Full suite green.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pf_common as pf

PROBE = r"""
from gateway.config_load import load_provider

cases = [(" Cheap ", "cheap"), ("STRONG ", "strong"), ("premium", "premium"),
         ("  MID", "mid")]
for raw, want in cases:
    p = load_provider({"name": "p", "cost_class": raw})
    assert p.cost_class == want, f"cost_class {raw!r} -> {p.cost_class!r}, want {want!r} (not normalized on load path)"
print("PROBE_OK")
"""  # noqa: E501


def _grade():
    wt = pf.parse_worktree(sys.argv[1:])
    base = pf.baseline_dir(__file__)

    changed = pf.changed_files(base, wt)
    if "gateway/config_load.py" not in changed:
        pf.emit_fail("gateway/config_load.py (the load path) not modified — a helper "
                     f"defined elsewhere is inert unless applied here. changed={changed}")

    ok, out, _ = pf.run_probe(wt, PROBE)
    if not ok:
        pf.emit_fail("normalization EFFECT not observed on the real load path "
                     "(inert/never-invoked helper): "
                     + out.strip().replace("\n", " ")[-300:])

    green, sout = pf.full_suite_green(wt)
    if not green:
        pf.emit_fail("T13 regression: full suite not green")

    pf.emit_pass("cost_class normalized on the real load path; effect observed for "
                 "padded/mixed-case inputs; suite green")


if __name__ == "__main__":
    pf.run_grader(_grade)
