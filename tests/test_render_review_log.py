from __future__ import annotations

from pathlib import Path

from tools.render_review_log import (
    HEADER,
    check,
    fragment_paths,
    render,
)


def _frag(d: Path, name: str, body: str) -> Path:
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def test_fragments_render_in_stable_lexical_order(tmp_path: Path) -> None:
    # Written out of order; the rollup must order them lexically by filename.
    _frag(tmp_path, "gamma.md", "## gamma\n\nthird")
    _frag(tmp_path, "alpha.md", "## alpha\n\nfirst")
    _frag(tmp_path, "beta.md", "## beta\n\nsecond")

    out = render(tmp_path)
    assert out.index("## alpha") < out.index("## beta") < out.index("## gamma")
    # Deterministic: rendering twice yields byte-identical output.
    assert render(tmp_path) == out


def test_readme_is_excluded_from_the_rollup(tmp_path: Path) -> None:
    _frag(tmp_path, "README.md", "# Review-log fragments\n\nconvention docs")
    _frag(tmp_path, "E1.md", "## E1\n\na real entry")

    paths = fragment_paths(tmp_path)
    assert [p.name for p in paths] == ["E1.md"]
    out = render(tmp_path)
    assert "convention docs" not in out
    assert "a real entry" in out


def test_generated_header_is_present(tmp_path: Path) -> None:
    _frag(tmp_path, "E1.md", "## E1\n\nbody")
    out = render(tmp_path)
    assert out.startswith(HEADER)
    assert "DO NOT EDIT" in out
    assert "tools/render_review_log.py" in out


def test_sections_joined_by_horizontal_rule(tmp_path: Path) -> None:
    _frag(tmp_path, "a.md", "## a\n\nalpha")
    _frag(tmp_path, "b.md", "## b\n\nbeta")
    out = render(tmp_path)
    assert "\n\n---\n\n" in out
    # exactly one separator for two fragments
    assert out.count("\n\n---\n\n") == 1


def test_fragment_content_preserved_verbatim(tmp_path: Path) -> None:
    body = "## E2\n\n- **bullet** with em—dash and `code`\n- second line"
    _frag(tmp_path, "E2.md", body)
    out = render(tmp_path)
    assert body in out


def test_check_passes_on_fresh_render_and_fails_on_stale(tmp_path: Path) -> None:
    frags = tmp_path / "frags"
    frags.mkdir()
    _frag(frags, "E1.md", "## E1\n\nbody")
    output = tmp_path / "REVIEW-LOG.md"

    # Stale: output does not exist yet.
    assert check(frags, output) is False

    # Freshly rendered → check passes.
    output.write_text(render(frags), encoding="utf-8")
    assert check(frags, output) is True

    # A new fragment makes the committed rollup stale.
    _frag(frags, "E2.md", "## E2\n\nmore")
    assert check(frags, output) is False

    # Re-render → fresh again.
    output.write_text(render(frags), encoding="utf-8")
    assert check(frags, output) is True


def test_added_fragment_changes_output_deterministically(tmp_path: Path) -> None:
    _frag(tmp_path, "E1.md", "## E1\n\nbody")
    before = render(tmp_path)

    _frag(tmp_path, "E2.md", "## E2\n\nsecond entry")
    after = render(tmp_path)

    assert after != before
    assert "second entry" in after
    assert "second entry" not in before
    # The same fragment set always renders identically.
    assert render(tmp_path) == after


def test_committed_rollup_is_not_stale() -> None:
    """The checked-in docs/REVIEW-LOG.md matches its fragments (guards CI parity)."""
    repo = Path(__file__).resolve().parent.parent
    assert check(repo / "docs" / "review-log", repo / "docs" / "REVIEW-LOG.md") is True


def test_empty_fragment_dir_renders_just_the_header(tmp_path: Path) -> None:
    out = render(tmp_path)
    assert out == HEADER + "\n"
