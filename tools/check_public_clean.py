#!/usr/bin/env python3
# @covers: public-clean
"""Public-clean lint — prevent personal/internal info from leaking into the public repo."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'10\.\d+\.\d+\.\d+'), 'internal IP (10.0.0.0/8)'),
    (re.compile(r'10\.0\.1\.\d+'), 'coordinator LAN subnet (10.0.1.0/24)'),   # named, explicit;
        # redundant with the generic 10.x pattern above by design (defense in depth: this
        # survives even if the generic pattern is ever narrowed/refactored, because it names
        # the coordinator's actual subnet directly rather than relying on a broad bucket)
    (re.compile(r'192\.168\.\d+\.\d+'), 'internal IP (192.168.0.0/16)'),
    (re.compile(r'172\.(1[6-9]|2\d|3[01])\.\d+\.\d+'), 'internal IP (172.16.0.0/12)'),
    (re.compile(r'\b4-?lom\b', re.IGNORECASE), 'hostname "4-lom"'),
    (re.compile(r'\bcharon-?vm\b', re.IGNORECASE), 'hostname "charon-vm"'),
    (re.compile(r'/home/stack'), 'home path "/home/stack"'),
    (re.compile(r'charon-private'), 'rig name "charon-private"'),
    (re.compile(r'\b[0-9a-fA-F]{40,}\b'), 'hex token shape (>=40 chars)'),
]
_WAIVER_RE = re.compile(r'public-clean:\s*allow\b')
_EXCEPTIONS_PATH = Path("tools/.public-clean-exceptions.json")


def _load_exceptions(config_path: Path | None = None) -> dict[str, set[str]]:
    """Load the exceptions config.

    Exemptions are keyed by exact line CONTENT (not line number) so an
    unrelated insertion/deletion elsewhere in the file can never silently
    shift a waiver onto the wrong line (which would either un-mask a real
    leak or mask a brand-new one). If the exempted content is edited or
    removed, the exemption simply stops matching and the line is
    re-evaluated against the patterns like any other — fail-safe, not
    fail-silent.
    """
    if config_path is None:
        config_path = _EXCEPTIONS_PATH
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text())
    return {fp: set(lines) for fp, lines in data.items()}


def check_file(path: Path, exceptions: dict[str, set[str]] | None = None) -> list[str]:
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
        if line in exempt:
            continue
        if _WAIVER_RE.search(line):
            continue
        for pat, desc in _PATTERNS:
            if pat.search(line):
                violations.append(f"{rel}:{lineno}: {desc}: {line.strip()[:80]}")
                break
    return violations


def check_paths(paths: list[Path], exceptions: dict[str, set[str]] | None = None) -> list[str]:
    all_v: list[str] = []
    for p in paths:
        all_v.extend(check_file(p, exceptions))
    return all_v


def _tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.split("\0") if f]


def _scan_rel_paths(rels: list[str], exceptions: dict[str, set[str]]) -> list[str]:
    """Scan an explicit list of repo-relative paths, skipping the exceptions ledger.

    The exceptions ledger itself necessarily restates the exact,
    already-elsewhere-exempted line content it waives (that's the whole point
    of content-based matching — see _load_exceptions). None of that text is a
    *new* disclosure: it is verbatim what was already reviewed and allowed at
    its original location. Scanning the ledger against itself would just re-flag
    its own bookkeeping, so it is excluded — the same way a detect-secrets
    baseline file is excluded from its own secret scan.
    """
    all_v: list[str] = []
    exceptions_rel = str(_EXCEPTIONS_PATH)
    for rel in rels:
        if rel == exceptions_rel:
            continue
        all_v.extend(check_file(Path(rel), exceptions))
    return all_v


def scan_tracked(exceptions: dict[str, set[str]] | None = None) -> list[str]:
    """Scan every git-tracked file for personal/internal leaks.

    Single source of truth for the whole-repo scan: both ``main()`` (the
    CLI/gate/CI entrypoint) and the pytest repo-scan regression test call this,
    so the tree the gate enforces and the tree the tests assert on can never
    drift apart.
    """
    if exceptions is None:
        exceptions = _load_exceptions()
    return _scan_rel_paths(sorted(_tracked_files()), exceptions)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    exceptions = _load_exceptions()
    if argv:
        # Explicit paths (e.g. the pre-commit hook passes staged files) — scan
        # just those. Still honours the exceptions ledger and inline waivers.
        all_v = _scan_rel_paths(argv, exceptions)
    else:
        all_v = scan_tracked(exceptions)
    if all_v:
        print("PUBLIC-CLEAN VIOLATION — personal/internal info found:", file=sys.stderr)
        for v in all_v:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("public-clean OK: no personal/internal patterns found in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
