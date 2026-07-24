"""Gate (a) — coverage_ssot: enforcement-coverage SSOT meta-gate.

Tracks numeric % coverage and classifies every rule as:
  - mechanized  (has a gate implementation)
  - guidance    (explicitly human-judgment; no gate expected)
  - GAP         (unclassified / missing coverage)

FAIL on any GAP or mechanizable-rule-with-no-gate.
Goal = 100 % where logical (all non-guidance rules mechanized).

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/coverage_ssot.py`` (Keystone Framework).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only changes from the KSF original are the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package)
and the gates_dir path (``ksf/gates/`` -> ``tools/_vendor/ksf_gates/`` so the
detector finds Charon's vendored copies). Everything else — including the
KSF-native ``check_coverage_ssot(db_path, manifest, modules)`` signature — is
untouched; see ``tools/check_coverage_ssot.py`` for the Charon-side adapter.
Do not hand-edit the logic below; re-copy from KSF and re-apply this header
if the upstream detector changes. See ``tools/_vendor/README.md``.
"""

from __future__ import annotations

import glob as glb
from pathlib import Path

from tools._vendor.ksf_gate_result import GateResult


# ---------------------------------------------------------------------------
# Rule classification registry — SSOT for what each rule expects.
# ---------------------------------------------------------------------------
_RULE_CLASSIFICATIONS: dict[str, str] = {
    # Built-in mechanized gates (all current gates have implementations)
    "coverage_ssot": "mechanized",
    "wiring_alignment": "mechanized",
    "redproof": "mechanized",
    "no_vacuous": "mechanized",
    "no_skip_game": "mechanized",
    "no_pipe_mask": "mechanized",
    "fail_loud": "mechanized",
    "leak_guard": "mechanized",
    "inert_code": "mechanized",
    # Guidance rules (human judgment; no gate expected) — declare explicitly
    # e.g. "ai_judgment": "guidance",
}


def _gate_functions(gates_dir: Path) -> set[str]:
    """Auto-discover check_* functions in tools/_vendor/ksf_gates/*.py."""
    names: set[str] = set()
    if not gates_dir.exists():
        return names
    for p in gates_dir.glob("*.py"):
        if p.name.startswith("_"):
            continue
        text = p.read_text()
        for line in text.splitlines():
            if line.startswith("def check_"):
                fname = line.split("(")[0].replace("def ", "").strip()
                if fname.startswith("check_"):
                    fname = fname[6:]
                names.add(fname)
    return names


def _classify_rule(rule_name: str, implemented: set[str]) -> str:
    """Return 'mechanized' | 'guidance' | 'GAP' for a rule.

    The returned value is the INTENDED classification, not the realization.
    Coverage gaps are derived from intended classification + implementation
    presence in _compute_coverage().
    """
    declared = _RULE_CLASSIFICATIONS.get(rule_name)
    if declared == "guidance":
        if rule_name in implemented:
            return "mechanized"
        return "guidance"
    if declared == "mechanized":
        return "mechanized"
    if rule_name in implemented:
        return "mechanized"
    return "GAP"


def _compute_coverage(
    registry: set[str],
    implemented: set[str],
) -> tuple[float, dict[str, str], list[str], list[str]]:
    """Compute coverage % and per-rule classification.

    Returns (pct, class_map, gaps, messages).
    """
    class_map: dict[str, str] = {}
    gaps: list[str] = []
    messages: list[str] = []

    for rule in sorted(registry | implemented):
        cls = _classify_rule(rule, implemented)
        class_map[rule] = cls
        if cls == "mechanized" and rule not in implemented:
            gaps.append("no-mechanism")
            messages.append(
                f"no-mechanism: rule '{rule}' classified mechanized but has no implementation"
            )
        if cls == "GAP":
            gaps.append("coverage-gap")
            messages.append(
                f"GAP: rule '{rule}' is unclassified (no mechanized gate, not declared guidance)"
            )

    total_rules = len(registry)
    covered = sum(
        1 for r in registry if class_map.get(r) in ("mechanized", "guidance")
    )
    if total_rules > 0:
        pct = covered / total_rules * 100.0
    else:
        pct = 100.0

    messages.append(f"coverage: {pct:.1f}% ({covered}/{total_rules} rules covered)")
    return pct, class_map, gaps, messages


def check_coverage_ssot(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    """
    Coverage SSOT gate.

    Checks:
      1) Every rule in manifest is classified mechanized/guidance/GAP.
      2) Numeric % coverage tracked (goal = 100%).
      3) mechanized rules MUST have an implementation.
      4) Red-proof tests exist for each implemented gate.
      5) Modules are wired with correct gates, tests, and surface.
    """
    repo_root = db_path.parent.parent
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    proofs_dir = repo_root / ".ksf" / "gates"

    # ---- 1. Rule-level coverage -------------------------------------------
    implemented = _gate_functions(gates_dir)
    manifest_gates = manifest.get("gates", {})
    if isinstance(manifest_gates, dict):
        manifest_gates = manifest_gates.get("list", [])
    registry = set(manifest_gates)

    pct, class_map, gaps, messages = _compute_coverage(registry, implemented)

    # Red-proof presence for mechanized gates
    for rule in sorted(registry):
        if class_map.get(rule) != "mechanized":
            continue
        rp_test = proofs_dir / f"test_redproof_{rule}.py"
        if not rp_test.exists():
            gaps.append("never-gone-red")
            messages.append(f"never-gone-red: gate '{rule}' has no red-proof test")

    # ---- 2. Module-level wiring checks ------------------------------------
    for mod in modules:
        mod_name = mod["name"]
        mod_surface = mod.get("surface") or ""
        wired = mod.get("wired", 0)

        # Find module.toml
        mod_toml_path: Path | None = None
        declared_gates: set[str] = set()
        for candidate in repo_root.rglob("module.toml"):
            text = candidate.read_text()
            if f'name = "{mod_name}"' in text:
                mod_toml_path = candidate
                for line in text.splitlines():
                    if line.strip().startswith("gates"):
                        raw = line.split("=")[1].strip()
                        declared_gates = set(
                            x.strip().strip('"').strip("'")
                            for x in raw.strip("[]").split(",")
                            if x.strip()
                        )
                break

        for g in sorted(declared_gates):
            if class_map.get(g) == "GAP":
                gaps.append("coverage-gap")
                messages.append(
                    f"GAP: module '{mod_name}' declares unclassified gate '{g}'"
                )
            elif g not in implemented:
                gaps.append("wired-not-activated")
                messages.append(
                    f"wired-not-activated: {mod_name} gate '{g}' not implemented"
                )

        if mod_toml_path is not None:
            rp = mod_toml_path.parent / "test_redproof.py"
            if not rp.exists():
                gaps.append("wired-not-activated")
                messages.append(
                    f"wired-not-activated: {mod_name} missing test_redproof.py"
                )

        if wired == 0:
            gaps.append("wired-not-activated")
            messages.append(f"wired-not-activated: {mod_name} wired=0")

        # surface-missing
        if mod_surface:
            matches = glb.glob(str(repo_root / mod_surface), recursive=True)
            if not matches:
                for p in str(repo_root / mod_surface).split(","):
                    if not glb.glob(p.strip()):
                        gaps.append("surface-missing")
                        messages.append(
                            f"surface-missing: {mod_name} surface '{mod_surface}' matches nothing"
                        )
                        break

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
