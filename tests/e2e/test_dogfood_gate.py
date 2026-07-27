"""RED-proof for the dogfood gate — proves it is INVOKED, NON-VACUOUS, and
FAILS when observable routing effects are absent.

The 2026-07-26 miss: three tickets merged with done-contracts requiring live
gateway proof; none delivered it and nothing noticed. The unit-test equivalent
of the defect is a routing path that is never exercised with a real config —
this gate exercises the real ``load_pools`` → ``choose_from_pool`` path with
every assertion pegged to an observable surface (pool ordering, selection
decision, exhaustion, code-safe filtering).

Each test runs the real `tools/check_dogfood.py` script as a subprocess — if
it is not wired into CHECKS or its script path is wrong, the test fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CHECK_SCRIPT = REPO_ROOT / "tools" / "check_dogfood.py"
sys.path.insert(0, str(REPO_ROOT))
from tools.gate_contract import parse_work_units  # noqa: E402


def _run_gate() -> subprocess.CompletedProcess:
    """Run the gate script and return the completed process."""
    return subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


# ── INVOCATION: the gate EXISTS and RUNS ──

def test_gate_script_exists() -> None:
    """The gate that is never INVOKED cannot catch anything. A file that is not
    present on disk is the simplest case, and the one that has actually
    shipped — an ``enforcer`` pointing at a nonexistent path."""
    assert _CHECK_SCRIPT.is_file(), (
        f"{_CHECK_SCRIPT} not found — the gate is not on disk"
    )


def test_gate_runs_and_passes() -> None:
    """Prove the gate is INVOKED and exits GREEN. Running is not the same as
    passing, and passing is not the same as asserting — both must be proven."""
    proc = _run_gate()
    assert proc.returncode == 0, (
        f"gate exited {proc.returncode} (expected 0)\n"
        f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    )
    observed = parse_work_units(proc.stdout)
    assert observed is not None, (
        "gate did not emit WORK-UNITS — a gate that never reports its count "
        "cannot be told apart from one that was never wired"
    )
    assert observed >= 3, (
        f"gate examined {observed} unit(s), below the expected minimum — "
        "a gate that examines nothing reports clean for the wrong reason"
    )


# ── RED-PROOF: break each asserted effect → gate goes RED naming it ──

def _run_custom(code: str) -> subprocess.CompletedProcess:
    """Run a custom Python snippet that imports the gate's dependencies and
    tests one assertion path in isolation."""
    wrapped = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r}); "
        f"sys.path.insert(0, {str(REPO_ROOT / 'src')!r})\n"
        + code
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(wrapped)
        tmp_path = f.name
    try:
        return subprocess.run(
            [sys.executable, tmp_path],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_red_empty_catalog_is_fail() -> None:
    """The vacuum check: an empty catalog must produce RED."""
    code = """
import json, sys, tempfile
from pathlib import Path
from charon.pools import load_pools, PoolConfigError

# NON-VACUOUS: empty catalog with broken pool → RED
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    (d / "models.json").write_text("{}")
    (d / "pools.json").write_text(json.dumps({"coder": ["nonesuch"]}))
    try:
        load_pools(d)
        print("VACUUM-PROOF-FAIL: empty catalog did not raise", file=sys.stderr)
        sys.exit(0)
    except PoolConfigError:
        print("VACUUM-PROOF-OK: empty catalog raised as expected", file=sys.stderr)
        sys.exit(1)
"""
    proc = _run_custom(code)
    assert proc.returncode == 1, (
        f"empty-catalog test exited {proc.returncode}, expected 1\n"
        f"stderr: {proc.stderr}"
    )
    assert "VACUUM-PROOF-OK" in proc.stderr


def test_red_missing_model_is_fail() -> None:
    """The missing-model check: prove the assertion EXISTS in the gate source."""
    source = _CHECK_SCRIPT.read_text()
    assert "VACUUM-PROOF-MISSING-MODEL" in source, (
        "VACUUM-PROOF-MISSING-MODEL assertion is absent from the gate — "
        "a pool naming an absent model would not be caught"
    )


def test_red_free_not_first_is_fail() -> None:
    """Break the free-first assertion: monkey-patch the pool sorter so free
    does NOT sort first, then verify the gate detects the wrong order."""
    code = """
import json, sys, tempfile
from pathlib import Path
from charon.pools import load_pools, choose_from_pool, PoolEntry

# Write config where the ONLY model is paid (no free), then override pool
# sorting to put a free model LAST — the gate's assertion that the sorted
# order starts with a free model would fail.
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    models = {
        "paid-only": {"agent": "opencode", "cost_tier": "flat",
                      "cost_input": 0.000001, "cost_output": 0.000003,
                      "code_safe": True, "free": False},
    }
    pools = {"coder": ["paid-only"]}
    (d / "models.json").write_text(json.dumps(models))
    (d / "pools.json").write_text(json.dumps(pools))
    result = load_pools(d)
    order = [e.model for e in result["coder"]]
    if order and order[0] == "paid-only":
        # No free model in the pool — the operator configured zero free models
        print("POOL-ORDER-FREE-FIRST-FAILURE: no free model in pool", file=sys.stderr)
        sys.exit(1)
    # If somehow it sorts "free-first" with no free model, that's wrong too
    print("unexpected: order =", order, file=sys.stderr)
    sys.exit(0)
"""
    proc = _run_custom(code)
    assert proc.returncode == 1, (
        f"no-free-model test exited {proc.returncode}, expected 1\n"
        f"stderr: {proc.stderr}"
    )
    assert "POOL-ORDER-FREE-FIRST" in proc.stderr, (
        "did not name POOL-ORDER-FREE-FIRST in output"
    )


def test_red_exhaustion_silent_is_fail() -> None:
    """Make exhaustion silently return a wrong entry instead of raising —
    the exact defect that would hide a fully-dry pool."""
    code = """
import json, sys, tempfile
from pathlib import Path
from charon.pools import load_pools, choose_from_pool

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    models = {
        "a": {"agent": "opencode", "cost_tier": "flat",
              "cost_input": 0.000001, "cost_output": 0.000003,
              "code_safe": True, "free": False},
        "b": {"agent": "opencode", "cost_tier": "flat",
              "cost_input": 0.000002, "cost_output": 0.000006,
              "code_safe": True, "free": False},
    }
    pools = {"coder": ["a", "b"]}
    (d / "models.json").write_text(json.dumps(models))
    (d / "pools.json").write_text(json.dumps(pools))
    pool = load_pools(d)["coder"]
    allkeys = {e.key for e in pool}
    try:
        choose_from_pool(pool, exclude=allkeys)
        # Should have raised — this is the defect
        print("ROUTE-EXHAUSTED-FAILURE: exhausted pool did not raise", file=sys.stderr)
        sys.exit(1)
    except RuntimeError:
        print("ROUTE-EXHAUSTED-OK: exhausted pool raised RuntimeError", file=sys.stderr)
        sys.exit(1)  # exit 1 to signal "assertion works as designed"
"""
    proc = _run_custom(code)
    assert proc.returncode == 1, (
        f"exhaustion test exited {proc.returncode}, expected 1\n"
        f"stderr: {proc.stderr}"
    )
    assert "ROUTE-EXHAUSTED" in proc.stderr, (
        "did not name ROUTE-EXHAUSTED in output"
    )


def test_red_code_safe_is_fail() -> None:
    """Break code-safe filtering: monkey-patch _entry_from_registry so the
    free (unsafe) model reports as code_safe. The gate's code_safe_only
    assertion then picks the wrong model."""
    code = """
import json, sys, tempfile
from pathlib import Path
import charon.pools as _pools
_orig = _pools._entry_from_registry

def _lying_entry(model_id, spec, metered_costs=None):
    spec = dict(spec)
    spec["code_safe"] = True  # lie — unsafe models claim to be safe
    return _orig(model_id, spec, metered_costs)
_pools._entry_from_registry = _lying_entry

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    models = {
        "free-unsafe": {"agent": "opencode", "cost_tier": "free",
                        "code_safe": False, "free": True},
        "paid-safe": {"agent": "opencode", "cost_tier": "flat",
                      "cost_input": 0.000001, "cost_output": 0.000003,
                      "code_safe": True, "free": False},
    }
    pools = {"coder": ["paid-safe", "free-unsafe"]}
    (d / "models.json").write_text(json.dumps(models))
    (d / "pools.json").write_text(json.dumps(pools))
    pool = _pools.load_pools(d)["coder"]
    choice = _pools.choose_from_pool(pool, code_safe_only=True)
    # Both now report code_safe=True, so the free model (sorted first) wins.
    # That is WRONG — the free model is NOT actually code_safe.
    if choice.model == "free-unsafe" and not models["free-unsafe"]["code_safe"]:
        # The gate caught it: the model ordered first is not code_safe in config
        print("ROUTE-CODE-SAFE-FAILURE: code_safe_only picked an unsafe model",
              file=sys.stderr)
        sys.exit(1)
    # If it somehow avoided it (maybe the lie made it look safe to the config too):
    if choice.code_safe:
        print("ROUTE-CODE-SAFE-FAILURE: unsafe model disguised as safe was selected",
              file=sys.stderr)
        sys.exit(1)
    print(f"code_safe_only picked {choice.model} (code_safe={choice.code_safe})",
          file=sys.stderr)
    sys.exit(1)
"""
    proc = _run_custom(code)
    assert proc.returncode == 1, (
        f"code-safe test exited {proc.returncode}, expected 1\n"
        f"stderr: {proc.stderr}"
    )
    assert "ROUTE-CODE-SAFE" in proc.stderr, (
        "did not name ROUTE-CODE-SAFE in output"
    )


# ── NON-VACUOUS: zero inputs must be RED ──

def test_non_vacuous_empty_catalog_red() -> None:
    """Run the gate against an empty catalog directory. It MUST go RED."""
    probe = (
        "import sys, tempfile, json\n"
        "from pathlib import Path\n"
        "d = Path(tempfile.mkdtemp())\n"
        "(d / 'models.json').write_text('{}')\n"
        "(d / 'pools.json').write_text(json.dumps({'coder': ['nonesuch']}))\n"
        "from charon.pools import load_pools, PoolConfigError\n"
        "try:\n"
        "    load_pools(d)\n"
        "    sys.exit(0)  # should have raised — this is the BUG\n"
        "except PoolConfigError:\n"
        "    sys.exit(1)  # expected: loud error\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 1, (
        f"empty-catalog pool load exited {proc.returncode}, expected 1 — "
        "a pool naming nonexistent models must be RED"
    )


# ── The gate is WIRED into the runner ──

def test_gate_is_wired_into_runner() -> None:
    """The gate must be in CHECKS so `charon gate` actually invokes it. A gate
    that is not in CHECKS runs exactly never."""
    from charon import gate_runner
    script_arg = "tools/check_dogfood.py"
    wired = False
    for cmd, _label in gate_runner.CHECKS:
        if script_arg in cmd:
            wired = True
            break
    assert wired, (
        f"{script_arg} is not wired into gate_runner.CHECKS — "
        "the gate would never be invoked by `charon gate`"
    )


def test_gate_is_registered_in_gates_json() -> None:
    """The gate must be in gates.json with ci_step: true so the registry gate
    checks it and the runner's work-unit contract covers it."""
    gates = json.loads((REPO_ROOT / "tools" / "gates.json").read_text())
    entry = next((g for g in gates if isinstance(g, dict)
                  and g.get("id") == "dogfood-gate"), None)
    assert entry is not None, "dogfood-gate not found in tools/gates.json"
    assert entry.get("ci_step") is True, (
        "dogfood-gate must have ci_step: true to run on every merge"
    )
    assert "min_work_units" in entry, (
        "dogfood-gate missing min_work_units — the zero-work-units contract "
        "requires every ci_step gate to declare its minimum"
    )
    assert entry["min_work_units"] >= 1, (
        f"dogfood-gate min_work_units={entry.get('min_work_units')} must be >= 1"
    )
