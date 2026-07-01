from __future__ import annotations

from pathlib import Path

from tools.check_public_clean import check_file, check_paths


def test_flags_internal_ip(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text('host = "10.0.0.1"\n')
    v = check_file(f)
    assert len(v) == 1
    assert "internal IP" in v[0]


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


def test_exception_config_suppresses_violation(tmp_path: Path) -> None:
    f = tmp_path / "exempt.json"
    rel = str(f)
    f.write_text('{"rig": "charon-private"}\n')
    v = check_file(f, {rel: {1}})
    assert len(v) == 0


def test_exception_config_only_suppresses_specific_lines(tmp_path: Path) -> None:
    f = tmp_path / "partial.json"
    rel = str(f)
    f.write_text('"ok": true\n"bad": "10.0.0.1"\n')
    v = check_file(f, {rel: {1}})
    assert len(v) == 1


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
