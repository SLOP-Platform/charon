#!/usr/bin/env python3
# @covers: ci-infra
"""CI workflow policy gate (fragility sweep finding #8).

GROUND: stdlib-only, no-YAML-dependency line/indent scanner over
`.github/workflows/*.yml` — same house style as tools/check_boundary.py.
Enforces three policies that previously existed only as prose comments a
human had to remember to re-apply:

1. Action-ref pin policy (OpenSSF-hardened): EVERY `uses:` line — first-party
   `actions/*` included — must be pinned to a full 40-char commit SHA (a
   trailing `# vN` comment is fine and encouraged for human readability). A
   bare version tag (`@v4`, `@v5.4.0`, ...) is a supply-chain-integrity
   violation: tags are mutable refs an attacker (or a compromised upstream
   maintainer account) can repoint after the fact, whereas a commit SHA is
   immutable. This is the industry-hardened default (OpenSSF Scorecard
   "Pinned-Dependencies" check) and the policy this gate exists to enforce
   — reverting any `uses:` line from a SHA back to a bare tag must fail this
   gate.
2. Fragile Windows smoke pattern: `Start-Process` (case-insensitive) inside
   a `run:` block is the known async-launch-then-poll pattern that rotted
   `windows-exe.yml` (HANDOFF-2026-07-04-v2 finding #2) — flagged wherever
   it appears.
3. Packaging-trigger path scoping: any workflow that builds/packages the
   product (heuristically: `release.yml`, `windows-exe.yml`, or a job name
   containing `image-smoke`/`modeA-isolation`/`package`/`build`) must scope
   its `push:`/`pull_request:` triggers with a `paths:` filter, so a
   docs-only change never triggers a full package build. `ci.yml` (the fast
   pytest/lint gate) is exempt by design. A `push:` block whose ONLY ref
   selector is `tags:` (no `branches:`) is also exempt from the paths:
   requirement: a version-tag push is already a deliberate, human-initiated
   release action (not the incidental commit the filter exists to screen
   out), and bolting a `paths:` filter onto a tag ref risks the release
   silently failing to fire on a GitHub tag-diff edge case.

4. RELEASE-GATE-PARITY: the gate executed by `release.yml` MUST be the same
   as the gate executed by `ci.yml` — same command, same pip install extras,
   same checkout depth. Divergence between these two is precisely the class
   that silently shipped a wrong-version deploy TWICE (v0.6.0 on 2026-07-23,
   v0.6.3 on 2026-08-08): PRs passing ci.yml's 23-checks gate while
   release.yml ran only 4 of those checks plus a narrower mypy. The fix is
   structural: both must invoke `python3 -m charon.cli gate` (or equivalent
   unified gate runner) with the same install extras, so the check list and
   scope come from one SSOT (gate_runner.CHECKS) rather than two diverging
   ad-hoc copies.

Exit non-zero if any violation is found across all workflow files, 0 if
clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo root on sys.path so the gate contract resolves both when this file is run
# standalone (python3 tools/check_*.py, sys.path[0]=tools/) and when the test
# suite imports it as tools.check_* (sys.path[0]=repo root).
_GC_ROOT = Path(__file__).resolve().parent.parent
if str(_GC_ROOT) not in sys.path:
    sys.path.insert(0, str(_GC_ROOT))
from tools.gate_contract import emit_work_units  # noqa: E402

_ACTION_RE = re.compile(r"""uses:\s*([^\s@'"]+)@([^\s'"]+)""")
_RUN_KEY_RE = re.compile(r"^(\s*)run:\s*(.*)$")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
_PACKAGING_JOB_HINTS = ("image-smoke", "modea-isolation", "package", "build")
_PACKAGING_FILENAMES = ("release.yml", "windows-exe.yml")
_EXEMPT_FILENAMES = ("ci.yml",)
# The install line pattern — matches `pip install -e '.[extras]'`
_INSTALL_RE = re.compile(
    r"pip\s+install\s+(?:--quiet\s+)?(?:--break-system-packages\s+)?"
    r"-e\s+'?\.(\[[^\]]*\])'?"
)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _make_block(yml: str) -> dict:
    """Simplified structure key -> content of the YAML for gate-parity scanning.

    Returns a dict of top-level keys to their raw text content (lines joined),
    and sub-keys under `jobs` similarly.
    """
    lines = yml.splitlines()
    n = len(lines)
    result: dict[str, str] = {}
    # Find top-level keys
    i = 0
    while i < n:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if _indent(lines[i]) == 0 and ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            j = i + 1
            while j < n:
                sj = lines[j].strip()
                if sj and not sj.startswith("#") and _indent(lines[j]) <= 0:
                    break
                j += 1
            result[key] = "\n".join(lines[i:j])
            i = j
            continue
        i += 1
    return result


def _pip_extras(text: str) -> list[list[str]]:
    """Extract all pip install extras lists from *text*, normalised.

    Returns each as a sorted list so `[dev,service,router,quality]` ==
    `[dev,quality,router,service]`.
    """
    results = []
    for m in _INSTALL_RE.finditer(text):
        extras_str = m.group(1)
        extras = sorted(e.strip() for e in extras_str.strip("[]").split(",") if e.strip())
        results.append(extras)
    return results


def _has_fetch_depth_zero(text: str) -> bool:
    """True when a ``fetch-depth: 0`` appears in a non-comment line."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"fetch-depth:\s*0", stripped):
            return True
    return False


def _has_gate_command(text: str) -> bool:
    """True when a unified gate invocation (charon.cli gate or tools/run_gate.py)
    appears in a non-comment, non-quoted context."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"python3\s+-m\s+charon\.cli\s+gate|python3\s+tools/run_gate\.py", stripped):
            return True
    return False


def check_release_gate_parity(
    ci_text: str | None, release_text: str | None
) -> list[str]:
    """Fail when ci.yml and release.yml diverge on their gate command, extras, or depth."""
    violations: list[str] = []
    if not ci_text or not release_text:
        return violations

    ci_block = _make_block(ci_text)
    release_block = _make_block(release_text)

    ci_jobs = ci_block.get("jobs", "")
    release_jobs = release_block.get("jobs", "")

    ci_extras = _pip_extras(ci_jobs)
    release_extras = _pip_extras(release_jobs)

    release_depth = _has_fetch_depth_zero(release_jobs)

    ci_has_gate = _has_gate_command(ci_jobs)
    release_has_gate = _has_gate_command(release_jobs)

    if not release_has_gate:
        violations.append(
            "release.yml: .github/workflows/release.yml does not invoke a unified "
            "gate (python3 -m charon.cli gate or python3 tools/run_gate.py). "
            "The release path must run the same checks as CI-merge, from the same "
            "SSOT (gate_runner.CHECKS), so they cannot drift."
        )
    elif not ci_has_gate:
        violations.append(
            "ci.yml: .github/workflows/ci.yml does not invoke a unified gate — "
            "the SSOT gate must exist in CI for release to converge against."
        )

    if not release_depth:
        violations.append(
            "release.yml: .github/workflows/release.yml must use "
            "fetch-depth: 0 in its checkout step. The diff-cover gate "
            "resolves origin/master and fails closed without it."
        )

    ci_extras_set = frozenset(tuple(e) for e in ci_extras) if ci_extras else frozenset()
    release_extras_set = frozenset(tuple(e) for e in release_extras) if release_extras else frozenset()

    if ci_extras_set != release_extras_set and ci_extras and release_extras:
        ci_str = " / ".join(f"[{','.join(e)}]" for e in sorted(ci_extras_set))
        r_str = " / ".join(f"[{','.join(e)}]" for e in sorted(release_extras_set))
        violations.append(
            f"release.yml: pip install extras diverge from ci.yml — "
            f"ci.yml: {ci_str} vs release.yml: {r_str}. "
            "Different extras mean different tools available at gate time; "
            "installing fewer extras on the release path is how the v0.6.3 "
            "release shipped without the litellm money-path tests."
        )

    return violations


def _block_children(
    lines: list[str], start: int, end: int
) -> list[tuple[str, int, int]]:
    """Return (key, child_start, child_end) for immediate mapping-key children
    of the block spanning lines[start:end] (both absolute indices into
    *lines*). child_end is the index of the next sibling key (or *end*)."""
    indents = [
        _indent(lines[i])
        for i in range(start, end)
        if lines[i].strip() and not lines[i].strip().startswith("#")
    ]
    if not indents:
        return []
    base_indent = min(indents)
    children: list[tuple[str, int, int]] = []
    i = start
    while i < end:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if _indent(line) == base_indent:
            m = re.match(r'^\s*["\']?([\w.\-]+)["\']?\s*:', line)
            if m:
                key = m.group(1)
                j = i + 1
                while j < end:
                    lj = lines[j]
                    sj = lj.strip()
                    if sj and not sj.startswith("#") and _indent(lj) <= base_indent:
                        break
                    j += 1
                children.append((key, i, j))
                i = j
                continue
        i += 1
    return children


def check_action_refs(path: Path, lines: list[str]) -> list[str]:
    violations = []
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            continue
        m = _ACTION_RE.search(line)
        if not m:
            continue
        ref, ver = m.group(1), m.group(2).split("#")[0].strip()
        if not _SHA_RE.fullmatch(ver):
            violations.append(
                f"{path}:{i + 1}: action {ref!r} must be pinned to a full 40-char "
                f"commit SHA (OpenSSF hardened pin policy), got {ver!r} — a bare "
                f"version tag is a mutable ref and a supply-chain-integrity "
                f"violation"
            )
    return violations


def check_start_process(path: Path, lines: list[str]) -> list[str]:
    violations = []
    i, n = 0, len(lines)
    while i < n:
        m = _RUN_KEY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        indent, rest = len(m.group(1)), m.group(2).strip()
        if rest == "" or rest.startswith("|") or rest.startswith(">"):
            j = i + 1
            block: list[tuple[int, str]] = []
            while j < n:
                lj = lines[j]
                if lj.strip() == "":
                    block.append((j, lj))
                    j += 1
                    continue
                if _indent(lj) <= indent:
                    break
                block.append((j, lj))
                j += 1
            for ln_idx, bl in block:
                if "start-process" in bl.lower():
                    violations.append(
                        f"{path}:{ln_idx + 1}: fragile Windows smoke pattern "
                        f"(Start-Process) in run: block"
                    )
            i = j
        else:
            if "start-process" in rest.lower():
                violations.append(
                    f"{path}:{i + 1}: fragile Windows smoke pattern "
                    f"(Start-Process) in run: block"
                )
            i += 1
    return violations


def check_paths_filter(path: Path, lines: list[str]) -> list[str]:
    if path.name in _EXEMPT_FILENAMES:
        return []
    root = {k: (s, e) for k, s, e in _block_children(lines, 0, len(lines))}

    is_packaging = path.name in _PACKAGING_FILENAMES
    if not is_packaging and "jobs" in root:
        js, je = root["jobs"]
        job_names = [k for k, _, _ in _block_children(lines, js + 1, je)]
        is_packaging = any(
            hint in jn.lower() for jn in job_names for hint in _PACKAGING_JOB_HINTS
        )
    if not is_packaging or "on" not in root:
        return []

    os_, oe = root["on"]
    on_children = {k: (s, e) for k, s, e in _block_children(lines, os_ + 1, oe)}

    violations = []
    for trigger in ("push", "pull_request"):
        if trigger not in on_children:
            continue
        ts, te = on_children[trigger]
        keys = {k for k, _, _ in _block_children(lines, ts + 1, te)}
        if trigger == "push" and "tags" in keys and "branches" not in keys:
            # Tag-only push trigger (release/version pipelines) — exempt,
            # see policy 3 in the module docstring.
            continue
        if "paths" not in keys:
            violations.append(
                f"{path}:{ts + 1}: packaging workflow missing paths: filter under "
                f"on.{trigger}"
            )
    return violations


def scan_workflow_file(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    violations: list[str] = []
    violations.extend(check_action_refs(path, lines))
    violations.extend(check_start_process(path, lines))
    violations.extend(check_paths_filter(path, lines))
    return violations


def main(root: str = ".github/workflows") -> int:
    base = Path(root)
    files = sorted(set(base.glob("*.yml")) | set(base.glob("*.yaml")))
    emit_work_units(len(files))
    all_violations: list[str] = []
    for f in files:
        all_violations.extend(scan_workflow_file(f))

    ci_path = base / "ci.yml"
    release_path = base / "release.yml"
    ci_text = ci_path.read_text() if ci_path.exists() else None
    release_text = release_path.read_text() if release_path.exists() else None
    all_violations.extend(check_release_gate_parity(ci_text, release_text))

    if all_violations:
        print("CI WORKFLOW POLICY VIOLATION:", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"workflow policy OK: no violations under {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ".github/workflows"))
