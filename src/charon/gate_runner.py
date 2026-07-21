"""Unified CHARON-GATE runner — runs all validation checks in sequence.

TWO CLASS-LEVEL CONTRACTS LIVE HERE, both of which exist because this runner has
twice reported "all checks passed" for work that did not happen:

1. SAME-TREE (see :func:`_verify_same_tree`). ``CHECKS`` shells
   ``python3 tools/check_*.py`` **CWD-relative**, so the check SCRIPTS come from
   the current checkout — while this module itself is resolved by Python's
   import machinery, which under an editable install points at whatever checkout
   was ``pip install -e``'d. The check LIST and the check SCRIPTS could therefore
   come from different commits, and a gate added on a branch was silently absent
   from the list a worktree run actually executed. ``_verify_gate_registry_wired``
   could not detect it: both of its inputs came from the same wrong tree, so it
   was self-consistently blind. Prefer ``python3 tools/run_gate.py``, which
   cannot resolve to a different checkout at all.

2. ZERO-WORK-UNITS (see ``tools/gate_contract.py``). A gate that examines nothing
   and exits 0 is indistinguishable from a gate that examined everything and
   found it clean. Gates declare ``min_work_units`` in ``tools/gates.json``, emit
   an actual count, and this runner fails CLOSED when the count is missing or
   short — even on exit 0.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# tools/ is not a package; gate_contract is imported by path below so this module
# stays importable regardless of CWD.
_WORK_UNITS_RE = re.compile(r"^\s*WORK-UNITS:\s*(-?\d+)\s*$", re.MULTILINE)
_PYTEST_COLLECTED_RE = re.compile(r"(\d+) (?:passed|failed|error)")

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
    """Resolve gates.json from the CURRENT WORKING DIRECTORY, not ``__file__``.

    ``CHECKS`` shells its tool scripts CWD-relative, so anchoring the manifest on
    ``__file__`` — the installed module — made the check list and the check
    scripts come from two different commits whenever the runner was invoked from
    a worktree. Resolving both from CWD makes them structurally consistent;
    :func:`_verify_same_tree` then reports the skew instead of hiding it.
    """
    return Path.cwd().resolve() / "tools" / "gates.json"


def _module_repo_root() -> Path:
    """The checkout this module was imported from (``<root>/src/charon/…``)."""
    return Path(__file__).resolve().parent.parent.parent


def _verify_same_tree() -> int:
    """Refuse to run when the imported ``charon`` is from a different checkout.

    Under an editable install, ``import charon`` resolves to whichever tree was
    installed — typically the main checkout on the default branch. Run from a
    worktree, this runner would then execute the MAIN checkout's ``CHECKS`` list
    against the WORKTREE's files: a gate added on the branch never ran, and the
    run still printed "all checks passed". That is a false receipt on the merge
    path, and it is worse than no receipt, so this fails loudly rather than
    guessing which half is authoritative.
    """
    module_root = _module_repo_root()
    cwd = Path.cwd().resolve()
    if module_root == cwd:
        return 0
    print(
        f"  GATE-SPLIT-BRAIN: the check LIST comes from {module_root}\n"
        f"  but the check SCRIPTS would run against {cwd}.\n"
        "  These are different checkouts, so a gate present in one and absent\n"
        "  from the other would silently not run. Refusing to report a pass.\n"
        "  Run 'python3 tools/run_gate.py' from the repo root instead — it is\n"
        "  repo-local and cannot resolve to a different checkout.",
        file=sys.stderr,
    )
    return 1


def _work_unit_minimums(gates: list[dict]) -> dict[str, tuple[int, str]]:
    """Map each gate's invocation key to its declared ``(minimum, gate id)``.

    The key is the ``tools/*.py`` script the gate shells, because that is the one
    string both ``gates.json`` and :data:`CHECKS` agree on — gate ids and CHECKS
    labels do not match each other.
    """
    mins: dict[str, tuple[int, str]] = {}
    for gate in gates:
        if not isinstance(gate, dict) or "min_work_units" not in gate:
            continue
        minimum = gate["min_work_units"]
        if not isinstance(minimum, int):
            continue
        gid = str(gate.get("id", "?"))
        script = next(
            (p for p in str(gate.get("enforcer", "")).split() if p.startswith("tools/")),
            None,
        )
        mins[script if script else gid] = (minimum, gid)
    return mins


def _check_key(cmd: list[str]) -> str | None:
    """The key under which this CHECKS entry declares its work-unit minimum."""
    for arg in cmd:
        if arg.startswith("tools/") and arg.endswith(".py"):
            return arg
    return "pytest" if "pytest" in cmd else None


def _observed_work_units(key: str, stdout: str) -> int | None:
    """Units the gate reports having examined, or None if it did not report.

    None and 0 are deliberately distinct: 0 means "ran, found nothing to do",
    None means "did not tell us", and only the second can also mean "was never
    really wired". Both fail, but they get different diagnostics.
    """
    if key == "pytest":
        matches = _PYTEST_COLLECTED_RE.findall(stdout)
        return sum(int(m) for m in matches) if matches else None
    found = _WORK_UNITS_RE.findall(stdout)
    return int(found[-1]) if found else None


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
    same_tree = _verify_same_tree()
    if same_tree != 0:
        return same_tree
    registry_ok = _verify_gate_registry_wired()
    if registry_ok != 0:
        return registry_ok
    try:
        mins = _work_unit_minimums(_load_gates_json())
    except GatesManifestError as e:
        print(f"  GATE-MANIFEST-UNREADABLE: {e}", file=sys.stderr)
        return 1

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

        # Zero-work-units contract: exit 0 is necessary but NOT sufficient.
        key = _check_key(cmd)
        declared = mins.get(key) if key is not None else None
        if key is not None and declared is not None:
            minimum, gid = declared
            observed = _observed_work_units(key, result.stdout)
            if observed is None:
                print("FAILED (no work-unit report)")
                print(
                    f"  ZERO-WORK-UNITS: gate {gid!r} exited 0 but never emitted\n"
                    "  'WORK-UNITS: <n>'. An unreported count cannot be told apart\n"
                    "  from a gate that was mis-invoked and examined nothing.\n"
                    "  See tools/gate_contract.py.",
                    file=sys.stderr,
                )
                return 1
            if observed < minimum:
                print(f"FAILED (examined {observed}, expected >= {minimum})")
                print(
                    f"  ZERO-WORK-UNITS: gate {gid!r} exited 0 having examined\n"
                    f"  {observed} unit(s), below its declared minimum of {minimum}.\n"
                    "  A gate that examines (almost) nothing reports clean for the\n"
                    "  wrong reason. Check its invocation before lowering the\n"
                    "  minimum in tools/gates.json.",
                    file=sys.stderr,
                )
                return 1
        print("OK")
    print("CHARON-GATE: all checks passed")
    return 0
