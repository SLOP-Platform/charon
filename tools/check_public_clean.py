#!/usr/bin/env python3
"""Public-clean lint — prevent personal/internal info from leaking into the public repo."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'10\.\d+\.\d+\.\d+'), 'internal IP (10.0.0.0/8)'),
    (re.compile(r'\b4-?lom\b', re.IGNORECASE), 'hostname "4-lom"'),
    (re.compile(r'\bcharon-?vm\b', re.IGNORECASE), 'hostname "charon-vm"'),
    (re.compile(r'/home/stack'), 'home path "/home/stack"'),
    (re.compile(r'charon-private'), 'rig name "charon-private"'),
    (re.compile(r'\b[0-9a-fA-F]{40,}\b'), 'hex token shape (>=40 chars)'),
]
_WAIVER_RE = re.compile(r'public-clean:\s*allow\b')
_EXCEPTIONS_PATH = Path("tools/.public-clean-exceptions.json")


def _load_exceptions(config_path: Path | None = None) -> dict[str, set[int]]:
    if config_path is None:
        config_path = _EXCEPTIONS_PATH
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text())
    return {fp: set(lines) for fp, lines in data.items()}


def check_file(path: Path, exceptions: dict[str, set[int]] | None = None) -> list[str]:
    if exceptions is None:
        exceptions = {}
    violations: list[str] = []
    rel = str(path)
    exempt = exceptions.get(rel, set())
    try:
        content = path.read_text()
    except (OSError, UnicodeDecodeError):
        return violations
    for lineno, line in enumerate(content.split("\n"), start=1):
        if lineno in exempt:
            continue
        if _WAIVER_RE.search(line):
            continue
        for pat, desc in _PATTERNS:
            if pat.search(line):
                violations.append(f"{rel}:{lineno}: {desc}: {line.strip()[:80]}")
                break
    return violations


def check_paths(paths: list[Path], exceptions: dict[str, set[int]] | None = None) -> list[str]:
    all_v: list[str] = []
    for p in paths:
        all_v.extend(check_file(p, exceptions))
    return all_v


def _tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.split("\0") if f]


def main() -> int:
    exceptions = _load_exceptions()
    all_v: list[str] = []
    for rel in sorted(_tracked_files()):
        all_v.extend(check_file(Path(rel), exceptions))
    if all_v:
        print("PUBLIC-CLEAN VIOLATION — personal/internal info found:", file=sys.stderr)
        for v in all_v:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("public-clean OK: no personal/internal patterns found in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
