from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from charon.acceptance import AcceptanceCheck, derive_remaining, derive_verified


def test_executable_check_passes_when_file_exists(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hi")
    c = AcceptanceCheck("a0", "test -f hello.txt")
    assert c.verify(str(tmp_path)) is True


def test_executable_check_fails_when_absent(tmp_path: Path) -> None:
    c = AcceptanceCheck("a0", "test -f missing.txt")
    assert c.verify(str(tmp_path)) is False


def test_remaining_is_machine_derived(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("x")
    checks = [AcceptanceCheck("a0", "test -f a"), AcceptanceCheck("a1", "test -f b")]
    assert derive_verified(checks, str(tmp_path)) == {"a0"}
    assert derive_remaining(checks, str(tmp_path)) == {"a1"}


def test_prose_acceptance_never_falsely_passes(tmp_path: Path) -> None:
    # BR-5: prose passed as a command is executed and cannot exit 0 -> never
    # falsely "done". It also warns.
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c = AcceptanceCheck("a0", "add comprehensive error handling to the function")
        assert any("prose" in str(x.message) for x in w)
    assert c.verify(str(tmp_path)) is False


def test_empty_command_rejected() -> None:
    with pytest.raises(ValueError):
        AcceptanceCheck("a0", "   ")
