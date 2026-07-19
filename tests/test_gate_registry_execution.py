"""Fail-on-revert: every gate registered in ``tools/gates.json`` with
``ci_step: true`` must actually EXECUTE — either via ``gate_runner.CHECKS``
(what ``python3 -m charon.cli gate`` runs) or as an explicit step in
``.github/workflows/ci.yml`` (for the handful of gates that run as their own
CI step rather than through the unified gate runner: the full pytest suite,
the review-log renderer, the decision-register linter, and the unified gate
command itself).

This closes the exact bug class an internal reachability audit found:
five gates (``check_no_rig_import.py``, ``check_arch.py``,
``check_security.py``, ``check_test_patterns.py``, ``check_workflows.py``)
were registered in ``gates.json`` but silently never executed by CI. Four
were wired into ``gate_runner.CHECKS`` in a prior fix; ``check_workflows.py``
(the ``workflow-policy`` gate) was the last of the five and is wired here.

Reverting ``check_workflows.py`` (or any future gate) out of
``gate_runner.CHECKS``/``ci.yml`` while leaving it registered in
``gates.json`` with ``ci_step: true`` must fail this test — a registered gate
can never again silently not-run.
"""
from __future__ import annotations

import json
from pathlib import Path

from charon import gate_runner

REPO_ROOT = Path(__file__).resolve().parent.parent
GATES_JSON = REPO_ROOT / "tools" / "gates.json"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _needle(enforcer: str) -> str:
    """The distinctive substring that proves *enforcer* actually runs.

    Most enforcers are a bare ``tools/x.py`` path — an unambiguous, unique
    substring. The handful of compound shell commands (``ruff check``,
    ``mypy ...``, ``python3 -m pytest``, ``python3 -m charon.cli gate``) are
    mapped to a distinctive keyword instead of their generic first token
    (``python3`` would spuriously "match" almost anything and defeat the
    point of this check).
    """
    if enforcer.startswith("tools/"):
        return enforcer.split()[0]
    if enforcer.startswith("ruff"):
        return "ruff check"
    if enforcer.startswith("mypy"):
        return "mypy"
    if "charon.cli gate" in enforcer:
        return "charon.cli gate"
    if "pytest" in enforcer:
        return "pytest"
    return enforcer.split()[0]


def _executed_haystack() -> str:
    """Everything gate_runner.CHECKS runs, plus the raw ci.yml text (for
    gates that execute as their own CI step instead of through gate_runner)."""
    parts = [" ".join(cmd) for cmd, _label in gate_runner.CHECKS]
    parts.append(CI_YML.read_text(encoding="utf-8"))
    return "\n".join(parts)


def find_unexecuted_gates(gates: list[dict], haystack: str) -> list[str]:
    """Return ids of gates that are ``ci_step: true`` but whose enforcer
    needle is not found anywhere in *haystack* — i.e. registered but never
    actually executed."""
    unexecuted: list[str] = []
    for gate in gates:
        if not gate.get("ci_step"):
            continue  # not required to run in CI (e.g. validate-board, rig-side)
        enforcer = gate["enforcer"]
        if enforcer.startswith("../"):
            continue  # external (rig-side) path — out of product-repo scope
        if _needle(enforcer) not in haystack:
            unexecuted.append(gate["id"])
    return unexecuted


def test_every_ci_step_gate_actually_executes() -> None:
    gates = json.loads(GATES_JSON.read_text(encoding="utf-8"))
    unexecuted = find_unexecuted_gates(gates, _executed_haystack())
    assert not unexecuted, (
        "gate(s) registered with ci_step=true in tools/gates.json but never "
        f"actually executed by gate_runner.CHECKS or ci.yml: {unexecuted} — "
        "see the internal reachability audit [[gates-must-actually-run]]"
    )


def test_detector_flags_a_registered_but_unwired_gate() -> None:
    """Proves the detector logic itself (not just today's repo state): a
    gate present in the registry but absent from the executed haystack is
    caught."""
    gates = [
        {"id": "wired-gate", "ci_step": True, "enforcer": "tools/check_arch.py"},
        {"id": "orphan-gate", "ci_step": True, "enforcer": "tools/check_orphan.py"},
        {"id": "not-required", "ci_step": False, "enforcer": "tools/check_never_run.py"},
    ]
    haystack = "python3 tools/check_arch.py\n"
    unexecuted = find_unexecuted_gates(gates, haystack)
    assert unexecuted == ["orphan-gate"]
