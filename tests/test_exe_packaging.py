"""Guards for the Windows ``charon.exe`` (PyInstaller) build, so its regressions
are caught in normal Linux CI instead of silently on release.

The historical windows-exe breakage was 4 stacked bugs; two were CODE invariants
that these tests lock in without needing a Windows runner:

  * cp1252 consoles (the Windows default) crash on non-ASCII CLI output (e.g. the
    ``->`` glyph U+2192 in help). ``cli.main`` reconfigures stdout/stderr to UTF-8
    so output is never fatal.
  * freezing the bare ``cli.py`` module as ``__main__`` broke its relative imports;
    the exe is frozen from ``packaging/charon_entry.py`` which imports ABSOLUTELY.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from charon import cli


def test_help_does_not_crash_on_cp1252_console(monkeypatch):
    """`charon --help` must not raise UnicodeEncodeError when stdout is a strict
    cp1252 stream (a default Windows console). ``main`` reconfigures stdout to
    UTF-8, so the non-ASCII help glyphs are written safely and argparse exits 0.
    Remove that reconfigure and this test fails with UnicodeEncodeError."""
    fake_out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict",
                                write_through=True)
    fake_err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict",
                                write_through=True)
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    with pytest.raises(SystemExit) as exc:  # argparse --help raises SystemExit(0)
        cli.main(["--help"])
    assert exc.value.code == 0  # a UnicodeEncodeError here = the regression is back


def test_frozen_entry_uses_absolute_import():
    """The PyInstaller entry (``packaging/charon_entry.py``) must import
    ``charon.cli`` ABSOLUTELY — freezing the bare module as ``__main__`` crashed
    the exe at startup with 'attempted relative import with no known parent
    package'. The ``.spec`` must point at this wrapper, not ``src/charon/cli.py``."""
    root = Path(__file__).resolve().parents[1]
    entry = root / "packaging" / "charon_entry.py"
    assert entry.exists(), "packaging/charon_entry.py (the exe entry point) is missing"
    assert "from charon.cli import main" in entry.read_text(encoding="utf-8"), (
        "the frozen exe entry must use an ABSOLUTE import of charon.cli")
    spec = (root / "packaging" / "charon.spec").read_text(encoding="utf-8")
    assert "charon_entry.py" in spec, (
        "charon.spec must freeze the charon_entry.py wrapper, not the bare cli.py")
