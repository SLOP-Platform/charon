#!/usr/bin/env python3
"""The zero-work-units gate contract.

WHY THIS EXISTS — a gate that examines nothing and exits 0 is indistinguishable,
on the merge path, from a gate that examined the whole tree and found it clean.
This tree has shipped that failure twice in different shapes: a Semgrep gate
whose invocation made every ``paths.include`` glob miss, so it scanned **0
files** and printed "OK", and a rule file that parsed but matched nothing, which
also printed "OK". Both produced green receipts that later sessions cited as
evidence. The receipts were for work that did not happen.

The contract, applied to every scanning gate rather than to the one that failed:

1. A gate MUST emit ``WORK-UNITS: <n>`` on stdout — the count of things it
   actually examined (files parsed, symbols walked, rows linted, tests
   collected). Emit it on the pass path AND the fail path.
2. ``tools/gates.json`` declares ``min_work_units`` for that gate.
3. The runner (``src/charon/gate_runner.py``) fails CLOSED when the line is
   absent, unparseable, or below the declared minimum — even if the gate exited
   0. "I could not tell whether this gate did anything" is a failure, never a
   pass.

Assert on the COUNT, never on the gate's source text. Round 6's test asserted
the literal ``SCAN_TARGETS = ["src", "tools", "tests"]`` was present in the
source, which pinned the very bug that made the scan empty: fixing the gate
broke its test.

Stdlib only, no imports beyond the standard library, so any tools/ script can
``import gate_contract`` — tools/ is sys.path[0] when a script there is run as
``python3 tools/check_x.py``, which is how gate_runner.CHECKS invokes them.
"""
from __future__ import annotations

import sys

WORK_UNITS_PREFIX = "WORK-UNITS:"


def emit_work_units(count: int) -> None:
    """Report how many units of work this gate actually examined.

    Call this unconditionally, before returning — a gate that emits the count
    only when it passes cannot be distinguished from one that crashed early.
    """
    print(f"{WORK_UNITS_PREFIX} {int(count)}", file=sys.stdout, flush=True)


def parse_work_units(stdout: str) -> int | None:
    """Extract the work-unit count from a gate's stdout, or None if absent.

    None means "the gate did not report", which the runner treats as a failure
    rather than as zero — the two are different diagnoses and conflating them is
    how a gate that was never wired looks like a gate that found nothing to do.
    The LAST occurrence wins, so a gate may refine its count as it goes.
    """
    found: int | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith(WORK_UNITS_PREFIX):
            continue
        try:
            found = int(stripped[len(WORK_UNITS_PREFIX):].strip())
        except ValueError:
            continue
    return found
