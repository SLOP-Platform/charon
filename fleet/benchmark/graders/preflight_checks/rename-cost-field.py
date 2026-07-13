#!/usr/bin/env python3
"""T8 behavior-preserving-refactor grader — rename across >=3 files, golden intact.

Rename Provider.cost_rank -> price_rank everywhere. PASS iff: the golden
characterization test (tests/test_characterization.py) is byte-identical to
baseline; the FULL suite is green; EVERY call site is updated (no 'cost_rank'
attribute usage remains in gateway/*.py and 'price_rank' appears in >=3 gateway
files); and the public behavior is preserved (probe). Missing one site ->
AttributeError -> suite red -> FAIL.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pf_common as pf

GATEWAY_FILES = ["gateway/providers.py", "gateway/routing.py", "gateway/meter.py"]

PROBE = r"""
from gateway.providers import Provider, cheapest
from gateway.routing import order_by_cost
from gateway.meter import rank_summary

# construct via the NEW field name — proves the rename actually happened
p = Provider(name="x", price_rank=5)
assert p.price_rank == 5
assert not hasattr(p, "cost_rank"), "old field cost_rank still present on Provider"

fx = [Provider("b", 2), Provider("a", 1), Provider("c", 3)]
assert cheapest(fx).name == "a"
assert [q.name for q in order_by_cost(fx)] == ["a", "b", "c"]
assert rank_summary(fx) == {"a": 1, "b": 2, "c": 3}
print("PROBE_OK")
"""

_COST_RANK = re.compile(r"\bcost_rank\b")


def _grade():
    wt = pf.parse_worktree(sys.argv[1:])
    base = pf.baseline_dir(__file__)

    # golden characterization test must be unchanged
    if not pf.file_unchanged(base, wt, "tests/test_characterization.py"):
        pf.emit_fail("tests/test_characterization.py was modified — the golden "
                     "characterization test must pass UNCHANGED across a pure rename")

    # every call site updated: no cost_rank remains, price_rank in >=3 files
    price_files = 0
    for rel in GATEWAY_FILES:
        p = wt / rel
        if not p.exists():
            pf.emit_fail(f"{rel} missing")
        text = p.read_text(errors="ignore")
        if _COST_RANK.search(text):
            pf.emit_fail(f"old field name 'cost_rank' still present in {rel} — "
                         "a call site was missed (partial rename)")
        if "price_rank" in text:
            price_files += 1
    if price_files < 3:
        pf.emit_fail(f"rename spans only {price_files} file(s); expected price_rank in "
                     ">=3 files (providers/routing/meter)")

    ok, out, _ = pf.run_probe(wt, PROBE)
    if not ok:
        pf.emit_fail("behavior/rename probe failed (missed site -> AttributeError): "
                     + out.strip().replace("\n", " ")[-300:])

    green, sout = pf.full_suite_green(wt)
    if not green:
        pf.emit_fail("T13/T8 regression: full suite not green (a call site was missed): "
                     + (sout.strip().splitlines()[-1] if sout.strip() else ""))

    pf.emit_pass("cost_rank->price_rank across >=3 files; golden test unchanged; every "
                 "call site updated; suite green; behavior preserved")


if __name__ == "__main__":
    pf.run_grader(_grade)
