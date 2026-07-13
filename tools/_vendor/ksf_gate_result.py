"""Vendored — verbatim copy of KSF's ``ksf/gate_result.py``.

Source: keystone/ksf/gate_result.py (KSF, Keystone Framework).
Vendored rather than pip-installed per fleet/state/WORK-FRAMEWORK-WIRING-PLAN.md
Part 2 (cross-repo local-path dependency would break for any fresh clone of
this product repo — Charon must not depend on a sibling checkout at build
time). See tools/_vendor/README.md for re-sync instructions.

DO NOT hand-edit the logic below — if KSF's gate_result.py changes, re-copy
it here verbatim and re-apply this header.
"""

from typing import NamedTuple


class GateResult(NamedTuple):
    passed: bool
    gaps: list[str]
    messages: list[str]
