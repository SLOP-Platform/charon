#!/usr/bin/env python3
# @covers: key-egress
"""Key-egress choke-point gate — runs the Semgrep rules in semgrep-key-egress.yml.

Replaces `check_security.py` check (e), a hand-rolled AST linter that a round-5
adversarial reviewer defeated with an EXECUTED exfil sender (see the rule file's
header and docs/adr/0019 for the full history).

STOPGAP: see docs/adr/0019. If the LiteLLM adopt (ADR-0017) lands, the guarded
code should be DELETED rather than ported, and these rules retargeted.

Exit 0 on clean, 1 on violation, 2 if the scan could not be performed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = REPO_ROOT / "tools" / "semgrep-key-egress.yml"

# Scanned from the repo root because the rule file's `paths.include` globs
# (`src/**`, `tools/**`, `tests/**`) are matched relative to the SCAN ROOT. If
# this ever scans a subdirectory instead, every include stops matching and the
# gate reports a silent, cheerful zero — which is precisely the H3 failure it
# exists to fix. `test_key_egress_gate.py` pins this by asserting the rule goes
# RED on a known-bad corpus, so a scope regression cannot pass as "clean".
SCAN_TARGETS = ["src", "tools", "tests"]


def _fail(msg: str) -> int:
    print(f"key-egress gate ERROR: {msg}", file=sys.stderr)
    return 2


def main() -> int:
    if shutil.which("semgrep") is None:
        # Deliberately NOT a skip. A gate that silently passes when its enforcer
        # is absent produces a green CI that never ran the check — the exact
        # failure mode this gate was rebuilt to eliminate. semgrep ships in the
        # `dev` extra; `pip install -e '.[dev,service]'` installs it.
        return _fail(
            "semgrep is not installed, so the key-egress choke point was NOT verified. "
            "Install it with: pip install -e '.[dev]'")

    if not RULES.is_file():
        return _fail(f"rule file missing: {RULES}")

    proc = subprocess.run(
        ["semgrep", "--config", str(RULES), "--json", "--quiet", "--metrics=off",
         "--error", *SCAN_TARGETS],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return _fail(
            f"semgrep produced no parseable report (exit {proc.returncode}): "
            f"{proc.stderr.strip()[:500]}")

    scan_errors = report.get("errors") or []
    if scan_errors:
        # A parse failure means some file was never actually examined. Reporting
        # that as "clean" is the false receipt this gate must never emit.
        for err in scan_errors:
            print(f"  scan error: {err.get('message', err)}", file=sys.stderr)
        return _fail(f"{len(scan_errors)} file(s) could not be scanned")

    findings = report.get("results") or []
    if findings:
        print("key-egress VIOLATION:", file=sys.stderr)
        for f in findings:
            rule = str(f.get("check_id", "")).split(".")[-1]
            line = f.get("start", {}).get("line", "?")
            msg = " ".join(str(f.get("extra", {}).get("message", "")).split())
            print(f"  {f.get('path')}:{line}: [{rule}] {msg}", file=sys.stderr)
        return 1

    print(f"key-egress OK: choke point intact across {'/'.join(SCAN_TARGETS)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
