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
    # public-clean: allow — the name-detection pattern must name the token it catches
    (re.compile(r'\bRafael\b', re.IGNORECASE), 'personal given name'),  # public-clean: allow
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


def _scan_content(
    rel: str, content: str, exceptions: dict[str, set[str]] | None = None
) -> list[str]:
    """Line-by-line pattern scan of already-read text.

    Single detection core shared by every entrypoint (working-tree file read,
    staged-blob read), so the working-tree scan and the staged-blob scan can
    never disagree about what counts as a leak.
    """
    if exceptions is None:
        exceptions = {}
    violations: list[str] = []
    exempt = exceptions.get(rel, set())
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


def check_file(path: Path, exceptions: dict[str, set[str]] | None = None) -> list[str]:
    rel = str(path)
    try:
        content = path.read_text()
    except (OSError, UnicodeDecodeError):
        return []
    return _scan_content(rel, content, exceptions)


def check_paths(paths: list[Path], exceptions: dict[str, set[str]] | None = None) -> list[str]:
    all_v: list[str] = []
    for p in paths:
        all_v.extend(check_file(p, exceptions))
    return all_v


def _tracked_files() -> list[str]:
    """Enumerate every git-tracked path (FAIL-CLOSED).

    A non-zero ``git ls-files`` (not a repo, git missing, permission error) or
    an empty result must NOT be swallowed into ``[]`` — that would make
    ``scan_tracked`` pass vacuously and let the gate print ``public-clean OK``
    without having scanned anything. Both cases raise loudly so the gate/CI
    exits non-zero instead of silently no-op'ing.
    """
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (rc={result.returncode}) — refusing to run public-clean on an "
            f"empty file set (fail-closed). stderr: {result.stderr.strip()}"
        )
    files = [f for f in result.stdout.split("\0") if f]
    if not files:
        raise RuntimeError(
            "git ls-files returned no tracked files — refusing to pass public-clean vacuously "
            "(fail-closed). Run from inside the repository working tree."
        )
    return files


def _staged_content(rel: str) -> str | None:
    """Return the STAGED (index) blob for ``rel`` as text, or None to skip it.

    Reads ``git show :<rel>`` so the pre-commit hook gates exactly what would be
    committed — not the working tree. Returns None when the path is not in the
    index (e.g. a deletion) or when the staged blob is binary/undecodable, which
    the caller skips (mirrors ``check_file``'s binary handling).
    """
    result = subprocess.run(["git", "show", f":{rel}"], capture_output=True, check=False)
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check_staged_paths(
    rels: list[str], exceptions: dict[str, set[str]] | None = None
) -> list[str]:
    """Scan the STAGED content of the given repo-relative paths (pre-commit).

    Unlike ``_scan_rel_paths`` (working-tree reads), this reads each path's
    index blob, so a leak that is ``git add``-ed but absent from the working
    copy is still caught, and an unstaged working-tree edit cannot false-red a
    clean commit.
    """
    if exceptions is None:
        exceptions = _load_exceptions()
    all_v: list[str] = []
    exceptions_rel = str(_EXCEPTIONS_PATH)
    for rel in rels:
        if rel == exceptions_rel:
            continue
        content = _staged_content(rel)
        if content is None:
            continue
        all_v.extend(_scan_content(rel, content, exceptions))
    return all_v


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
    staged = bool(argv) and argv[0] == "--staged"
    if staged:
        argv = argv[1:]
    if staged:
        # Pre-commit path: scan the STAGED index blobs of the given paths, so the
        # hook gates exactly what will be committed (not the working tree).
        all_v = check_staged_paths(argv, exceptions)
    elif argv:
        # Explicit working-tree paths — scan just those. Still honours the
        # exceptions ledger and inline waivers.
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
