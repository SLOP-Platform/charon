#!/usr/bin/env python3
"""Lint docs/DECISIONS.md and the ADRs it cross-references.

Exit codes:
  0  all checks pass
  1  one or more issues found

Usage:
  python tools/check_decisions.py           # human-readable report
  python tools/check_decisions.py --check   # CI mode: exits 1 on any issue
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Status values allowed in the register.
_STATUS_RE = re.compile(r"^(Settled|Open|Superseded→D\d{3,})$")

# Patterns for classifying a source token (after paren-stripping).
_ADR_TOKEN_RE = re.compile(r"^ADR-(\d{4})(?:\s+(.+))?$")
_REVIEW_LOG_RE = re.compile(r"^REVIEW-LOG\s+\S+$")
_DTC_RE = re.compile(r"^DTC\s+\S+$")

# Tokens accepted without document verification (non-verifiable but known).
_OPAQUE_OK = frozenset({"memory"})


_ESC_PIPE = "\x00"


def _parse_rows(text: str) -> list[dict[str, str]]:
    """Extract register table rows from DECISIONS.md text.

    Handles `\\|` (escaped pipe) inside cells — replaces with a placeholder
    before splitting, then restores.
    """
    rows: list[dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        if not line.startswith("|"):
            in_table = False
            continue
        # Temporarily hide escaped pipes so split doesn't treat them as delimiters.
        safe = line.replace(r"\|", _ESC_PIPE)
        cells = [c.strip().replace(_ESC_PIPE, "|") for c in safe.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if cells[0].upper() == "ID":
            in_table = True
            continue
        if all(re.fullmatch(r"-+", c) for c in cells):
            continue
        if not in_table:
            continue
        id_, _dec, _own, status, source = (cells + [""] * 5)[:5]
        if not re.fullmatch(r"D\d{3,}", id_):
            continue
        rows.append({"id": id_, "status": status, "source": source})
    return rows


def _id_num(id_str: str) -> int:
    return int(id_str[1:])


def _find_adr(adr_dir: Path, num: str) -> Path | None:
    hits = list(adr_dir.glob(f"{num}-*.md"))
    return hits[0] if hits else None


def _adr_status(path: Path) -> str | None:
    """Return 'Accepted' or 'Proposed' from the ADR status line (first 10 lines)."""
    for line in path.read_text().splitlines()[:10]:
        if "status" in line.lower():
            if re.search(r"\bAccepted\b", line, re.IGNORECASE):
                return "Accepted"
            if re.search(r"\bProposed\b", line, re.IGNORECASE):
                return "Proposed"
    return None


def _section_exists(path: Path, section: str) -> bool:
    """True if `section` (e.g. 'D2', 'D-ESC-1') appears as a heading identifier."""
    content = path.read_text()
    pat = r"(?<![A-Za-z0-9])" + re.escape(section) + r"(?![A-Za-z0-9])"
    return bool(re.search(pat, content))


def _source_tokens(source: str) -> list[str]:
    """Split source cell into tokens, discarding parenthesised annotations."""
    cleaned = re.sub(r"\([^)]*\)", "", source)
    return [t.strip() for t in cleaned.split(",") if t.strip()]


def _check_token(token: str, adr_dir: Path, review_log: Path) -> str | None:
    """Return an error string if the token is unresolvable, else None."""
    if not token or token in _OPAQUE_OK:
        return None
    m = _ADR_TOKEN_RE.match(token)
    if m:
        num, sec = m.group(1), m.group(2)
        adr = _find_adr(adr_dir, num)
        if adr is None:
            return f"ADR-{num}: file docs/adr/{num}-*.md not found"
        if sec:
            for s in re.split(r"[/,]", sec):
                s = s.strip()
                if s and not _section_exists(adr, s):
                    return f"ADR-{num} section '{s}' not found in {adr.name}"
        return None
    if _REVIEW_LOG_RE.match(token):
        return None if review_log.exists() else f"REVIEW-LOG: {review_log} not found"
    if _DTC_RE.match(token):
        return f"standalone DTC token '{token}' has no anchor document"
    return f"unrecognised source token '{token}'"


def lint(docs_dir: Path | None = None) -> list[str]:
    """Run all register checks; return list of issue strings (empty = pass)."""
    root = docs_dir or Path("docs")
    register = root / "DECISIONS.md"
    adr_dir = root / "adr"
    review_log = root / "REVIEW-LOG.md"

    if not register.exists():
        return [f"register not found: {register}"]

    rows = _parse_rows(register.read_text())
    if not rows:
        return ["no decision rows found"]

    issues: list[str] = []

    # 1. ID monotonicity — flag gaps, duplicates, and out-of-order rows.
    prev = 0
    seen: set[int] = set()
    for r in rows:
        n = _id_num(r["id"])
        if n in seen:
            issues.append(f"{r['id']}: duplicate ID")
        seen.add(n)
        if prev > 0:
            if n <= prev:
                issues.append(f"{r['id']}: out-of-order (follows D{prev:03d})")
            elif n != prev + 1:
                issues.append(f"{r['id']}: gap — expected D{prev+1:03d}, got {r['id']}")
        prev = max(prev, n)

    # 2. Status enum check.
    for r in rows:
        if not _STATUS_RE.match(r["status"]):
            issues.append(
                f"{r['id']}: invalid Status {r['status']!r} "
                f"(allowed: Settled | Open | Superseded→Dxxx)"
            )

    # 3. Source token resolution.
    for r in rows:
        for tok in _source_tokens(r["source"]):
            err = _check_token(tok, adr_dir, review_log)
            if err:
                issues.append(f"{r['id']}: {err}")

    # 4. Register-Settled vs ADR-Proposed: Settled requires Accepted ADR.
    for r in rows:
        if r["status"] != "Settled":
            continue
        for tok in _source_tokens(r["source"]):
            m = _ADR_TOKEN_RE.match(tok)
            if not m:
                continue
            adr = _find_adr(adr_dir, m.group(1))
            if adr and _adr_status(adr) == "Proposed":
                issues.append(
                    f"{r['id']}: Status=Settled but ADR-{m.group(1)} is still Proposed"
                )

    return issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint the Charon decision register.")
    ap.add_argument("--check", action="store_true", help="CI mode: exit 1 on any issue")
    ap.add_argument("--docs", default=None, help="Path to docs/ directory")
    args = ap.parse_args(argv)

    docs_dir = Path(args.docs) if args.docs else None
    issues = lint(docs_dir)

    if args.check:
        if issues:
            print(f"check_decisions: {len(issues)} issue(s)", file=sys.stderr)
            for iss in issues:
                print(f"  {iss}", file=sys.stderr)
            return 1
        print("check_decisions: OK")
        return 0

    if issues:
        print(f"Decision register: {len(issues)} issue(s)\n")
        for iss in issues:
            print(f"  • {iss}")
        return 1
    print("Decision register: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
