"""RED-proof for the key-egress choke-point gate (tools/check_key_egress.py).

Round 5 shipped a hand-rolled AST linter whose stated thesis was that the unsafe
request had become "unrepresentable". An adversarial reviewer then EXECUTED a
complete key-bearing, redirect-following exfil sender that the linter passed with
exit 0. The linter had NO test of its own, which is how a gate that caught
exactly two spellings could be described as structural for a whole round.

So this suite asserts the gate goes RED on every documented evasion, not merely
that it goes GREEN on the current tree. A gate that only proves "clean tree is
clean" cannot distinguish a working rule from a rule that matches nothing — which
is the failure this file exists to make impossible.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = REPO_ROOT / "tools" / "semgrep-key-egress.yml"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "key_egress"
GATE = REPO_ROOT / "tools" / "check_key_egress.py"

# Each evasion from the round-5 review's EVADES table, plus the transports and
# the path-suffix hole. Keyed by fixture filename so a failure names the shape.
EVASION_FIXTURES = [
    "bare_name_urlopen.py",
    "aliased_urlopen.py",
    "aliased_build_opener.py",
    "opener_directory.py",
    "header_name_obfuscated.py",
    "other_transports.py",
    "literal_shapes.py",
]

requires_semgrep = pytest.mark.skipif(
    shutil.which("semgrep") is None,
    reason="semgrep not installed; tools/check_key_egress.py fails loudly (exit 2) in that case, "
           "which is asserted separately by test_gate_refuses_to_pass_without_semgrep",
)


def _stage(tmp_path: Path) -> Path:
    """Copy the fixture corpus into a fake repo whose layout the rule scopes to.

    The rule's `paths.include` globs are matched relative to the SCAN ROOT, so
    the fixtures have to sit under a real `src/charon/` for Rule A to apply.
    """
    src = tmp_path / "src" / "charon"
    src.mkdir(parents=True)
    for name in EVASION_FIXTURES:
        shutil.copy(FIXTURES / "should_flag" / name, src / name)
    shutil.copy(FIXTURES / "should_pass" / "correct_usage.py", src / "correct_usage.py")
    # H2: the predecessor exempted any path ENDING in `charon/netutil.py`, so a
    # file at src/charon/adapters/charon/netutil.py was a gate-free zone. Staged
    # at that exact path so the assertion is about the real hole, not a lookalike.
    nested = src / "adapters" / "charon"
    nested.mkdir(parents=True)
    shutil.copy(FIXTURES / "should_flag" / "nested_charon_netutil" / "netutil.py",
                nested / "netutil.py")
    return tmp_path


def _scan(root: Path) -> list[dict]:
    proc = subprocess.run(
        ["semgrep", "--config", str(RULES), "--json", "--quiet", "--metrics=off", "."],
        cwd=root, capture_output=True, text=True,
    )
    report = json.loads(proc.stdout)
    assert not report.get("errors"), f"semgrep could not scan: {report.get('errors')}"
    return report["results"]


@requires_semgrep
@pytest.mark.parametrize("fixture", EVASION_FIXTURES)
def test_every_documented_evasion_is_flagged(tmp_path: Path, fixture: str) -> None:
    """Each shape that EVADED the round-5 AST linter must now go RED."""
    findings = _scan(_stage(tmp_path))
    hit = [f for f in findings if f["path"].endswith(fixture)]
    assert hit, (
        f"{fixture} produced NO finding — this shape was verified to evade the "
        f"previous gate, so a miss here means the replacement regressed to the "
        f"same class of hole.")


@requires_semgrep
def test_nested_charon_netutil_is_not_exempt(tmp_path: Path) -> None:
    """H2: only the ONE real choke-point path is exempt, not any `*/charon/netutil.py`."""
    findings = _scan(_stage(tmp_path))
    hit = [f for f in findings if "adapters/charon/netutil.py" in f["path"]]
    assert hit, (
        "src/charon/adapters/charon/netutil.py scanned clean — the exemption is "
        "matching a path SUFFIX again, which makes every nested `charon/netutil.py` "
        "a gate-free zone.")


@requires_semgrep
def test_sanctioned_usage_is_not_flagged(tmp_path: Path) -> None:
    """Positive control: the netutil-based shape and a header-redaction map stay GREEN.

    Without this, the rule could be made to pass the evasion tests by flagging
    everything, which is unlandable and would get the gate switched off — the
    round-5 regression review flagged exactly that risk in the old ast.Dict arm.
    """
    findings = _scan(_stage(tmp_path))
    hit = [f for f in findings if f["path"].endswith("correct_usage.py")]
    assert not hit, f"sanctioned netutil usage was flagged: {hit}"


@requires_semgrep
def test_real_tree_is_clean() -> None:
    """The shipped tree passes — the gate is landable as well as strict."""
    proc = subprocess.run(["python3", str(GATE)], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"key-egress gate failed on the real tree:\n{proc.stderr}"


@requires_semgrep
def test_gate_scans_tools_and_tests_not_just_src() -> None:
    """H3: the predecessor was invoked with no argument, so it rooted at `src/`
    and had no opinion about `tools/` (shipped, operator-run, key-bearing) or
    `tests/`. Pin the scan targets so that cannot silently narrow again."""
    source = GATE.read_text()
    assert 'SCAN_TARGETS = ["src", "tools", "tests"]' in source, (
        "the key-egress gate's scan targets changed — narrowing them is how the "
        "previous gate ended up never scanning tools/ or tests/")


def test_gate_refuses_to_pass_without_semgrep(tmp_path: Path) -> None:
    """A missing enforcer must FAIL, never skip.

    'Gates must actually run': a green CI that never invoked the check is the
    known failure mode, so absence of semgrep is exit 2, not exit 0.
    """
    # An empty PATH is what makes semgrep unfindable. The interpreter is invoked
    # by absolute path so that emptying PATH does not also hide python itself.
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    env = {"PATH": str(stub_bin), "HOME": str(tmp_path)}
    proc = subprocess.run([sys.executable, str(GATE)], cwd=REPO_ROOT,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 2, (
        f"gate returned {proc.returncode} with semgrep absent; it must fail loudly "
        f"rather than report a clean scan it never performed.\n{proc.stdout}{proc.stderr}")
    assert "not installed" in proc.stderr
