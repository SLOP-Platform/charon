"""Unified CHARON-GATE runner — runs all validation checks in sequence."""

import json
import subprocess
import sys
from pathlib import Path

CHECKS: list[tuple[list[str], str]] = [
    (["ruff", "check", "src", "tests"], "ruff"),
    (["mypy", "src", "tests"], "mypy"),
    (["python3", "tools/check_boundary.py", "src"], "host-boundary"),
    (["python3", "tools/check_version.py"], "version"),
    (["python3", "tools/check_gate_registry.py"], "gate-registry"),
    (["python3", "tools/check_public_clean.py"], "public-clean"),
    (["python3", "tools/check_no_rig_import.py"], "no-rig-import"),
    (["python3", "tools/check_arch.py"], "check-arch"),
    (["python3", "tools/check_security.py"], "security-scan"),
    (["python3", "tools/check_test_patterns.py"], "test-patterns"),
    (["python3", "tools/check_workflows.py"], "workflow-policy"),
    (["python3", "tools/check_inert_code.py"], "inert-code"),
    (["python3", "tools/check_catalog_case_quant.py"], "catalog-case-quant"),
    (["python3", "-m", "pytest", "-q"], "pytest"),
    # docs/REVIEW-LOG.md is gitignored (generated artifact from the per-ticket
    # fragments in docs/review-log/). Running in generate mode is idempotent
    # (deterministic render of the SoT fragments) and is what .github/workflows/ci.yml
    # already does for the same reason. The --check form would always fail on a fresh
    # checkout because the rollup doesn't exist yet. Must run BEFORE check-decisions
    # because D002/D011 reference REVIEW-LOG and the linter will fail if it's missing.
    (["python3", "tools/render_review_log.py"], "render-review-log"),
    (["python3", "tools/check_decisions.py", "--check"], "check-decisions"),
]


def _ci_step_tools_from_checks() -> set[str]:
    """Build the set of tool scripts that CHECKS currently invokes."""
    tools: set[str] = set()
    for args, _label in CHECKS:
        for arg in args:
            if arg.startswith("tools/") and arg.endswith(".py"):
                tools.add(arg)
                break
    return tools


def _gates_json_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "tools" / "gates.json"


class GatesManifestError(Exception):
    """The gates.json manifest could not be read or understood.

    This is deliberately NOT swallowed. "Could not determine whether the gates
    are wired" must never be reported as "all gates passed" — a false receipt on
    the merge path is worse than no receipt at all.
    """


def _load_gates_json() -> list[dict]:
    """Load and validate tools/gates.json, or raise GatesManifestError.

    Fails CLOSED: a missing, unreadable, empty or unparseable manifest raises
    rather than yielding an empty gate list (which would vacuously "pass").
    """
    gates_path = _gates_json_path()
    try:
        raw = gates_path.read_text()
    except FileNotFoundError as e:
        raise GatesManifestError(f"{gates_path} not found (gate manifest is missing)") from e
    except OSError as e:
        raise GatesManifestError(f"{gates_path} is unreadable: {e}") from e

    if not raw.strip():
        raise GatesManifestError(f"{gates_path} is empty (zero bytes of manifest)")

    try:
        gates = json.loads(raw)
    except json.JSONDecodeError as e:
        raise GatesManifestError(f"{gates_path} is not valid JSON: {e}") from e

    if not isinstance(gates, list):
        raise GatesManifestError(
            f"{gates_path} must contain a JSON array, got {type(gates).__name__}"
        )
    if not gates:
        raise GatesManifestError(f"{gates_path} registers no gates (empty array)")
    return gates


def _verify_gate_registry_wired() -> int:
    """Every ci_step:true enforcer in gates.json must be wired into CHECKS."""
    try:
        gates = _load_gates_json()
    except GatesManifestError as e:
        print(
            f"  GATE-MANIFEST-UNREADABLE: {e}\n"
            "  Refusing to report a pass: the gate registry could not be verified.",
            file=sys.stderr,
        )
        return 1
    wired_tools = _ci_step_tools_from_checks()
    issues: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        if gate.get("id") == "charon-gate":
            continue
        if not gate.get("ci_step"):
            continue
        enforcer = gate.get("enforcer", "")
        parts = enforcer.split()
        if not parts:
            continue
        first = parts[0]
        if not first.startswith("tools/") and not first.startswith("python3"):
            continue
        if first.startswith("python3"):
            if len(parts) < 2 or not parts[1].startswith("tools/"):
                continue
            first = parts[1]
        if first not in wired_tools:
            issues.append(
                f"GATE-REGISTRY-MISMATCH: {gate['id']} enforcer "
                f"{enforcer!r} is ci_step:true but not wired into gate_runner.CHECKS"
            )
    for issue in issues:
        print(f"  {issue}", file=sys.stderr)
    return 1 if issues else 0


def run_gate() -> int:
    print("CHARON GATE — running all validation checks...")
    registry_ok = _verify_gate_registry_wired()
    if registry_ok != 0:
        return registry_ok
    for cmd, label in CHECKS:
        print(f"  [{label}] ", end="", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FAILED (exit {result.returncode})")
            if result.stderr:
                sys.stderr.write(result.stderr)
            if result.stdout:
                sys.stdout.write(result.stdout)
            return result.returncode
        print("OK")
    print("CHARON-GATE: all checks passed")
    return 0
