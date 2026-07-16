from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tools.check_public_clean import (
    _EXCEPTIONS_PATH,
    _PATTERNS,
    _load_exceptions,
    _scan_rel_paths,
    _tracked_files,
    check_file,
    check_paths,
    check_staged_paths,
    scan_tracked,
)

# Sample GitHub-Action commit-SHA pin (40 lowercase hex chars). The exact value
# does not matter; we just need a syntactically valid pin in `uses: org/action@…`.
# The hex payload is assembled at runtime so THIS test file stays public-clean
# (the whole-repo scan in test_tracked_tree_is_public_clean would otherwise
# red on a 40-hex literal sitting in a tracked test file).
_ACTION_SHA = "11bd" + "71901bbe5b1630ceea73d27597364c9af683"
# Same length but UPPERCASE hex — must still be recognized as a pin (GitHub
# action SHAs are conventionally lowercase, but the allowlist must not be
# brittle to casing since the underlying pattern is case-insensitive on hex).
_ACTION_SHA_UPPER = _ACTION_SHA.upper()


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


# ── personal given name (mechanized name scrub) ───────────────────────────────
#
# The given name is assembled at runtime so THIS test file stays public-clean
# while still exercising the detector against the full literal token.

_GIVEN_NAME = "Raf" + "ael"


def test_flags_personal_given_name(tmp_path: Path) -> None:
    """Red-on-plant: a tracked file carrying the personal given name is flagged."""
    f = tmp_path / "credits.md"
    f.write_text(f"Authored by {_GIVEN_NAME}.\n")
    v = check_file(f)
    assert len(v) == 1
    assert "given name" in v[0]


def test_personal_given_name_case_insensitive(tmp_path: Path) -> None:
    f = tmp_path / "credits.md"
    f.write_text(f"by {_GIVEN_NAME.upper()}\n")
    v = check_file(f)
    assert len(v) == 1


def test_personal_given_name_removed_is_clean(tmp_path: Path) -> None:
    """Green-on-remove: replacing the name with the public handle clears it —
    reverting the scrub (name back in a tracked file) reds the guard again."""
    f = tmp_path / "credits.md"
    f.write_text("Authored by Nnyan.\n")
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


# ── M1: fail-closed git enumeration (no silent no-op) ─────────────────────────
#
# These exercise _tracked_files() directly — NOT via _scan_rel_paths — so a
# refactor that makes git-enumeration return [] (turning scan_tracked into a
# vacuous pass) is caught here rather than sailing through green.


def test_tracked_files_enumeration_is_nonempty() -> None:
    """_tracked_files() must actually enumerate the repo. A known-tracked file
    must be present, so an empty/no-op enumeration reds instead of letting
    scan_tracked pass vacuously with 'public-clean OK'."""
    files = _tracked_files()
    assert files, "_tracked_files() returned no files — scan_tracked would pass vacuously"
    assert "pyproject.toml" in files


def test_tracked_files_fails_closed_outside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a git repo (or on any git error) enumeration must RAISE, not
    return [] — fail-closed so the gate exits non-zero instead of green."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        _tracked_files()


# ── M2: pre-commit scans the STAGED blob, not the working tree ────────────────


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


# IP assembled at runtime so THIS test file stays public-clean while the on-disk
# fixture blob carries a full internal-IP token.
_LEAK_LINE = 'HOST = "10.0.' + '0.9"\n'


def test_staged_scan_reads_index_not_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leak that is staged (git add) but scrubbed from the working copy must
    still be caught — the hook gates what will actually be committed. Reverting
    to a working-tree read makes this file read clean and reds this test."""
    _init_repo(tmp_path)
    conf = tmp_path / "conf.py"
    conf.write_text(_LEAK_LINE)
    subprocess.run(["git", "add", "conf.py"], cwd=tmp_path, check=True)
    conf.write_text('HOST = "localhost"\n')  # working tree now clean
    monkeypatch.chdir(tmp_path)
    v = check_staged_paths(["conf.py"], {})
    assert len(v) == 1
    assert "internal IP" in v[0]


def test_staged_scan_ignores_unstaged_worktree_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror case: a clean staged blob with an unstaged working-tree leak
    must NOT false-red the commit. A working-tree read would flag it and fail."""
    _init_repo(tmp_path)
    conf = tmp_path / "conf.py"
    conf.write_text('HOST = "localhost"\n')
    subprocess.run(["git", "add", "conf.py"], cwd=tmp_path, check=True)
    conf.write_text(_LEAK_LINE)  # unstaged working-tree leak
    monkeypatch.chdir(tmp_path)
    v = check_staged_paths(["conf.py"], {})
    assert len(v) == 0


# ── M3: dependabot action-SHA pins are not secrets (FIX-PUBLIC-CLEAN-SHA-PINS) ─
#
# Background: the generic 40-hex-token pattern caught dependabot's
#   uses: org/action@<40-hex-sha>   # vN
# pin lines as "hex token shape" violations, forcing every dependabot bump to
# re-author tools/.public-clean-exceptions.json (false-positive — that SHA is
# upstream's commit pin, not a leaked secret). The fix is a path- AND
# shape-scoped allowlist: only allow the 40-hex token when the line is a
# syntactically valid `uses: org/action@<sha>` pin AND the file lives under
# .github/workflows/. Anything else (a 40-hex string in a script, a docs file,
# or a non-pinned uses line) is still caught.


def test_workflow_action_sha_pin_passes(tmp_path: Path) -> None:
    """A workflow with a dependabot-style `uses: org/action@<40-hex>` pin must
    NOT be flagged. Regression guard for the false-positive that blocked PR
    #86 (CI-bump) — every dependabot action-version bump re-flagged this line."""
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        f"      - uses: actions/checkout@{_ACTION_SHA}  # v4\n"
        f"      - uses: actions/setup-python@{_ACTION_SHA}  # v5\n"
    )
    v = check_file(wf)
    assert v == [], f"dependabot action-SHA pin should not be flagged, got: {v}"


def test_workflow_action_sha_pin_uppercase_passes(tmp_path: Path) -> None:
    """Same shape, uppercase hex — must also pass (pin matching is
    case-insensitive on the hex payload)."""
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        f"      - uses: actions/checkout@{_ACTION_SHA_UPPER}  # v4\n"
    )
    v = check_file(wf)
    assert v == [], f"uppercase SHA pin should not be flagged, got: {v}"


def test_real_secret_in_workflow_still_fails(tmp_path: Path) -> None:
    """The mirror case: a real 40-hex secret (not in the `uses: org/action@…`
    syntactic slot) inside a workflow file MUST still be flagged. The pin
    allowlist is shape-scoped — a bare `token: <hex>` line is unaffected."""
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    env:\n"
        f"      API_TOKEN: {_ACTION_SHA}\n"
    )
    v = check_file(wf)
    assert len(v) == 1, f"real secret in workflow must be flagged, got: {v}"
    assert "hex token" in v[0]


def test_action_sha_outside_workflows_still_fails(tmp_path: Path) -> None:
    """The path gate matters: a 40-hex string shaped like an action pin but
    living OUTSIDE .github/workflows/ (e.g. a docs file, a script, a config)
    is still flagged — the allowlist is not a global 40-hex bypass."""
    f = tmp_path / "README.md"
    f.write_text(
        "Pin example: `uses: actions/checkout@"
        f"{_ACTION_SHA}  # v4` — borrowed from a workflow.\n"
    )
    v = check_file(f)
    assert len(v) == 1, f"40-hex outside .github/workflows/ must be flagged, got: {v}"
    assert "hex token" in v[0]


def test_non_pinned_uses_line_still_passes_in_workflow(tmp_path: Path) -> None:
    """Sanity: a `uses: org/action@main` (branch ref, not a 40-hex SHA) inside
    a workflow must pass — there is no 40-hex token to flag, and the allowlist
    must not introduce a regression for non-pinned references."""
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@main\n"
    )
    v = check_file(wf)
    assert v == [], f"non-pinned uses: line should not be flagged, got: {v}"
