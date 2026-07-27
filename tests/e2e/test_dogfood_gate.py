"""RED-proof for the dogfood gate — proves it is INVOKED, NON-VACUOUS, and
FAILS when observable routing effects are absent.

The 2026-07-26 miss: three tickets merged with done-contracts requiring live
gateway proof; none delivered it and nothing noticed. The unit-test equivalent
of the defect is a routing path that is never exercised with a real config —
this gate exercises the real ``CatalogCache.registry_and_pool_map`` →
``load_pools`` → ``choose_from_pool`` path with every assertion pegged to an
observable surface (fp4 fold, capacity-tier fold, preview-alias fold, pool
ordering, selection decision, exhaustion, code-safe filtering).

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


# ── RED-PROOF #1: the 2026-07-26 acceptance test ──
# Revert the fp4 fold in proxy.py and verify the gate goes RED naming the
# fp4 case. This is the test the prior run failed to deliver.

def test_red_fp4_fold_revert_is_fail() -> None:
    """The fp4 fold MUST be observable: a real advertised id like
    ``MiniMaxAI/MiniMax-M2.5-FP4`` and its base ``MiniMaxAI/MiniMax-M2.5`` MUST
    collapse to the SAME routable pool id ``minimax-m2.5`` with BOTH members,
    and there MUST be no orphan ``minimax-m2.5-fp4`` pool. With the fold
    reverted, the base pool holds only one member and ``minimax-m2.5-fp4``
    forms its own orphan — the gate MUST go RED naming the fp4 case."""
    proxy_path = REPO_ROOT / "src" / "charon" / "proxy.py"
    original = proxy_path.read_text()
    try:
        # Revert the fp4 fold: drop ``fp4`` from the quant-suffix regex.
        reverted = original.replace("fp4|fp8|fp16", "fp8|fp16")
        assert reverted != original, (
            "could not revert fp4|fp8|fp16 → fp8|fp16 in proxy.py — the test "
            "cannot simulate the regression"
        )
        proxy_path.write_text(reverted)
        proc = _run_gate()
        assert proc.returncode != 0, (
            f"gate exited {proc.returncode} (expected NON-ZERO) with the "
            "fp4 fold reverted — the gate that cannot fail on the very "
            "regression it exists to catch is the theater this ticket "
            "exists to end.\nstderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
        combined = proc.stdout + proc.stderr
        assert "fp4" in combined.lower(), (
            "gate did not name the fp4 case in its RED output — a gate that "
            "fails generically on the fold regression hides which fold "
            "actually broke. Combined output:\n" + combined
        )
    finally:
        proxy_path.write_text(original)


# ── RED-PROOF #2: the tier fold (a second asserted effect) ──

def test_red_tier_fold_revert_is_fail() -> None:
    """The capacity-tier fold MUST be observable: every tier
    ``:low|:medium|:high|:max`` MUST resolve to the base id ``claude-opus-4``
    with all 4 tier members in that one pool. With the tier regex reverted,
    no ``claude-opus-4`` base pool exists at all."""
    proxy_path = REPO_ROOT / "src" / "charon" / "proxy.py"
    original = proxy_path.read_text()
    try:
        reverted = original.replace(
            ":(?:free|nitro|online|low|medium|high|max)", ":free")
        assert reverted != original, (
            "could not revert tier regex in proxy.py"
        )
        proxy_path.write_text(reverted)
        proc = _run_gate()
        assert proc.returncode != 0, (
            f"gate exited {proc.returncode} (expected NON-ZERO) with the tier "
            "fold reverted — the second asserted effect does not gate.\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
        combined = proc.stdout + proc.stderr
        assert ("claude-opus-4" in combined
                or "capacity-tier" in combined.lower()
                or "tier" in combined.lower()), (
            "gate did not name the tier family in its RED output. Combined:\n"
            + combined
        )
    finally:
        proxy_path.write_text(original)


# ── NON-VACUOUS: zero inputs must be RED ──

def test_non_vacuous_empty_catalog_red() -> None:
    """The vacuum check: an empty catalog must produce RED. With nothing
    discovered, the catalog cache has no fold-asserted pools — the fold
    assertions all fail, the gate exits non-zero."""
    probe = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'src')!r})\n"
        "import tools.check_dogfood as g\n"
        "# Monkey-patch _put so the cache stays empty — simulates zero providers\n"
        "g._put = lambda *a, **kw: None\n"
        "sys.exit(g.run())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode != 0, (
        f"empty-cache gate exited {proc.returncode}, expected NON-ZERO — "
        "a gate that silently passes on zero providers is the theater this "
        "ticket exists to end\nstderr: {proc.stderr}\nstdout: {proc.stdout}"
    )


def test_non_vacuous_missing_model_is_loud() -> None:
    """An empty models.json with a pools.json naming a nonexistent model
    MUST raise PoolConfigError — a gate that swallows misconfiguration is
    silent theater."""
    code = """
import json, sys, tempfile
from pathlib import Path
from charon.pools import load_pools, PoolConfigError

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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert proc.returncode == 1, (
            f"missing-model probe exited {proc.returncode}, expected 1\n"
            f"stderr: {proc.stderr}"
        )
        assert "VACUUM-PROOF-OK" in proc.stderr
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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


def test_gate_asserts_observable_pool_effects() -> None:
    """The gate must assert observable pool effects for the three production
    fold families (fp4, capacity tiers, preview alias) — its source must
    contain the assertion labels that name each regression. A gate whose
    assertions are absent cannot fire on the regression."""
    source = _CHECK_SCRIPT.read_text()
    for label in (
        "FOLD-FP4-BOTH-MEMBERS",
        "FOLD-FP4-NO-ORPHAN",
        "FOLD-CAPACITY-TIERS",
        "FOLD-PREVIEW-ALIAS",
    ):
        assert label in source, (
            f"{label} assertion is absent from the gate — a fold "
            "regression would not be named in RED output"
        )


def test_gate_uses_repo_local_src() -> None:
    """The gate must put the worktree's src/ at the FRONT of sys.path so
    `import charon` resolves to THIS checkout, not whatever `charon` an
    editable install made shadow it. Without this, a gate run inside a
    worktree silently exercises a different tree's fold logic — the exact
    defect this ticket exists to catch."""
    source = _CHECK_SCRIPT.read_text()
    assert "sys.path.insert(0, str(_REPO_SRC))" in source, (
        "gate does not insert its own src/ at the FRONT of sys.path — "
        "a worktree run could exercise a different checkout's fold logic"
    )