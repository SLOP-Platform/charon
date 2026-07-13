#!/usr/bin/env python3
# @covers: registry
# @covers: gate
"""Gate registry validator — single source of truth for all validation rules.

Reads tools/gates.json, validates every gate has a living enforcer,
checks no two gates cover the same domain, and prints a coverage summary.

Usage:
    python3 tools/check_gate_registry.py

Exit 0 on pass, 1 on violation.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
GATES_PATH = TOOLS_DIR / "gates.json"

ALL_DOMAINS: frozenset[str] = frozenset({
    "boundary", "security", "arch", "test", "test-patterns",
    "lint", "type", "version", "registry", "gate", "fleet", "docs", "decisions",
    "public-clean", "inert",
})


def load_gates() -> list[dict]:
    with open(GATES_PATH) as f:
        return json.load(f)


def scan_covers_annotations() -> dict[str, str]:
    """Scan tools/*.py for '# @covers: <domain>' and return {domain: rel_path}."""
    covers: dict[str, str] = {}
    for py_file in sorted(TOOLS_DIR.glob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            m = re.match(r'^[ \t]*#[ \t]*@covers:\s*(\S+)', line)
            if m:
                domain = m.group(1).strip()
                rel = str(py_file.relative_to(REPO_ROOT))
                if domain in covers:
                    print(
                        f"WARNING: duplicate @covers:{domain} in {rel} "
                        f"(already claimed by {covers[domain]})",
                        file=sys.stderr,
                    )
                else:
                    covers[domain] = rel
    return covers


def _resolve_enforcer(enforcer: str) -> tuple[bool, str]:
    """Check whether *enforcer* resolves to an existing file or runnable command.

    Returns (found: bool, description: str).
    """
    parts = enforcer.split()
    if not parts:
        return False, ""

    first = parts[0]

    # External path (e.g. '../charon-private/...') — resolve without verifying
    if first.startswith("../"):
        return True, f"<external:{first}>"

    # Direct file path inside repo
    candidate = REPO_ROOT / first
    if candidate.is_file():
        return True, str(candidate.relative_to(REPO_ROOT))

    # Command on PATH
    if shutil.which(first):
        return True, f"<cmd:{first}>"

    return False, ""


def validate() -> int:
    if not GATES_PATH.exists():
        print(f"ERROR: {GATES_PATH} not found", file=sys.stderr)
        return 1

    try:
        gates = load_gates()
    except json.JSONDecodeError as e:
        print(f"ERROR: {GATES_PATH} is not valid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(gates, list):
        print("ERROR: gates.json must contain a JSON array", file=sys.stderr)
        return 1

    if not gates:
        print("ERROR: gates.json is empty", file=sys.stderr)
        return 1

    issues: list[str] = []

    # 1. Schema validation + enforcer existence
    required_fields = {"id", "domain", "enforcer"}
    for i, gate in enumerate(gates):
        if not isinstance(gate, dict):
            issues.append(f"entry {i}: not a JSON object")
            continue

        gid = gate.get("id", f"#{i}")
        missing = required_fields - set(gate.keys())
        if missing:
            issues.append(f"{gid}: missing required fields: {sorted(missing)}")
            continue

        enforcer = gate.get("enforcer", "")
        if not enforcer:
            issues.append(f"{gid}: enforcer is empty")
            continue

        exists, resolved = _resolve_enforcer(enforcer)
        if not exists:
            issues.append(f"{gid}: enforcer {enforcer!r} does not resolve to a file or command")

    # 2. Domain uniqueness
    domains_seen: dict[str, str] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        domain = gate.get("domain", "")
        if not domain:
            issues.append(f"{gate.get('id', '?')}: domain is empty")
            continue
        if domain in domains_seen:
            issues.append(
                f"DOMAIN-OVERLAP: {gate['id']} and {domains_seen[domain]} "
                f"both cover domain {domain!r}"
            )
        else:
            domains_seen[domain] = gate["id"]

    # 3. Invariant uniqueness (Rule 5 — no duplicate invariant coverage)
    invariants_seen: dict[str, str] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        invariant = gate.get("invariant", "")
        if not invariant:
            continue
        if invariant in invariants_seen:
            issues.append(
                f"INVARIANT-OVERLAP: {gate['id']} and {invariants_seen[invariant]} "
                f"both cover invariant {invariant!r}"
            )
        else:
            invariants_seen[invariant] = gate["id"]

    # 4. ID uniqueness
    ids_seen: dict[str, int] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gid = gate.get("id", "")
        if not gid:
            continue
        if gid in ids_seen:
            idx = list(gates).index(gate)
            issues.append(
                f"DUPLICATE-ID: {gid} appears at entries {ids_seen[gid]} and {idx}"
            )
        else:
            ids_seen[gid] = list(gates).index(gate)

    # 5. @covers: annotation consistency — every annotation should have a gate
    covers = scan_covers_annotations()
    for domain, file_path in sorted(covers.items()):
        if domain not in domains_seen:
            issues.append(
                f"ORPHAN-COVERS: {file_path} has @covers:{domain} but no gate "
                f"in registry covers domain {domain!r}"
            )

    # 6. @covers: annotation consistency — warn if a tools/*.py enforcer
    #    lacks its domain annotation (informational, not a failure)
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        domain = gate.get("domain", "")
        enforcer = gate.get("enforcer", "")
        if not domain or not enforcer:
            continue
        first_token = enforcer.split()[0]
        if first_token.startswith("tools/") and domain not in covers:
            print(
                f"  (info) {gate.get('id')}: {first_token} has no @covers:{domain} annotation",
                file=sys.stderr,
            )

    # Coverage summary
    uncovered = sorted(ALL_DOMAINS - set(domains_seen.keys()))
    extra = sorted(set(domains_seen.keys()) - ALL_DOMAINS)

    print("=== Gate Registry ===")
    print(f"  Gates: {len(gates)}")
    print(f"  Domains covered: {sorted(domains_seen.keys())}")
    if uncovered:
        print(f"  Domains uncovered: {uncovered}")
    if extra:
        print(f"  Unknown domains (not in ALL_DOMAINS): {extra}")
    print(f"  @covers annotations: {len(covers)}")

    if issues:
        print(f"\n=== Issues ({len(issues)}) ===", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    print("\ncheck_gate_registry: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())
