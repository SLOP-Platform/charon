#!/usr/bin/env python3
# @covers: deadcode
"""Deadcode-tools gate — wired-in adoption of ``vulture`` + ``deadcode`` as a
single, deduplicated, findings-budget-ratcheting merge gate.

WHY THIS EXISTS. ``tools/check_inert_code.py`` (the KSF reachability gate)
catches **mutually-referencing dead islands** by walking the call graph from
real entrypoints — the class a hand-rolled audit previously missed
(``tool_repair.py``, ``pricing_limits_checker.py``, ``engine/reconcile.py``).
Neither ``vulture`` nor ``deadcode`` does that; both are reference-counting.
Per the operator-approved DEADCODE-TOOL-REDERIVE substrate
(merged d90381d) the two checkers are kept AND we adopt vulture + deadcode
**additively** for the classes they each do best:

- **vulture (100% confidence)** uniquely detects ``unreachable code after
  return/try`` — a class neither ruff nor our reachability gate produces.
  The substrate also emits function/class/method/property/attribute findings
  that mostly duplicate ``deadcode``; we run vulture at 100% confidence so
  only those unique findings survive.
- **deadcode** emits a clean DC01..DC11 taxonomy (variable, function, class,
  method, attribute, property, empty-file, ...) that maps cleanly onto
  findings-budget arithmetic.

Adopted-wire contract — every RED proof must exercise this:

  a. A newly-introduced unused method/class/attribute makes the check RED.
  b. A newly-introduced unreachable-after-return/try statement makes the
     check RED (the vulture-unique class — the whole reason vulture is here).
  c. The findings count is a SHRINKING-ONLY RATCHET. The current count is
     recorded in :data:`BUDGET_FILE`; runs that exceed it fail. Below it,
     the count in the file must be updated downward in the SAME commit
     that lowered it. A frozen baseline that reports green over a growing
     pile is the fake-green class this whole programme is about — the
     number must be a ratchet, not a floor.
  d. **It runs in CI.** A configured-but-unrun scanner is exactly the inert
     class this gate is named after.

DEDUPE. ``vulture`` and ``deadcode`` frequently report the same symbol at
the same line. We collapse by ``(path, line, name)``; the resulting list
is what the ratchet counts. Without dedupe the budget would double-count
the overlap and the ratchet would have a moving target.

SCOPE. ``src/`` only. ``tests/`` and ``tools/`` are not scanned: tests are
exercise surface (an unused test helper is an import pattern, not dead
product code), and ``tools/`` is dev-only wiring — outside the product.
``tools/_vendor/`` is the KSF-detector directory, not Charon's own code,
so it is excluded from ``vulture`` and ``deadcode`` (both have a way to
limit the file list — we use the directory path itself as the input
boundary; the ``src/`` constraint is enforced by the gate before
delegating to either tool, so neither tool even walks ``tools/_vendor/``).

WORK UNITS. We report ``len(findings)`` — the number of (path, line, name)
tuples both tools collectively emitted after dedupe. A zero-finding run on
a non-empty ``src/`` is suspicious but legal (every symbol reachable) and
the ratchet enforces that the trend is downward, so a clean tree with
``BUDGET=0`` is the future steady state.

Stdlib plus the two adopted detector packages; nothing else.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.gate_contract import emit_work_units  # noqa: E402


# Finding shape after dedupe.
class Finding(TypedDict):
    path: str  # repo-relative, slash-separated
    line: int
    name: str
    classes: list[str]  # e.g. ["DC04", "vulture:unreachable"]; classification tag list


BUDGET_FILE = REPO_ROOT / "tools" / "deadcode-tools-budget.json"

# vulture's unique class — everything else deadcode covers. We restrict vulture
# to 100% confidence to suppress duplicate-of-deadcode findings.
_VULTURE_MIN_CONFIDENCE = 100
_VULTURE_UNREACHABLE_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):\s*unreachable code after '(?P<after>\w+)'"
    r" \(\d+% confidence\)$"
)
# Anything vulture emits that isn't 'unreachable' is treated as duplicate of
# deadcode's reference-counting output — drop it (dedupe). The line below the
# regex tells readers why; keep them aligned.
_VULTURE_GENERIC_RE = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+):\s*(?P<rest>.+)$")


def _scan_vulture(src_root: Path) -> list[Finding]:
    """Return vulture-unique findings (100% confidence, unreachable-only).

    Runs vulture as a subprocess to honour its native resolution (whitelist
    handling, configuration file loading if present) rather than its Python
    API. ``vulture`` exits non-zero when findings exist — we must not
    surface that as our exit code, so we capture and ignore. Outliers are
    parsed only against :data:`_VULTURE_UNREACHABLE_RE`; any other 100%-line
    vulture emits (e.g. the 5 ``unused variable`` lines on
    ``proxy_server.py`` / ``drain.py`` etc.) is intentionally dropped here
    because deadcode already reports them and dedupe-with-our-ratchet needs
    a single source of truth per (path, line, name).
    """
    proc = subprocess.run(
        ["vulture", str(src_root), "--min-confidence", str(_VULTURE_MIN_CONFIDENCE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    findings: list[Finding] = []
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        m = _VULTURE_UNREACHABLE_RE.match(line.strip())
        if not m:
            continue
        findings.append(
            Finding(
                path=_repo_rel(m.group("path")),
                line=int(m.group("line")),
                name=f"unreachable-after-{m.group('after')}",
                classes=["vulture:unreachable"],
            )
        )
    return findings


def _scan_deadcode(src_root: Path) -> list[Finding]:
    """Return deadcode's DC01..DC11 findings (excluding empty-file class).

    Empty-file is left to ``check_inert_code.py`` — its disposition file
    already tracks the 0-in-scope count, and double-reporting would
    double the ratchet burden. Other classes pass through.
    """
    from deadcode.cli import find_python_filenames, find_unused_names
    from deadcode.data_types import Args

    args = Args(paths=[str(src_root)])
    files = [str(p) for p in find_python_filenames(args)]
    findings: list[Finding] = []
    for item in find_unused_names(files, args):
        if item.error_code == "DC11":  # empty file — exclude
            continue
        findings.append(
            Finding(
                path=_repo_rel(str(item.filename)),
                line=int(item.name_line),
                name=str(item.name),
                classes=[str(item.error_code)],
            )
        )
    return findings


def _repo_rel(abs_or_repo_path: str) -> str:
    p = Path(abs_or_repo_path)
    try:
        return str(p.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _dedupe(all_findings: Iterable[Finding]) -> list[Finding]:
    """Collapse duplicates by ``(path, line, name)``; merge their class tags.

    vulture and deadcode legitimately cover different classes of dead code
    for the same symbol at the same line (e.g. both call out an unused
    function). The ratchet counts the symbol once and the class tags list
    carries both classifications so reviewers can see why two tools agreed.
    """
    merged: dict[tuple[str, int, str], Finding] = {}
    for f in all_findings:
        key = (f["path"], f["line"], f["name"])
        if key not in merged:
            merged[key] = Finding(
                path=f["path"],
                line=f["line"],
                name=f["name"],
                classes=list(f["classes"]),
            )
        else:
            existing_classes = merged[key]["classes"]
            for c in f["classes"]:
                if c not in existing_classes:
                    existing_classes.append(c)
            merged[key]["classes"] = existing_classes
    # Sort for stable output / stable display across runs.
    return sorted(
        merged.values(),
        key=lambda f: (f["path"], f["line"], f["name"]),
    )


def collect_findings(src_root: Path = REPO_ROOT / "src") -> list[Finding]:
    """Run both tools, dedupe, return the sorted findings list."""
    src_root = src_root.resolve()
    if not src_root.is_dir():
        raise FileNotFoundError(f"src root not found: {src_root}")
    vulture_findings = _scan_vulture(src_root)
    deadcode_findings = _scan_deadcode(src_root)
    return _dedupe(iter(list(vulture_findings) + list(deadcode_findings)))


def load_budget() -> int:
    """Return the frozen-or-current findings budget, or raise a clear error."""
    if not BUDGET_FILE.exists():
        raise FileNotFoundError(
            f"deadcode-tools-budget.json not found at {BUDGET_FILE} — the gate "
            "cannot run without a recorded baseline (RATCHET-CONTRACT)."
        )
    data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    n = data.get("findings_count")
    if not isinstance(n, int) or n < 0:
        raise ValueError(
            f"{BUDGET_FILE.name}: 'findings_count' must be a non-negative int, got {n!r}"
        )
    return n


def check(
    src_root: Path = REPO_ROOT / "src",
    budget_file: Path = BUDGET_FILE,
) -> tuple[bool | None, int, int, list[Finding]]:
    """Run the gate; return ``(state, observed, budget, findings)``.

    ``state`` is the three-valued ratchet verdict:

    - ``True`` — findings equal the recorded budget. Gate passes.
    - ``False`` — findings exceed the budget (regression). Gate fails CLOSED.
    - ``None`` — findings below the budget (shrinkage, BUDGET-OUT-OF-DATE).
      Gate fails CLOSED until the budget file is lowered to match.

    ``src_root`` and ``budget_file`` are injectable for tests — the real
    invocation in CI leaves both at their defaults.
    """
    findings = collect_findings(src_root=src_root)
    observed = len(findings)
    if not budget_file.exists():
        raise FileNotFoundError(
            f"deadcode-tools-budget.json not found at {budget_file} — the gate "
            "cannot run without a recorded baseline (RATCHET-CONTRACT)."
        )
    data = json.loads(budget_file.read_text(encoding="utf-8"))
    budget = data.get("findings_count")
    if not isinstance(budget, int) or budget < 0:
        raise ValueError(
            f"{budget_file.name}: 'findings_count' must be a non-negative int, got {budget!r}"
        )
    if observed > budget:
        state: bool | None = False
    elif observed < budget:
        state = None
    else:
        state = True
    return state, observed, budget, findings


def main() -> int:
    findings = collect_findings()
    observed = len(findings)
    # Emit zero-arg work-unit line on every path — including the FAIL path —
    # so the runner's zero-work-units contract can tell a gate that examined
    # nothing apart from one that scanned the tree and found nothing.
    emit_work_units(len(list((REPO_ROOT / "src").rglob("*.py"))))

    try:
        state, _, budget, _ = check()
    except (FileNotFoundError, ValueError) as e:
        print(f"deadcode-tools: BUDGET-LOAD-FAILED: {e}", file=sys.stderr)
        return 1

    print(
        f"deadcode-tools: {observed} finding(s) after dedupe "
        f"(vulture 100% unreachable-only + deadcode DC01..DC10); "
        f"budget={budget}"
    )
    by_class: dict[str, int] = {}
    for f in findings:
        for c in f["classes"]:
            by_class[c] = by_class.get(c, 0) + 1
    for cls in sorted(by_class):
        print(f"  {cls}: {by_class[cls]}")

    if state is False:
        print(
            f"\nRATCHET-REGRESSION: findings above the recorded baseline.\n"
            f"  observed: {observed}\n"
            f"  budget:   {budget}\n"
            f"  Overshoot is {observed - budget}. The gate is a SHRINKING-ONLY\n"
            f"  ratchet; new dead code is a regression that must be fixed (the\n"
            f"  finding removed) or added to the budget file in the SAME commit\n"
            f"  that introduced it. A frozen baseline that reports green over a\n"
            f"  growing pile is the fake-green class this gate exists to prevent.",
            file=sys.stderr,
        )
        return 1

    if state is None:
        print(
            f"\nBUDGET-OUT-OF-DATE: findings below the recorded baseline.\n"
            f"  observed: {observed}\n"
            f"  budget:   {budget}\n"
            f"  Update tools/deadcode-tools-budget.json to {observed} in the\n"
            f"  same commit that lowered it. The budget that does not shrink with\n"
            f"  the actual count is a ceiling, not a ratchet.",
            file=sys.stderr,
        )
        return 1

    print("deadcode-tools: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
