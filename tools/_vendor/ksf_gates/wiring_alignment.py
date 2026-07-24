"""Gate (b) — wiring_alignment: production-path == test-path + auto-derive entrypoints.

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/wiring_alignment.py`` (Keystone Framework).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only changes from the KSF original are the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package)
and the `glob` import rename to `glb` to avoid shadowing the stdlib `glob`
module used elsewhere. Everything else — including the KSF-native
``check_wiring_alignment(db_path, manifest, modules)`` signature — is
untouched; see ``tools/check_wiring_alignment.py`` for the Charon-side
adapter. Do not hand-edit the logic below; re-copy from KSF and re-apply
this header if the upstream detector changes. See ``tools/_vendor/README.md``.
"""

from __future__ import annotations

import glob as glb
import json
import tomllib
from pathlib import Path

from tools._vendor.ksf_gate_result import GateResult


def _derive_entrypoints(repo_root: Path) -> dict[str, str]:
    """Read [project.scripts] from pyproject.toml via stdlib tomllib."""
    entrypoints: dict[str, str] = {}
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text())
        scripts = data.get("project", {}).get("scripts", {})
        for name, spec in scripts.items():
            # spec: "dotted.path:callable"
            if isinstance(spec, str) and ":" in spec:
                module = spec.split(":")[0]
                entrypoints[name] = module
    return entrypoints


def _load_static_entrypoints(repo_root: Path) -> dict[str, str]:
    ep_file = repo_root / ".ksf" / "entrypoints.json"
    if ep_file.exists():
        with ep_file.open("rb") as f:
            data = json.load(f)
            if isinstance(data, dict):
                entrypoints: dict[str, str] = {}
                for name, spec in data.items():
                    if isinstance(spec, str) and ":" in spec:
                        entrypoints[name] = spec.split(":")[0]
                    else:
                        entrypoints[name] = spec
                return entrypoints
    return {}


def _module_entrypoints(repo_root: Path, mod_name: str) -> list[str]:
    """Read module.toml entrypoints list, if any."""
    for candidate in repo_root.rglob("module.toml"):
        text = candidate.read_text()
        if f'name = "{mod_name}"' in text:
            for line in text.splitlines():
                if line.strip().startswith("entrypoints"):
                    raw = line.split("=")[1].strip()
                    return [
                        x.strip().strip('"').strip("'")
                        for x in raw.strip("[]").split(",")
                        if x.strip()
                    ]
    return []


def _tests_import_module(repo_root: Path, module: str) -> bool:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return False
    for pyfile in tests_dir.rglob("*.py"):
        text = pyfile.read_text()
        if f"import {module}" in text or f"from {module}" in text:
            return True
    return False


def check_wiring_alignment(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    repo_root = db_path.parent.parent
    gaps: list[str] = []
    messages: list[str] = []

    auto_eps = _derive_entrypoints(repo_root)
    static_eps = _load_static_entrypoints(repo_root)
    # merge: static overrides auto
    entrypoints = {**auto_eps, **static_eps}

    # add module-level entrypoints
    for mod in modules:
        for ep in _module_entrypoints(repo_root, mod["name"]):
            entrypoints[mod["name"]] = ep

    # verify each entrypoint has a test importing the same module path
    for name, module in sorted(entrypoints.items()):
        if not _tests_import_module(repo_root, module):
            gaps.append("missing-test-import")
            messages.append(f"missing-test-import: entrypoint '{name}' -> '{module}' has no test import")

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
