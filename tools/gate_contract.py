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

import os
import sys
from collections.abc import Mapping

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


# ---------------------------------------------------------------------------
# The gate-reentrancy contract
# ---------------------------------------------------------------------------
#
# THE CLASS: a gate runs the test suite AND the test suite runs every gate =>
# unbounded recursion. Both halves are already true here:
#
#   * ``tests/test_gate_contract.py`` parametrises over EVERY gate in
#     ``tools/gates.json`` whose enforcer starts with ``tools/`` and runs each
#     one as a subprocess (that is how the work-unit contract is red-proofed).
#   * ``src/charon/gate_runner.py`` :func:`run_gate` shells every declared gate,
#     and ``python3 -m pytest`` is itself one of the entries in ``CHECKS``.
#
# So the day any gate invokes pytest (a coverage gate, a diff-coverage gate, a
# mutation gate — all natural things to want), the cycle closes:
# ``pytest -> test_gate_contract -> <gate> -> pytest -> ...`` from either entry
# point. This is PREVENTIVE: no gate on the default branch spawns pytest today.
# The sibling build rig learned this class the expensive way — a
# gate -> test -> handoff -> gate cycle there reached ~18,900 processes and
# fork-starved the machine before it was killed. The lever below is the same one
# that repo settled on (``CHARON_GATE_ACTIVE``), ported deliberately rather than
# reinvented, so the two repos share one name for one idea.
#
# WHAT THE MARKER MEANS: "a gate/test-suite run is already in flight in an
# ancestor process of mine". It is set by the two places a run originates —
# :func:`charon.gate_runner.run_gate` (on the env of its pytest step) and the
# gate-spawning helper in ``tests/test_gate_contract.py`` — and inherited by
# every descendant.
#
# WHAT IT IS EXPLICITLY NOT: a "disable the gates" switch. Nothing skips a gate
# because this marker is set. It suppresses exactly ONE action — a gate spawning
# a SECOND, nested test suite — because the outer run is already running that
# suite for real. Everything else about the gate still executes and still
# reports.
#
# WHY A STRAY ``CHARON_GATE_ACTIVE=1`` IN CI CANNOT MANUFACTURE A GREEN: because
# suppression is not a pass. A gate that suppresses its nested suite emits no
# work-unit count, and ``gate_runner`` — which never sets the marker on the env
# of a gate script — then fails CLOSED on it with ZERO-WORK-UNITS. Only the
# suite that SET the marker (``tests/test_gate_contract.py``) accepts a
# suppressed response, because it is the one that knows the suppression was its
# own doing. A stray export therefore turns a suite-running gate RED under
# ``charon gate``, which is loud and fixable; it can never turn it silently
# green. And suppression is always announced on stdout with the greppable
# prefix below — never a silent no-op.
#
# FOR GATE AUTHORS: if your gate wants to run the test suite (pytest, coverage,
# mutmut, ...), guard that spawn with :func:`gate_run_is_nested` and announce it
# with :func:`suppress_nested_suite`. Do not spawn a suite unconditionally.

GATE_ACTIVE_ENV = "CHARON_GATE_ACTIVE"
SUPPRESSED_PREFIX = "GATE-REENTRANCY-SUPPRESSED:"


def gate_run_is_nested(env: Mapping[str, str] | None = None) -> bool:
    """True when a gate/test-suite run is already in flight in an ancestor.

    A gate that would otherwise spawn the test suite MUST consult this first.
    Whitespace-only values read as unset so an ``export CHARON_GATE_ACTIVE=``
    does not half-arm the guard.
    """
    source = os.environ if env is None else env
    return bool(source.get(GATE_ACTIVE_ENV, "").strip())


def child_env_marked_active(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of ``env`` marked so the spawned process knows it is nested.

    Returned as a fresh dict rather than mutating the caller's environment: the
    marker travels down the spawn chain only, so a run that never spawns a gate
    is never affected by one that does.
    """
    source = os.environ if env is None else env
    return {**source, GATE_ACTIVE_ENV: "1"}


def suppress_nested_suite(gate_id: str) -> None:
    """Announce, LOUDLY, that a nested test-suite spawn was suppressed.

    Suppression must never look like "nothing happened". This prints a
    greppable line naming the guard and the gate so a reader of the gate output
    can tell a suppressed nested run from a run that quietly did no work.
    """
    print(
        f"{SUPPRESSED_PREFIX} {gate_id} did not spawn a nested test suite — "
        f"already inside a gate/test run (reentrancy guard, see "
        f"tools/gate_contract.py {GATE_ACTIVE_ENV}). The OUTER run performs "
        f"this check; only the redundant nested re-invocation is suppressed.",
        file=sys.stdout,
        flush=True,
    )


def nested_suite_suppressed(stdout: str) -> bool:
    """True if a gate reported suppressing its nested test-suite spawn.

    Only a runner that itself set the marker may treat this as an acceptable
    response — see the contract note above.
    """
    return any(
        line.strip().startswith(SUPPRESSED_PREFIX) for line in stdout.splitlines()
    )
