"""test_citation_audit.py — verifies the AUDIT.md the model wrote is
factually correct: every cited symbol resolves to a real lib.py
definition, every definition is quoted exactly, and the unused symbol
is flagged as such (not cited as used)."""
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(errors="ignore")


def test_audit_cites_used_symbols():
    """Each used symbol must be cited with file:line + the real line."""
    audit = _read(Path("AUDIT.md"))
    for name, lineno, expected_quote in [
        ("fetch_data", 1, "def fetch_data(url: str) -> bytes:"),
        ("parse_payload", 4, "def parse_payload(raw: bytes) -> dict:"),
        ("cache_get", 7, "def cache_get(key: str) -> bytes | None:"),
        ("cache_set", 10, "def cache_set(key: str, val: bytes, ttl: int = 60) -> None:"),
    ]:
        assert f"lib.py:{lineno}" in audit, (
            f"AUDIT.md must cite {name} at lib.py:{lineno}"
        )
        assert expected_quote in audit, (
            f"AUDIT.md must quote the definition of {name} verbatim"
        )


def test_audit_flags_unused_symbol():
    """The unused legacy_v1_api_handler must be flagged as UNUSED
    (not cited as a used reference)."""
    audit = _read(Path("AUDIT.md"))
    assert "legacy_v1_api_handler" in audit, (
        "AUDIT.md must mention the unused symbol legacy_v1_api_handler"
    )
    # Locate the line. It must be tagged as UNUSED, not as a used citation.
    for line in audit.splitlines():
        if "legacy_v1_api_handler" in line:
            assert "UNUSED" in line or "unused" in line, (
                f"legacy_v1_api_handler must be flagged UNUSED, got: {line!r}"
            )


def test_no_invented_citations():
    """No file:line reference to a non-existent lib.py line."""
    audit = _read(Path("AUDIT.md"))
    lib_text = _read(Path("lib.py"))
    import re
    for m in re.finditer(r"lib\.py:(\d+)", audit):
        ln = int(m.group(1))
        lib_lines = lib_text.splitlines()
        assert 1 <= ln <= len(lib_lines), (
            f"AUDIT.md cites lib.py:{ln} which does not exist "
            f"(lib.py has only {len(lib_lines)} lines)"
        )
