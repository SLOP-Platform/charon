from __future__ import annotations

from pathlib import Path

from tools.check_public_clean import (
    _EXCEPTIONS_PATH,
    _PATTERNS,
    _load_exceptions,
    _scan_rel_paths,
    check_file,
    check_paths,
    scan_tracked,
)


def test_flags_internal_ip(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text('host = "10.0.0.1"\n')
    v = check_file(f)
    assert len(v) == 1
    assert "internal IP" in v[0]


def test_coordinator_subnet_pattern_named_and_matches(tmp_path: Path) -> None:
    """10.0.1.x is already caught by the generic 10.0.0.0/8 pattern (which wins
    the first-match break in check_file — verified below), so the dedicated
    'coordinator LAN subnet' pattern is tested directly against _PATTERNS
    rather than via check_file's reported description string."""
    named = [desc for _, desc in _PATTERNS if "coordinator LAN subnet" in desc]
    assert named, "expected a named coordinator-subnet pattern in _PATTERNS"
    pat = next(p for p, desc in _PATTERNS if desc == named[0])
    assert pat.search("10.0.1.42")
    # confirm it is genuinely flagged end-to-end (via whichever pattern wins)
    f = tmp_path / "coord.py"
    f.write_text('host = "10.0.1.42"\n')
    v = check_file(f)
    assert len(v) == 1


def test_flags_internal_ip_192_range(tmp_path: Path) -> None:
    f = tmp_path / "bad192.py"
    f.write_text('host = "192.168.1.5"\n')
    v = check_file(f)
    assert len(v) == 1
    assert "192.168.0.0/16" in v[0]


def test_flags_internal_ip_172_range(tmp_path: Path) -> None:
    f = tmp_path / "bad172.py"
    f.write_text('host = "172.20.3.4"\n')
    v = check_file(f)
    assert len(v) == 1
    assert "172.16.0.0/12" in v[0]


def test_flags_hostname_4_lom(tmp_path: Path) -> None:
    f = tmp_path / "readme.md"
    f.write_text("CI runs on 4-lom.\n")
    v = check_file(f)
    assert len(v) == 1
    assert "4-lom" in v[0]


def test_flags_hostname_4_LOM_case_insensitive(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("Runs on 4-LOM.\n")
    v = check_file(f)
    assert len(v) == 1


def test_flags_hostname_charon_vm(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("Tested on charon-vm.\n")
    v = check_file(f)
    assert len(v) == 1
    assert "charon-vm" in v[0]


def test_flags_home_path(tmp_path: Path) -> None:
    f = tmp_path / "script.sh"
    f.write_text("cd /home/stack/repo\n")
    v = check_file(f)
    assert len(v) == 1
    assert "home path" in v[0]


def test_flags_rig_name(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("See charon-private/fleet/\n")
    v = check_file(f)
    assert len(v) == 1
    assert "charon-private" in v[0]


def test_flags_hex_40_or_more(tmp_path: Path) -> None:
    f = tmp_path / "config.yml"
    f.write_text("token: ab12cd34ef567890ab12cd34ef567890ab12cd34\n")
    v = check_file(f)
    assert len(v) == 1
    assert "hex token" in v[0]


def test_hex_shorter_than_40_is_ok(tmp_path: Path) -> None:
    f = tmp_path / "ok.yml"
    f.write_text("short: ab12cd34ef567890ab12cd34ef5678\n")
    v = check_file(f)
    assert len(v) == 0


# ── waiver ────────────────────────────────────────────────────────────────────


def test_inline_waiver_suppresses_violation(tmp_path: Path) -> None:
    f = tmp_path / "waived.py"
    f.write_text("# 4-lom is our runner  # public-clean: allow — CI runner name\n")
    v = check_file(f)
    assert len(v) == 0


def test_inline_waiver_markdown(tmp_path: Path) -> None:
    f = tmp_path / "waived.md"
    f.write_text("We use 4-lom <!-- public-clean: allow — CI runner ref -->\n")
    v = check_file(f)
    assert len(v) == 0


def test_waiver_only_works_on_same_line(tmp_path: Path) -> None:
    f = tmp_path / "partial.md"
    f.write_text(
        "# public-clean: allow — next line is intentional\n"
        'host = "10.0.0.1"\n'
    )
    v = check_file(f)
    assert len(v) == 1


def test_waiver_keyword_allow_is_required(tmp_path: Path) -> None:
    f = tmp_path / "not_waived.py"
    f.write_text('x = "10.0.0.5"  # public-clean: skip this\n')
    v = check_file(f)
    assert len(v) == 1


# ── exception config ──────────────────────────────────────────────────────────
#
# Exemptions are keyed by exact line CONTENT, not line number. A future
# insertion/deletion elsewhere in the file shifts line numbers but not line
# content, so the waiver keeps tracking the line it was written for instead
# of silently sliding onto a neighboring line (which could un-mask a real
# leak or mask a new one). If the exempted content itself changes, the
# exemption simply stops matching and the check re-evaluates that line
# normally — fail-safe, not fail-silent.


def test_exception_config_suppresses_violation(tmp_path: Path) -> None:
    f = tmp_path / "exempt.json"
    rel = str(f)
    f.write_text('{"rig": "charon-private"}\n')
    v = check_file(f, {rel: {'{"rig": "charon-private"}'}})  # public-clean: allow — test fixture
    assert len(v) == 0


def test_exception_config_only_suppresses_specific_lines(tmp_path: Path) -> None:
    f = tmp_path / "partial.json"
    rel = str(f)
    f.write_text('"ok": true\n"bad": "10.0.0.1"\n')
    v = check_file(f, {rel: {'"ok": true'}})
    assert len(v) == 1


def test_exception_content_no_longer_present_stops_suppressing(tmp_path: Path) -> None:
    """If the file's line content drifts away from what the exemption
    recorded (e.g. someone edits the surrounding comment), the exemption
    must NOT keep suppressing whatever now occupies that line — content
    drift re-exposes the line to normal checking instead of silently
    carrying the old waiver forward."""
    f = tmp_path / "drifted.json"
    rel = str(f)
    f.write_text('{"rig": "charon-private"}\n')
    # exemption was written for different content than what's now on the line
    v = check_file(f, {rel: {'{"rig": "some-other-value"}'}})
    assert len(v) == 1


def test_shipped_exceptions_match_tracked_file_content() -> None:
    """Shape-assertion / drift guard: every entry in
    tools/.public-clean-exceptions.json must be an exact line still present
    verbatim in its target file. If a file was edited and the exempted line
    moved, was reworded, or was deleted, this fails loudly and names the
    offending file — instead of the exemption quietly doing nothing (content
    match: line no longer exempt) or, worse, quietly matching an unrelated
    new line that happens to have identical text elsewhere in a *different*
    exceptions entry never being noticed as stale."""
    exceptions = _load_exceptions()
    assert exceptions, "expected the shipped exceptions file to be non-empty"
    problems: list[str] = []
    for fp, contents in exceptions.items():
        p = Path(fp)
        if not p.exists():
            problems.append(f"{fp}: file referenced in {_EXCEPTIONS_PATH} no longer exists")
            continue
        file_lines = set(p.read_text().split("\n"))
        for c in contents:
            if c not in file_lines:
                problems.append(f"{fp}: exempted line no longer found verbatim: {c[:80]!r}")
    msg = "stale public-clean exceptions (re-author or remove):\n" + "\n".join(problems)
    assert not problems, msg


# ── binary / unreadable ───────────────────────────────────────────────────────


def test_binary_file_is_skipped(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x80\x81\x82")
    v = check_file(f)
    assert len(v) == 0


# ── one-violation-per-line ────────────────────────────────────────────────────


def test_only_first_match_per_line_reported(tmp_path: Path) -> None:
    f = tmp_path / "multi.py"
    f.write_text('x = "/home/stack/charon-private/docs"\n')
    v = check_file(f)
    assert len(v) == 1


# ── clean ─────────────────────────────────────────────────────────────────────


def test_clean_file_has_no_violations(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text("import os\nfrom pathlib import Path\nx = 1\n")
    v = check_file(f)
    assert len(v) == 0


# ── check_paths ───────────────────────────────────────────────────────────────


def test_check_paths_aggregates(tmp_path: Path) -> None:
    f1 = tmp_path / "a.py"
    f1.write_text('x = "10.0.0.1"\n')
    f2 = tmp_path / "b.md"
    f2.write_text("CI is on 4-lom\n")
    v = check_paths([f1, f2])
    assert len(v) == 2


# ── red-proof / green-proof ───────────────────────────────────────────────────


def test_red_proof_planted_leak(tmp_path: Path) -> None:
    """Rule 3: a file containing personal info must be flagged."""
    f = tmp_path / "leak.py"
    f.write_text("# CI runner is 4-lom\n")
    v = check_file(f)
    assert len(v) == 1
    assert "4-lom" in v[0]


def test_green_proof_clean_file(tmp_path: Path) -> None:
    """Rule 3: a clean file must not be flagged."""
    f = tmp_path / "clean.py"
    f.write_text("import os\nprint('hello')\n")
    v = check_file(f)
    assert len(v) == 0


# ── whole-repo scan (real tracked tree) ───────────────────────────────────────
#
# The unit tests above exercise the detector on synthetic fixtures. These two
# close the "tests never scan the real repo" gap: they run the SAME scan the
# CI gate runs (scan_tracked) against this checkout's git-tracked files, so a
# personal/internal token that lands in a real tracked file fails `pytest`
# (hence CI) — not just the standalone `charon gate` step.


def test_tracked_tree_is_public_clean() -> None:
    """The whole git-tracked tree must contain no unallowlisted personal or
    internal info. If a leak is committed, this fails and NAMES the offending
    file:line — this is the regression guard that makes the gate real. Revert
    the wiring (delete this test) and a leaked token would sail through pytest.
    """
    violations = scan_tracked()
    assert not violations, (
        "personal/internal info found in tracked files "
        "(add an allowlist entry only after review):\n  " + "\n  ".join(violations)
    )


def test_repo_scan_catches_a_planted_leak(tmp_path: Path) -> None:
    """Proof the whole-repo scan actually catches a leak: feed the same scan
    path a file carrying a personal token and confirm it is flagged. Guards
    against a future refactor that silently turns scan_tracked into a no-op
    (which would make test_tracked_tree_is_public_clean pass vacuously).
    """
    leak = tmp_path / "leak.py"
    # Assemble the token at runtime so THIS test file stays public-clean while
    # the fixture file on disk carries the full internal home-path token.
    leak.write_text("HOME = '/home/" + "stack/secret'\n")
    v = _scan_rel_paths([str(leak)], _load_exceptions())
    assert len(v) == 1
    assert "home path" in v[0]
