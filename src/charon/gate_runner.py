"""Unified CHARON-GATE runner — runs all validation checks in sequence."""

import subprocess
import sys

CHECKS: list[tuple[list[str], str]] = [
    (["ruff", "check", "src", "tests"], "ruff"),
    (["mypy", "src", "tests"], "mypy"),
    (["python3", "tools/check_boundary.py", "src"], "SLOP-boundary"),
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


def run_gate() -> int:
    print("CHARON GATE — running all validation checks...")
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
